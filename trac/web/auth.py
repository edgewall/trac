# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2018 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgström <jonas@edgewall.com>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.
#
# Author: Jonas Borgström <jonas@edgewall.com>

from __future__ import print_function

from abc import ABCMeta, abstractmethod
from base64 import b64decode, b64encode
from hashlib import md5, sha1
import os
import re
import sys
import urllib2
import urlparse

from genshi.builder import tag

from trac.config import BoolOption, IntOption, Option
from trac.core import *
from trac.web.api import IAuthenticator, IRequestHandler
from trac.web.chrome import Chrome, INavigationContributor
from trac.util import hex_entropy, md5crypt
from trac.util.compat import crypt
from trac.util.concurrency import threading
from trac.util.datefmt import time_now
from trac.util.translation import _, tag_


class LoginModule(Component):
    """User authentication manager.

    This component implements user authentication based on HTTP
    authentication provided by the web-server, combined with cookies
    for communicating the login information across the whole site.

    This mechanism expects that the web-server is setup so that a
    request to the path '/login' requires authentication (such as
    Basic or Digest). The login name is then stored in the database
    and associated with a unique key that gets passed back to the user
    agent using the 'trac_auth' cookie. This cookie is used to
    identify the user in subsequent requests to non-protected
    resources.
    """

    implements(IAuthenticator, INavigationContributor, IRequestHandler)

    is_valid_default_handler = False

    check_ip = BoolOption('trac', 'check_auth_ip', 'false',
         """Whether the IP address of the user should be checked for
         authentication.""")

    ignore_case = BoolOption('trac', 'ignore_auth_case', 'false',
        """Whether login names should be converted to lower case.""")

    auth_cookie_domain = Option('trac', 'auth_cookie_domain', '',
        """Auth cookie domain attribute.

        The auth cookie can be shared among multiple subdomains
        by setting the value to the domain. (//since 1.2//)
        """)

    auth_cookie_lifetime = IntOption('trac', 'auth_cookie_lifetime', 0,
        """Lifetime of the authentication cookie, in seconds.

        This value determines how long the browser will cache
        authentication information, and therefore, after how much
        inactivity a user will have to log in again. The value
        of 0 makes the cookie expire at the end of the browsing
        session. (''since 0.12'')""")

    auth_cookie_path = Option('trac', 'auth_cookie_path', '',
        """Path for the authentication cookie. Set this to the common
        base path of several Trac instances if you want them to share
        the cookie.  (''since 0.12'')""")

    # IAuthenticator methods

    def authenticate(self, req):
        authname = None
        if req.remote_user:
            authname = req.remote_user
        elif 'trac_auth' in req.incookie:
            authname = self._get_name_for_cookie(req,
                                                 req.incookie['trac_auth'])

        if not authname:
            return None

        if self.ignore_case:
            authname = authname.lower()

        return authname

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'login'

    def get_navigation_items(self, req):
        if req.authname and req.authname != 'anonymous':
            yield ('metanav', 'login',
                   tag_("logged in as %(user)s",
                        user=Chrome(self.env).authorinfo(req, req.authname)))
            yield ('metanav', 'logout',
                   tag.form(tag.div(tag.button(_("Logout"),
                                               name='logout', type='submit')),
                            action=req.href.logout(), method='post',
                            id='logout', class_='trac-logout'))
        else:
            yield ('metanav', 'login',
                   tag.a(_("Login"), href=req.href.login()))

    # IRequestHandler methods

    def match_request(self, req):
        return re.match('/(login|logout)/?$', req.path_info)

    def process_request(self, req):
        if req.path_info.startswith('/login'):
            self._do_login(req)
        elif req.path_info.startswith('/logout'):
            self._do_logout(req)
        self._redirect_back(req)

    # Internal methods

    def _do_login(self, req):
        """Log the remote user in.

        This function expects to be called when the remote user name
        is available. The user name is inserted into the `auth_cookie`
        table and a cookie identifying the user on subsequent requests
        is sent back to the client.

        If the Authenticator was created with `ignore_case` set to
        true, then the authentication name passed from the web server
        in req.remote_user will be converted to lower case before
        being used. This is to avoid problems on installations
        authenticating against Windows which is not case sensitive
        regarding user names and domain names
        """
        if not req.remote_user:
            # TRANSLATOR: ... refer to the 'installation documentation'. (link)
            inst_doc = tag.a(_("installation documentation"),
                             title=_("Configuring Authentication"),
                             href=req.href.wiki('TracInstall') +
                                                "#ConfiguringAuthentication")
            raise TracError(tag_("Authentication information not available. "
                                 "Please refer to the %(inst_doc)s.",
                                 inst_doc=inst_doc))
        remote_user = req.remote_user
        if self.ignore_case:
            remote_user = remote_user.lower()

        if req.authname not in ('anonymous', remote_user):
            raise TracError(_("Already logged in as %(user)s.",
                              user=req.authname))

        with self.env.db_transaction as db:
            # Delete cookies older than 10 days
            db("DELETE FROM auth_cookie WHERE time < %s",
               (int(time_now()) - 86400 * 10,))
            # Insert a new cookie if we haven't already got one
            cookie = None
            trac_auth = req.incookie.get('trac_auth')
            if trac_auth is not None:
                name = self._cookie_to_name(req, trac_auth)
                cookie = trac_auth.value if name == remote_user else None
            if cookie is None:
                cookie = hex_entropy()
                db("""
                    INSERT INTO auth_cookie (cookie, name, ipnr, time)
                         VALUES (%s, %s, %s, %s)
                   """, (cookie, remote_user, req.remote_addr,
                         int(time_now())))
        req.authname = remote_user
        req.outcookie['trac_auth'] = cookie
        if self.auth_cookie_domain:
            req.outcookie['trac_auth']['domain'] = self.auth_cookie_domain
        req.outcookie['trac_auth']['path'] = self.auth_cookie_path \
                                             or req.base_path or '/'
        if self.env.secure_cookies:
            req.outcookie['trac_auth']['secure'] = True
        req.outcookie['trac_auth']['httponly'] = True
        if self.auth_cookie_lifetime > 0:
            req.outcookie['trac_auth']['expires'] = self.auth_cookie_lifetime

    def _do_logout(self, req):
        """Log the user out.

        Simply deletes the corresponding record from the auth_cookie
        table.
        """
        if req.method != 'POST':
            return
        if req.authname == 'anonymous':
            # Not logged in
            return

        if 'trac_auth' in req.incookie:
            self.env.db_transaction("DELETE FROM auth_cookie WHERE cookie=%s",
                                    (req.incookie['trac_auth'].value,))
        else:
            self.env.db_transaction("DELETE FROM auth_cookie WHERE name=%s",
                                    (req.authname,))
        self._expire_cookie(req)
        custom_redirect = self.config['metanav'].get('logout.redirect')
        if custom_redirect:
            if not re.match(r'https?:|/', custom_redirect):
                custom_redirect = req.href(custom_redirect)
            req.redirect(custom_redirect)

    def _expire_cookie(self, req):
        """Instruct the user agent to drop the auth cookie by setting
        the "expires" property to a date in the past.
        """
        req.outcookie['trac_auth'] = ''
        if self.auth_cookie_domain:
            req.outcookie['trac_auth']['domain'] = self.auth_cookie_domain
        req.outcookie['trac_auth']['path'] = self.auth_cookie_path \
                                             or req.base_path or '/'
        req.outcookie['trac_auth']['expires'] = -10000
        if self.env.secure_cookies:
            req.outcookie['trac_auth']['secure'] = True
        req.outcookie['trac_auth']['httponly'] = True

    def _cookie_to_name(self, req, cookie):
        # This is separated from _get_name_for_cookie(), because the
        # latter is overridden in AccountManager.
        if self.check_ip:
            sql = "SELECT name FROM auth_cookie WHERE cookie=%s AND ipnr=%s"
            args = (cookie.value, req.remote_addr)
        else:
            sql = "SELECT name FROM auth_cookie WHERE cookie=%s"
            args = (cookie.value,)
        for name, in self.env.db_query(sql, args):
            return name

    def _get_name_for_cookie(self, req, cookie):
        name = self._cookie_to_name(req, cookie)
        if name is None:
            # The cookie is invalid (or has been purged from the
            # database), so tell the user agent to drop it as it is
            # invalid
            self._expire_cookie(req)
        return name

    def _redirect_back(self, req):
        """Redirect the user back to the URL she came from."""
        referer = self._referer(req)
        if referer:
            if not referer.startswith(('http://', 'https://')):
                # Make URL absolute
                scheme, host = urlparse.urlparse(req.base_url)[:2]
                referer = urlparse.urlunparse((scheme, host, referer, None,
                                               None, None))
            pos = req.base_url.find(':')
            base_scheme = req.base_url[:pos]
            base_noscheme = req.base_url[pos:]
            base_noscheme_norm = base_noscheme.rstrip('/')
            referer_noscheme = referer[referer.find(':'):]
            # only redirect to referer if it is from the same site
            if referer_noscheme == base_noscheme or \
                    referer_noscheme.startswith(base_noscheme_norm + '/'):
                # avoid redirect loops
                if referer_noscheme.rstrip('/') != \
                        base_noscheme_norm + req.path_info.rstrip('/'):
                    req.redirect(base_scheme + referer_noscheme)
        req.redirect(req.abs_href())

    def _referer(self, req):
        return req.args.get('referer') or req.get_header('Referer')


class HTTPAuthentication(object):

    __metaclass__ = ABCMeta

    @abstractmethod
    def do_auth(self, environ, start_response):
        pass


class PasswordFileAuthentication(HTTPAuthentication):
    def __init__(self, filename):
        self.filename = filename
        self.mtime = os.stat(filename).st_mtime
        self.load(self.filename)
        self._lock = threading.Lock()

    def check_reload(self):
        with self._lock:
            mtime = os.stat(self.filename).st_mtime
            if mtime != self.mtime:
                self.mtime = mtime
                self.load(self.filename)


class BasicAuthentication(PasswordFileAuthentication):

    def __init__(self, htpasswd, realm):
        # FIXME pass a logger
        self.realm = realm
        self.crypt = crypt
        self.hash = {}
        PasswordFileAuthentication.__init__(self, htpasswd)

    def load(self, filename):
        # FIXME use a logger
        self.hash = {}
        fd = open(filename, 'r')
        for line in fd:
            line = line.split('#')[0].strip()
            if not line:
                continue
            try:
                u, h = line.split(':')[:2]
            except ValueError:
                print("Warning: invalid password line in %s: %s"
                      % (filename, line), file=sys.stderr)
                continue
            if '$' in h or h.startswith('{SHA}') or self.crypt:
                self.hash[u] = h
            else:
                print('Warning: cannot parse password for user "%s" '
                      'without the "crypt" module. Install the passlib '
                      'package from PyPI' % u, file=sys.stderr)

        if self.hash == {}:
            print("Warning: found no users in file:", filename,
                  file=sys.stderr)

    def test(self, user, password):
        self.check_reload()
        the_hash = self.hash.get(user)
        if the_hash is None:
            return False

        if the_hash.startswith('{SHA}'):
            return b64encode(sha1(password).digest()) == the_hash[5:]

        if '$' not in the_hash:
            return self.crypt(password, the_hash[:2]) == the_hash

        magic, salt = the_hash[1:].split('$')[:2]
        magic = '$' + magic + '$'
        return md5crypt(password, salt, magic) == the_hash

    def do_auth(self, environ, start_response):
        header = environ.get('HTTP_AUTHORIZATION')
        if header and header.startswith('Basic'):
            auth = b64decode(header[6:]).split(':')
            if len(auth) == 2:
                user, password = auth
                if self.test(user, password):
                    return user

        start_response('401 Unauthorized',
                       [('WWW-Authenticate', 'Basic realm="%s"' % self.realm),
                        ('Content-Length', '0')])('')


class DigestAuthentication(PasswordFileAuthentication):
    """A simple HTTP digest authentication implementation
    (:rfc:`2617`)."""

    MAX_NONCES = 100

    def __init__(self, htdigest, realm):
        # FIXME pass a logger
        self.active_nonces = []
        self.realm = realm
        self.hash = {}
        PasswordFileAuthentication.__init__(self, htdigest)

    def load(self, filename):
        """Load account information from apache style htdigest files,
        only users from the specified realm are used
        """
        # FIXME use a logger
        self.hash = {}
        fd = open(filename, 'r')
        for line in fd:
            line = line.split('#')[0].strip()
            if not line:
                continue
            try:
                u, r, a1 = line.split(':')[:3]
            except ValueError:
                print("Warning: invalid digest line in %s: %s"
                      % (filename, line), file=sys.stderr)
                continue
            if r == self.realm:
                self.hash[u] = a1
        if self.hash == {}:
            print("Warning: found no users in realm:", self.realm,
                  file=sys.stderr)

    def parse_auth_header(self, authorization):
        values = {}
        for value in urllib2.parse_http_list(authorization):
            n, v = value.split('=', 1)
            if v[0] == '"' and v[-1] == '"':
                values[n] = v[1:-1]
            else:
                values[n] = v
        return values

    def send_auth_request(self, environ, start_response, stale='false'):
        """Send a digest challange to the browser. Record used nonces
        to avoid replay attacks.
        """
        nonce = hex_entropy()
        self.active_nonces.append(nonce)
        if len(self.active_nonces) > self.MAX_NONCES:
            self.active_nonces = self.active_nonces[-self.MAX_NONCES:]
        start_response('401 Unauthorized',
                       [('WWW-Authenticate',
                        'Digest realm="%s", nonce="%s", qop="auth", stale="%s"'
                        % (self.realm, nonce, stale)),
                        ('Content-Length', '0')])('')

    def do_auth(self, environ, start_response):
        header = environ.get('HTTP_AUTHORIZATION')
        if not header or not header.startswith('Digest'):
            self.send_auth_request(environ, start_response)
            return None

        auth = self.parse_auth_header(header[7:])
        required_keys = ['username', 'realm', 'nonce', 'uri', 'response',
                         'nc', 'cnonce']
        # Invalid response?
        for key in required_keys:
            if key not in auth:
                self.send_auth_request(environ, start_response)
                return None
        # Unknown user?
        self.check_reload()
        if auth['username'] not in self.hash:
            self.send_auth_request(environ, start_response)
            return None

        kd = lambda x: md5(':'.join(x)).hexdigest()
        a1 = self.hash[auth['username']]
        a2 = kd([environ['REQUEST_METHOD'], auth['uri']])
        # Is the response correct?
        correct = kd([a1, auth['nonce'], auth['nc'],
                      auth['cnonce'], auth['qop'], a2])
        if auth['response'] != correct:
            self.send_auth_request(environ, start_response)
            return None
        # Is the nonce active, if not ask the client to use a new one
        if not auth['nonce'] in self.active_nonces:
            self.send_auth_request(environ, start_response, stale='true')
            return None
        self.active_nonces.remove(auth['nonce'])
        return auth['username']
