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
from mod_python import apache, util
from trac import auth, core, Environment, Href, Session, Wiki

env = None

class ModPythonRequest(core.Request):

    def __init__(self, req):
        self.req = req

    def init_request(self):
        core.Request.init_request(self)

        # TODO This will need proxy host name support (see #437 and [581])
        host = self.req.hostname
        port = self.req.connection.local_addr[1]
        path = re.sub(self.req.path_info + '$', '', self.req.uri)
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

    def send_response(self, code):
        self.req.status = code

    def send_header(self, name, value):
        self.req.headers_out.add(name, str(value))

    def end_headers(self):
        pass

class TracFieldStorage(util.FieldStorage):
    """
    FieldStorage class with an added get function.
    """
    def get(self, key, default=''):
        return util.FieldStorage.get(self, key, default)


def init(req):
    global env

    try:
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
                            'Run "trac-admin %s upgrade"' % path)
        elif version > Environment.db_version:
            raise TracError('Unknown Trac Environment version (%d).' % version)

        env.href = Href.Href(req.cgi_location)
        env.abs_href = Href.Href(req.base_url)

        database = env.get_db_cnx()

        # Let the wiki module build a dictionary of all page names
        Wiki.populate_page_dict(database, env)

    except Exception, e:
        apache.log_error(str(e))
        raise apache.SERVER_RETURN, apache.HTTP_INTERNAL_SERVER_ERROR

def handler(req):
    global env

    mpr = ModPythonRequest(req)
    mpr.init_request()

    if not env:
        init(mpr)

    database = env.get_db_cnx()
    authenticator = auth.Authenticator(database, mpr)
    referrer = req.headers_in.get('Referer', None)
    if req.path_info == '/logout':
        authenticator.logout()
        try:
            mpr.redirect(referrer or env.href.wiki())
        except core.RedirectException:
            pass
        return apache.OK
    if mpr.remote_user and authenticator.authname == 'anonymous':
        authenticator.login(mpr)
    if req.path_info == '/login':
        try:
            mpr.redirect(referrer or env.href.wiki())
        except core.RedirectException:
            pass
        return apache.OK
    mpr.authname = authenticator.authname

    # TODO This doesn't handle POST requests yet, because we can't get a
    #      file-like object for the request body to pass into parse_args
    args = TracFieldStorage(req)
    core.parse_path_info(args, req.path_info)
    core.add_args_to_hdf(args, mpr.hdf)

    newsession = args.has_key('newsession') and args['newsession']
    mpr.session = Session.Session(env, mpr, newsession)

    # TODO This needs to be done by the modules, because it can not be
    #      overridden later. Ideally, there'd be a set_content_type method in
    #      trac.core.Request
    req.content_type = 'text/html'

    pool = None
    try:
        # Load the selected module
        module = core.module_factory(args, env, database, mpr)
        pool = module.pool
        module.run()
    finally:
        if pool:
            import svn.core
            svn.core.svn_pool_destroy(pool)

    return apache.OK
