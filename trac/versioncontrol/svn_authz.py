# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2004 Edgewall Software
# Copyright (C) 2004 Francois Harvey <fharvey@securiweb.net>
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
# Author: Francois Harvey <fharvey@securiweb.net>

from trac.versioncontrol import Authorizer


class SubversionAuthorizer(Authorizer):

    auth_name = ''
    module_name = ''
    conf_authz = None
    authz_file = ''

    def __init__(self, env, authname):
        self.auth_name = authname
        
        if env.get_config('trac','authz_module_name','') == '':
            self.module_name = ''
        else:
            self.module_name = env.get_config('trac','authz_module_name') + ':'
                                 
        self.autz_file = env.get_config('trac','authz_file')    
        if env.get_config('trac','authz_file'):
            from ConfigParser import ConfigParser
            self.conf_authz = ConfigParser()
            self.conf_authz.read(self.autz_file)

        self.db = env.get_db_cnx()

    def group_contains_user(self, group_name, user_name):
        if self.conf_authz.has_section('groups'):
            if self.conf_authz.has_option('groups', group_name):
                users_list = self.conf_authz.get('groups', group_name).split(',')
                return users_list.has_key(user_name)
        return 0

    def has_permission(self, path):
        acc = ''

        if path != None and self.conf_authz != None:
            if self.conf_authz.has_section(self.module_name + '/') and \
                   self.conf_authz.has_option(self.module_name  + '/',
                                              self.auth_name):
                acc = self.conf_authz.get(self.module_name + '/',self.auth_name)
            elif self.conf_authz.has_section(self.module_name + '/') and \
                 self.conf_authz.has_option(self.module_name  + '/', '*'):
                     acc = self.conf_authz.get(self.module_name + '/','*')
            path_comb = ''
            for path_elem in path.split('/'):
                if path_elem != '':
                    path_comb = self.module_name + path_comb + '/' + path_elem
                    if self.conf_authz.has_section(path_comb) and \
                           self.conf_authz.has_option(path_comb, self.auth_name):
                        acc =  self.conf_authz.get(path_comb, self.auth_name)
                    elif self.conf_authz.has_section(path_comb) and \
                            self.conf_authz.has_option(path_comb, '*'):
                        acc =  self.conf_authz.get(path_comb, '*')
        else:
            acc = 'r'
        return acc

    def has_permission_for_changeset(self, rev):
        cursor = self.db.cursor()
        cursor.execute("SELECT path FROM node_change WHERE rev=%s", (rev,))
        for row in cursor:
            if self.has_permission(row[0]):
                return 1
        return 0
