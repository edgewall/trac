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
    'about'       : ('About', 'About', 0),
    'search'      : ('Search', 'Search', 0),
    'report'      : ('Report', 'Report', 0),
    'ticket'      : ('Ticket', 'Ticket', 0),
    'browser'     : ('Browser', 'Browser', 1),
    'timeline'    : ('Timeline', 'Timeline', 1),
    'changeset'   : ('Changeset', 'Changeset', 1),
    'newticket'   : ('Ticket', 'Newticket', 0),
    }

def parse_args(path_info):
    args = {}
    if not path_info:
        return args
    match = re.search('/about(/?.*)', path_info)
    if match:
        args['mode'] = 'about'
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

def open_database():
    import db
    db_name = os.getenv('TRAC_DB')
    if not db_name:
        raise EnvironmentError, \
              'Missing environment variable "TRAC_DB". Trac ' \
              'requires this variable to a valid Trac database.'
        
    return db.Database(db_name)

def real_main():
    import sync
    import Href
    import perm
    import auth
    from util import dict_get_with_default, redirect

    path_info = os.getenv('PATH_INFO')
    remote_addr = os.getenv('REMOTE_ADDR')
    remote_user = os.getenv('REMOTE_USER')
    http_cookie = os.getenv('HTTP_COOKIE')
    http_referer = os.getenv('HTTP_REFERER')
    cgi_location = os.getenv('SCRIPT_NAME')
    
    database = open_database()
    config = database.load_config()
    
    Href.initialize(cgi_location)

    # Authenticate the user
    cookie = Cookie.SimpleCookie(http_cookie)
    if cookie.has_key('trac_auth'):
        auth_cookie = cookie['trac_auth'].value
    else:
        auth_cookie = None

    authenticator = auth.Authenticator(database, auth_cookie, remote_addr)
    if path_info == '/logout':
        authenticator.logout()
        redirect (http_referer or Href.href.wiki())
    elif remote_user and authenticator.authname == 'anonymous':
        auth_cookie = authenticator.login(remote_user, remote_addr)
        # send the cookie to the browser as a http header
        cookie = Cookie.SimpleCookie()
        cookie['trac_auth'] = auth_cookie
        cookie['trac_auth']['path'] = cgi_location
        print cookie.output()
    if path_info == '/login':
        redirect (http_referer or Href.href.wiki())

    # Parse arguments
    args = parse_args(path_info)
    _args = cgi.FieldStorage()
    for x in _args.keys():
        args[x] = _args[x].value

    # Load the selected module
    mode = dict_get_with_default(args, 'mode', 'wiki')
    module_name, constructor_name, need_svn = modules[mode]
    module = __import__(module_name, globals(),  locals(), [])
    constructor = getattr(module, constructor_name)
    module = constructor(config, args)
    module._name = mode
    module.db = database
    module.authname = authenticator.authname
    module.remote_addr = remote_addr
    module.cgi_location = cgi_location

    module.perm = perm.PermissionCache(database, authenticator.authname)
    module.perm.add_to_hdf(module.cgi.hdf)

    # Only open the subversion repository for the modules that really
    # need it. This saves us some precious time.
    if need_svn:
        from svn import util, repos, core

        core.apr_initialize()
        pool = core.svn_pool_create(None)

        repos_dir = config['general']['repository_dir']

        # Remove any trailing slash or else subversion might abort
        if not os.path.split(repos_dir)[1]:
            repos_dir = os.path.split(repos_dir)[0]
            
        rep = repos.svn_repos_open(repos_dir, pool)
        fs_ptr = repos.svn_repos_fs(rep)
        module.repos = rep
        module.fs_ptr = fs_ptr
        sync.sync(database, rep, fs_ptr, pool)
    else:
        pool = None
        
    # Let the wiki module build a dictionary of all page names
    import Wiki
    Wiki.populate_page_dict(database)
    module.pool = pool
    module.run()
    
    if pool:
        core.svn_pool_destroy(pool)
        core.apr_terminate()

def create_error_cgi():
    import neo_cgi
    import os.path
    from Href import href
    
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
    real_e = None
    real_tb = None
    # In case of an exception. First try to display a fancy error
    # message using the error.cs template. If that failes fall
    # back to a plain/text version.
    try:
        try:
            real_main()
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
            cgi.hdf.setValue('error.traceback',tb.getvalue())
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
            cgi.hdf.setValue('title', 'Oups')
            cgi.hdf.setValue('error.type', 'internal')
            cgi.hdf.setValue('error.message', str(e))
            cgi.hdf.setValue('error.traceback',tb.getvalue())
            name = os.path.join (templates_dir, 'error.cs')
            cgi.display(name)
    except Exception:
        print 'Content-Type: text/plain\r\n\r\n',
        print 'Oups...'
        print
        print 'Trac detected an internal error:'
        print
        print real_e
        print
        print real_tb.getvalue()
