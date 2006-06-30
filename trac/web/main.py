# -*- coding: utf-8 -*-
#
# Copyright (C) 2005 Edgewall Software
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
# Copyright (C) 2005 Matthew Good <trac@matt-good.net>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://projects.edgewall.com/trac/.
#
# Author: Christopher Lenz <cmlenz@gmx.de>
#         Matthew Good <trac@matt-good.net>

import locale
import os
import sys
import dircache
import urllib

from trac.config import ExtensionOption, OrderedExtensionsOption
from trac.core import *
from trac.env import open_environment
from trac.perm import PermissionCache, NoPermissionCache, PermissionError
from trac.util import reversed, get_last_traceback
from trac.util.datefmt import format_datetime, http_date
from trac.util.text import to_unicode
from trac.util.markup import Markup
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
            'homepage': 'http://trac.edgewall.com/'
        }

        hdf['base_url'] = req.base_url
        hdf['base_host'] = req.base_url[:req.base_url.rfind(req.base_path)]
        hdf['cgi_location'] = req.base_path
        hdf['trac.authname'] = req.authname

        if req.perm:
            for action in req.perm.permissions():
                req.hdf['trac.acl.' + action] = True

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
        
        Options include `TimeLineModule`, `RoadmapModule`, `BrowserModule`,
        `QueryModule`, `ReportModule` and `NewticketModule` (''since 0.9'').""")

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
        # FIXME: For backwards compatibility, should be removed in 0.11
        self.env.href = req.href
        self.env.abs_href = req.abs_href

        # Select the component that should handle the request
        chosen_handler = None
        if not req.path_info or req.path_info == '/':
            chosen_handler = self.default_handler
        else:
            for handler in self.handlers:
                if handler.match_request(req):
                    chosen_handler = handler
                    break

        for filter_ in self.filters:
            chosen_handler = filter_.pre_process_request(req, chosen_handler)

        if not chosen_handler:
            raise HTTPNotFound('No handler matched request to %s',
                               req.path_info)

        # Attach user information to the request
        anonymous_request = getattr(chosen_handler, 'anonymous_request', False)
        if anonymous_request:
            req.authname = 'anonymous'
            req.perm = NoPermissionCache()
        else:
            req.authname = self.authenticate(req)
            req.perm = PermissionCache(self.env, req.authname)
            req.session = Session(self.env, req)

        # Prepare HDF for the clearsilver template
        use_template = getattr(chosen_handler, 'use_template', True)
        if use_template:
            chrome = Chrome(self.env)
            req.hdf = HDFWrapper(loadpaths=chrome.get_all_templates_dirs())
            populate_hdf(req.hdf, self.env, req)
            chrome.populate_hdf(req, chosen_handler)

        # Process the request and render the template
        try:
            try:
                resp = chosen_handler.process_request(req)
                if resp:
                    for filter_ in reversed(self.filters):
                        resp = filter_.post_process_request(req, *resp)
                    template, content_type = resp
                    req.display(template, content_type or 'text/html')
                else:
                    for filter_ in reversed(self.filters):
                        filter_.post_process_request(req, None, None)
            except PermissionError, e:
                raise HTTPForbidden(to_unicode(e))
            except TracError, e:
                raise HTTPInternalError(e.message)
        finally:
            # Give the session a chance to persist changes
            if req.session:
                req.session.save()


def dispatch_request(environ, start_response):
    """Main entry point for the Trac web interface.
    
    @param environ: the WSGI environment dict
    @param start_response: the WSGI callback for starting the response
    """
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
            environ['PATH_INFO'] = '/'.join([''] + path_info)

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
    env = _open_environment(env_path, run_once=environ['wsgi.run_once'])

    if env.base_url:
        environ['trac.base_url'] = env.base_url

    req = Request(environ, start_response)
    try:
        db = env.get_db_cnx()
        try:
            try:
                dispatcher = RequestDispatcher(env)
                dispatcher.dispatch(req)
            except RequestDone:
                pass
            return req._response or []
        finally:
            db.close()

    except HTTPException, e:
        env.log.warn(e)
        if req.hdf:
            req.hdf['title'] = e.reason or 'Error'
            req.hdf['error'] = {
                'title': e.reason or 'Error',
                'type': 'TracError',
                'message': e.message
            }
        try:
            req.send_error(sys.exc_info(), status=e.code)
        except RequestDone:
            return []

    except Exception, e:
        env.log.exception(e)

        if req.hdf:
            req.hdf['title'] = to_unicode(e) or 'Error'
            req.hdf['error'] = {
                'title': to_unicode(e) or 'Error',
                'type': 'internal',
                'traceback': get_last_traceback()
            }
        try:
            req.send_error(sys.exc_info(), status=500)
        except RequestDone:
            return []

def send_project_index(environ, start_response, parent_dir=None,
                       env_paths=None):
    from trac.config import default_dir

    req = Request(environ, start_response)

    loadpaths = [default_dir('templates')]
    if req.environ.get('trac.env_index_template'):
        tmpl_path, template = os.path.split(req.environ['trac.env_index_template'])
        loadpaths.insert(0, tmpl_path)
    else:
        template = 'index.cs'
    req.hdf = HDFWrapper(loadpaths)

    tmpl_vars = {}
    if req.environ.get('trac.template_vars'):
        for pair in req.environ['trac.template_vars'].split(','):
            key, val = pair.split('=')
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

        req.hdf['projects'] = projects
        req.display(template)
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
