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

from trac.util import escape
from trac.web.main import populate_hdf


class Module:

    db = None
    env = None
    _name = None
    template_name = None
    links = None

    def __init__(self):
        self.links = {}

    def run(self, req):
        if req.args.has_key('format'):
            disp = getattr(self, 'display_' + req.args.get('format'))
        else:
            disp = self.display
        populate_hdf(req.hdf, self.env, req)
        for action in self.perm.permissions():
            req.hdf['trac.acl.' + action] = 1
        self._add_default_links(req)
        self.render(req)
        req.hdf['trac.active_module'] = self._name
        req.hdf['links'] = self.links
        disp(req)

    def _add_default_links(self, req):
        self.add_link('start', self.env.href.wiki())
        self.add_link('search', self.env.href.search())
        self.add_link('help', self.env.href.wiki('TracGuide'))
        
        icon = self.env.get_config('project', 'icon')
        if icon:
            if not icon[0] == '/' and icon.find('://') < 0:
                icon = req.hdf.get('htdocs_location', '') + icon
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

    def render(self, req):
        """
        Override this function to add data the template requires
        in the HDF.
        """
        pass

    def display(self, req):
        req.display(self.template_name)

    def display_hdf(self, req):
        req.send_response(200)
        req.send_header('Content-Type', 'text/plain;charset=utf-8')
        req.end_headers()
        req.write(str(req.hdf))
