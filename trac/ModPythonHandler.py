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

import re
import auth, core, Environment, Href, Session, Wiki
from mod_python import apache, util

content_type_re = re.compile(r'^Content-Type$', re.IGNORECASE)

class ModPythonRequest(core.Request):

    def __init__(self, req):
        self.req = req

    def init_request(self):
        core.Request.init_request(self)

        # TODO This will need proxy host name support (see #437 and [581])
        host = self.req.hostname
        port = self.req.connection.local_addr[1]
        path = re.sub('%s$' % re.escape(self.req.path_info), '', self.req.uri)
        if port == 80:
            self.base_url = 'http://%s%s' % (host, path)
        elif port == 443:
            self.base_url = 'https://%s%s' % (host, path)
        else:
            self.base_url = 'http://%s:%d%s' % (host, port, path)

        self.cgi_location = path
        self.remote_addr = self.req.connection.remote_ip
        self.remote_user = self.req.user
        self.command = self.req.method

        if self.req.headers_in.has_key('Cookie'):
            self.incookie.load(self.req.headers_in['Cookie'])

        self.hdf.setValue('HTTP.Host', self.req.hostname)

    def read(self, len):
        return self.req.read(len)

    def write(self, data):
        self.req.write(data)

    def get_header(self, name):
        return self.req.headers_in.get(name)

    def send_response(self, code):
        self.req.status = code

    def send_header(self, name, value):
        if content_type_re.match(name):
            self.req.content_type = value
        else:
            self.req.headers_out.add(name, str(value))

    def end_headers(self):
        pass


class TracFieldStorage(util.FieldStorage):
    """
    FieldStorage class with an added get function.
    """
    def get(self, key, default=''):
        return util.FieldStorage.get(self, key, default)


env = None

def init(req):
    global env

    options = req.req.get_options()
    if not options.has_key('TracEnv'):
        raise EnvironmentError, \
            'Missing PythonOption "TracEnv". Trac requires this option '\
            'to point to a valid Trac Environment.'
    env_path = options['TracEnv']

    env = Environment.Environment(env_path)
    version = env.get_version()
    if version < Environment.db_version:
        raise TracError('The Trac environment needs to be upgraded. '
                        'Run "trac-admin %s upgrade"' % env_path)
    elif version > Environment.db_version:
        raise TracError('Unknown Trac Environment version (%d).' % version)

    env.href = Href.Href(req.cgi_location)
    env.abs_href = Href.Href(req.base_url)

    # Let the wiki module build a dictionary of all page names
    database = env.get_db_cnx()
    Wiki.populate_page_dict(database, env)

def handler(req):
    global env

    mpr = ModPythonRequest(req)
    mpr.init_request()

    if not env:
        init(mpr)

    args = TracFieldStorage(req)
    core.parse_path_info(args, req.path_info)

    referrer = req.headers_in.get('Referer', None)

    req.content_type = 'text/html'

    try:
        core.dispatch_request(req.path_info, args, mpr, env)
    except Exception, e:
        core.send_pretty_error(e, env, mpr)

    return apache.OK
