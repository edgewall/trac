# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2003-2005 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2005 Matthew Good <trac@matt-good.net>
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
#
# Todo:
# - External auth using mod_proxy / squid.

from trac import util, __version__
from trac.env import open_environment
from trac.web.api import Request
from trac.web.cgi_frontend import TracFieldStorage
from trac.web.main import dispatch_request, get_environment, \
                          send_pretty_error, send_project_index

import os
import re
import sys
import md5
import time
import socket, errno
import urllib
import urllib2
from SocketServer import ThreadingMixIn
from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler


class DigestAuth:
    """A simple HTTP DigestAuth implementation (rfc2617)"""

    MAX_NONCES = 100

    def __init__(self, htdigest, realm):
        self.active_nonces = []
        self.hash = {}
        self.realm = realm
        self.load_htdigest(htdigest, realm)

    def load_htdigest(self, filename, realm):
        """
        Load account information from apache style htdigest files,
        only users from the specified realm are used
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
        """
        Send a digest challange to the browser. Record used nonces
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


class TracHTTPServer(ThreadingMixIn, HTTPServer):

    projects = None

    def __init__(self, server_address, env_parent_dir, env_paths, auths):
        HTTPServer.__init__(self, server_address, TracHTTPRequestHandler)

        if self.server_port == 80:
            self.http_host = self.server_name
        else:
            self.http_host = '%s:%d' % (self.server_name, self.server_port)

        self.env_parent_dir = env_parent_dir and {'TRAC_ENV_PARENT_DIR':
                                                  env_parent_dir}
        self.auths = auths

        self.projects = {}
        for env_path in env_paths:
            # Remove trailing slashes
            while env_path and not os.path.split(env_path)[1]:
                env_path = os.path.split(env_path)[0]
            project = os.path.split(env_path)[1]
            self.projects[project] = env_path

    def get_env_opts(self, project=None):
        if self.env_parent_dir:
            opts = self.env_parent_dir.items()
        else:
            opts = [('TRAC_ENV', self.projects[project])]
        return dict(opts + os.environ.items())

    def send_project_index(self, req):
        if self.env_parent_dir:
            return send_project_index(req, self.get_env_opts())
        else:
            return send_project_index(req, os.environ, self.projects.values())


class TracHTTPRequestHandler(BaseHTTPRequestHandler):

    server_version = 'tracd/' + __version__
    url_re = re.compile('/(?P<project>[^/\?]+)'
                        '(?P<path_info>/?[^\?]*)?'
                        '(?:\?(?P<query_string>.*))?')

    env = None
    log = None
    project_name = None

    def do_POST(self):
        self._do_trac_req()

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        self._do_trac_req()

    def _do_trac_req(self):
        if self.path == '/':
            path_info = '/'
            req = TracHTTPRequest(self, '', '')
            self.server.send_project_index(req)
            return

        m = self.url_re.findall(self.path)
        if not m:
            self.send_error(400, 'Bad Request')
            return

        project_name, path_info, query_string = m[0]
        project_name = urllib.unquote(project_name)
        path_info = urllib.unquote(path_info)
        req = TracHTTPRequest(self, project_name, query_string)

        try:
            opts = self.server.get_env_opts(project_name)
        except KeyError:
            # unrecognized project
            self.server.send_project_index(req)
            return

        env = get_environment(req, opts)
        if not env:
            self.server.send_project_index(req)
            return

        req.remote_user = None
        if path_info == '/login':
            auth = self.server.auths.get(project_name)
            if not auth:
                raise util.TracError('Authentication not enabled. '
                                     'Please use the tracd --auth option.\n')
            req.remote_user = auth.do_auth(self)
            if not req.remote_user:
                return

        try:
            start = time.time()
            dispatch_request(path_info, req, env)
            env.log.debug('Total request time: %f s', time.time() - start)
        except socket.error, (code, msg):
            if code == errno.EPIPE or code == 10053: # Windows
                env.log.info('Lost connection to client: %s'
                             % self.address_string())
            else:
                raise
        except Exception, e:
            try:
                send_pretty_error(e, env, req)
            except socket.error, (code, msg):
                if code == errno.EPIPE or code == 10053: # Windows
                    env.log.info('Lost connection to client: %s'
                                 % self.address_string())
                else:
                    raise


class TracHTTPRequest(Request):

    def __init__(self, handler, project_name, query_string):
        Request.__init__(self)
        self.__handler = handler

        self.scheme = 'http'
        self.method = self.__handler.command
        self.remote_addr = str(self.__handler.client_address[0])
        self.server_name = self.__handler.server.server_name
        self.server_port = self.__handler.server.server_port
        if self.__handler.headers.has_key('Cookie'):
            self.incookie.load(self.__handler.headers['Cookie'])

        self.cgi_location = '/' + project_name
        self.idx_location = '/'

        environ = {'REQUEST_METHOD': self.method,
                   'QUERY_STRING': query_string}
        headers = self.__handler.headers
        if self.method in ('GET', 'HEAD'):
            headers = None
        self.args = TracFieldStorage(self.__handler.rfile, environ=environ,
                                     headers=headers, keep_blank_values=1)

    def read(self, size=None):
        return self.__handler.rfile.read(size)

    def write(self, data):
        self.__handler.wfile.write(data)

    def get_header(self, name):
        return self.__handler.headers.get(name)

    def send_response(self, code):
        self.__handler.send_response(code)

    def send_header(self, name, value):
        self.__handler.send_header(name, value)

    def end_headers(self):
        self.__handler.end_headers()
