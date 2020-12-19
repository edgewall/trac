# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2020 Edgewall Software
# Copyright (C) 2005-2007 Christopher Lenz <cmlenz@gmx.de>
# Copyright (C) 2005 Matthew Good <trac@matt-good.net>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.
#
# Author: Christopher Lenz <cmlenz@gmx.de>
#         Matthew Good <trac@matt-good.net>

import cgi
import fnmatch
from functools import partial
import gc
import io
import locale
import os
import pkg_resources
from pprint import pformat, pprint
import re
import sys
import traceback
from urllib.parse import urlparse

from jinja2 import FileSystemLoader

from trac import __version__ as TRAC_VERSION
from trac.config import BoolOption, ChoiceOption, ConfigSection, \
                        ConfigurationError, ExtensionOption, Option, \
                        OrderedExtensionsOption
from trac.core import *
from trac.env import open_environment
from trac.loader import get_plugin_info, match_plugins_to_frames
from trac.perm import PermissionCache, PermissionError
from trac.resource import ResourceNotFound
from trac.util import arity, get_frame_info, get_last_traceback, hex_entropy, \
                      lazy, read_file, safe_repr, translation
from trac.util.concurrency import get_thread_id
from trac.util.datefmt import format_datetime, localtz, timezone, user_time
from trac.util.html import tag, valid_html_bytes
from trac.util.text import (exception_to_unicode, jinja2env, shorten_line,
                            to_unicode, to_utf8, unicode_quote)
from trac.util.translation import _, get_negotiated_locale, has_babel, \
                                  safefmt, tag_
from trac.web.api import HTTPBadRequest, HTTPException, HTTPForbidden, \
                         HTTPInternalServerError, HTTPNotFound, IAuthenticator, \
                         IRequestFilter, IRequestHandler, Request, \
                         RequestDone, TracNotImplementedError, \
                         is_valid_default_handler
from trac.web.chrome import Chrome, ITemplateProvider, add_notice, \
                            add_stylesheet, add_warning
from trac.web.href import Href
from trac.web.session import SessionDict, Session

#: This URL is used for semi-automatic bug reports (see
#: `send_internal_error`). Please modify it to point to your own
#: Trac instance if you distribute a patched version of Trac.
default_tracker = 'https://trac.edgewall.org'


class FakeSession(SessionDict):

    def get_session(self, sid, authenticated=False):
        pass

    def save(self):
        pass


class FakePerm(object):

    username = 'anonymous'

    def __call__(self, realm_or_resource, id=False, version=False):
        return self

    def has_permission(self, action, realm_or_resource=None, id=False,
                       version=False):
        return False

    __contains__ = has_permission

    def require(self, action, realm_or_resource=None, id=False, version=False,
                message=None):
        if message is None:
            raise PermissionError(action)
        else:
            raise PermissionError(msg=message)

    assert_permission = require


class RequestWithSession(Request):
    """A request that saves its associated session when sending the reply."""

    def send_response(self, code=200):
        if code < 400:
            self.session.save()
        super(RequestWithSession, self).send_response(code)


class RequestDispatcher(Component):
    """Web request dispatcher.

    This component dispatches incoming requests to registered handlers.
    It also takes care of user authentication and request pre- and
    post-processing.
    """
    required = True

    implements(ITemplateProvider)

    authenticators = ExtensionPoint(IAuthenticator)
    handlers = ExtensionPoint(IRequestHandler)

    filters = OrderedExtensionsOption('trac', 'request_filters',
                                      IRequestFilter,
        doc="""Ordered list of filters to apply to all requests.""")

    default_handler = ExtensionOption('trac', 'default_handler',
                                      IRequestHandler, 'WikiModule',
        """Name of the component that handles requests to the base
        URL.

        Options include `TimelineModule`, `RoadmapModule`,
        `BrowserModule`, `QueryModule`, `ReportModule`, `TicketModule`
        and `WikiModule`.

        The [/prefs/userinterface session preference] for default handler
        take precedence, when set.
        """)

    default_timezone = Option('trac', 'default_timezone', '',
        """The default timezone to use""")

    default_language = Option('trac', 'default_language', '',
        """The preferred language to use if no user preference has been set.
        """)

    default_date_format = ChoiceOption('trac', 'default_date_format',
                                       ('', 'iso8601'),
        """The date format. Valid options are 'iso8601' for selecting
        ISO 8601 format, or leave it empty which means the default
        date format will be inferred from the browser's default
        language. (''since 1.0'')
        """)

    use_xsendfile = BoolOption('trac', 'use_xsendfile', 'false',
        """When true, send a `X-Sendfile` header and no content when sending
        files from the filesystem, so that the web server handles the content.
        This requires a web server that knows how to handle such a header,
        like Apache with `mod_xsendfile` or lighttpd. (''since 1.0'')
        """)

    xsendfile_header = Option('trac', 'xsendfile_header', 'X-Sendfile',
        """The header to use if `use_xsendfile` is enabled. If Nginx is used,
        set `X-Accel-Redirect`. (''since 1.0.6'')""")

    configurable_headers = ConfigSection('http-headers', """
        Headers to be added to the HTTP request. (''since 1.2.3'')

        The header name must conform to
        [https://tools.ietf.org/html/rfc7230 RFC7230] and the following
        reserved names are not allowed: content-type, content-length,
        location, etag, pragma, cache-control, expires.
        """)

    # Public API

    def authenticate(self, req):
        for authenticator in self.authenticators:
            try:
                authname = authenticator.authenticate(req)
            except TracError as e:
                self.log.error("Can't authenticate using %s: %s",
                               authenticator.__class__.__name__,
                               exception_to_unicode(e, traceback=True))
                add_warning(req, _("Authentication error. "
                                   "Please contact your administrator."))
                break  # don't fallback to other authenticators
            if authname:
                return authname
        return 'anonymous'

    def dispatch(self, req):
        """Find a registered handler that matches the request and let
        it process it.

        In addition, this method initializes the data dictionary
        passed to the the template and adds the web site chrome.
        """
        self.log.debug('Dispatching %r', req)
        chrome = Chrome(self.env)

        try:
            # Select the component that should handle the request
            chosen_handler = None
            for handler in self._request_handlers.values():
                if handler.match_request(req):
                    chosen_handler = handler
                    break
            if not chosen_handler and req.path_info in ('', '/'):
                chosen_handler = self._get_valid_default_handler(req)
            # pre-process any incoming request, whether a handler
            # was found or not
            self.log.debug("Chosen handler is %s", chosen_handler)
            chosen_handler = self._pre_process_request(req, chosen_handler)
            if not chosen_handler:
                if req.path_info.endswith('/'):
                    # Strip trailing / and redirect
                    target = unicode_quote(req.path_info.rstrip('/'))
                    if req.query_string:
                        target += '?' + req.query_string
                    req.redirect(req.href + target, permanent=True)
                raise HTTPNotFound('No handler matched request to %s',
                                   req.path_info)

            req.callbacks['chrome'] = partial(chrome.prepare_request,
                                              handler=chosen_handler)

            # Protect against CSRF attacks: we validate the form token
            # for all POST requests with a content-type corresponding
            # to form submissions
            if req.method == 'POST':
                ctype = req.get_header('Content-Type')
                if ctype:
                    ctype, options = cgi.parse_header(ctype)
                if ctype in ('application/x-www-form-urlencoded',
                             'multipart/form-data') and \
                        req.args.get('__FORM_TOKEN') != req.form_token:
                    if self.env.secure_cookies and req.scheme == 'http':
                        msg = _('Secure cookies are enabled, you must '
                                'use https to submit forms.')
                    else:
                        msg = _('Do you have cookies enabled?')
                    raise HTTPBadRequest(_('Missing or invalid form token.'
                                           ' %(msg)s', msg=msg))

            # Process the request and render the template
            resp = chosen_handler.process_request(req)
            if resp:
                template, data, metadata = \
                    self._post_process_request(req, *resp)
                if 'hdfdump' in req.args:
                    req.perm.require('TRAC_ADMIN')
                    # debugging helper - no need to render first
                    with io.TextIOWrapper(io.BytesIO(), encoding='utf-8',
                                          newline='\n',
                                          write_through=True) as out:
                        pprint({'template': template,
                                'metadata': metadata,
                                'data': data}, out)
                        out = out.buffer.getvalue()
                    req.send(out, 'text/plain')
                self.log.debug("Rendering response with template %s", template)
                metadata.setdefault('iterable', chrome.use_chunked_encoding)
                content_type = metadata.get('content_type')
                output = chrome.render_template(req, template, data, metadata)
                req.send(output, content_type or 'text/html')
            else:
                self.log.debug("Empty or no response from handler. "
                               "Entering post_process_request.")
                self._post_process_request(req)
        except RequestDone:
            raise
        except Exception as e:
            # post-process the request in case of errors
            err = sys.exc_info()
            try:
                self._post_process_request(req)
            except RequestDone:
                raise
            except TracError as e2:
                self.log.warning("Exception caught while post-processing"
                                 " request: %s", exception_to_unicode(e2))
            except Exception as e2:
                if not (type(e) is type(e2) and e.args == e2.args):
                    self.log.error("Exception caught while post-processing"
                                   " request: %s",
                                   exception_to_unicode(e2, traceback=True))
            if isinstance(e, PermissionError):
                raise HTTPForbidden(e) from e
            if isinstance(e, ResourceNotFound):
                raise HTTPNotFound(e) from e
            if isinstance(e, NotImplementedError):
                tb = traceback.extract_tb(err[2])[-1]
                self.log.warning("%s caught from %s:%d in %s: %s",
                                 e.__class__.__name__, tb[0], tb[1], tb[2],
                                 to_unicode(e) or "(no message)")
                raise HTTPInternalServerError(TracNotImplementedError(e)) from e
            if isinstance(e, TracError):
                raise HTTPInternalServerError(e) from e
            raise e

    # ITemplateProvider methods

    def get_htdocs_dirs(self):
        return []

    def get_templates_dirs(self):
        return [pkg_resources.resource_filename('trac.web', 'templates')]

    # Internal methods

    def set_default_callbacks(self, req):
        """Setup request callbacks for lazily-evaluated properties.
        """
        req.callbacks.update({
            'authname': self.authenticate,
            'chrome': Chrome(self.env).prepare_request,
            'form_token': self._get_form_token,
            'lc_time': self._get_lc_time,
            'locale': self._get_locale,
            'perm': self._get_perm,
            'session': self._get_session,
            'tz': self._get_timezone,
            'use_xsendfile': self._get_use_xsendfile,
            'xsendfile_header': self._get_xsendfile_header,
            'configurable_headers': self._get_configurable_headers,
        })

    @lazy
    def _request_handlers(self):
        return {handler.__class__.__name__: handler
                for handler in self.handlers}

    def _get_valid_default_handler(self, req):
        # Use default_handler from the Session if it is a valid value.
        name = req.session.get('default_handler')
        handler = self._request_handlers.get(name)
        if handler and not is_valid_default_handler(handler):
            handler = None

        if not handler:
            # Use default_handler from project configuration.
            handler = self.default_handler
            if not is_valid_default_handler(handler):
                raise ConfigurationError(
                    tag_("%(handler)s is not a valid default handler. Please "
                         "update %(option)s through the %(page)s page or by "
                         "directly editing trac.ini.",
                         handler=tag.code(handler.__class__.__name__),
                         option=tag.code("[trac] default_handler"),
                         page=tag.a(_("Basic Settings"),
                                    href=req.href.admin('general/basics'))))
        return handler

    def _get_perm(self, req):
        if isinstance(req.session, FakeSession):
            return FakePerm()
        else:
            return PermissionCache(self.env, req.authname)

    def _get_session(self, req):
        try:
            return Session(self.env, req)
        except TracError as e:
            msg = "can't retrieve session: %s"
            if isinstance(e, TracValueError):
                self.log.warning(msg, e)
            else:
                self.log.error(msg, exception_to_unicode(e))
            return FakeSession()

    def _get_locale(self, req):
        if has_babel:
            preferred = req.session.get('language')
            default = self.default_language
            negotiated = get_negotiated_locale([preferred, default] +
                                               req.languages)
            self.log.debug("Negotiated locale: %s -> %s", preferred,
                           negotiated)
            return negotiated

    def _get_lc_time(self, req):
        lc_time = req.session.get('lc_time')
        if not lc_time or lc_time == 'locale' and not has_babel:
            lc_time = self.default_date_format
        if lc_time == 'iso8601':
            return 'iso8601'
        return req.locale

    def _get_timezone(self, req):
        try:
            return timezone(req.session.get('tz', self.default_timezone
                                            or 'missing'))
        except Exception:
            return localtz

    def _get_form_token(self, req):
        """Used to protect against CSRF.

        The 'form_token' is strong shared secret stored in a user
        cookie. By requiring that every POST form to contain this
        value we're able to protect against CSRF attacks. Since this
        value is only known by the user and not by an attacker.

        If the the user does not have a `trac_form_token` cookie a new
        one is generated.
        """
        if 'trac_form_token' in req.incookie:
            return req.incookie['trac_form_token'].value
        else:
            req.outcookie['trac_form_token'] = form_token = hex_entropy(24)
            req.outcookie['trac_form_token']['path'] = req.base_path or '/'
            if self.env.secure_cookies:
                req.outcookie['trac_form_token']['secure'] = True
            req.outcookie['trac_form_token']['httponly'] = True
            return form_token

    def _get_use_xsendfile(self, req):
        return self.use_xsendfile

    @lazy
    def _xsendfile_header(self):
        header = self.xsendfile_header.strip()
        if Request.is_valid_header(header):
            return header
        else:
            if not self._warn_xsendfile_header:
                self._warn_xsendfile_header = True
                self.log.warning("[trac] xsendfile_header is invalid: '%s'",
                                 header)
            return None

    def _get_xsendfile_header(self, req):
        return self._xsendfile_header

    @lazy
    def _configurable_headers(self):
        headers = []
        invalids = []
        for name, val in self.configurable_headers.options():
            if Request.is_valid_header(name, val):
                headers.append((name, val))
            else:
                invalids.append((name, val))
        if invalids:
            self.log.warning('[http-headers] invalid headers are ignored: %s',
                             ', '.join('%r: %r' % i for i in invalids))
        return tuple(headers)

    def _get_configurable_headers(self, req):
        return iter(self._configurable_headers)

    def _pre_process_request(self, req, chosen_handler):
        for filter_ in self.filters:
            chosen_handler = filter_.pre_process_request(req, chosen_handler)
        return chosen_handler

    def _post_process_request(self, req, *args):
        metadata = {}
        resp = args
        if len(args) == 3:
            metadata = args[2]
        elif len(args) == 2:
            resp += (metadata,)
        elif len(args) == 0:
            resp = (None,) * 3
        for f in reversed(self.filters):
            resp = f.post_process_request(req, *resp)
            if len(resp) == 2:
                resp += (metadata,)
        return resp


_slashes_re = re.compile(r'/+')

def dispatch_request(environ, start_response):
    """Main entry point for the Trac web interface.

    :param environ: the WSGI environment dict
    :param start_response: the WSGI callback for starting the response
    """

    # SCRIPT_URL is an Apache var containing the URL before URL rewriting
    # has been applied, so we can use it to reconstruct logical SCRIPT_NAME
    script_url = environ.get('SCRIPT_URL')
    if script_url is not None:
        path_info = environ.get('PATH_INFO')
        if not path_info:
            environ['SCRIPT_NAME'] = script_url
        else:
            # mod_wsgi squashes slashes in PATH_INFO (!)
            script_url = _slashes_re.sub('/', script_url)
            path_info = _slashes_re.sub('/', path_info)
            if script_url.endswith(path_info):
                environ['SCRIPT_NAME'] = script_url[:-len(path_info)]

    # If the expected configuration keys aren't found in the WSGI environment,
    # try looking them up in the process environment variables
    environ.setdefault('trac.env_path', os.getenv('TRAC_ENV'))
    environ.setdefault('trac.env_parent_dir',
                       os.getenv('TRAC_ENV_PARENT_DIR'))
    environ.setdefault('trac.env_index_template',
                       os.getenv('TRAC_ENV_INDEX_TEMPLATE'))
    environ.setdefault('trac.template_vars',
                       os.getenv('TRAC_TEMPLATE_VARS'))
    environ.setdefault('trac.locale', '')
    environ.setdefault('trac.base_url',
                       os.getenv('TRAC_BASE_URL'))

    locale.setlocale(locale.LC_ALL, environ['trac.locale'])

    # Determine the environment
    env_path = environ.get('trac.env_path')
    if not env_path:
        env_parent_dir = environ.get('trac.env_parent_dir')
        env_paths = environ.get('trac.env_paths')
        if env_parent_dir or env_paths:
            # The first component of the path is the base name of the
            # environment
            path_info = environ.get('PATH_INFO', '').lstrip('/').split('/')
            env_name = path_info.pop(0)

            if not env_name:
                # No specific environment requested, so render an environment
                # index page
                send_project_index(environ, start_response, env_parent_dir,
                                   env_paths)
                return []

            errmsg = None

            # To make the matching patterns of request handlers work, we append
            # the environment name to the `SCRIPT_NAME` variable, and keep only
            # the remaining path in the `PATH_INFO` variable.
            script_name = environ.get('SCRIPT_NAME', '')
            try:
                if isinstance(script_name, str):
                    script_name = script_name.encode('iso-8859-1')  # PEP 3333
                script_name = str(script_name, 'utf-8')
            except UnicodeDecodeError:
                errmsg = 'Invalid URL encoding (was %r)' % script_name
            else:
                # (as Href expects unicode parameters)
                environ['SCRIPT_NAME'] = Href(script_name)(env_name)
                environ['PATH_INFO'] = '/' + '/'.join(path_info)

                if env_parent_dir:
                    env_path = os.path.join(env_parent_dir, env_name)
                else:
                    env_path = get_environments(environ).get(env_name)

                if not env_path or not os.path.isdir(env_path):
                    errmsg = 'Environment not found'

            if errmsg:
                errmsg = errmsg.encode('utf-8')
                start_response('404 Not Found',
                               [('Content-Type', 'text/plain'),
                                ('Content-Length', str(len(errmsg)))])
                return [errmsg]

    if not env_path:
        raise EnvironmentError('The environment options "TRAC_ENV" or '
                               '"TRAC_ENV_PARENT_DIR" or the mod_python '
                               'options "TracEnv" or "TracEnvParentDir" are '
                               'missing. Trac requires one of these options '
                               'to locate the Trac environment(s).')
    run_once = environ['wsgi.run_once']

    env = env_error = None
    try:
        env = open_environment(env_path, use_cache=not run_once)
    except Exception as e:
        env_error = e
    else:
        if env.base_url_for_redirect:
            environ['trac.base_url'] = env.base_url

        # Web front-end type and version information
        if not hasattr(env, 'webfrontend'):
            mod_wsgi_version = environ.get('mod_wsgi.version')
            if mod_wsgi_version:
                mod_wsgi_version = (
                        "%s (WSGIProcessGroup %s WSGIApplicationGroup %s)" %
                        ('.'.join(str(x) for x in mod_wsgi_version),
                         environ.get('mod_wsgi.process_group'),
                         environ.get('mod_wsgi.application_group') or
                         '%{GLOBAL}'))
                environ.update({
                    'trac.web.frontend': 'mod_wsgi',
                    'trac.web.version': mod_wsgi_version})
            env.webfrontend = environ.get('trac.web.frontend')
            if env.webfrontend:
                env.webfrontend_version = environ['trac.web.version']

    req = RequestWithSession(environ, start_response)
    # fixup env.abs_href if `[trac] base_url` was not specified
    if env and not env.abs_href.base:
        env.abs_href = req.abs_href
    translation.make_activable(lambda: req.locale, env.path if env else None)
    resp = []
    try:
        if env_error:
            raise HTTPInternalServerError(env_error)
        dispatcher = RequestDispatcher(env)
        dispatcher.set_default_callbacks(req)
        try:
            dispatcher.dispatch(req)
        except RequestDone as req_done:
            resp = req_done.iterable
    except HTTPException as e:
        if not req.response_started:
            _send_user_error(req, env, e)
    except Exception:
        if not req.response_started:
            send_internal_error(env, req, sys.exc_info())
    else:
        resp = resp or req._response or []
    finally:
        translation.deactivate()
        if env and not run_once:
            env.shutdown(get_thread_id())
            # Now it's a good time to do some clean-ups
            #
            # Note: enable the '##' lines as soon as there's a suspicion
            #       of memory leak due to uncollectable objects (typically
            #       objects with a __del__ method caught in a cycle)
            #
            ##gc.set_debug(gc.DEBUG_UNCOLLECTABLE)
            unreachable = gc.collect()
            ##env.log.debug("%d unreachable objects found.", unreachable)
            ##uncollectable = len(gc.garbage)
            ##if uncollectable:
            ##    del gc.garbage[:]
            ##    env.log.warning("%d uncollectable objects found.",
            ##                    uncollectable)
        return resp


def _send_error(req, exc_info, template='error.html', content_type='text/html',
                status=500, env=None, data={}):
    if env:
        add_stylesheet(req, 'common/css/code.css')
        metadata = {'content_type': 'text/html', 'iterable': False}
        try:
            content = Chrome(env).render_template(req, template,
                                                  data, metadata)
        except Exception:
            # second chance rendering, in "safe" mode
            data['trac_error_rendering'] = True
            try:
                content = Chrome(env).render_template(req, template,
                                                      data, metadata)
            except Exception:
                content = get_last_traceback()
                content_type = 'text/plain'
    else:
        content_type = 'text/plain'
        content = '%s\n\n%s: %s' % (data.get('title'),
                                    data.get('type'),
                                    data.get('message'))

    if isinstance(content, str):
        content = content.encode('utf-8')

    try:
        req.send_error(exc_info, content, content_type, status)
    except RequestDone:
        pass


def _send_user_error(req, env, e):
    # See trac/web/api.py for the definition of HTTPException subclasses.
    if env:
        env.log.warning('[%s] %s, %r, referrer %r',
                        req.remote_addr, exception_to_unicode(e),
                        req, req.environ.get('HTTP_REFERER'))
    data = {'title': e.title, 'type': 'TracError', 'message': e.message,
            'frames': [], 'traceback': None}
    if e.code == 403 and not req.is_authenticated:
        # TRANSLATOR: ... not logged in, you may want to 'do so' now (link)
        do_so = tag.a(_("do so"), href=req.href.login())
        add_notice(req, tag_("You are currently not logged in. You may want "
                             "to %(do_so)s now.", do_so=do_so))
    _send_error(req, sys.exc_info(), status=e.code, env=env, data=data)


def send_internal_error(env, req, exc_info):
    if env:
        env.log.error("[%s] Internal Server Error: %r, referrer %r%s",
                      req.remote_addr, req, req.environ.get('HTTP_REFERER'),
                      exception_to_unicode(exc_info[1], traceback=True))
    message = exception_to_unicode(exc_info[1])
    traceback = get_last_traceback()

    frames, plugins, faulty_plugins, interface_custom = [], [], [], []
    th = 'http://trac-hacks.org'
    try:
        has_admin = 'TRAC_ADMIN' in req.perm
    except Exception:
        has_admin = False

    tracker = default_tracker
    tracker_args = {}
    if has_admin and not isinstance(exc_info[1], MemoryError):
        # Collect frame and plugin information
        frames = get_frame_info(exc_info[2])
        if env:
            plugins = [p for p in get_plugin_info(env)
                       if any(c['enabled']
                              for m in p['modules'].values()
                              for c in m['components'].values())]
            match_plugins_to_frames(plugins, frames)

            # Identify the tracker where the bug should be reported
            faulty_plugins = [p for p in plugins if 'frame_idx' in p]
            faulty_plugins.sort(key=lambda p: p['frame_idx'])
            if faulty_plugins:
                info = faulty_plugins[0]['info']
                home_page = info.get('home_page', '')
                if 'trac' in info:
                    tracker = info['trac']
                elif urlparse(home_page).netloc == urlparse(th).netloc:
                    tracker = th
                    plugin_name = info.get('home_page', '').rstrip('/') \
                                                           .split('/')[-1]
                    tracker_args = {'component': plugin_name}
            interface_custom = Chrome(env).get_interface_customization_files()

    def get_description(_):
        if env and has_admin:
            sys_info = "".join("|| '''`%s`''' || `%s` ||\n"
                               % (k, (v.replace('\n', '` [[br]] `') if v
                                      else _('N/A')))
                               for k, v in env.system_info)
            sys_info += "|| '''`jQuery`''' || `#JQUERY#` ||\n" \
                        "|| '''`jQuery UI`''' || `#JQUERYUI#` ||\n" \
                        "|| '''`jQuery Timepicker`''' || `#JQUERYTP#` ||\n"
            enabled_plugins = "".join("|| '''`%s`''' || `%s` ||\n"
                                      % (p['name'], p['version'] or _('N/A'))
                                      for p in plugins)
            files = Chrome(env).get_interface_customization_files()
            interface_files = "".join("|| **%s** || %s ||\n"
                                      % (k, ", ".join("`%s`" % f for f in v))
                                      for k, v in sorted(files.items()))
        else:
            sys_info = _("''System information not available''\n")
            enabled_plugins = _("''Plugin information not available''\n")
            interface_files = _("''Interface customization information not "
                                 "available''\n")
        return _("""\
==== How to Reproduce

While doing a %(method)s operation on `%(path_info)s`, \
Trac issued an internal error.

''(please provide additional details here)''

Request parameters:
{{{
%(req_args)s
}}}

User agent: `#USER_AGENT#`

==== System Information
%(sys_info)s
==== Enabled Plugins
%(enabled_plugins)s
==== Interface Customization
%(interface_customization)s
==== Python Traceback
{{{
%(traceback)s}}}""",
            method=req.method, path_info=req.path_info,
            req_args=pformat(req.args), sys_info=sys_info,
            enabled_plugins=enabled_plugins,
            interface_customization=interface_files,
            traceback=to_unicode(traceback))

    # Generate the description once in English, once in the current locale
    description_en = get_description(lambda s, **kw: safefmt(s, kw))
    try:
        description = get_description(_)
    except Exception:
        description = description_en

    data = {'title': 'Internal Error',
            'type': 'internal', 'message': message,
            'traceback': traceback, 'frames': frames,
            'shorten_line': shorten_line, 'repr': safe_repr,
            'plugins': plugins, 'faulty_plugins': faulty_plugins,
            'interface': interface_custom,
            'tracker': tracker, 'tracker_args': tracker_args,
            'description': description, 'description_en': description_en}

    if env:
        Chrome(env).add_jquery_ui(req)
    _send_error(req, sys.exc_info(), status=500, env=env, data=data)


def send_project_index(environ, start_response, parent_dir=None,
                       env_paths=None):
    req = Request(environ, start_response)

    loadpaths = [pkg_resources.resource_filename('trac', 'templates')]
    if req.environ.get('trac.env_index_template'):
        env_index_template = req.environ['trac.env_index_template']
        tmpl_path, template = os.path.split(env_index_template)
        loadpaths.insert(0, tmpl_path)
    else:
        template = 'index.html'

    data = {'trac': {'version': TRAC_VERSION,
                     'time': user_time(req, format_datetime)},
            'req': req}
    if req.environ.get('trac.template_vars'):
        for pair in req.environ['trac.template_vars'].split(','):
            key, val = pair.split('=')
            data[key] = val

    href = Href(req.base_path)
    projects = []
    for env_name, env_path in get_environments(environ).items():
        try:
            env = open_environment(env_path,
                                   use_cache=not environ['wsgi.run_once'])
        except Exception as e:
            proj = {'name': env_name, 'description': to_unicode(e)}
        else:
            proj = {
                'env': env,
                'name': env.project_name,
                'description': env.project_description,
                'href': href(env_name)
            }
        projects.append(proj)
    projects.sort(key=lambda proj: proj['name'].lower())

    data['projects'] = projects

    jenv = jinja2env(loader=FileSystemLoader(loadpaths))
    jenv.globals.update(translation.functions)
    tmpl = jenv.get_template(template)
    output = valid_html_bytes(tmpl.render(**data).encode('utf-8'))
    content_type = 'text/xml' if template.endswith('.xml') else 'text/html'
    try:
        req.send(output, content_type)
    except RequestDone:
        pass


def get_tracignore_patterns(env_parent_dir):
    """Return the list of patterns from env_parent_dir/.tracignore or
    a default pattern of `".*"` if the file doesn't exist.
    """
    path = os.path.join(env_parent_dir, '.tracignore')
    try:
        lines = [line.strip() for line in read_file(path).splitlines()]
    except IOError:
        return ['.*']
    return [line for line in lines if line and not line.startswith('#')]


def get_environments(environ, warn=False):
    """Retrieve canonical environment name to path mapping.

    The environments may not be all valid environments, but they are
    good candidates.
    """
    env_paths = environ.get('trac.env_paths', [])
    env_parent_dir = environ.get('trac.env_parent_dir')
    if env_parent_dir:
        env_parent_dir = os.path.normpath(env_parent_dir)
        # Filter paths that match the .tracignore patterns
        ignore_patterns = get_tracignore_patterns(env_parent_dir)
        paths = [name for name in os.listdir(env_parent_dir)
                      if os.path.isdir(os.path.join(env_parent_dir, name)) and
                      not any(fnmatch.fnmatch(name, pattern)
                              for pattern in ignore_patterns)]
        env_paths.extend(os.path.join(env_parent_dir, project)
                         for project in paths)
    envs = {}
    for env_path in env_paths:
        env_path = os.path.normpath(env_path)
        if not os.path.isdir(env_path):
            continue
        env_name = os.path.split(env_path)[1]
        if env_name in envs:
            if warn:
                print('Warning: Ignoring project "%s" since it conflicts with'
                      ' project "%s"' % (env_path, envs[env_name]),
                      file=sys.stderr)
        else:
            envs[env_name] = env_path
    return envs
