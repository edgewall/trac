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

# permissions
TIMELINE_VIEW  = 'TIMELINE_VIEW'
SEARCH_VIEW    = 'SEARCH_VIEW'
CONFIG_VIEW    = 'CONFIG_VIEW'
LOG_VIEW       = 'LOG_VIEW'
FILE_VIEW      = 'FILE_VIEW'
CHANGESET_VIEW = 'CHANGESET_VIEW'
BROWSER_VIEW   = 'BROWSER_VIEW'
ROADMAP_VIEW   = 'ROADMAP_VIEW'

TICKET_VIEW    = 'TICKET_VIEW'
TICKET_CREATE  = 'TICKET_CREATE'
TICKET_MODIFY  = 'TICKET_MODIFY'

REPORT_VIEW    = 'REPORT_VIEW'
REPORT_SQL_VIEW = 'REPORT_SQL_VIEW'
REPORT_CREATE  = 'REPORT_CREATE'
REPORT_MODIFY  = 'REPORT_MODIFY'
REPORT_DELETE  = 'REPORT_DELETE'

WIKI_VIEW      = 'WIKI_VIEW'
WIKI_CREATE    = 'WIKI_CREATE'
WIKI_MODIFY    = 'WIKI_MODIFY'
WIKI_DELETE    = 'WIKI_DELETE'

MILESTONE_VIEW = 'MILESTONE_VIEW'
MILESTONE_CREATE = 'MILESTONE_CREATE'
MILESTONE_MODIFY = 'MILESTONE_MODIFY'
MILESTONE_DELETE = 'MILESTONE_DELETE'

TRAC_ADMIN = 'TRAC_ADMIN'
TICKET_ADMIN = 'TICKET_ADMIN'
REPORT_ADMIN = 'REPORT_ADMIN'
WIKI_ADMIN = 'WIKI_ADMIN'
ROADMAP_ADMIN = 'MILESTONE_ADMIN'

meta_permission = {
    TRAC_ADMIN: [TICKET_ADMIN, REPORT_ADMIN, WIKI_ADMIN, ROADMAP_ADMIN,
                 TIMELINE_VIEW, SEARCH_VIEW, CONFIG_VIEW, LOG_VIEW,
                 FILE_VIEW, CHANGESET_VIEW, BROWSER_VIEW],
    TICKET_ADMIN: [TICKET_VIEW, TICKET_CREATE, TICKET_MODIFY],
    REPORT_ADMIN: [REPORT_VIEW, REPORT_SQL_VIEW, REPORT_CREATE, REPORT_MODIFY,
                   REPORT_DELETE],
    WIKI_ADMIN: [WIKI_VIEW, WIKI_CREATE, WIKI_MODIFY, WIKI_DELETE],
    ROADMAP_ADMIN: [ROADMAP_VIEW, MILESTONE_VIEW, MILESTONE_CREATE,
                    MILESTONE_MODIFY, MILESTONE_DELETE]
}


class PermissionError (StandardError):
    """Insufficient permissions to complete the operation"""
    def __init__ (self, action):
        self.action = action
    def __str__ (self):
        return '%s privileges required to perform this operation' % self.action


class PermissionCache:
    """
    Permission groups can be created in Trac by assigning
    permissions to an imaginary user with the same name as
    the group.
    Example:
    
    $ trac-admin myenv permission add developer WIKI_ADMIN
    $ trac-admin myenv permission add developer TICKET_ADMIN
    $ trac-admin myenv permission add developer REPORT_ADMIN
    
    Grant "developer privileges" to some users:
    
    $ trac-admin myenv permission add bob developer
    $ trac-admin myenv permission add john developer
    
    Special 'groups':
     'anonymous':     Permissions granted to this user will apply to
                      anyone.
     'authenticated': Permissions granted to this user will apply to
                      any authenticated (logged in with HTTP_AUTH) user.
    """
    def __init__(self, db, username):
        self.perm_cache = {}
        cursor = db.cursor()
        cursor.execute ("SELECT username, action FROM permission")
        result = cursor.fetchall()

        perms = []
        users = ['anonymous']
        if username != 'anonymous':
            users += [username, 'autenticated']
        while 1:
            num_users = len(users)
            num_perms = len(perms)
            for u, a in result:
                if u in users:
                    if not a in perms:
                        perms.append(a)
                    if a.islower() and not a in users:
                        users.append(a)
            if num_users == len(users) and num_perms == len(perms):
                break
        for perm in perms:
            self.expand_meta_permission(perm)
        
    def expand_meta_permission(self, action):
        self.perm_cache[action] = 1
        if meta_permission.has_key(action):
            for perm in meta_permission[action]:
                self.expand_meta_permission(perm)

    def has_permission(self, action):
        return self.perm_cache.has_key (action)

    def assert_permission (self, action):
        if not self.perm_cache.has_key (action):
            raise PermissionError (action)

    def add_to_hdf(self, hdf):
        for action in self.perm_cache.keys():
            hdf.setValue('trac.acl.' + action, 'true')
    
