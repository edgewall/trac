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

import time
import random

class Authenticator:
    def __init__(self, db, cookie, remote_addr):
        self.db = db
        cursor = db.cursor ()
        cursor.execute ("SELECT name FROM auth_cookie "
                        "WHERE cookie='%s' AND ipnr='%s'"
                        % (cookie, remote_addr))
        if cursor.rowcount >= 1:
            self.authname = cursor.fetchone()[0]
        else:
            self.authname = 'anonymous'

    def login(self, remote_user, remote_addr):
        cursor = self.db.cursor ()
        cookie = str(random.random())
        cursor.execute ("INSERT INTO auth_cookie (cookie, name, ipnr, time)" +
                        "VALUES ('%s', '%s', '%s', %d)"
                        % (cookie, remote_user, remote_addr, int(time.time())));
        self.db.commit ()
        self.authname = remote_user
        return cookie

    def logout(self):
        cursor = self.db.cursor ()
        cursor.execute ("DELETE FROM auth_cookie WHERE name='%s'" %
                        self.authname)
        self.db.commit ()
