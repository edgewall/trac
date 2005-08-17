# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2005 Edgewall Software
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
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

import cgi
import locale
import os
import re
import sys

from trac.web.api import Request
from trac.web.main import dispatch_request, get_environment, \
                          send_pretty_error, send_project_index


class CGIRequest(Request):
    """Request implementation for CGI."""

    def __init__(self, environ=os.environ, input=sys.stdin, output=sys.stdout):
        Request.__init__(self)
        self.__environ = environ
        self.__input = input
        self.__output = output

        self.method = self.__environ.get('REQUEST_METHOD')
        self.remote_addr = self.__environ.get('REMOTE_ADDR')
        self.remote_user = self.__environ.get('REMOTE_USER')
        self.server_name = self.__environ.get('SERVER_NAME')
        self.server_port = int(self.__environ.get('SERVER_PORT', 0))
        self.scheme = 'http'
        if self.__environ.get('HTTPS') in ('on', '1') or self.server_port == 443:
            self.scheme = 'https'
        if self.__environ.get('HTTP_COOKIE'):
            self.incookie.load(self.__environ.get('HTTP_COOKIE'))
        self.args = self._getFieldStorage()

        self.cgi_location = self.__environ.get('SCRIPT_NAME')
        self.idx_location = self.cgi_location

        self.path_info = self.__environ.get('PATH_INFO', '')

        if 'TRAC_ENV_PARENT_DIR' in os.environ and self.path_info:
            env_path = '/' + self.path_info.split('/', 2)[1]
            self.path_info = self.path_info[len(env_path):]
            self.cgi_location += env_path



    def _getFieldStorage(self):
        return TracFieldStorage(self.__input, environ=self.__environ,
                                keep_blank_values=1)

    def read(self, len):
        return self.__input.read(len)

    def write(self, data):
        return self.__output.write(data)

    def get_header(self, name):
        return self.__environ.get('HTTP_' + re.sub('-', '_', name.upper()))

    def send_response(self, code):
        self.write('Status: %d\r\n' % code)

    def send_header(self, name, value):
        self.write('%s: %s\r\n' % (name, value))

    def end_headers(self):
        self.write('\r\n')


class TracFieldStorage(cgi.FieldStorage):
    """
    FieldStorage class with a few more functions to make it behave a bit
    more like a dictionary
    """
    get = cgi.FieldStorage.getvalue

    def __setitem__(self, name, value):
        if self.has_key(name):
            del self[name]
        self.list.append(cgi.MiniFieldStorage(name, value))

    def __delitem__(self, name):
        if not self.has_key(name):
            raise KeyError(name)
        self.list = filter(lambda x, name=name: x.name != name, self.list)


def run():
    locale.setlocale(locale.LC_ALL, '')

    req = CGIRequest()
    env = get_environment(req, os.environ, threaded=False)

    if not env:
        send_project_index(req, os.environ)
        return

    try:
        dispatch_request(req.path_info, req, env)
    except Exception, e:
        send_pretty_error(e, env, req)
