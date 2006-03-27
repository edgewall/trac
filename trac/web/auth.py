# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2005 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgström <jonas@edgewall.com>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://projects.edgewall.com/trac/.
#
# Author: Jonas Borgström <jonas@edgewall.com>

import re
import time

from trac.core import *
from trac.config import IConfigurable, ConfigOption
from trac.web.api import IAuthenticator, IRequestHandler
from trac.web.chrome import INavigationContributor
from trac.util import escape, hex_entropy, Markup


class LoginModule(Component):
    """Implements user authentication based on HTTP authentication provided by
    the web-server, combined with cookies for communicating the login
    information across the whole site.

    This mechanism expects that the web-server is setup so that a request to the
    path '/login' requires authentication (such as Basic or Digest). The login
    name is then stored in the database and associated with a unique key that
    gets passed back to the user agent using the 'trac_auth' cookie. This cookie
    is used to identify the user in subsequent requests to non-protected
    resources.
    """

    implements(IConfigurable, IAuthenticator, INavigationContributor,
               IRequestHandler)

    # IConfigurable

    def get_config_options(self):
        yield ('trac', [
            ConfigOption('check_auth_ip', 'true',
                         """Whether the IP address of the user should be
                         checked for authentication (true, false)
                         (''since 0.9'')
                         """),
            ConfigOption('ignore_auth_case', 'false',
                         """Whether case should be ignored for login names
                         (true, false) (''since 0.9'')
                         """)])
        
    # IAuthenticator methods

    def authenticate(self, req):
        authname = None
        if req.remote_user:
            authname = req.remote_user
        elif req.incookie.has_key('trac_auth'):
            authname = self._get_name_for_cookie(req, req.incookie['trac_auth'])

        if not authname:
            return None

        if self.config.getbool('trac', 'ignore_auth_case'):
            authname = authname.lower()

        return authname

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'login'

    def get_navigation_items(self, req):
        if req.authname and req.authname != 'anonymous':
            yield ('metanav', 'login', 'logged in as %s' % req.authname)
            yield ('metanav', 'logout',
                   Markup('<a href="%s">Logout</a>' 
                          % escape(self.env.href.logout())))
        else:
            yield ('metanav', 'login',
                   Markup('<a href="%s">Login</a>' 
                          % escape(self.env.href.login())))

    # IRequestHandler methods

    def match_request(self, req):
        return re.match('/(login|logout)/?', req.path_info)

    def process_request(self, req):
        if req.path_info.startswith('/login'):
            self._do_login(req)
        elif req.path_info.startswith('/logout'):
            self._do_logout(req)
        self._redirect_back(req)

    # Internal methods

    def _do_login(self, req):
        """Log the remote user in.

        This function expects to be called when the remote user name is
        available. The user name is inserted into the `auth_cookie` table and a
        cookie identifying the user on subsequent requests is sent back to the
        client.

        If the Authenticator was created with `ignore_case` set to true, then 
        the authentication name passed from the web server in req.remote_user
        will be converted to lower case before being used. This is to avoid
        problems on installations authenticating against Windows which is not
        case sensitive regarding user names and domain names
        """
        assert req.remote_user, 'Authentication information not available.'

        remote_user = req.remote_user
        if self.config.getbool('trac', 'ignore_auth_case'):
            remote_user = remote_user.lower()

        assert req.authname in ('anonymous', remote_user), \
               'Already logged in as %s.' % req.authname

        cookie = hex_entropy()
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("INSERT INTO auth_cookie (cookie,name,ipnr,time) "
                       "VALUES (%s, %s, %s, %s)", (cookie, remote_user,
                       req.remote_addr, int(time.time())))
        db.commit()

        req.authname = remote_user
        req.outcookie['trac_auth'] = cookie
        req.outcookie['trac_auth']['path'] = self.env.href()

    def _do_logout(self, req):
        """Log the user out.

        Simply deletes the corresponding record from the auth_cookie table.
        """
        if req.authname == 'anonymous':
            # Not logged in
            return

        # While deleting this cookie we also take the opportunity to delete
        # cookies older than 10 days
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("DELETE FROM auth_cookie WHERE name=%s OR time < %s",
                       (req.authname, int(time.time()) - 86400 * 10))
        db.commit()
        self._expire_cookie(req)

    def _expire_cookie(self, req):
        """Instruct the user agent to drop the auth cookie by setting the
        "expires" property to a date in the past.
        """
        req.outcookie['trac_auth'] = ''
        req.outcookie['trac_auth']['path'] = self.env.href()
        req.outcookie['trac_auth']['expires'] = -10000

    def _get_name_for_cookie(self, req, cookie):
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        if self.config.getbool('trac', 'check_auth_ip'):
            cursor.execute("SELECT name FROM auth_cookie "
                           "WHERE cookie=%s AND ipnr=%s",
                           (cookie.value, req.remote_addr))
        else:
            cursor.execute("SELECT name FROM auth_cookie WHERE cookie=%s",
                           (cookie.value,))
        row = cursor.fetchone()
        if not row:
            # The cookie is invalid (or has been purged from the database), so
            # tell the user agent to drop it as it is invalid
            self._expire_cookie(req)
            return None

        return row[0]

    def _redirect_back(self, req):
        """Redirect the user back to the URL she came from."""
        referer = req.get_header('Referer')
        if referer and not referer.startswith(req.base_url):
            # only redirect to referer if it is from the same site
            referer = None
        req.redirect(referer or self.env.abs_href())
