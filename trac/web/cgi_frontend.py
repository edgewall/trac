# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2005 Edgewall Software
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
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
from trac.Href import Href
from trac.web.main import Request, dispatch_request, send_pretty_error

import cgi
import locale
import os
import re
import sys


class CGIRequest(Request):
    """
    Request implementation for CGI.
    """

    def __init__(self, environ=os.environ, input=sys.stdin, output=sys.stdout):
        self.__environ = environ
        self.__input = input
        self.__output = output

    def init_request(self):
        Request.init_request(self)

        self.cgi_location = self.__environ.get('SCRIPT_NAME')
        self.remote_addr = self.__environ.get('REMOTE_ADDR')
        self.remote_user = self.__environ.get('REMOTE_USER')
        self.command = self.__environ.get('REQUEST_METHOD')
        if self.__environ.get('HTTP_COOKIE'):
            self.incookie.load(self.__environ.get('HTTP_COOKIE'))

        scheme = 'http'
        port = int(self.__environ.get('SERVER_PORT', 0))
        if self.__environ.get('HTTPS') in ('on', '1') or port == 443:
            scheme = 'https'

        # Reconstruct the absolute base URL
        host = self.__environ.get('HTTP_HOST')
        if self.__environ.has_key('HTTP_X_FORWARDED_FOR'):
            host = self.__environ['HTTP_X_FORWARDED_FOR']
        if not host:
            # Missing host header, so reconstruct the host from the
            # server name and port
            default_port = {'http': 80, 'https': 443}
            name = self.__environ.get('SERVER_NAME', 'localhost')
            if port and port != default_port[scheme]:
                host = '%s:%d' % (name, port)
            else:
                host = name
        from urlparse import urlunparse
        self.base_url = urlunparse((scheme, host, self.cgi_location, None, None,
                                   None))

        self.args = TracFieldStorage(self.__input, environ=self.__environ,
                                     keep_blank_values=1)

        # Populate the HDF with some HTTP info
        # FIXME: Ideally, the templates shouldn't even need this data
        self.hdf.setValue('HTTP.Protocol', scheme)
        self.hdf.setValue('HTTP.Host', host)

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
    try:
        req = CGIRequest()
        req.init_request()
        env = open_environment()
        env.href = Href(req.cgi_location)
        env.abs_href = Href(req.base_url)
        dispatch_request(os.getenv('PATH_INFO', ''), req, env)
    except Exception, e:
        send_pretty_error(e, env, req)
