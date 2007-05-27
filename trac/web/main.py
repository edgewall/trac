# -*- coding: utf-8 -*-
#
# Copyright (C) 2005 Edgewall Software
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
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
import locale
import os
import pkg_resources
import sys
import urllib

from genshi import Markup
from genshi.output import DocType
from genshi.template import TemplateLoader

from trac.config import ExtensionOption, Option, OrderedExtensionsOption
from trac.core import *
from trac.env import open_environment
from trac.perm import PermissionCache, PermissionError, PermissionSystem
from trac.util import get_lines_from_file, get_last_traceback, hex_entropy
from trac.util.compat import partial, reversed
from trac.util.datefmt import format_datetime, http_date, localtz, timezone
from trac.util.text import shorten_line, to_unicode
from trac.web.api import *
from trac.web.chrome import Chrome
from trac.web.clearsilver import HDFWrapper
from trac.web.href import Href
from trac.web.session import Session

# Environment cache for multithreaded front-ends:
try:
    import threading
except ImportError:
    import dummy_threading as threading

env_cache = {}
env_cache_lock = threading.Lock()

def _open_environment(env_path, run_once=False):
    if run_once:
        return open_environment(env_path)

    global env_cache, env_cache_lock
    env = None
    env_cache_lock.acquire()
    try:
        if not env_path in env_cache:
            env_cache[env_path] = open_environment(env_path)
        env = env_cache[env_path]
    finally:
        env_cache_lock.release()

    # Re-parse the configuration file if it changed since the last the time it
    # was parsed
    env.config.parse_if_needed()

    return env

def populate_hdf(hdf, env, req=None):
    """Populate the HDF data set with various information, such as common URLs,
    project information and request-related information.
    FIXME: do we really have req==None at times?
    """
    from trac import __version__
    hdf['trac'] = {
        'version': __version__,
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

        # Select the component that should handle the request
        chosen_handler = None
        try:
            if not req.path_info or req.path_info == '/':
                chosen_handler = self.default_handler
            else:
                for handler in self.handlers:
                    if handler.match_request(req):
                        chosen_handler = handler
                        break
            chosen_handler = self._pre_process_request(req, chosen_handler)
        except TracError, e:
            raise HTTPInternalError(e)
        if not chosen_handler:
            raise HTTPNotFound('No handler matched request to %s',
                               req.path_info)

        req.callbacks['chrome'] = partial(chrome.prepare_request,
                                          handler=chosen_handler)

        # Protect against CSRF attacks: we validate the form token for all POST
        # requests with a content-type corresponding to form submissions
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
        try:
            try:
                resp = chosen_handler.process_request(req)
                if resp:
                    if len(resp) == 2: # Clearsilver
                        chrome.populate_hdf(req)
                        template, content_type = \
                                  self._post_process_request(req, *resp)
                        # Give the session a chance to persist changes
                        if req.session:
                            req.session.save()
                        req.display(template, content_type or 'text/html')
                    else: # Genshi
                        template, data, content_type = \
                                  self._post_process_request(req, *resp)
                        output = chrome.render_template(req, template, data,
                                                        content_type)
                        # Give the session a chance to persist changes
                        if req.session:
                            req.session.save()

                        if 'hdfdump' in req.args:
                            from pprint import pprint
                            out = StringIO()
                            pprint(data, out)
                            req.send(out.getvalue(), 'text/plain')
                        else:
                            req.send(output, content_type or 'text/html')
                else:
                    self._post_process_request(req)
            except RequestDone:
                raise
            except:
                err = sys.exc_info()
                try:
                    self._post_process_request(req)
                except Exception, e:
                    self.log.exception(e)
                raise err[0], err[1], err[2]
        except PermissionError, e:
            raise HTTPForbidden(to_unicode(e))
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
            req.outcookie['trac_form_token']['path'] = req.base_path
            return req.outcookie['trac_form_token'].value

    def _pre_process_request(self, req, chosen_handler):
        for filter_ in self.filters:
            chosen_handler = filter_.pre_process_request(req, chosen_handler)
        return chosen_handler

    def _post_process_request(self, req, *args):
        nbargs = len(args)
        resp = args
        for f in reversed(self.filters):
            arity = f.post_process_request.func_code.co_argcount - 2
            if nbargs:
                if arity == nbargs:
                    resp = f.post_process_request(req, *resp)
            else:
                resp = f.post_process_request(req, *(None,)*arity)
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

    if 'mod_python.options' in environ:
        options = environ['mod_python.options']
        environ.setdefault('trac.env_path', options.get('TracEnv'))
        environ.setdefault('trac.env_parent_dir',
                           options.get('TracEnvParentDir'))
        environ.setdefault('trac.env_index_template',
                           options.get('TracEnvIndexTemplate'))
        environ.setdefault('trac.template_vars',
                           options.get('TracTemplateVars'))
        environ.setdefault('trac.locale', options.get('TracLocale'))

        if 'TracUriRoot' in options:
            # Special handling of SCRIPT_NAME/PATH_INFO for mod_python, which
            # tends to get confused for whatever reason
            root_uri = options['TracUriRoot'].rstrip('/')
            request_uri = environ['REQUEST_URI'].split('?', 1)[0]
            if not request_uri.startswith(root_uri):
                raise ValueError('TracUriRoot set to %s but request URL '
                                 'is %s' % (root_uri, request_uri))
            environ['SCRIPT_NAME'] = root_uri
            environ['PATH_INFO'] = urllib.unquote(request_uri[len(root_uri):])

    else:
        environ.setdefault('trac.env_path', os.getenv('TRAC_ENV'))
        environ.setdefault('trac.env_parent_dir',
                           os.getenv('TRAC_ENV_PARENT_DIR'))
        environ.setdefault('trac.env_index_template',
                           os.getenv('TRAC_ENV_INDEX_TEMPLATE'))
        environ.setdefault('trac.template_vars',
                           os.getenv('TRAC_TEMPLATE_VARS'))
        environ.setdefault('trac.locale', '')

    locale.setlocale(locale.LC_ALL, environ['trac.locale'])

    # Allow specifying the python eggs cache directory using SetEnv
    if 'mod_python.subprocess_env' in environ:
        egg_cache = environ['mod_python.subprocess_env'].get('PYTHON_EGG_CACHE')
        if egg_cache:
            os.environ['PYTHON_EGG_CACHE'] = egg_cache

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
                start_response('404 Not Found', [])
                return ['Environment not found']

    if not env_path:
        raise EnvironmentError('The environment options "TRAC_ENV" or '
                               '"TRAC_ENV_PARENT_DIR" or the mod_python '
                               'options "TracEnv" or "TracEnvParentDir" are '
                               'missing. Trac requires one of these options '
                               'to locate the Trac environment(s).')
    run_once = environ['wsgi.run_once']

    env = env_error = None
    try:
        env = _open_environment(env_path, run_once=run_once)
        if env.base_url:
            environ['trac.base_url'] = env.base_url
    except TracError, e:
        env_error = e

    req = Request(environ, start_response)
    try:
        if not env and env_error:
            raise HTTPInternalError(env_error)
        try:
            try:
                dispatcher = RequestDispatcher(env)
                dispatcher.dispatch(req)
            except RequestDone:
                pass
            return req._response or []
        finally:
            if not run_once:
                env.shutdown(threading._get_ident())

    except HTTPException, e:
        if env:
            env.log.warn(e)
        title = 'Error'
        if e.reason:
            if 'error' in e.reason.lower():
                title = e.reason
            else:
                title = 'Error: %s' % e.reason
        data = {'title': title, 'type': 'TracError', 'message': e.detail,
                'frames': [], 'traceback': None}
        try:
            req.send_error(sys.exc_info(), status=e.code, env=env, data=data)
        except RequestDone:
            return []

    except Exception, e:
        env.log.exception(e)

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
            if has_admin:
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

            try: # clear chrome data is already set
                del req.chrome
            except AttributeError:
                pass

            try:
                req.send_error(exc_info, status=500, env=env, data=data)
            except RequestDone:
                return []

        finally:
            del exc_info

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

    data = {}
    if req.environ.get('trac.template_vars'):
        for pair in req.environ['trac.template_vars'].split(','):
            key, val = pair.split('=')
            data[key] = val
            if use_clearsilver:
                req.hdf[key] = val

    if parent_dir and not env_paths:
        env_paths = dict([(filename, os.path.join(parent_dir, filename))
                          for filename in os.listdir(parent_dir)])

    try:
        href = Href(req.base_path)
        projects = []
        for env_name, env_path in get_environments(environ).items():
            try:
                env = _open_environment(env_path,
                                        run_once=environ['wsgi.run_once'])
                proj = {
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

        markuptemplate = TemplateLoader(loadpaths).load(template)
        stream = markuptemplate.generate(**data)
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
                      for project in paths if project[-1] == '/']
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
