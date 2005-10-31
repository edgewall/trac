# -*- coding: utf-8 -*-
#
# Copyright (C) 2005 Edgewall Software
# Copyright (C) 2005 Matthew Good <trac@matt-good.net>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://projects.edgewall.com/trac/.
#
# Author: Matthew Good <trac@matt-good.net>

from trac.web.api import RequestDone
from trac.web.cgi_frontend import CGIRequest
from trac.web.main import dispatch_request, get_environment, \
                          send_pretty_error, send_project_index

import _thfcgi
#import _fcgi
import os
import locale

def run():
    locale.setlocale(locale.LC_ALL, '')
    _thfcgi.THFCGI(_handler).run()
    #_fcgi.Server(_handler).run()

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
        send_project_index(req, os.environ)
        return

    try:  
        dispatch_request(req.path_info, req, env)
    except Exception, e:
        send_pretty_error(e, env, req)
    return
