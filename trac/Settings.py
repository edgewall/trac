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
from trac.util import escape, TracError
from trac.web.chrome import INavigationContributor
from trac.web.main import IRequestHandler

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
        if action == 'save':
            self.save_settings(req)
        elif action == 'load':
            self.load_session(req)
        elif action == 'login':
            req.redirect(self.env.href.login())
        elif action == 'newsession':
            raise TracError, 'new session'

        req.hdf['title'] = 'Settings'
        req.hdf['settings'] = req.session
        if req.session.sid:
            req.hdf['settings.session_id'] = req.session.sid

        return 'settings.cs', None

    # Internal methods

    def save_settings(self, req):
        for field in self._form_fields:
            val = req.args.get(field)
            if val:
                if field == 'newsid' and val:
                    req.session.change_sid(val)
                else:
                    req.session[field] = val

    def load_session(self, req):
        if req.authname == 'anonymous':
            oldsid = req.args.get('loadsid')
            req.session.get_session(oldsid)
