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

import core


class Module:
    def run(self):
        core.populate_hdf(self.req.hdf, self.env, self.db, self.req)
        self.req.hdf.setValue('trac.active_module', self._name)
        try:
            disp = getattr(self, 'display_' + self.args['format'])
        except (KeyError,AttributeError):
            disp = self.display
        try:
            self.render()
            disp()
        except core.RedirectException:
            pass
        
    def render (self):
        """
        Override this function to add data the template requires
        to self.req.hdf.
        """
        pass
    
    def display(self):
        self.req.display(self.template_name)

    def display_hdf(self):
        def hdf_tree_walk(node,prefix=''):
            while node: 
                np = (prefix and prefix+'.' or '') + (node.name() or '')
                nvalue = node.value()
                if nvalue: result.append((np, nvalue))
                hdf_tree_walk(node.child(), np)
                node = node.next()
        self.req.send_response(200)
        self.req.send_header('Content-Type', 'text/plain')
        self.req.end_headers()
        result = []
        hdf_tree_walk (self.req.hdf)
        result.sort()
        for (name,value) in result:
            self.req.write(name)
            if value.find('\n') == -1:
                self.req.write('= %s\r\n' % value)
            else:
                self.req.write('<< EOM\r\n%s\r\nEOM\r\n' % value)
        
