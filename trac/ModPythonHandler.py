# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2004 Edgewall Software
# Copyright (C) 2004 Christopher Lenz <cmlenz@gmx.de>
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

import locale
locale.setlocale(locale.LC_ALL, '')

import os
import re, threading

from trac import auth, core, Environment, Href
from trac.util import TracError, href_join, rstrip

from mod_python import apache, util


class ModPythonRequest(core.Request):

    def __init__(self, req):
        self.req = req

    def init_request(self):
        core.Request.init_request(self)
        options = self.req.get_options()

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

        # Reconstruct the absolute base URL
        port = self.req.connection.local_addr[1]
        scheme = 'http'
        if self.req.subprocess_env.get('HTTPS') in ('on', '1') or port == 443:
            scheme = 'https'
        host = self.req.hostname
        if self.req.headers_in.has_key('X-Forwarded-For'):
            host = self.req.headers_in['X-Forwarded-For']
        if not host:
            # Missing host header, so reconstruct the host from the
            # server name and port
            default_port = {'http': 80, 'https': 443}
            name = self.req.server.server_hostname
            if port != default_port[scheme]:
                host = '%s:%d' % (name, port)
            else:
                host = name
        from urlparse import urlunparse
        self.base_url = urlunparse((scheme, host, self.cgi_location, None, None,
                                    None))

        self.remote_addr = self.req.connection.remote_ip
        self.remote_user = self.req.user
        self.command = self.req.method

        if self.req.headers_in.has_key('Cookie'):
            self.incookie.load(self.req.headers_in['Cookie'])

        # Populate the HDF with some HTTP info
        # FIXME: Ideally, the templates shouldn't even need this data
        self.hdf.setValue('HTTP.Host', self.req.hostname)
        self.hdf.setValue('HTTP.Protocol', scheme)

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
    default value for the 'default' parameter, mimicking the CGI interface.
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

def open_environment(env_path, mpr):
    env = Environment.Environment(env_path)
    version = env.get_version()
    if version < Environment.db_version:
        raise TracError('The Trac environment needs to be upgraded. '
                        'Run "trac-admin %s upgrade"' % env_path)
    elif version > Environment.db_version:
        raise TracError('Unknown Trac Environment version (%d).' % version)

    env.href = Href.Href(mpr.cgi_location)
    env.abs_href = Href.Href(mpr.base_url)

    return env

env_cache = {}
env_cache_lock = threading.Lock()

def get_environment(req, mpr):
    global env_cache, env_cache_lock
    options = req.get_options()
    
    if not options.has_key('TracEnv') and not options.has_key('TracEnvParentDir'):
        raise EnvironmentError, \
              'Missing PythonOption "TracEnv" or "TracEnvParentDir". Trac '\
              'requires one of these options to locate the Trac environment(s).'
    
    if options.has_key('TracEnv'):
        env_path = options['TracEnv']
        
    elif options.has_key('TracEnvParentDir'):
        env_parent_dir = options['TracEnvParentDir']
        env_name = mpr.cgi_location.split('/')[-1]
        env_path = os.path.join(env_parent_dir, env_name)
        if len(env_name) == 0 or not os.path.exists(env_path):
            send_project_index(req, mpr, env_parent_dir)
            return None
        
    try:
        env = None
        env_cache_lock.acquire()
        if not env_path in env_cache:
            env_cache[env_path] = open_environment(env_path, mpr)
        env = env_cache[env_path]
    finally:
        env_cache_lock.release()
    return env

def handler(req):
    mpr = ModPythonRequest(req)
    mpr.init_request()

    env = get_environment(req, mpr)
    if not env:
        return apache.OK

    mpr.args = FieldStorageWrapper(req, keep_blank_values=1)

    req.content_type = 'text/html'
    try:
        core.dispatch_request(mpr.path_info, mpr, env)
    except Exception, e:
        core.send_pretty_error(e, env, mpr)
    return apache.OK
