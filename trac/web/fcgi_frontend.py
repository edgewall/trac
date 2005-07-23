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

from trac.web.cgi_frontend import *
from trac.web.main import RequestDone, get_environment
from trac.util import TracError, enum, href_join

import _thfcgi, locale, sys

def run():
    locale.setlocale(locale.LC_ALL, '')
    _thfcgi.THFCGI(_handler).run()

class FCGIRequest(CGIRequest):
    def __init__(self, environ, input, output, fieldStorage):
        self._fieldStorage = fieldStorage
        CGIRequest.__init__(self, environ, input, output)

    def _getFieldStorage(self):
        return self._fieldStorage


def _handler(_req, _env, _fieldStorage):
      req = FCGIRequest(_env, _req.stdin, _req.out, _fieldStorage)
      env = get_environment(req, os.environ)

      if not env:
          return

      try:  
          dispatch_request(req.path_info, req, env)
      except Exception, e:
          send_pretty_error(e, env, req)

#      _req.finish()
