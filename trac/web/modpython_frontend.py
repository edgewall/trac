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

import locale
import mimetypes
import os
import re
import threading

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from mod_python import apache, util

from trac.env import open_environment
from trac.util import TracError, enum, href_join, http_date, rstrip
from trac.web.main import Request, RequestDone, dispatch_request, \
                          send_pretty_error


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
        self.args = FieldStorageWrapper(self.req)

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
        elif name.lower() == 'content-length':
            self.req.set_content_length(int(value))
        else:
            self.req.headers_out.add(name, str(value))

    def end_headers(self):
        pass

    def send_file(self, path, mimetype=None):
        stat = os.stat(path)
        last_modified = http_date(stat.st_mtime)
        if last_modified == self.req.headers_in.get('If-Modified-Since'):
            self.send_response(304)
            raise RequestDone

        self.req.status = 200
        if not mimetype:
            mimetype = mimetypes.guess_type(path)[0]
        self.req.content_type = mimetype
        self.req.set_content_length(stat.st_size)
        self.req.headers_out.add('Last-Modified', http_date(stat.st_mtime))

        self.req.sendfile(path)
        raise RequestDone


class FieldStorageWrapper(util.FieldStorage):
    """
    mod_python FieldStorage wrapper that improves compatibility with the other
    front-ends.
    """

    def __init__(self, req):
        """
        The mod_python FieldStorage implementation, unlike cgi.py, always
        includes GET parameters, even if they are also defined in the body of
        a POST request. We work around this to provide the behaviour of cgi.py
        here.
        """
        class RequestWrapper(object):
            def __init__(self, req):
                self.req = req
                self.args = ''
            def __getattr__(self, name):
                return getattr(self.req, name)
        util.FieldStorage.__init__(self, RequestWrapper(req), keep_blank_values=1)

        # Populate FieldStorage with the original query string parameters, if
        # they aren't already defined through the request body
        if req.args:
            qsargs = []
            for pair in util.parse_qsl(req.args, 1):
                if self.has_key(pair[0]):
                    continue
                qsargs.append(util.Field(pair[0], StringIO(pair[1]),
                                         "text/plain", {}, None, {}))
            self.list += qsargs

    def get(self, key, default=None):
        return util.FieldStorage.get(self, key, default)

    def __setitem__(self, key, value):
        if not key in self:
            self.list.append(util.Field(key, StringIO(value), 'text/plain',
                             {}, None, {}))


def send_project_index(req, mpr, dir, options):
    from trac.web.clearsilver import HDFWrapper

    if 'TracEnvIndexTemplate' in options:
        # Custom project listing template configured
        tmpl_path, template = os.path.split(options['TracEnvIndexTemplate'])

        from trac.config import default_dir
        mpr.hdf = HDFWrapper(loadpaths=[default_dir('templates'), tmpl_path])

        tmpl_vars = {}
        if 'TracTemplateVars' in options:
            pairs = options['TracTemplateVars'].split(',')
            for pair in pairs:
                key,val = pair.split('=')
                mpr.hdf[key] = val

    else:
        # Use the default project listing template
        mpr.hdf = HDFWrapper()
        template = mpr.hdf.parse("""<html>
<head><title>Available Projects</title></head>
<body><h1>Available Projects</h1><ul><?cs
 each:project = projects ?><li><a href="<?cs
  var:project.href ?>"><?cs var:project.name ?></a></li><?cs
 /each ?></ul></body>
</html>""")

    try:
        projects = []
        for idx, project in enum(os.listdir(dir)):
            env_path = os.path.join(dir, project)
            if not os.path.isdir(env_path):
                continue
            try:
                env = open_environment(env_path)
                projects.append({
                    'name': env.config.get('project', 'name'),
                    'description': env.config.get('project', 'descr'),
                    'href': href_join(mpr.idx_location, project)
                })
            except TracError, e:
                req.log_error('Error opening environment at %s: %s'
                              % (env_path, e))
        projects.sort(lambda x, y: cmp(x['name'], y['name']))
        mpr.hdf['projects'] = projects
        mpr.display(template, response=200)
    except RequestDone:
        pass

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
            send_project_index(req, mpr, env_parent_dir, options)
            return None
    else:
        raise TracError, \
              'Missing PythonOption "TracEnv" or "TracEnvParentDir". Trac ' \
              'requires one of these options to locate the Trac environment(s).'

    env = None
    env_cache_lock.acquire()
    try:
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
