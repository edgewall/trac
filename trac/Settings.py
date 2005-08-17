# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2004, 2005 Edgewall Software
# Copyright (C) 2004, 2005 Daniel Lundin <daniel@edgewall.com>
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
# Author: Daniel Lundin <daniel@edgewall.com>

from __future__ import generators

from trac.core import *
from trac.util import escape
from trac.web import IRequestHandler
from trac.web.chrome import INavigationContributor

class SettingsModule(Component):

    implements(INavigationContributor, IRequestHandler)

    _form_fields = ['newsid','name', 'email']

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'settings'

    def get_navigation_items(self, req):
        yield 'metanav', 'settings', '<a href="%s">Settings</a>' \
              % escape(self.env.href.settings())

    # IRequestHandler methods

    def match_request(self, req):
        return req.path_info == '/settings'

    def process_request(self, req):
        action = req.args.get('action')

        if req.method == 'POST':
            if action == 'save':
                self._do_save(req)
            elif action == 'load':
                self._do_load(req)

        req.hdf['title'] = 'Settings'
        req.hdf['settings'] = req.session
        if req.authname == 'anonymous':
            req.hdf['settings.session_id'] = req.session.sid

        return 'settings.cs', None

    # Internal methods

    def _do_save(self, req):
        for field in self._form_fields:
            val = req.args.get(field)
            if val:
                if field == 'newsid' and val:
                    req.session.change_sid(val)
                else:
                    req.session[field] = val
        req.redirect(self.env.href.settings())

    def _do_load(self, req):
        if req.authname == 'anonymous':
            oldsid = req.args.get('loadsid')
            req.session.get_session(oldsid)
        req.redirect(self.env.href.settings())
