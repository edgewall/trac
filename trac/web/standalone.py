# -*- coding: iso-8859-1 -*-
#
# Copyright (C) 2003-2005 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2005 Matthew Good <trac@matt-good.net>
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
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
#         Matthew Good <trac@matt-good.net>
#         Christopher Lenz <cmlenz@gmx.de>

try:
    from base64 import b64decode
except ImportError:
    from base64 import decodestring as b64decode
import md5
import os
import re
import sys
import time
import socket, errno
import urllib
import urllib2
from SocketServer import ThreadingMixIn

from trac import util, __version__
from trac.util import md5crypt
from trac.web.main import dispatch_request
from trac.web.wsgi import WSGIServer, WSGIRequestHandler


class BasicAuth(object):

    def __init__(self, htpasswd, realm):
        self.hash = {}
        self.realm = realm
        try:
            import crypt
            self.crypt = crypt.crypt
        except ImportError:
            self.crypt = None
        self.load(htpasswd)

    def load(self, filename):
        fd = open(filename, 'r')
        for line in fd:
            u, h = line.strip().split(':')
            if '$' in h or self.crypt:
                self.hash[u] = h
            else:
                print >>sys.stderr, 'Warning: cannot parse password for ' \
                                    'user "%s" without the "crypt" module' % u

        if self.hash == {}:
            print >> sys.stderr, "Warning: found no users in file:", filename

    def test(self, user, password):
        the_hash = self.hash.get(user)
        if the_hash is None:
            return False

        if not '$' in the_hash:
            return self.crypt(password, the_hash[:2]) == the_hash

        magic, salt = the_hash[1:].split('$')[:2]
        magic = '$' + magic + '$'
        return md5crypt(password, salt, magic) == the_hash

    def send_auth_request(self, req):
        req.send_response(401)
        req.send_header('WWW-Authenticate', 'Basic realm="%s"' % self.realm)
        req.end_headers()

    def do_auth(self, req):
        if not 'Authorization' in req.headers or \
               not req.headers['Authorization'].startswith('Basic'):
            self.send_auth_request(req)
            return None

        auth = req.headers['Authorization'][len('Basic')+1:]
        auth = b64decode(auth).split(':')
        if len(auth) != 2:
            self.send_auth_request(req)
            return None

        user, password = auth
        if not self.test(user, password):
            self.send_auth_request(req)
            return None

        return user


class DigestAuth(object):
    """A simple HTTP DigestAuth implementation (rfc2617)"""

    MAX_NONCES = 100

    def __init__(self, htdigest, realm):
        self.active_nonces = []
        self.hash = {}
        self.realm = realm
        self.load_htdigest(htdigest, realm)

    def load_htdigest(self, filename, realm):
        """Load account information from apache style htdigest files, only
        users from the specified realm are used
        """
        fd = open(filename, 'r')
        for line in fd.readlines():
            u, r, a1 = line.strip().split(':')
            if r == realm:
                self.hash[u] = a1
        if self.hash == {}:
            print >> sys.stderr, "Warning: found no users in realm:", realm
        
    def parse_auth_header(self, authorization):
        values = {}
        for value in urllib2.parse_http_list(authorization):
            n, v = value.split('=', 1)
            if v[0] == '"' and v[-1] == '"':
                values[n] = v[1:-1]
            else:
                values[n] = v
        return values

    def send_auth_request(self, req, stale='false'):
        """Send a digest challange to the browser. Record used nonces
        to avoid replay attacks.
        """
        nonce = util.hex_entropy()
        self.active_nonces.append(nonce)
        if len(self.active_nonces) > DigestAuth.MAX_NONCES:
            self.active_nonces = self.active_nonces[-DigestAuth.MAX_NONCES:]
        req.send_response(401)
        req.send_header('WWW-Authenticate',
                        'Digest realm="%s", nonce="%s", qop="auth", stale="%s"'
                        % (self.realm, nonce, stale))
        req.end_headers()

    def do_auth(self, req):
        if not 'Authorization' in req.headers or \
               not req.headers['Authorization'].startswith('Digest'):
            self.send_auth_request(req)
            return None
        auth = self.parse_auth_header(req.headers['Authorization'][7:])
        required_keys = ['username', 'realm', 'nonce', 'uri', 'response',
                           'nc', 'cnonce']
        # Invalid response?
        for key in required_keys:
            if not auth.has_key(key):
                self.send_auth_request(req)
                return None
        # Unknown user?
        if not self.hash.has_key(auth['username']):
            self.send_auth_request(req)
            return None

        kd = lambda x: md5.md5(':'.join(x)).hexdigest()
        a1 = self.hash[auth['username']]
        a2 = kd([req.command, auth['uri']])
        # Is the response correct?
        correct = kd([a1, auth['nonce'], auth['nc'],
                      auth['cnonce'], auth['qop'], a2])
        if auth['response'] != correct:
            self.send_auth_request(req)
            return None
        # Is the nonce active, if not ask the client to use a new one
        if not auth['nonce'] in self.active_nonces:
            self.send_auth_request(req, stale='true')
            return None
        self.active_nonces.remove(auth['nonce'])
        return auth['username']


class TracHTTPServer(ThreadingMixIn, WSGIServer):

    def __init__(self, server_address, env_parent_dir, env_paths, auths):
        WSGIServer.__init__(self, server_address, dispatch_request,
                            request_handler=TracHTTPRequestHandler)
        self.environ['trac.env_path'] = None
        if env_parent_dir:
            self.environ['trac.env_parent_dir'] = env_parent_dir
        else:
            self.environ['trac.env_paths'] = env_paths
        self.auths = auths


class TracHTTPRequestHandler(WSGIRequestHandler):

    server_version = 'tracd/' + __version__

    def handle_one_request(self):
        environ = self.setup_environ()
        path_info = environ.get('PATH_INFO', '')
        path_parts = filter(None, path_info.split('/'))
        if len(path_parts) > 1 and path_parts[1] == 'login':
            env_name = path_parts[0]
            if env_name:
                auth = self.server.auths.get(env_name,
                                             self.server.auths.get('*'))
                if not auth:
                    self.send_error(500, 'Authentication not enabled for %s. '
                                         'Please use the tracd --auth option.'
                                         % env_name)
                    return
                remote_user = auth.do_auth(self)
                if not remote_user:
                    return
                environ['REMOTE_USER'] = remote_user

        gateway = self.server.gateway(self, environ)
        gateway.run(self.server.application)
