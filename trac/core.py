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
import time
from types import ListType

import perm
import Environment
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
        from trac import authzperm, sync
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
