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

from util import *
from Module import Module
import perm

import time

class Settings(Module):
    template_name = 'settings.cs'

    _form_fields = ['newsid','name', 'email', 'tz']

    def render(self):
        self.req.hdf.setValue('title', 'Settings')
        action = self.args.get('action')
        self.env.log.debug('Session action: %s' % action)
        if action == 'save':
            self.save_settings()
        elif action == 'load':
            self.load_session()
        elif action == 'login':
            self.req.redirect (self.env.href.login())
        elif action == 'newsession':
            raise TracError, 'new session'

    def save_settings(self):
        for field in self._form_fields:
            val = self.args.get(field)
            if val:
                if field =='newsid':
                    self.req.session.change_sid(val)
                else:
                    self.req.session[field] = val
        self.req.session.populate_hdf() # Update HDF

    def load_session(self):
        oldsid = self.args.get('loadsid')
        self.req.session.get_session(oldsid)
