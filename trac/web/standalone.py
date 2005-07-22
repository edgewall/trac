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
#
# Todo:
# - External auth using mod_proxy / squid.

from trac import util, __version__
from trac.env import open_environment
from trac.web.main import Request, dispatch_request, send_pretty_error
from trac.web.cgi_frontend import TracFieldStorage
from trac.web import href

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
               req.headers['Authorization'][:6] != 'Digest':
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

    def __init__(self, server_address, env_paths, auths):
        HTTPServer.__init__(self, server_address, TracHTTPRequestHandler)

        if self.server_port == 80:
            self.http_host = self.server_name
        else:
            self.http_host = '%s:%d' % (self.server_name, self.server_port)

        self.projects = {}
        for path in env_paths:
            # Remove trailing slashes
            while path and not os.path.split(path)[1]:
                path = os.path.split(path)[0]
            project = os.path.split(path)[1]
            # We assume the projenv filenames follow the following
            # naming convention: /some/path/project
            auth = auths.get(project, None)
            env = open_environment(path)
            env.href = href.Href('/' + project)
            env.abs_href = href.Href('http://%s/%s' % (self.http_host, project))
            env.config.set('trac', 'htdocs_location', '')
            self.projects[project] = env
            self.projects[project].auth = auth


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
        if self.path[0:13] == '/':
            self._do_project_index()
        else:
            self._do_trac_req()

    def _do_project_index(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write('<html><head><title>Available Projects</title></head>')
        self.wfile.write('<body><h1>Available Projects</h1><ul>')
        for proj in self.server.projects.keys():
            self.wfile.write('<li><a href="%s">%s</a></li>' % (urllib.quote(proj), proj))
        self.wfile.write('</ul></body><html>')

    def _do_trac_req(self):
        m = self.url_re.findall(self.path)
        if not m:
            self.send_error(400, 'Bad Request')
            return
        project_name, path_info, query_string = m[0]
        project_name = urllib.unquote(project_name)
        if not self.server.projects.has_key(project_name):
            self.send_error(404, 'Not Found')
            return
        path_info = urllib.unquote(path_info)
        env = self.server.projects[project_name]

        req = TracHTTPRequest(self, project_name, query_string)
        req.remote_user = None
        if path_info == '/login':
            if not env.auth:
                raise util.TracError('Authentication not enabled. '
                                     'Please use the tracd --auth option.\n')
            req.remote_user = env.auth.do_auth(self)
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
