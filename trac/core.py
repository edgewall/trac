# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2003, 2004, 2005 Edgewall Software
# Copyright (C) 2003, 2004, 2005 Jonas Borgström <jonas@edgewall.com>
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
from types import ListType

import Href
import perm
import auth
import authzperm
import Environment
import Session
from util import escape, TracError

from __init__ import __version__

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
            set_if_missing(args, 'id', urllib.unquote(match.group(1)))
        return args
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

def module_factory(env, db, req):
    mode = req.args.get('mode', 'wiki')
    module_name, constructor_name, need_svn = modules[mode]
    module = __import__(module_name, globals(),  locals())
    constructor = getattr(module, constructor_name)
    module = constructor()
    module._name = mode

    module.env = env
    module.log = env.log
    module.db = db
    module.perm = perm.PermissionCache(module.db, req.authname)

    # Only open the subversion repository for the modules that really
    # need it. This saves us some precious time.
    module.authzperm = None
    module.pool = None
    if need_svn:
        import sync
        module.authzperm = authzperm.AuthzPermission(env, req.authname)
        repos_dir = env.get_config('trac', 'repository_dir')
        pool, rep, fs_ptr = open_svn_repos(repos_dir)
        module.repos = rep
        module.fs_ptr = fs_ptr
        sync.sync(db, rep, fs_ptr, pool)
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

def open_svn_repos(repos_dir):
    from svn import repos, core

    core.apr_initialize()
    pool = core.svn_pool_create(None)
    # Remove any trailing slash or else subversion might abort
    if not os.path.split(repos_dir)[1]:
        repos_dir = os.path.split(repos_dir)[0]

    rep = repos.svn_repos_open(repos_dir, pool)
    fs_ptr = repos.svn_repos_fs(rep)
    return pool, rep, fs_ptr

def populate_hdf(hdf, env, req=None):
    htdocs_location = env.get_config('trac', 'htdocs_location')
    if htdocs_location[-1] != '/':
        htdocs_location += '/'
    hdf.setValue('htdocs_location', htdocs_location)
    hdf.setValue('project.name', env.get_config('project', 'name'))
    # Kludges for RSS, etc
    hdf.setValue('project.name.encoded',
                 escape(env.get_config('project', 'name')))
    hdf.setValue('project.descr', env.get_config('project', 'descr'))
    hdf.setValue('project.footer', env.get_config('project', 'footer',
                  ' Visit the Trac open source project at<br />'
                  '<a href="http://trac.edgewall.com/">http://trac.edgewall.com/</a>'))
    hdf.setValue('project.url', env.get_config('project', 'url'))
    hdf.setValue('trac.href.wiki', env.href.wiki())
    hdf.setValue('trac.href.browser', env.href.browser('/'))
    hdf.setValue('trac.href.timeline', env.href.timeline())
    hdf.setValue('trac.href.roadmap', env.href.roadmap())
    hdf.setValue('trac.href.milestone', env.href.milestone(None))
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
    hdf.setValue('header_logo.alt', escape(env.get_config('header_logo', 'alt')))
    src = env.get_config('header_logo', 'src')
    src_abs = re.match(r'https?://', src) != None
    if not src[0] == '/' and not src_abs:
        src = htdocs_location + src
    hdf.setValue('header_logo.src', src)
    hdf.setValue('header_logo.src_abs', str(src_abs))
    hdf.setValue('header_logo.width', env.get_config('header_logo', 'width'))
    hdf.setValue('header_logo.height', env.get_config('header_logo', 'height'))
    hdf.setValue('trac.href.logout', env.href.logout())
    if req:
        hdf.setValue('cgi_location', req.cgi_location)
        hdf.setValue('trac.authname', escape(req.authname))

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
    authname = None
    session = None
    _headers = None # additional headers to send

    def init_request(self):
        import neo_cgi
        # The following line is needed so that ClearSilver can be loaded when
        # we are being run in multiple interpreters under mod_python
        neo_cgi.update()
        import neo_util
        self.hdf = neo_util.HDF()
        import Cookie
        self.incookie = Cookie.SimpleCookie()
        self.outcookie = Cookie.SimpleCookie()
        self._headers = []

    def get_header(self, name):
        raise RuntimeError, 'Virtual method not implemented'

    def send_response(self, code):
        raise RuntimeError, 'Virtual method not implemented'

    def send_header(self, name, value):
        raise RuntimeError, 'Virtual method not implemented'

    def end_headers(self):
        raise RuntimeError, 'Virtual method not implemented'

    def check_modified(self, timesecs, extra=''):
        etag = 'W"%s/%d/%s"' % (self.authname, timesecs, extra)
        inm = self.get_header('If-None-Match')
        if (not inm or inm != etag):
            self._headers.append(('ETag', etag))
        else:
            self.send_response(304)
            self.end_headers()
            raise NotModifiedException()

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
        if type(cs) == type(''):
            filename = cs
            import neo_cs
            cs = neo_cs.CS(self.hdf)
            cs.parseFile(filename)
        data = cs.render()
        self.send_response(response)
        self.send_header('Cache-control', 'must-revalidate')
        self.send_header('Expires', 'Fri, 01 Jan 1999 00:00:00 GMT')
        self.send_header('Content-Type', content_type + ';charset=utf-8')
        self.send_header('Content-Length', len(data))
        for name, value in self._headers:
            self.send_header(name, value)
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

    def __init__(self, environ=os.environ, input=sys.stdin, output=sys.stdout):
        self.__environ = environ
        self.__input = input
        self.__output = output

    def init_request(self):
        Request.init_request(self)

        self.cgi_location = self.__environ.get('SCRIPT_NAME')
        self.remote_addr = self.__environ.get('REMOTE_ADDR')
        self.remote_user = self.__environ.get('REMOTE_USER')
        self.command = self.__environ.get('REQUEST_METHOD')

        host = self.__environ.get('SERVER_NAME')
        proto_port = ''
        port = int(self.__environ.get('SERVER_PORT', 0))

        if self.__environ.get('HTTPS') in ('on', '1'):
            # when you support Apache's way, you get it 60% right
            proto  = 'https'
            if port and port != 443:
               proto_port = ':%d' % port
        elif port == 443:
            proto = 'https'
        else:
           proto = 'http'
           if port and port != 80:
               proto_port = ':%d' % port

        if self.__environ.has_key('HTTP_X_FORWARDED_HOST'):
            self.base_url = '%s://%s%s' % (
                            proto,
                            self.__environ['HTTP_X_FORWARDED_HOST'],
                            self.cgi_location)
        else:
            self.base_url = '%s://%s%s%s' % (
                            proto, host, proto_port, self.cgi_location)

        self.args = TracFieldStorage(self.__input, environ=self.__environ,
                                     keep_blank_values=1)

        if self.__environ.get('HTTP_COOKIE'):
            self.incookie.load(self.__environ.get('HTTP_COOKIE'))
        if self.__environ.get('HTTP_HOST'):
            self.hdf.setValue('HTTP.Host',
                              self.__environ.get('HTTP_HOST').split(':')[0])
        if self.__environ.get('PATH_INFO'):
            self.hdf.setValue('HTTP.PathInfo',
                              self.__environ.get('PATH_INFO'))

        self.hdf.setValue('HTTP.Protocol', proto)
        if proto_port:
            self.hdf.setValue('HTTP.Port', str(port))

    def read(self, len):
        return self.__input.read(len)

    def write(self, data):
        return self.__output.write(data)

    def get_header(self, name):
        return self.__environ.get('HTTP_' + re.sub('-', '_', name.upper()))

    def send_response(self, code):
        self.write('Status: %d\r\n' % code)

    def send_header(self, name, value):
        self.write('%s: %s\r\n' % (name, value))

    def end_headers(self):
        self.write('\r\n')


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


class NotModifiedException(Exception):
    pass


class RedirectException(Exception):
    pass


def dispatch_request(path_info, req, env):

    parse_path_info(req.args, path_info)

    db = env.get_db_cnx()

    # Let the wiki module build a dictionary of all page names
    import Wiki
    Wiki.populate_page_dict(db, env)

    try:
        try:
            authenticator = auth.Authenticator(db, req)
            if path_info == '/logout':
                authenticator.logout()
                referer = req.get_header('Referer')
                if referer and referer[0:len(req.base_url)] != req.base_url:
                    # only redirect to referer if the latter is from the same
                    # instance
                    referer = None
                req.redirect(referer or env.href.wiki())
            elif req.remote_user and authenticator.authname == 'anonymous':
                authenticator.login(req)
            if path_info == '/login':
                referer = req.get_header('Referer')
                if referer and referer[0:len(req.base_url)] != req.base_url:
                    # only redirect to referer if the latter is from the same
                    # instance
                    referer = None
                req.redirect(referer or env.href.wiki())
            req.authname = authenticator.authname

            newsession = req.args.has_key('newsession')
            req.session = Session.Session(env, db, req, newsession)

            add_args_to_hdf(req.args, req.hdf)
            try:
                pool = None
                # Load the selected module
                module = module_factory(env, db, req)
                pool = module.pool
                module.run(req)
            finally:
                # We do this even if the cgi will terminate directly after. A
                # pool destruction might trigger important clean-up functions.
                if pool:
                    import svn.core
                    svn.core.svn_pool_destroy(pool)

                # Give the session a chance to persist changes
                req.session.save()

        except NotModifiedException:
            pass
        except RedirectException:
            pass

    finally:
        db.close()

def send_pretty_error(e, env, req=None):
    import traceback
    import StringIO
    tb = StringIO.StringIO()
    traceback.print_exc(file=tb)
    if not req:
        req = CGIRequest()
        req.init_request()
        req.authname = ''
    try:
        if not env:
            env = open_environment()
        env.href = Href.Href(req.cgi_location)
        populate_hdf(req.hdf, env, req)

        if isinstance(e, TracError):
            req.hdf.setValue('title', e.title or 'Error')
            req.hdf.setValue('error.title', e.title or 'Error')
            req.hdf.setValue('error.type', 'TracError')
            req.hdf.setValue('error.message', e.message)
            if e.show_traceback:
                req.hdf.setValue('error.traceback', escape(tb.getvalue()))
        elif isinstance(e, perm.PermissionError):
            req.hdf.setValue('title', 'Permission Denied')
            req.hdf.setValue('error.type', 'permission')
            req.hdf.setValue('error.action', e.action)
            req.hdf.setValue('error.message', str(e))
        else:
            req.hdf.setValue('title', 'Oops')
            req.hdf.setValue('error.type', 'internal')
            req.hdf.setValue('error.message', escape(str(e)))
            req.hdf.setValue('error.traceback', escape(tb.getvalue()))
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

    path_info = os.getenv('PATH_INFO')

    req = CGIRequest()
    req.init_request()

    env = open_environment()
    env.href = Href.Href(req.cgi_location)
    env.abs_href = Href.Href(req.base_url)

    dispatch_request(path_info, req, env)

def cgi_start():
    try:
        locale.setlocale(locale.LC_ALL, '')
        real_cgi_start()
    except Exception, e:
        send_pretty_error(e, None)
