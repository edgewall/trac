# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2004 Edgewall Software
# Copyright (C) 2004 Jonas Borgström <jonas@edgewall.com>
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

import util
import perm
from Module import Module


class About (Module):
    template_name = 'about.cs'
    
    def render (self):
        page = util.dict_get_with_default(self.args, 'page', 'default')
        
        self.cgi.hdf.setValue('title', 'About Trac')
        
        if page[0:7] == '/config':
            self.perm.assert_permission(perm.CONFIG_VIEW)
            self.cgi.hdf.setValue('about.page', 'config')
            # Export the config table to hdf
            i = 0
            for section in self.config.keys():
                for name in self.config[section].keys():
                    value = self.config[section][name]
                    self.cgi.hdf.setValue('about.config.%d.section' % i, section)
                    self.cgi.hdf.setValue('about.config.%d.name' % i, name)
                    self.cgi.hdf.setValue('about.config.%d.value' % i, value)
                    i = i + 1
            # TODO:
            # We should probably export more info here like:
            # permissions, components...

