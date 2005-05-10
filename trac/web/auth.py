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

from __future__ import generators

import time

from trac import util
from trac.core import *
from trac.web.chrome import INavigationContributor


class Authenticator:
    """
    Provides user authentication based on HTTP authentication provided by the
    web-server, combined with cookies for communicating the login information
    across the whole site.

    Expects that the web-server is setup so that a request to the path '/login'
    requires authentication (such as Basic or Digest). The login name is then
    stored in the database and associated with a unique key that gets passed
    back to the user agent using the 'trac_auth' cookie. This cookie is used
    to identify the user in subsequent requests to non-protected resources.
    """

    def __init__(self, db, req, check_ip=1):
        self.db = db
        self.authname = 'anonymous'
        if req.incookie.has_key('trac_auth'):
            cookie = req.incookie['trac_auth'].value
            cursor = db.cursor()
            if check_ip:
                cursor.execute("SELECT name FROM auth_cookie "
                               "WHERE cookie=%s AND ipnr=%s",
                               (cookie, req.remote_addr))
            else:
                cursor.execute("SELECT name FROM auth_cookie WHERE cookie=%s",
                               (cookie,))
            row = cursor.fetchone()
            if row:
                self.authname = row[0]

    def login(self, req):
        """
        Logs the remote user in. This function expects to be called when the
        remote user name is available. The user name is inserted into the
        auth_cookie table and a cookie identifying the user on subsequent
        requests is sent back to the client.
        """
        assert req.remote_user, 'Authentication information not available.'
        if self.authname == req.remote_user:
            # Already logged in with the same user name
            return
        assert self.authname == 'anonymous', \
               'Already logged in as %s.' % self.authname

        cookie = util.hex_entropy()
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO auth_cookie (cookie,name,ipnr,time) "
                       "VALUES (%s, %s, %s, %s)",
                       (cookie, req.remote_user, req.remote_addr,
                        int(time.time())));
        self.db.commit()
        self.authname = req.remote_user
        req.outcookie['trac_auth'] = cookie
        req.outcookie['trac_auth']['path'] = req.cgi_location

    def logout(self):
        """
        Logs the user out. Simply deletes the corresponding record from the
        auth_cookie table.
        """
        if self.authname == 'anonymous':
            # Not logged in
            return

        cursor = self.db.cursor()
        cursor.execute("DELETE FROM auth_cookie WHERE name=%s", self.authname)
        self.db.commit()


class LoginModule(Component):

    implements(INavigationContributor)

    # INavigationContributor methods

    def get_navigation_items(self, req):
        if req.authname and req.authname != 'anonymous':
            yield 'metanav', 'login', 'logged in as %s' \
                  % util.escape(req.authname)
            yield 'metanav', 'logout', '<a href="%s">Logout</a>' \
                  % util.escape(self.env.href.logout())
        else:
            yield 'metanav', 'login', '<a href="%s">Login</a>' \
                  % util.escape(self.env.href.login())
