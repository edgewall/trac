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
import Cookie
import warnings

import perm

warnings.filterwarnings('ignore', 'DB-API extension cursor.next() used')

modules = {
#  name module class need_db need_svn    
    'log'         : ('Log', 'Log', 1),
    'file'        : ('File', 'File', 1),
    'wiki'        : ('Wiki', 'Wiki', 0),
    'about_trac'  : ('About', 'About', 0),
    'search'      : ('Search', 'Search', 0),
    'report'      : ('Report', 'Report', 0),
    'ticket'      : ('Ticket', 'Ticket', 0),
    'browser'     : ('Browser', 'Browser', 1),
    'timeline'    : ('Timeline', 'Timeline', 1),
    'changeset'   : ('Changeset', 'Changeset', 1),
    'newticket'   : ('Ticket', 'Newticket', 0),
    }

def parse_path_info(path_info):
    args = {}
    if not path_info:
        return args
    match = re.search('/about_trac(/?.*)', path_info)
    if match:
        args['mode'] = 'about_trac'
        if len(match.group(1)) > 0:
            args['page'] = match.group(1)
        return args
    if re.search('/newticket/?', path_info):
        args['mode'] = 'newticket'
        return args
    if re.search('/timeline/?', path_info):
        args['mode'] = 'timeline'
        return args
    if re.search('/search/?', path_info):
        args['mode'] = 'search'
        return args
    match = re.search('/wiki/(.*[^/])/?', path_info)
    if match:
        args['mode'] = 'wiki'
        if len(match.group(1)) > 0:
            args['page'] = match.group(1)
        return args
    match = re.search('/ticket/([0-9]+)/?', path_info)
    if match:
        args['mode'] = 'ticket'
        args['id'] = match.group(1)
        return args
    match = re.search('/report/([0-9]*)/?', path_info)
    if match:
        args['mode'] = 'report'
        if len(match.group(1)) > 0:
            args['id'] = match.group(1)
        return args
    match = re.search('/browser(/?.*)', path_info)
    if match:
        args['mode'] = 'browser'
        if len(match.group(1)) > 0:
            args['path'] = match.group(1)
        return args
    match = re.search('/log/(.+)', path_info)
    if match:
        args['mode'] = 'log'
        args['path'] = match.group(1)
        return args
    match = re.search('/file/(.+)/?', path_info)
    if match:
        args['mode'] = 'file'
        args['path'] = match.group(1)
        return args
    match = re.search('/changeset/([0-9]+)/?', path_info)
    if match:
        args['mode'] = 'changeset'
        args['rev'] = match.group(1)
        return args
    return args

def parse_args(command, path_info, query_string,
               fp=None, env = None, _headers=None):
    args = parse_path_info(path_info)
    if not env:
        env = {'REQUEST_METHOD': command, 'QUERY_STRING': query_string}
    if command == 'GET':
        _headers = None
    fs = cgi.FieldStorage(fp, environ=env, headers=_headers)
    for x in fs.keys():
        argv = fs[x]
        if type(argv) == list:
            argv = argv[0]
        args[x] = argv.value.replace('\r','')
    return args

def module_factory(args, db, config, req, authname):
    mode = args.get('mode', 'wiki')
    module_name, constructor_name, need_svn = modules[mode]
    module = __import__(module_name,
                        globals(),  locals())
    constructor = getattr(module, constructor_name)
    module = constructor(config, args)
    module.req = req
    module._name = mode
    module.db = db
    module.authname = authname
    module.perm = perm.PermissionCache(db, authname)
    module.perm.add_to_hdf(req.hdf)
    # Only open the subversion repository for the modules that really
    # need it. This saves us some precious time.
    if need_svn:
        import sync
        repos_dir = config['general']['repository_dir']
        pool, rep, fs_ptr = open_svn_repos(repos_dir)
        module.repos = rep
        module.fs_ptr = fs_ptr
        sync.sync(db, rep, fs_ptr, pool)
        module.pool = pool
    else:
        module.pool = None
    return module

def open_database():
    import db
    db_name = os.getenv('TRAC_DB')
    if not db_name:
        raise EnvironmentError, \
              'Missing environment variable "TRAC_DB". Trac ' \
              'requires this variable to a valid Trac database.'
        
    return db.Database(db_name)

class RedirectException(Exception):
    pass

class Request:
    """
    This class is used to abstract the interface between different frontends.

    Trac modules must use this interface. It is not allowed to have
    frontend (cgi, tracd, mod_python) specific code in the modules.
    """
    def init_request(self):
        import neo_cgi
        import neo_cs
        import neo_util
        self.hdf = neo_util.HDF()
        
    def redirect(self, url):
        self.send_response(302)
        self.send_header('Location', url)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.write('Redirecting...')
        raise RedirectException()

    def display(self, cs, content_type='text/html'):
        import neo_cgi
        import neo_cs
        import neo_util
        if type(cs) == type(''):
            filename = cs
            cs = neo_cs.CS(self.hdf)
            cs.parseFile(filename)
        data = cs.render()
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', len(data))
        self.end_headers()
        self.write(data)

    def read(self, len):
        assert 0
    
    def write(self, data):
        assert 0

class CGIRequest(Request):
    def read(self, len):
        return sys.stdin.read(len)
    
    def write(self, data):
        return sys.stdout.write(data)

    def send_response(self, code):
        pass
    
    def send_header(self, name, value):
        self.write('%s: %s\r\n' % (name, value))
        pass
    
    def end_headers(self):
        self.write('\r\n')

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

def real_main():
    import Href
    import perm
    import auth

    # We need this to be global to be able to use it later
    # in the exception handler if something goes wrong.
    global href

    path_info = os.getenv('PATH_INFO')
    remote_addr = os.getenv('REMOTE_ADDR')
    remote_user = os.getenv('REMOTE_USER')
    http_cookie = os.getenv('HTTP_COOKIE')
    http_referer = os.getenv('HTTP_REFERER')
    cgi_location = os.getenv('SCRIPT_NAME')
    
    database = open_database()
    config = database.load_config()

    # Let the wiki module build a dictionary of all page names
    import Wiki
    Wiki.populate_page_dict(database)
    
    req = CGIRequest()
    req.init_request()

    href = Href.Href(cgi_location)

    # Authenticate the user
    cookie = Cookie.SimpleCookie(http_cookie)

    if cookie.has_key('trac_auth'):
        auth_cookie = cookie['trac_auth'].value
    else:
        auth_cookie = None

    authenticator = auth.Authenticator(database, auth_cookie, remote_addr)
    if path_info == '/logout':
        authenticator.logout()
        try:
            req.redirect (http_referer or href.wiki())
        except RedirectException:
            pass
    elif remote_user and authenticator.authname == 'anonymous':
        auth_cookie = authenticator.login(remote_user, remote_addr)
        # send the cookie to the browser as a http header
        cookie = Cookie.SimpleCookie()
        cookie['trac_auth'] = auth_cookie
        cookie['trac_auth']['path'] = cgi_location
        print cookie.output()
    if path_info == '/login':
        try:
            req.redirect (http_referer or href.wiki())
        except RedirectException:
            pass

    # Parse arguments
    args = parse_args(os.getenv('REQUEST_METHOD'),
                      path_info, os.getenv('QUERY_STRING'),
                      sys.stdin, os.environ)

    # Load the selected module
    module = module_factory(args, database, config, req,
                            authenticator.authname)
    module.href = href
    module.remote_addr = remote_addr
    module.cgi_location = cgi_location
        
    module.run()
    # We do this even if the cgi will terminate directly after. A pool
    # destruction might trigger important clean-up functions.
    if module.pool:
        import svn.core
        svn.core.svn_pool_destroy(module.pool)


def create_error_cgi():
    import neo_cgi
    import os.path
    global href
    
    database = open_database()
    cursor = database.cursor()
    cursor.execute('SELECT value FROM config WHERE section=%s '
                   'AND name=%s', 'general', 'templates_dir')
    row = cursor.fetchone()
    templates_dir = row[0]
    cursor.execute('SELECT value FROM config WHERE section=%s '
                   'AND name=%s', 'general', 'htdocs_location')
    row = cursor.fetchone()
    htdocs_location = row[0]
    cgi = neo_cgi.CGI()
    cgi.hdf.setValue('hdf.loadpaths.0', templates_dir)
    cgi.hdf.setValue('htdocs_location', htdocs_location)
    cgi.hdf.setValue('trac.href.wiki', href.wiki())
    cgi.hdf.setValue('trac.href.browser', href.browser('/'))
    cgi.hdf.setValue('trac.href.timeline', href.timeline())
    cgi.hdf.setValue('trac.href.report', href.report())
    cgi.hdf.setValue('trac.href.newticket', href.newticket())
    cgi.hdf.setValue('trac.href.search', href.search())
    cgi.hdf.setValue('trac.href.about', href.about())
    cgi.hdf.setValue('trac.href.about_config', href.about('config/'))
    cgi.hdf.setValue('trac.href.login', href.login())
    cgi.hdf.setValue('trac.href.logout', href.logout())
    cgi.hdf.setValue('trac.href.homepage', 'http://trac.edgewall.com/')
    return cgi, templates_dir

def main():
    import util
    real_e = None
    real_tb = None
    # In case of an exception. First try to display a fancy error
    # message using the error.cs template. If that failes fall
    # back to a plain/text version.
    try:
        try:
            real_main()
        except util.TracError, e:
            import traceback
            import StringIO
            tb = StringIO.StringIO()
            traceback.print_exc(file=tb)
            real_e = e
            real_tb = tb
            cgi, templates_dir = create_error_cgi()
            cgi.hdf.setValue('title', e.title or 'Error')
            cgi.hdf.setValue('error.title', e.title or 'Error')
            cgi.hdf.setValue('error.type', 'TracError')
            cgi.hdf.setValue('error.message', e.message)
            if e.show_traceback:
                cgi.hdf.setValue('error.traceback',tb.getvalue())
            name = os.path.join (templates_dir, 'error.cs')
            cgi.display(name)
        except perm.PermissionError, e:
            import traceback
            import StringIO
            tb = StringIO.StringIO()
            traceback.print_exc(file=tb)
            real_e = e
            real_tb = tb
            cgi, templates_dir = create_error_cgi()
            cgi.hdf.setValue('title', 'Permission Denied')
            cgi.hdf.setValue('error.type', 'permission')
            cgi.hdf.setValue('error.action', e.action)
            cgi.hdf.setValue('error.message', str(e))
            name = os.path.join (templates_dir, 'error.cs')
            cgi.display(name)
        except Exception, e:
            import traceback
            import StringIO
            tb = StringIO.StringIO()
            traceback.print_exc(file=tb)
            real_e = e
            real_tb = tb
            cgi, templates_dir = create_error_cgi()
            cgi.hdf.setValue('title', 'Oops')
            cgi.hdf.setValue('error.type', 'internal')
            cgi.hdf.setValue('error.message', str(e))
            cgi.hdf.setValue('error.traceback',tb.getvalue())
            name = os.path.join (templates_dir, 'error.cs')
            cgi.display(name)
    except Exception:
        print 'Content-Type: text/plain\r\n\r\n',
        print 'Oops...'
        print
        print 'Trac detected an internal error:'
        print
        print real_e
        print
        print real_tb.getvalue()
