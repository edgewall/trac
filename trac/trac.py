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
import warnings
from util import dict_get_with_default, redirect
from svn import util, repos, core
import Href

warnings.filterwarnings('ignore', 'DB-API extension cursor.next() used')

import db
from auth import verify_authentication, authenticate_user
from perm import cache_permissions, PermissionError, perm_to_hdf

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

def parse_args():
    args = {}
    info = os.getenv ('PATH_INFO')
    if not info:
        return args
    
    match = re.search('/about(/?.*)', info)
    if match:
        args['mode'] = 'about'
        if len(match.group(1)) > 0:
            args['page'] = match.group(1)
        return args
    if re.search('/newticket/?', info):
        args['mode'] = 'newticket'
        return args
    if re.search('/timeline/?', info):
        args['mode'] = 'timeline'
        return args
    if re.search('/search/?', info):
        args['mode'] = 'search'
        return args
    match = re.search('/wiki/(.*)/?', info)
    if match:
        args['mode'] = 'wiki'
        if len(match.group(1)) > 0:
            args['page'] = match.group(1)
        return args
    match = re.search('/ticket/([0-9]+)/?', info)
    if match:
        args['mode'] = 'ticket'
        args['id'] = match.group(1)
        return args
    match = re.search('/report/([0-9]*)/?', info)
    if match:
        args['mode'] = 'report'
        if len(match.group(1)) > 0:
            args['id'] = match.group(1)
        return args
    match = re.search('/browser(/?.*)', info)
    if match:
        args['mode'] = 'browser'
        if len(match.group(1)) > 0:
            args['path'] = match.group(1)
        return args
    match = re.search('/log/(.+)', info)
    if match:
        args['mode'] = 'log'
        args['path'] = match.group(1)
        return args
    match = re.search('/file/(.+)/([0-9]+)/?', info)
    if match:
        args['mode'] = 'file'
        args['path'] = match.group(1)
        args['rev'] = match.group(2)
        return args
    match = re.search('/changeset/([0-9]+)/?', info)
    if match:
        args['mode'] = 'changeset'
        args['rev'] = match.group(1)
        return args
    return args

def main():
    db.init()
    config = db.load_config()
    Href.initialize(config)

    core.apr_initialize()
    pool = core.svn_pool_create(None)

    args = parse_args()
    _args = cgi.FieldStorage()
    for x in _args.keys():
        args[x] = _args[x].value

    mode = dict_get_with_default(args, 'mode', 'wiki')

    module_name, constructor_name, need_svn = modules[mode]
    module = __import__(module_name, globals(),  locals(), [])
    constructor = getattr(module, constructor_name)
    module = constructor(config, args, pool)
    module._name = mode

    verify_authentication(args)
    cache_permissions()
    perm_to_hdf(module.cgi.hdf)

    # Only open the subversion repository for the modules that really
    # need it. This saves us some precious time.
    if need_svn:
        repos_dir = config['general']['repository_dir']
        rep = repos.svn_repos_open(repos_dir, pool)
        fs_ptr = repos.svn_repos_fs(rep)
        module.repos = rep
        module.fs_ptr = fs_ptr
        db.sync(rep, fs_ptr, pool)

    # Let the wiki module build a dictionary of all page names
    import Wiki
    Wiki.populate_page_dict()
    
    module.run()
        
    core.svn_pool_destroy(pool)
    core.apr_terminate()
