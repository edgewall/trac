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

from exceptions import StandardError
from auth import get_authname
from db import get_connection

perm_cache = {}

# permissions
LOG_VIEW       = 'LOG_VIEW'

FILE_VIEW      = 'FILE_VIEW'

CHANGESET_VIEW = 'CHANGESET_VIEW'

BROWSER_VIEW   = 'BROWSER_VIEW'

TICKET_VIEW    = 'TICKET_VIEW'
TICKET_CREATE  = 'TICKET_CREATE'
TICKET_MODIFY  = 'TICKET_MODIFY'

REPORT_VIEW    = 'REPORT_VIEW'
REPORT_CREATE  = 'REPORT_CREATE'
REPORT_MODIFY  = 'REPORT_MODIFY'
REPORT_DELETE  = 'REPORT_DELETE'

WIKI_VIEW      = 'WIKI_VIEW'
WIKI_CREATE    = 'WIKI_CREATE'
WIKI_MODIFY    = 'WIKI_MODIFY'
WIKI_DELETE    = 'WIKI_DELETE'

TIMELINE_VIEW  = 'TIMELINE_VIEW'

SEARCH_VIEW = 'SEARCH_VIEW'

meta_permission = {
    'TICKET_ADMIN': [TICKET_VIEW, TICKET_CREATE, TICKET_MODIFY],
    'REPORT_ADMIN': [REPORT_VIEW, REPORT_CREATE, REPORT_MODIFY, REPORT_DELETE],
    'WIKI_ADMIN'  : [WIKI_VIEW, WIKI_CREATE, WIKI_MODIFY, WIKI_DELETE]
    }

class PermissionError (StandardError):
    """Insufficient permissions to complete the operation"""
    def __init__ (self, action):
        self.action = action
    def __str__ (self):
        return '%s privileges required to perform this operation' % self.action

def cache_permissions ():
    global perm_cache, meta_permission

    # Special usernames:
    # 'anonymous':     Permissions granted to this user will apply to anyone.
    # 'authenticated': Permissions granted to this user will apply to
    #                  any authenticated (logged in with HTTP_AUTH) user.

    cnx = get_connection ()
    if get_authname() == 'anonymous':
        rs = cnx.db.execute ("SELECT action FROM permission "
                             "WHERE user='anonymous'")
    else:
        rs = cnx.db.execute ("SELECT action FROM permission "
                             "WHERE user='%s' OR user='anonymous' "
                             "OR user = 'authenticated'" %
                             get_authname ())
    for row in rs.row_list:
        action = row[0]
        if meta_permission.has_key(action):
	    for perm in meta_permission[action]:
		perm_cache[perm] = 1
#            map (lambda action: perm_cache.__setitem__(action, 1),
#                 meta_permission[action])
        perm_cache[action] = 1

def has_permission (action):
    global perm_cache
    return perm_cache.has_key (action)

def assert_permission (action):
    global perm_cache
    if not perm_cache.has_key (action):
        raise PermissionError (action)

def perm_to_hdf(hdf):
    global perm_cache
    for action in perm_cache.keys():
        hdf.setValue('trac.acl.' + action, 'true')
    
