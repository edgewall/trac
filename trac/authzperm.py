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

from exceptions import StandardError
import ConfigParser
import string
import os

class AuthzPermissionError (StandardError):
    """Insufficient permission to view this file"""
    def __str__ (self):
        return 'Insufficient permission to view this file (mod_authz_svn)'
    

class AuthzPermission:
    auth_name = ''
    module_name = ''
    conf_authz = None
    authz_file = ''
    
    def __init__(self,env,authname):
	if authname == 'anonymous':
	    self.auth_name = '*'
	else:
	    self.auth_name = authname
	self.module_name = env.get_config('project', 'name')
	self.autz_file = env.get_config('trac','authz_file')	
	if env.get_config('trac','authz_file'):
	    self.conf_authz = ConfigParser.ConfigParser()
	    self.conf_authz.read( self.autz_file )
    
    def group_contains_user(self, group_name, user_name):
	if self.conf_authz.has_section('groups'):
	    if self.conf_authz.has_option('groups', group_name):
		users_list = self.conf_authz.get('groups', group_name).split(',')
		return users_list.has_key(user_name)
	return False
    
    def has_permission(self, path):
	acc = 'r'

	if path != None and self.conf_authz != None:
	    if self.conf_authz.has_section(self.module_name + ':/') and \
                   self.conf_authz.has_option(self.module_name + ':/',
                                              self.auth_name):
		acc = self.conf_authz.get(self.module_name + ':/',self.auth_name)

            path_comb = ''
	    for path_ele in path.split('/'):
		if path_ele != '':
		    path_comb = path_comb + '/' + path_ele
		    section_name = self.module_name + ':' + path_comb
		    if self.conf_authz.has_section(section_name) and \
                           self.conf_authz.has_option(section_name,self.auth_name):
			acc =  self.conf_authz.get(section_name ,self.auth_name)
        return acc

    def assert_permission (self, path):
	if self.has_permission(path) == '':
	    raise AuthzPermissionError()
