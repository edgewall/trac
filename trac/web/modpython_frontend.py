# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2004, 2005 Edgewall Software
# Copyright (C) 2004, 2005 Christopher Lenz <cmlenz@gmx.de>
# Copyright (C) 2005 Matthew Good <trac@matt-good.net>
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
# Author: Matthew Good <trac@matt-good.net>

import locale
import mimetypes
import os
import re

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from mod_python import apache, util

from trac.util import http_date, rstrip
from trac.web.api import Request, RequestDone
from trac.web.main import dispatch_request, get_environment, \
                          send_pretty_error, send_project_index


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
        if mimetype:
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
        # Work around a quirk with the ModPython FieldStorage class.
        # Instances of a string subclass are returned instead of real
        # strings, this confuses psycopg2 among others.
        v = util.FieldStorage.get(self, key, default)
        if isinstance(v, util.StringField):
            return v.value
        else:
            return v

    def __setitem__(self, key, value):
        if value is not None and key not in self:
            self.list.append(util.Field(key, StringIO(value), 'text/plain',
                             {}, None, {}))

def dict_translate(orig, *mappings):
    result = {}
    for src, dest in mappings:
        if src in orig:
            result[dest] = orig[src]
    return result

def handler(req):
    options = req.get_options()
    if options.has_key('TracLocale'):
        locale.setlocale(locale.LC_ALL, options['TracLocale'])
    else:
        locale.setlocale(locale.LC_ALL, '')

    # Allow specifying the python eggs cache directory using SetEnv
    if req.subprocess_env.has_key('PYTHON_EGG_CACHE'):
        os.environ['PYTHON_EGG_CACHE'] = req.subprocess_env['PYTHON_EGG_CACHE']

    mpr = ModPythonRequest(req, options)
    project_opts = dict_translate(options,
            ('TracEnv', 'TRAC_ENV'),
            ('TracEnvParentDir', 'TRAC_ENV_PARENT_DIR'),
            ('TracEnvIndexTemplate', 'TRAC_ENV_INDEX_TEMPLATE'),
            ('TracTemplateVars', 'TRAC_TEMPLATE_VARS'))
    env = get_environment(mpr, project_opts)
    if not env:
        send_project_index(mpr, project_opts)
        return apache.OK

    req.content_type = 'text/html'
    try:
        dispatch_request(mpr.path_info, mpr, env)
    except Exception, e:
        send_pretty_error(e, env, mpr)
    return apache.OK
