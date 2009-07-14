# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2009 Edgewall Software
# Copyright (C) 2005-2007 Christopher Lenz <cmlenz@gmx.de>
# Copyright (C) 2005 Matthew Good <trac@matt-good.net>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.
#
# Author: Christopher Lenz <cmlenz@gmx.de>
#         Matthew Good <trac@matt-good.net>

import cgi
import dircache
import gc
import locale
import os
import pkg_resources
import sys
try:
    import threading
except ImportError:
    import dummy_threading as threading

from genshi.core import Markup
from genshi.builder import Fragment
from genshi.output import DocType
from genshi.template import TemplateLoader

from trac import __version__ as TRAC_VERSION
from trac.config import ExtensionOption, Option, OrderedExtensionsOption
from trac.core import *
from trac.env import open_environment
from trac.perm import PermissionCache, PermissionError, PermissionSystem
from trac.resource import ResourceNotFound
from trac.util import get_lines_from_file, get_last_traceback, hex_entropy, \
                      arity
from trac.util.compat import partial, reversed
from trac.util.datefmt import format_datetime, http_date, localtz, timezone
from trac.util.text import exception_to_unicode, shorten_line, to_unicode
from trac.util.translation import _
from trac.web.api import *
from trac.web.chrome import Chrome
from trac.web.clearsilver import HDFWrapper
from trac.web.href import Href
from trac.web.session import Session

def populate_hdf(hdf, env, req=None):
    """Populate the HDF data set with various information, such as common URLs,
    project information and request-related information.
    """
    # FIXME: do we really have req==None at times?
    hdf['trac'] = {
        'version': TRAC_VERSION,
        'time': format_datetime(),
        'time.gmt': http_date()
    }
    hdf['project'] = {
        'shortname': os.path.basename(env.path),
        'name': env.project_name,
        'name_encoded': env.project_name,
        'descr': env.project_description,
        'footer': Markup(env.project_footer),
        'url': env.project_url
    }

    if req:
        hdf['trac.href'] = {
            'wiki': req.href.wiki(),
            'browser': req.href.browser('/'),
            'timeline': req.href.timeline(),
            'roadmap': req.href.roadmap(),
            'milestone': req.href.milestone(None),
            'report': req.href.report(),
            'query': req.href.query(),
            'newticket': req.href.newticket(),
            'search': req.href.search(),
            'about': req.href.about(),
            'about_config': req.href.about('config'),
            'login': req.href.login(),
            'logout': req.href.logout(),
            'settings': req.href.settings(),
            'homepage': 'http://trac.edgewall.org/'
        }

        hdf['base_url'] = req.base_url
        hdf['base_host'] = req.base_url[:req.base_url.rfind(req.base_path)]
        hdf['cgi_location'] = req.base_path
        hdf['trac.authname'] = req.authname

        if req.perm:
            for action in req.perm.permissions():
                hdf['trac.acl.' + action] = True

        for arg in [k for k in req.args.keys() if k]:
            if isinstance(req.args[arg], (list, tuple)):
                hdf['args.%s' % arg] = [v for v in req.args[arg]]
            elif isinstance(req.args[arg], basestring):
                hdf['args.%s' % arg] = req.args[arg]
            # others are file uploads


class RequestDispatcher(Component):
    """Component responsible for dispatching requests to registered handlers."""

    authenticators = ExtensionPoint(IAuthenticator)
    handlers = ExtensionPoint(IRequestHandler)

    filters = OrderedExtensionsOption('trac', 'request_filters', IRequestFilter,
        doc="""Ordered list of filters to apply to all requests
            (''since 0.10'').""")

    default_handler = ExtensionOption('trac', 'default_handler',
                                      IRequestHandler, 'WikiModule',
        """Name of the component that handles requests to the base URL.
        
        Options include `TimelineModule`, `RoadmapModule`, `BrowserModule`,
        `QueryModule`, `ReportModule` and `TicketModule` (''since 0.9'').""")

    default_timezone = Option('trac', 'default_timezone', '',
        """The default timezone to use""")

    # Public API

    def authenticate(self, req):
        for authenticator in self.authenticators:
            authname = authenticator.authenticate(req)
            if authname:
                return authname
        else:
            return 'anonymous'

    def dispatch(self, req):
        """Find a registered handler that matches the request and let it process
        it.
        
        In addition, this method initializes the HDF data set and adds the web
        site chrome.
        """
        self.log.debug('Dispatching %r', req)
        chrome = Chrome(self.env)

        # Setup request callbacks for lazily-evaluated properties
        req.callbacks.update({
            'authname': self.authenticate,
            'chrome': chrome.prepare_request,
            'hdf': self._get_hdf,
            'perm': self._get_perm,
            'session': self._get_session,
            'tz': self._get_timezone,
            'form_token': self._get_form_token
        })

        try:
            try:
                # Select the component that should handle the request
                chosen_handler = None
                try:
                    for handler in self.handlers:
                        if handler.match_request(req):
                            chosen_handler = handler
                            break
                    if not chosen_handler:
                        if not req.path_info or req.path_info == '/':
                            chosen_handler = self.default_handler
                    # pre-process any incoming request, whether a handler
                    # was found or not
                    chosen_handler = self._pre_process_request(req,
                                                               chosen_handler)
                except TracError, e:
                    raise HTTPInternalError(e)
                if not chosen_handler:
                    if req.path_info.endswith('/'):
                        # Strip trailing / and redirect
                        target = req.path_info.rstrip('/').encode('utf-8')
                        if req.query_string:
                            target += '?' + req.query_string
                        req.redirect(req.href() + target, permanent=True)
                    raise HTTPNotFound('No handler matched request to %s',
                                       req.path_info)

                req.callbacks['chrome'] = partial(chrome.prepare_request,
                                                  handler=chosen_handler)

                # Protect against CSRF attacks: we validate the form token for
                # all POST requests with a content-type corresponding to form
                # submissions
                if req.method == 'POST':
                    ctype = req.get_header('Content-Type')
                    if ctype:
                        ctype, options = cgi.parse_header(ctype)
                    if ctype in ('application/x-www-form-urlencoded',
                                 'multipart/form-data') and \
                            req.args.get('__FORM_TOKEN') != req.form_token:
                        raise HTTPBadRequest('Missing or invalid form token. '
                                             'Do you have cookies enabled?')

                # Process the request and render the template
                resp = chosen_handler.process_request(req)
                if resp:
                    if len(resp) == 2: # Clearsilver
                        chrome.populate_hdf(req)
                        template, content_type = \
                                  self._post_process_request(req, *resp)
                        # Give the session a chance to persist changes
                        req.session.save()
                        req.display(template, content_type or 'text/html')
                    else: # Genshi
                        template, data, content_type = \
                                  self._post_process_request(req, *resp)
                        if 'hdfdump' in req.args:
                            req.perm.require('TRAC_ADMIN')
                            # debugging helper - no need to render first
                            from pprint import pprint
                            out = StringIO()
                            pprint(data, out)
                            req.send(out.getvalue(), 'text/plain')
                        else:
                            output = chrome.render_template(req, template,
                                                            data, content_type)
                            # Give the session a chance to persist changes
                            req.session.save()
                            req.send(output, content_type or 'text/html')
                else:
                    self._post_process_request(req)
            except RequestDone:
                raise
            except:
                # post-process the request in case of errors
                err = sys.exc_info()
                try:
                    self._post_process_request(req)
                except RequestDone:
                    raise
                except Exception, e:
                    self.log.error("Exception caught while post-processing"
                                   " request: %s",
                                   exception_to_unicode(e, traceback=True))
                raise err[0], err[1], err[2]
        except PermissionError, e:
            raise HTTPForbidden(to_unicode(e))
        except ResourceNotFound, e:
            raise HTTPNotFound(e)
        except TracError, e:
            raise HTTPInternalError(e)

    # Internal methods

    def _get_hdf(self, req):
        hdf = HDFWrapper(loadpaths=Chrome(self.env).get_all_templates_dirs())
        populate_hdf(hdf, self.env, req)
        return hdf

    def _get_perm(self, req):
        return PermissionCache(self.env, self.authenticate(req))

    def _get_session(self, req):
        return Session(self.env, req)

    def _get_timezone(self, req):
        try:
            return timezone(req.session.get('tz', self.default_timezone
                                            or 'missing'))
        except:
            return localtz

    def _get_form_token(self, req):
        """Used to protect against CSRF.

        The 'form_token' is strong shared secret stored in a user cookie.
        By requiring that every POST form to contain this value we're able to
        protect against CSRF attacks. Since this value is only known by the
        user and not by an attacker.
        
        If the the user does not have a `trac_form_token` cookie a new
        one is generated.
        """
        if req.incookie.has_key('trac_form_token'):
            return req.incookie['trac_form_token'].value
        else:
            req.outcookie['trac_form_token'] = hex_entropy(24)
            req.outcookie['trac_form_token']['path'] = req.base_path or '/'
            if self.env.secure_cookies:
                req.outcookie['trac_form_token']['secure'] = True
            return req.outcookie['trac_form_token'].value

    def _pre_process_request(self, req, chosen_handler):
        for filter_ in self.filters:
            chosen_handler = filter_.pre_process_request(req, chosen_handler)
        return chosen_handler

    def _post_process_request(self, req, *args):
        nbargs = len(args)
        resp = args
        for f in reversed(self.filters):
            # As the arity of `post_process_request` has changed since 
            # Trac 0.10, only filters with same arity gets passed real values.
            # Errors will call all filters with None arguments,
            # and results will not be not saved.
            extra_arg_count = arity(f.post_process_request) - 2
            if extra_arg_count == nbargs:
                resp = f.post_process_request(req, *resp)
            elif nbargs == 0:
                f.post_process_request(req, *(None,)*extra_arg_count)
        return resp


def dispatch_request(environ, start_response):
    """Main entry point for the Trac web interface.
    
    @param environ: the WSGI environment dict
    @param start_response: the WSGI callback for starting the response
    """

    # SCRIPT_URL is an Apache var containing the URL before URL rewriting
    # has been applied, so we can use it to reconstruct logical SCRIPT_NAME
    script_url = environ.get('SCRIPT_URL')
    if script_url is not None:
        path_info = environ.get('PATH_INFO')
        if not path_info:
            environ['SCRIPT_NAME'] = script_url
        elif script_url.endswith(path_info):
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

            # To make the matching patterns of request handlers work, we append
            # the environment name to the `SCRIPT_NAME` variable, and keep only
            # the remaining path in the `PATH_INFO` variable.
            environ['SCRIPT_NAME'] = Href(environ['SCRIPT_NAME'])(env_name)
            environ['PATH_INFO'] = '/' + '/'.join(path_info)

            if env_parent_dir:
                env_path = os.path.join(env_parent_dir, env_name)
            else:
                env_path = get_environments(environ).get(env_name)

            if not env_path or not os.path.isdir(env_path):
                errmsg = 'Environment not found'
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
        if env.base_url_for_redirect:
            environ['trac.base_url'] = env.base_url

        # Web front-end type and version information
        if not hasattr(env, 'webfrontend'):
            mod_wsgi_version = environ.get('mod_wsgi.version')
            if mod_wsgi_version:
                environ.update({
                    'trac.web.frontend': 'mod_wsgi',
                    'trac.web.version': '.'.join([str(x) for x in 
                                                  mod_wsgi_version])})
            env.webfrontend = environ.get('trac.web.frontend')
            if env.webfrontend:
                env.systeminfo.append((env.webfrontend, 
                                       environ['trac.web.version']))
    except Exception, e:
        env_error = e

    req = Request(environ, start_response)
    try:
        return _dispatch_request(req, env, env_error)
    finally:
        if env and not run_once:
            env.shutdown(threading._get_ident())
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
            ##    env.log.warn("%d uncollectable objects found.", uncollectable)

def _dispatch_request(req, env, env_error):
    resp = []

    # fixup env.abs_href if `[trac] base_url` was not specified
    if env and not env.abs_href.base:
        env._abs_href = req.abs_href

    try:
        if not env and env_error:
            raise HTTPInternalError(env_error)
        try:
            dispatcher = RequestDispatcher(env)
            dispatcher.dispatch(req)
        except RequestDone:
            pass
        resp = req._response or []

    except HTTPException, e:
        # This part is a bit more complex than it should be.
        # See trac/web/api.py for the definition of HTTPException subclasses.
        if env:
            env.log.warn(exception_to_unicode(e))
        title = 'Error'
        if e.reason:
            if 'error' in e.reason.lower():
                title = e.reason
            else:
                title = 'Error: %s' % e.reason
        # The message is based on the e.detail, which can be an Exception
        # object, but not a TracError one: when creating HTTPException,
        # a TracError.message is directly assigned to e.detail
        if isinstance(e.detail, Exception): # not a TracError
            message = exception_to_unicode(e.detail)
        elif isinstance(e.detail, Fragment): # markup coming from a TracError
            message = e.detail
        else:
            message = to_unicode(e.detail)
        data = {'title': title, 'type': 'TracError', 'message': message,
                'frames': [], 'traceback': None}
        if e.code == 403 and req.authname == 'anonymous':
            req.chrome['notices'].append(Markup(
                _('You are currently not logged in. You may want to '
                  '<a href="%(href)s">do so</a> now.',
                  href=req.href.login())))
        try:
            req.send_error(sys.exc_info(), status=e.code, env=env, data=data)
        except RequestDone:
            pass

    except Exception, e:
        if env:
            env.log.error("Internal Server Error: %s", 
                          exception_to_unicode(e, traceback=True))

        exc_info = sys.exc_info()
        try:
            message = "%s: %s" % (e.__class__.__name__, to_unicode(e))
            traceback = get_last_traceback()

            frames = []
            has_admin = False
            try:
                has_admin = 'TRAC_ADMIN' in req.perm
            except Exception, e:
                pass
            if has_admin and not isinstance(e, MemoryError):
                tb = exc_info[2]
                while tb:
                    tb_hide = tb.tb_frame.f_locals.get('__traceback_hide__')
                    if tb_hide in ('before', 'before_and_this'):
                        del frames[:]
                        tb_hide = tb_hide[6:]
                    if not tb_hide:
                        filename = tb.tb_frame.f_code.co_filename
                        lineno = tb.tb_lineno - 1
                        before, line, after = get_lines_from_file(filename,
                                                                  lineno, 5)
                        frames += [{'traceback': tb, 'filename': filename,
                                    'lineno': lineno, 'line': line,
                                    'lines_before': before, 'lines_after': after,
                                    'function': tb.tb_frame.f_code.co_name,
                                    'vars': tb.tb_frame.f_locals}]
                    tb = tb.tb_next

            data = {'title': 'Internal Error',
                    'type': 'internal', 'message': message,
                    'traceback': traceback, 'frames': frames,
                    'shorten_line': shorten_line}

            try:
                req.send_error(exc_info, status=500, env=env, data=data)
            except RequestDone:
                pass

        finally:
            del exc_info
    return resp

def send_project_index(environ, start_response, parent_dir=None,
                       env_paths=None):
    req = Request(environ, start_response)

    loadpaths = [pkg_resources.resource_filename('trac', 'templates')]
    use_clearsilver = False
    if req.environ.get('trac.env_index_template'):
        tmpl_path, template = os.path.split(req.environ['trac.env_index_template'])
        loadpaths.insert(0, tmpl_path)
        use_clearsilver = template.endswith('.cs') # assume Clearsilver
        if use_clearsilver:
            req.hdf = HDFWrapper(loadpaths) # keep that for custom .cs templates
    else:
        template = 'index.html'

    data = {'trac': {'version': TRAC_VERSION, 'time': format_datetime()}}
    if req.environ.get('trac.template_vars'):
        for pair in req.environ['trac.template_vars'].split(','):
            key, val = pair.split('=')
            data[key] = val
            if use_clearsilver:
                req.hdf[key] = val
    try:
        href = Href(req.base_path)
        projects = []
        for env_name, env_path in get_environments(environ).items():
            try:
                env = open_environment(env_path,
                                       use_cache=not environ['wsgi.run_once'])
                proj = {
                    'env': env,
                    'name': env.project_name,
                    'description': env.project_description,
                    'href': href(env_name)
                }
            except Exception, e:
                proj = {'name': env_name, 'description': to_unicode(e)}
            projects.append(proj)
        projects.sort(lambda x, y: cmp(x['name'].lower(), y['name'].lower()))

        data['projects'] = projects
        if use_clearsilver:
            req.hdf['projects'] = projects
            req.display(template)

        loader = TemplateLoader(loadpaths, variable_lookup='lenient')
        tmpl = loader.load(template)
        stream = tmpl.generate(**data)
        output = stream.render('xhtml', doctype=DocType.XHTML_STRICT)
        req.send(output, 'text/html')

    except RequestDone:
        pass

def get_environments(environ, warn=False):
    """Retrieve canonical environment name to path mapping.

    The environments may not be all valid environments, but they are good
    candidates.
    """
    env_paths = environ.get('trac.env_paths', [])
    env_parent_dir = environ.get('trac.env_parent_dir')
    if env_parent_dir:
        env_parent_dir = os.path.normpath(env_parent_dir)
        paths = dircache.listdir(env_parent_dir)[:]
        dircache.annotate(env_parent_dir, paths)
        env_paths += [os.path.join(env_parent_dir, project) \
                      for project in paths 
                      if project[-1] == '/' and project != '.egg-cache/']
    envs = {}
    for env_path in env_paths:
        env_path = os.path.normpath(env_path)
        if not os.path.isdir(env_path):
            continue
        env_name = os.path.split(env_path)[1]
        if env_name in envs:
            if warn:
                print >> sys.stderr, ('Warning: Ignoring project "%s" since '
                                      'it conflicts with project "%s"'
                                      % (env_path, envs[env_name]))
        else:
            envs[env_name] = env_path
    return envs
