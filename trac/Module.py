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
from util import add_to_hdf, escape


class Module:
    db = None
    env = None
    req = None
    _name = None
    args = []
    template_name = None
    links = {}

    def run(self):
        if self.args.has_key('format'):
            disp = getattr(self, 'display_' + self.args.get('format'))
        else:
            disp = self.display
        self.add_default_links()
        self.render()
        core.populate_hdf(self.req.hdf, self.env, self.db, self.req)
        self.req.hdf.setValue('trac.active_module', self._name)
        add_to_hdf(self.links, self.req.hdf, 'links')
        disp()

    def add_default_links(self):
        self.links.clear()
        self.add_link('start', self.env.href.wiki())
        self.add_link('search', self.env.href.search())
        self.add_link('help', self.env.href.wiki('TracGuide'))
        
        icon = self.env.get_config('project', 'icon')
        if icon:
            if not icon[0] == '/' and icon.find('://') < 0:
                icon = self.req.hdf.getValue('htdocs_location', '') + icon
            mimetype = self.env.mimeview.get_mimetype(icon)
            self.add_link('icon', icon, type=mimetype)
            self.add_link('shortcut icon', icon, type=mimetype)

    def add_link(self, rel, href, title=None, type=None, className=None):
        if not self.links.has_key(rel):
            self.links[rel] = []
        link = { 'href': escape(href) }
        if title: link['title'] = escape(title)
        if type: link['type'] = type
        if className: link['class'] = className
        self.links[rel].append(link)

    def render(self):
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
                name = node.name() or ''
                if not node.child():
                    value = node.value()
                    self.req.write('%s%s = ' % (prefix, name))
                    if value.find('\n') == -1:
                        self.req.write('%s\r\n' % value)
                    else:
                        self.req.write('<< EOM\r\n%s\r\nEOM\r\n' % value)
                else:
                    self.req.write('%s%s {\r\n' % (prefix, name))
                    hdf_tree_walk(node.child(), prefix + '  ')
                    self.req.write('%s}\r\n' % prefix)
                node = node.next()
        self.req.send_response(200)
        self.req.send_header('Content-Type', 'text/plain;charset=utf-8')
        self.req.end_headers()
        hdf_tree_walk (self.req.hdf.child())
