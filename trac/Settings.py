# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2004 Edgewall Software
# Copyright (C) 2004 Daniel Lundin <daniel@edgewall.com>
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

import time

import perm
from util import TracError
from Module import Module


class Settings(Module):
    template_name = 'settings.cs'

    _form_fields = ['newsid','name', 'email']

    def render(self, req):
        req.hdf.setValue('title', 'Settings')
        action = req.args.get('action')
        if action == 'save':
            self.save_settings(req)
        elif action == 'load':
            self.load_session(req)
        elif action == 'login':
            req.redirect (self.env.href.login())
        elif action == 'newsession':
            raise TracError, 'new session'

    def save_settings(self, req):
        for field in self._form_fields:
            val = req.args.get(field)
            if val:
                if field =='newsid':
                    req.session.change_sid(val)
                else:
                    req.session[field] = val
        req.session.populate_hdf() # Update HDF

    def load_session(self, req):
        oldsid = req.args.get('loadsid')
        req.session.get_session(oldsid)
