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

from trac.perm import PermissionCache
from trac.util import escape
from trac.web.main import populate_hdf


class Module:

    db = None
    env = None
    log = None
    perm = None

    _name = None

    def run(self, req):
        populate_hdf(req.hdf, self.env, req)
        req.hdf['trac.active_module'] = self._name
        for action in self.perm.permissions():
            req.hdf['trac.acl.' + action] = 1
        self._add_default_links(req)
        self.render(req)

    def _add_default_links(self, req):
        self.add_link(req, 'start', self.env.href.wiki())
        self.add_link(req, 'search', self.env.href.search())
        self.add_link(req, 'help', self.env.href.wiki('TracGuide'))
        icon = self.env.get_config('project', 'icon')
        if icon:
            if not icon[0] == '/' and icon.find('://') < 0:
                icon = req.hdf.get('htdocs_location', '') + icon
            mimetype = self.env.mimeview.get_mimetype(icon)
            self.add_link(req, 'icon', icon, type=mimetype)
            self.add_link(req, 'shortcut icon', icon, type=mimetype)

    def add_link(self, req, rel, href, title=None, type=None, className=None):
        link = {'href': escape(href)}
        if title: link['title'] = escape(title)
        if type: link['type'] = type
        if className: link['class'] = className
        idx = 0
        while req.hdf.get('links.%s.%d.href' % (rel, idx)):
            idx += 1
        req.hdf['links.%s.%d' % (rel, idx)] = link

    def render(self, req):
        raise NotImplementedError


modules = {
#    name           (module_name,   class_name)
    'about_trac'  : ('About',       'About'),
    'attachment'  : ('attachment',  'AttachmentModule'),
    'browser'     : ('Browser',     'BrowserModule'),
    'changeset'   : ('Changeset',   'ChangesetModule'),
    'file'        : ('Browser',     'FileModule'),
    'log'         : ('Browser',     'LogModule'),
    'milestone'   : ('Milestone',   'Milestone'),
    'newticket'   : ('Ticket',      'NewticketModule'),
    'query'       : ('Query',       'QueryModule'),
    'report'      : ('Report',      'Report'),
    'roadmap'     : ('Roadmap',     'Roadmap'),
    'search'      : ('Search',      'Search'),
    'settings'    : ('Settings',    'Settings'),
    'ticket'      : ('Ticket',      'TicketModule'),
    'timeline'    : ('Timeline',    'Timeline'),
    'wiki'        : ('Wiki',        'WikiModule'),
}

def module_factory(env, db, req):
    mode = req.args.get('mode', 'wiki')
    module_name, constructor_name = modules[mode]
    module = __import__(module_name, globals(),  locals())
    constructor = getattr(module, constructor_name)
    module = constructor()
    module._name = mode

    module.env = env
    module.log = env.log
    module.db = db
    module.perm = PermissionCache(module.db, req.authname)

    return module
