# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2004, 2005 Edgewall Software
# Copyright (C) 2004, 2005 Christopher Lenz <cmlenz@gmx.de>
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
# Author: Christopher Lenz <cmlenz@gmx.de>

from trac.core import open_environment
from trac.util import TracError, href_join, rstrip
from trac.web.main import Request, dispatch_request, send_pretty_error

from mod_python import apache, util

import locale
import os
import re
import threading


class ModPythonRequest(Request):

    idx_location = None

    def __init__(self, req, options):
        Request.__init__(self)
        self.req = req

        self.method = self.req.method
        self.server_name = self.req.server.server_hostname
        self.server_port = self.req.connection.local_addr[1]
        self.remote_addr = self.req.connection.remote_ip
        self.remote_user = self.req.user
        self.scheme = 'http'
        if self.req.subprocess_env.get('HTTPS') in ('on', '1') \
                or self.server_port == 443:
            self.scheme = 'https'
        if self.req.headers_in.has_key('Cookie'):
            self.incookie.load(self.req.headers_in['Cookie'])
        self.args = FieldStorageWrapper(self.req, keep_blank_values=1)

        # The root uri sometimes has to be explicitly specified because apache
        # sometimes get req.path_info wrong if many <alias> and <location> directives
        # are used.
        if options.has_key('TracUriRoot'):
            root_uri = rstrip(options['TracUriRoot'], '/')
            if self.req.uri[:len(root_uri)] != root_uri:
                raise ValueError('TracRootUri set to "%s" but req.uri starts with "%s"' %
                                 (root_uri, self.req.uri[:len(root_uri)]))
            self.path_info = self.req.uri[len(root_uri):]
        else:
            self.path_info = self.req.path_info

        if len(self.path_info):
            self.idx_location = self.req.uri[:-len(self.path_info)]
        else:
            self.idx_location = self.req.uri

        if options.has_key('TracEnvParentDir') and self.path_info:
            # We have to remove one path element from path_info when we're
            # using TracEnvParentDir
            self.path_info = re.sub('/[^/]+', '', self.path_info, 1)

        if len(self.path_info):
            self.cgi_location = self.req.uri[:-len(self.path_info)] or '/'
        else:
            self.cgi_location = self.req.uri

    def read(self, len):
        return self.req.read(len)

    def write(self, data):
        self.req.write(data)

    def get_header(self, name):
        return self.req.headers_in.get(name)

    def send_response(self, code):
        self.req.status = code

    def send_header(self, name, value):
        if name.lower() == 'content-type':
            self.req.content_type = value
        else:
            self.req.headers_out.add(name, str(value))

    def end_headers(self):
        pass


class FieldStorageWrapper(util.FieldStorage):
    """
    FieldStorage class with a get function that provides an empty string as the
    default value for the 'default' parameter, mimicking
    trac.web.cgi_frontend.TracFieldStorage
    """

    def get(self, key, default=''):
        return util.FieldStorage.get(self, key, default)


def send_project_index(req, mpr, dir):
    req.content_type = 'text/html'
    req.write('<html><head><title>Available Projects</title></head>')
    req.write('<body><h1>Available Projects</h1><ul>')
    for project in os.listdir(dir):
        req.write('<li><a href="%s">%s</a></li>'
                  % (href_join(mpr.idx_location, project), project))
    req.write('</ul></body><html>')

env_cache = {}
env_cache_lock = threading.Lock()

def get_environment(req, mpr, options):
    global env_cache, env_cache_lock

    if options.has_key('TracEnv'):
        env_path = options['TracEnv']
    elif options.has_key('TracEnvParentDir'):
        env_parent_dir = options['TracEnvParentDir']
        env_name = mpr.cgi_location.split('/')[-1]
        env_path = os.path.join(env_parent_dir, env_name)
        if len(env_name) == 0 or not os.path.exists(env_path):
            send_project_index(req, mpr, env_parent_dir)
            return None
    else:
        raise TracError, \
              'Missing PythonOption "TracEnv" or "TracEnvParentDir". Trac ' \
              'requires one of these options to locate the Trac environment(s).'

    env = None
    try:
        env_cache_lock.acquire()
        if not env_path in env_cache:
            env_cache[env_path] = open_environment(env_path)
        env = env_cache[env_path]
    finally:
        env_cache_lock.release()
    return env

def handler(req):
    options = req.get_options()
    if options.has_key('TracLocale'):
        locale.setlocale(locale.LC_ALL, options['TracLocale'])
    else:
        locale.setlocale(locale.LC_ALL, '')

    mpr = ModPythonRequest(req, options)
    env = get_environment(req, mpr, options)
    if not env:
        return apache.OK

    req.content_type = 'text/html'
    try:
        dispatch_request(mpr.path_info, mpr, env)
    except Exception, e:
        send_pretty_error(e, env, mpr)
    return apache.OK
