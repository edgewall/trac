# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2003, 2004 Edgewall Software
# Copyright (C) 2003, 2004 Jonas Borgström <jonas@edgewall.com>
#
# Trac is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version.
#
# Trac is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#
# Author: Jonas Borgström <jonas@edgewall.com>

import os
import re
import sys
import cgi
import time
import locale
import urllib
import warnings
import util
from types import ListType

import Href
import perm
import auth
import authzperm
import Environment
import Session

from util import sql_to_hdf, TracError
from __init__ import __version__

warnings.filterwarnings('ignore', 'DB-API extension cursor.next() used')

modules = {
#    name           (module_name, class_name, requires_svn)
    'log'         : ('Log', 'Log', 1),
    'file'        : ('File', 'File', 1),
    'wiki'        : ('Wiki', 'WikiModule', 0),
    'about_trac'  : ('About', 'About', 0),
    'search'      : ('Search', 'Search', 0),
    'report'      : ('Report', 'Report', 0),
    'ticket'      : ('Ticket', 'TicketModule', 0),
    'browser'     : ('Browser', 'Browser', 1),
    'timeline'    : ('Timeline', 'Timeline', 1),
    'changeset'   : ('Changeset', 'Changeset', 1),
    'newticket'   : ('Ticket', 'NewticketModule', 0),
    'query'       : ('Query', 'QueryModule', 0),
    'attachment'  : ('File', 'Attachment', 0),
    'roadmap'     : ('Roadmap', 'Roadmap', 0),
    'settings'    : ('Settings', 'Settings', 0),
    'milestone'   : ('Milestone', 'Milestone', 0)
    }

class TracFieldStorage(cgi.FieldStorage):
    """
    FieldStorage class with a few more functions to make it behave a bit
    more like a dictionary
    """
    get = cgi.FieldStorage.getvalue

    def __setitem__(self, name, value):
        if self.has_key(name):
            del self[name]
        self.list.append(cgi.MiniFieldStorage(name, value))

    def __delitem__(self, name):
        if not self.has_key(name):
            raise KeyError(name)
        self.list = filter(lambda x, name=name: x.name != name, self.list)


def parse_path_info(args, path_info):
    def set_if_missing(fs, name, value):
        if value and not fs.has_key(name):
            fs.list.append(cgi.MiniFieldStorage(name, value))

    if not path_info or path_info in ['/login', '/logout']:
        return args
    match = re.search('^/(about_trac|wiki)(?:/(.*))?', path_info)
    if match:
        set_if_missing(args, 'mode', match.group(1))
        if match.group(2):
            set_if_missing(args, 'page', match.group(2))
        return args
    match = re.search('^/(newticket|timeline|search|roadmap|settings|query)/?', path_info)
    if match:
        set_if_missing(args, 'mode', match.group(1))
        return args
    match = re.search('^/(ticket|report)(?:/([0-9]+)/*)?', path_info)
    if match:
        set_if_missing(args, 'mode', match.group(1))
        if match.group(2):
            set_if_missing(args, 'id', match.group(2))
        return args
    match = re.search('^/(browser|log|file)(?:(/.*))?', path_info)
    if match:
        set_if_missing(args, 'mode', match.group(1))
        if match.group(2):
            set_if_missing(args, 'path', match.group(2))
        return args
    match = re.search('^/changeset/([0-9]+)/?', path_info)
    if match:
        set_if_missing(args, 'mode', 'changeset')
        set_if_missing(args, 'rev', match.group(1))
        return args
    match = re.search('^/attachment/([a-zA-Z_]+)/([^/]+)(?:/(.*)/?)?', path_info)
    if match:
        set_if_missing(args, 'mode', 'attachment')
        set_if_missing(args, 'type', match.group(1))
        set_if_missing(args, 'id', urllib.unquote(match.group(2)))
        set_if_missing(args, 'filename', match.group(3))
        return args
    match = re.search('^/milestone(?:/([^\?]+))?(?:/(.*)/?)?', path_info)
    if match:
        set_if_missing(args, 'mode', 'milestone')
        if match.group(1):
            set_if_missing(args, 'id', urllib.unquote_plus(match.group(1)))
        return args
    return args

def parse_args(command, path_info, query_string,
               fp=None, env = None, _headers=None):
    if not env:
        env = {'REQUEST_METHOD': command, 'QUERY_STRING': query_string}
    if command in ['GET', 'HEAD']:
        _headers = None
    args = TracFieldStorage(fp, environ=env, headers=_headers, keep_blank_values=1)
    parse_path_info(args, path_info)
    return args

def add_args_to_hdf(args, hdf):
    for key in args.keys():
        if not key:
            continue
        if type(args[key]) is not ListType:
            hdf.setValue('args.%s' % key, str(args[key].value))
        else:
            for i in range(len(args[key])):
                hdf.setValue('args.%s.%d' % (key, i), str(args[key][i].value))

def module_factory(args, env, db, req):
    mode = args.get('mode', 'wiki')
    module_name, constructor_name, need_svn = modules[mode]
    module = __import__(module_name, globals(),  locals())
    constructor = getattr(module, constructor_name)
    module = constructor()
    module.pool = None
    module.args = args
    module.env = env
    module.log = env.log
    module.req = req
    module._name = mode
    module.db = db
    module.perm = perm.PermissionCache(module.db, req.authname)
    module.perm.add_to_hdf(req.hdf)
    module.authzperm = None

    # Only open the subversion repository for the modules that really
    # need it. This saves us some precious time.
    if need_svn:
        import sync
        module.authzperm = authzperm.AuthzPermission(env,req.authname)
        repos_dir = env.get_config('trac', 'repository_dir')
        pool, rep, fs_ptr = open_svn_repos(repos_dir)
        module.repos = rep
        module.fs_ptr = fs_ptr
        sync.sync(module.db, rep, fs_ptr, pool)
        module.pool = pool
    return module

def open_environment():
    env_path = os.getenv('TRAC_ENV')
    if not env_path:
        raise EnvironmentError, \
              'Missing environment variable "TRAC_ENV". Trac ' \
              'requires this variable to point to a valid Trac Environment.'

    env = Environment.Environment(env_path)
    version = env.get_version()
    if version < Environment.db_version:
        raise TracError('The Trac Environment needs to be upgraded. '
                        'Run "trac-admin %s upgrade"' % env_path)
    elif version > Environment.db_version:
        raise TracError('Unknown Trac Environment version (%d).' % version)
    return env

class RedirectException(Exception):
    pass

def populate_hdf(hdf, env, db, req):
    sql_to_hdf(db, "SELECT name FROM enum WHERE type='priority' "
               "ORDER BY value", hdf, 'enums.priority')
    sql_to_hdf(db, "SELECT name FROM enum WHERE type='severity' "
               "ORDER BY value", hdf, 'enums.severity')

    htdocs_location = env.get_config('trac', 'htdocs_location')
    if htdocs_location[-1] != '/':
        htdocs_location += '/'
    hdf.setValue('htdocs_location', htdocs_location)
    hdf.setValue('project.name', env.get_config('project', 'name'))
    # Kludges for RSS, etc
    hdf.setValue('project.name.encoded',
                 util.escape(env.get_config('project', 'name')))
    hdf.setValue('project.descr', env.get_config('project', 'descr'))
    hdf.setValue('project.footer', env.get_config('project', 'footer',
                  ' Visit the Trac open source project at<br />'
                  '<a href="http://trac.edgewall.com/">http://trac.edgewall.com/</a>'))
    hdf.setValue('project.url', env.get_config('project', 'url'))
    hdf.setValue('trac.href.wiki', env.href.wiki())
    hdf.setValue('trac.href.browser', env.href.browser('/'))
    hdf.setValue('trac.href.timeline', env.href.timeline())
    hdf.setValue('trac.href.roadmap', env.href.roadmap())
    hdf.setValue('trac.href.report', env.href.report())
    hdf.setValue('trac.href.query', env.href.query())
    hdf.setValue('trac.href.newticket', env.href.newticket())
    hdf.setValue('trac.href.search', env.href.search())
    hdf.setValue('trac.href.about', env.href.about())
    hdf.setValue('trac.href.about_config', env.href.about('config'))
    hdf.setValue('trac.href.login', env.href.login())
    hdf.setValue('trac.href.logout', env.href.logout())
    hdf.setValue('trac.href.settings', env.href.settings())
    hdf.setValue('trac.href.homepage', 'http://trac.edgewall.com/')
    hdf.setValue('trac.version', __version__)
    hdf.setValue('trac.time', time.strftime('%c', time.localtime()))
    hdf.setValue('trac.time.gmt', time.strftime('%a, %d %b %Y %H:%M:%S GMT',
                                                time.gmtime()))

    hdf.setValue('header_logo.link', env.get_config('header_logo', 'link'))
    hdf.setValue('header_logo.alt', env.get_config('header_logo', 'alt'))
    src = env.get_config('header_logo', 'src')
    src_abs = src[:7] == 'http://' and 1 or 0
    if not src[0] == '/' and not src_abs:
        src = htdocs_location + src
    hdf.setValue('header_logo.src', src)
    hdf.setValue('header_logo.src_abs', str(src_abs))
    hdf.setValue('header_logo.width', env.get_config('header_logo', 'width'))
    hdf.setValue('header_logo.height', env.get_config('header_logo', 'height'))
    hdf.setValue('trac.href.logout', env.href.logout())
    if req:
        hdf.setValue('cgi_location', req.cgi_location)
        hdf.setValue('trac.authname', util.escape(req.authname))

    templates_dir = env.get_config('trac', 'templates_dir')
    hdf.setValue('hdf.loadpaths.0', env.get_templates_dir())
    hdf.setValue('hdf.loadpaths.1', templates_dir)


class Request:
    """
    This class is used to abstract the interface between different frontends.

    Trac modules must use this interface. It is not allowed to have
    frontend (cgi, tracd, mod_python) specific code in the modules.
    """

    command = None
    hdf = None
    session = None

    def init_request(self):
        import neo_cgi
        # The following line is needed so that ClearSilver can be loaded when
        # we are being run in multiple interpreters under mod_python
        neo_cgi.update()
        import neo_cs
        import neo_util
        import Cookie
        self.hdf = neo_util.HDF()
        self.incookie = Cookie.SimpleCookie()
        self.outcookie = Cookie.SimpleCookie()

    def get_header(self, name):
        raise RuntimeError, 'Virtual method not implemented'

    def send_response(self, code):
        raise RuntimeError, 'Virtual method not implemented'

    def send_header(self, name, value):
        raise RuntimeError, 'Virtual method not implemented'

    def end_headers(self):
        raise RuntimeError, 'Virtual method not implemented'

    def redirect(self, url):
        self.send_response(302)
        self.send_header('Location', url)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Cache-control', 'no-cache')
        self.send_header('Expires', 'Fri, 01 Jan 1999 00:00:00 GMT')
        cookies = self.outcookie.output(header='')
        for cookie in cookies.splitlines():
            self.send_header('Set-Cookie', cookie.strip())
        self.end_headers()
        self.write('Redirecting...')
        raise RedirectException()

    def display(self, cs, content_type='text/html', response=200):
        import neo_cgi
        # The following line is needed so that ClearSilver can be loaded when
        # we are being run in multiple interpreters under mod_python
        neo_cgi.update()
        import neo_cs
        import neo_util
        if type(cs) == type(''):
            filename = cs
            cs = neo_cs.CS(self.hdf)
            cs.parseFile(filename)
        data = cs.render()
        self.send_response(response)
        self.send_header('Cache-control', 'no-cache')
        self.send_header('Expires', 'Fri, 01 Jan 1999 00:00:00 GMT')
        self.send_header('Content-Type', content_type + ';charset=utf-8')
        self.send_header('Content-Length', len(data))
        cookies = self.outcookie.output(header='')
        for cookie in cookies.splitlines():
            self.send_header('Set-Cookie', cookie.strip())
        self.end_headers()
        if self.command != 'HEAD':
            self.write(data)

    def read(self, len):
        assert 0

    def write(self, data):
        assert 0

class CGIRequest(Request):
    def init_request(self):
        Request.init_request(self)
        self.cgi_location = os.getenv('SCRIPT_NAME')
        self.remote_addr = os.getenv('REMOTE_ADDR')
        self.remote_user = os.getenv('REMOTE_USER')
        self.command = os.getenv('REQUEST_METHOD')
        host = os.getenv('SERVER_NAME')
        proto_port = ''
        port = int(os.environ.get('SERVER_PORT', 80))
        if port == 443:
           proto = 'https'
        else:
           proto = 'http'
           if port != 80:
               proto_port = ':%d' % port

        if os.getenv('HTTP_X_FORWARDED_HOST'):
            self.base_url = '%s://%s%s/' % (proto,
                                            os.getenv('HTTP_X_FORWARDED_HOST'),
                                            self.cgi_location)
        else:
            self.base_url = '%s://%s%s%s' % (proto, host, proto_port, self.cgi_location)

        if os.getenv('HTTP_COOKIE'):
            self.incookie.load(os.getenv('HTTP_COOKIE'))
        if os.getenv('HTTP_HOST'):
            self.hdf.setValue('HTTP.Host', os.getenv('HTTP_HOST'))
        if os.getenv('PATH_INFO'):
            self.hdf.setValue('HTTP.PathInfo', os.getenv('PATH_INFO'))

        self.hdf.setValue('HTTP.Protocol', proto)
        if proto_port:
            self.hdf.setValue('HTTP.Port', str(port))

    def read(self, len):
        return sys.stdin.read(len)

    def write(self, data):
        return sys.stdout.write(data)

    def get_header(self, name):
        return os.getenv('HTTP_' + re.sub('-', '_', name.upper()))

    def send_response(self, code):
        self.write('Status: %d\r\n' % code)

    def send_header(self, name, value):
        self.write('%s: %s\r\n' % (name, value))
        pass

    def end_headers(self):
        self.write('\r\n')

def dispatch_request(path_info, args, req, env, database=None):
    import Wiki

    if not database:
        database = env.get_db_cnx()

    # Let the wiki module build a dictionary of all page names
    Wiki.populate_page_dict(database, env)

    authenticator = auth.Authenticator(database, req)
    if path_info == '/logout':
        authenticator.logout()
        referer = req.get_header('Referer')
        if referer[0:len(req.base_url)] != req.base_url:
            # only redirect to referer if the latter is from the same instance
            referer = None
        try:
            req.redirect(referer or env.href.wiki())
        except RedirectException:
            pass
    elif req.remote_user and authenticator.authname == 'anonymous':
        auth_cookie = authenticator.login(req)
    if path_info == '/login':
        referer = req.get_header('Referer')
        if referer[0:len(req.base_url)] != req.base_url:
            # only redirect to referer if the latter is from the same instance
            referer = None
        try:
            req.redirect(referer or env.href.wiki())
        except RedirectException:
            pass
    req.authname = authenticator.authname

    newsession = args.has_key('newsession') and args['newsession']
    req.session = Session.Session(env, req, newsession)

    add_args_to_hdf(args, req.hdf)
    try:
        pool = None
        # Load the selected module
        module = module_factory(args, env, database, req)
        pool = module.pool
        module.run()
    finally:
        # We do this even if the cgi will terminate directly after. A pool
        # destruction might trigger important clean-up functions.
        if pool:
            import svn.core
            svn.core.svn_pool_destroy(pool)

def open_svn_repos(repos_dir):
    from svn import util, repos, core

    core.apr_initialize()
    pool = core.svn_pool_create(None)
    # Remove any trailing slash or else subversion might abort
    if not os.path.split(repos_dir)[1]:
        repos_dir = os.path.split(repos_dir)[0]

    rep = repos.svn_repos_open(repos_dir, pool)
    fs_ptr = repos.svn_repos_fs(rep)
    return pool, rep, fs_ptr

def send_pretty_error(e, env, req=None):
    import util
    import Href
    import os.path
    import traceback
    import StringIO
    tb = StringIO.StringIO()
    traceback.print_exc(file=tb)
    if not req:
        req = CGIRequest()
        req.authname = ''
        req.init_request()
    try:
        if not env:
            env = open_environment()
        env.href = Href.Href(req.cgi_location)
        cnx = env.get_db_cnx()
        populate_hdf(req.hdf, env, cnx, req)

        if isinstance(e, util.TracError):
            req.hdf.setValue('title', e.title or 'Error')
            req.hdf.setValue('error.title', e.title or 'Error')
            req.hdf.setValue('error.type', 'TracError')
            req.hdf.setValue('error.message', e.message)
            if e.show_traceback:
                req.hdf.setValue('error.traceback', util.escape(tb.getvalue()))
        elif isinstance(e, perm.PermissionError):
            req.hdf.setValue('title', 'Permission Denied')
            req.hdf.setValue('error.type', 'permission')
            req.hdf.setValue('error.action', e.action)
            req.hdf.setValue('error.message', str(e))
        else:
            req.hdf.setValue('title', 'Oops')
            req.hdf.setValue('error.type', 'internal')
            req.hdf.setValue('error.message', util.escape(str(e)))
            req.hdf.setValue('error.traceback', util.escape(tb.getvalue()))
        req.display('error.cs', response=500)
    except Exception:
        req.send_response(500)
        req.send_header('Content-Type', 'text/plain')
        req.end_headers()
        req.write('Oops...\n\nTrac detected an internal error:\n\n')
        req.write(str(e))
        req.write('\n')
        req.write(tb.getvalue())
    if env and env.log != None:
        env.log.error(str(e))
        env.log.error(tb.getvalue())

def real_cgi_start():

    env = open_environment()

    req = CGIRequest()
    req.init_request()

    env.href = Href.Href(req.cgi_location)
    env.abs_href = Href.Href(req.base_url)

    # Parse arguments
    path_info = os.getenv('PATH_INFO')
    args = parse_args(req.command,
                      path_info, os.getenv('QUERY_STRING'),
                      sys.stdin, os.environ)
    dispatch_request(path_info, args, req, env)

def cgi_start():
    try:
        locale.setlocale(locale.LC_ALL, '')
        real_cgi_start()
    except Exception, e:
        send_pretty_error(e, None)
