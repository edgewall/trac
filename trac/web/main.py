# -*- coding: iso8859-1 -*-
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

import os

from trac.core import *
from trac.env import open_environment
from trac.perm import PermissionCache, PermissionError
from trac.util import escape, enum
from trac.web.api import absolute_url, Request, RequestDone, IAuthenticator, \
                         IRequestHandler
from trac.web.chrome import Chrome
from trac.web.clearsilver import HDFWrapper
from trac.web.href import Href
from trac.web.session import Session

# Environment cache for multithreaded front-ends:
try:
    import threading
except ImportError:
    has_threads = False
else:
    has_threads = True
    env_cache = {}
    env_cache_lock = threading.Lock()

def _open_environment(env_path, threaded=True):
    if not has_threads or not threaded:
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
    return env


class RequestDispatcher(Component):
    """Component responsible for dispatching requests to registered handlers."""

    authenticators = ExtensionPoint(IAuthenticator)
    handlers = ExtensionPoint(IRequestHandler)

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
        req.authname = self.authenticate(req)
        req.perm = PermissionCache(self.env, req.authname)

        chrome = Chrome(self.env)
        req.hdf = HDFWrapper(loadpaths=chrome.get_templates_dirs())
        populate_hdf(req.hdf, self.env, req)

        newsession = req.args.has_key('newsession')
        req.session = Session(self.env, req, newsession)

        # Select the component that should handle the request
        chosen_handler = None
        default_handler = None
        if not req.path_info or req.path_info == '/':
            default_handler = self.config.get('trac', 'default_handler')
        for handler in self.handlers:
            if handler.match_request(req) or \
               handler.__class__.__name__ == default_handler:
                chosen_handler = handler
                break

        chrome.populate_hdf(req, chosen_handler)

        if not chosen_handler:
            # FIXME: Should return '404 Not Found' to the client
            raise TracError, 'No handler matched request to %s' % req.path_info

        try:
            resp = chosen_handler.process_request(req)
            if resp:
                template, content_type = resp
                if not content_type:
                    content_type = 'text/html'

                req.display(template, content_type or 'text/html')
        finally:
            # Give the session a chance to persist changes
            req.session.save()


def dispatch_request(path_info, req, env):
    """Main entry point for the Trac web interface."""

    # Re-parse the configuration file if it changed since the last the time it
    # was parsed
    env.config.parse_if_needed()

    base_url = env.config.get('trac', 'base_url')
    if not base_url:
        base_url = absolute_url(req)
    req.base_url = base_url
    req.path_info = path_info

    env.href = Href(req.cgi_location)
    env.abs_href = Href(req.base_url)

    db = env.get_db_cnx()
    try:
        try:
            dispatcher = RequestDispatcher(env)
            dispatcher.dispatch(req)
        except RequestDone:
            pass
    finally:
        db.close()

def populate_hdf(hdf, env, req=None):
    """Populate the HDF data set with various information, such as common URLs,
    project information and request-related information.
    """
    from trac import __version__
    from time import gmtime, localtime, strftime
    hdf['trac'] = {
        'version': __version__,
        'time': strftime('%c', localtime()),
        'time.gmt': strftime('%a, %d %b %Y %H:%M:%S GMT', gmtime())
    }
    hdf['trac.href'] = {
        'wiki': env.href.wiki(),
        'browser': env.href.browser('/'),
        'timeline': env.href.timeline(),
        'roadmap': env.href.roadmap(),
        'milestone': env.href.milestone(None),
        'report': env.href.report(),
        'query': env.href.query(),
        'newticket': env.href.newticket(),
        'search': env.href.search(),
        'about': env.href.about(),
        'about_config': env.href.about('config'),
        'login': env.href.login(),
        'logout': env.href.logout(),
        'settings': env.href.settings(),
        'homepage': 'http://trac.edgewall.com/'
    }

    hdf['project'] = {
        'name': env.config.get('project', 'name'),
        'name.encoded': escape(env.config.get('project', 'name')),
        'descr': env.config.get('project', 'descr'),
        'footer': env.config.get('project', 'footer',
                 'Visit the Trac open source project at<br />'
                 '<a href="http://trac.edgewall.com/">'
                 'http://trac.edgewall.com/</a>'),
        'url': env.config.get('project', 'url')
    }

    if req:
        hdf['base_url'] = req.base_url
        hdf['base_host'] = req.base_url[:req.base_url.rfind(req.cgi_location)]
        hdf['cgi_location'] = req.cgi_location
        hdf['trac.authname'] = escape(req.authname)

        for action in req.perm.permissions():
            req.hdf['trac.acl.' + action] = True

        for arg in [k for k in req.args.keys() if k]:
            if isinstance(req.args[arg], (list, tuple)):
                hdf['args.%s' % arg] = [v.value for v in req.args[arg]]
            else:
                hdf['args.%s' % arg] = req.args[arg].value

def send_pretty_error(e, env, req=None):
    """Send a "pretty" HTML error page to the client."""
    import traceback
    import StringIO
    tb = StringIO.StringIO()
    traceback.print_exc(file=tb)
    if not req:
        from trac.web.cgi_frontend import CGIRequest
        from trac.web.clearsilver import HDFWrapper
        req = CGIRequest()
        req.authname = ''
        req.hdf = HDFWrapper()
    try:
        if not env:
            from trac.env import open_environment
            env = open_environment()
            env.href = Href(req.cgi_location)
        if env and env.log:
            env.log.exception(e)
        populate_hdf(req.hdf, env, req)

        if isinstance(e, TracError):
            req.hdf['title'] = e.title or 'Error'
            req.hdf['error.title'] = e.title or 'Error'
            req.hdf['error.type'] = 'TracError'
            req.hdf['error.message'] = e.message
            if e.show_traceback:
                req.hdf['error.traceback'] = escape(tb.getvalue())
            req.display('error.cs', response=500)

        elif isinstance(e, PermissionError):
            req.hdf['title'] = 'Permission Denied'
            req.hdf['error.type'] = 'permission'
            req.hdf['error.action'] = e.action
            req.hdf['error.message'] = e
            req.display('error.cs', response=403)

        else:
            req.hdf['title'] = 'Oops'
            req.hdf['error.type'] = 'internal'
            req.hdf['error.message'] = escape(str(e))
            req.hdf['error.traceback'] = escape(tb.getvalue())
            req.display('error.cs', response=500)

    except RequestDone:
        pass
    except Exception, e2:
        if env and env.log:
            env.log.error('Failed to render pretty error page: %s', e2,
                          exc_info=True)
        req.send_response(500)
        req.send_header('Content-Type', 'text/plain')
        req.end_headers()
        req.write('Oops...\n\nTrac detected an internal error:\n\n')
        req.write(str(e))
        req.write('\n')
        req.write(tb.getvalue())

def send_project_index(req, options, env_paths=None):
    from trac.web.clearsilver import HDFWrapper

    if 'TRAC_ENV_INDEX_TEMPLATE' in options:
        tmpl_path, template = os.path.split(options['TRAC_ENV_INDEX_TEMPLATE'])

        from trac.config import default_dir
        req.hdf = HDFWrapper(loadpaths=[default_dir('templates'), tmpl_path])

        tmpl_vars = {}
        if 'TRAC_TEMPLATE_VARS' in options:
            for pair in options['TRAC_TEMPLATE_VARS'].split(','):
                key, val = pair.split('=')
                req.hdf[key] = val
    else:
        req.hdf = HDFWrapper()
        template = req.hdf.parse('''<html>
<head><title>Available Projects</title></head>
<body><h1>Available Projects</h1><ul><?cs
 each:project = projects ?><li><?cs
  if:project.href ?>
   <a href="<?cs var:project.href ?>" title="<?cs var:project.description ?>">
    <?cs var:project.name ?></a><?cs
  else ?>
   <small><?cs var:project.name ?>: <em>Error</em> <br />
   (<?cs var:project.description ?>)</small><?cs
  /if ?>
  </li><?cs
 /each ?></ul></body>
</html>''')

    if not env_paths and 'TRAC_ENV_PARENT_DIR' in options:
        dir = options['TRAC_ENV_PARENT_DIR']
        env_paths = [os.path.join(dir, f) for f in os.listdir(dir)]

    href = Href(req.idx_location)
    try:
        projects = []
        for env_path in env_paths:
            if not os.path.isdir(env_path):
                continue
            env_dir, project = os.path.split(env_path)
            try:
                env = _open_environment(env_path)
                proj = {
                    'name': env.config.get('project', 'name'),
                    'description': env.config.get('project', 'descr'),
                    'href': href(project)
                }
            except Exception, e:
                proj = {'name': project, 'description': str(e)}
            projects.append(proj)
        projects.sort(lambda x, y: cmp(x['name'], y['name']))
        req.hdf['projects'] = projects

        # TODO maybe this should be 404 if index wasn't specifically requested
        req.display(template, response=200)
    except RequestDone:
        pass


def get_environment(req, options, threaded=True):
    if 'TRAC_ENV' in options:
        env_path = options['TRAC_ENV']
    elif 'TRAC_ENV_PARENT_DIR' in options:
        env_parent_dir = options['TRAC_ENV_PARENT_DIR']
        env_name = req.cgi_location.split('/')[-1]
        env_path = os.path.join(env_parent_dir, env_name)
        if not len(env_name) or not os.path.exists(env_path):
            return None
    else:
        raise TracError, \
              'The environment options "TRAC_ENV" or "TRAC_ENV_PARENT_DIR" ' \
              'or the mod_python options "TracEnv" or "TracEnvParentDir" ' \
              'are missing.  Trac requires one of these options to locate ' \
              'the Trac environment(s).'

    return _open_environment(env_path, threaded)
