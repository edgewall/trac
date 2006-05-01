# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2005 Edgewall Software
# Copyright (C) 2004-2005 Christopher Lenz <cmlenz@gmx.de>
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
# Author: Christopher Lenz <cmlenz@gmx.de>
#         Matthew Good <trac@matt-good.net>

from mod_python import apache

from trac.web.main import dispatch_request
from trac.web.wsgi import WSGIGateway, _ErrorsWrapper


class InputWrapper(object):

    def __init__(self, req):
        self.req = req

    def close(self):
        pass

    def read(self, size=-1):
        return self.req.read(size)

    def readline(self):
        return self.req.readline()

    def readlines(self, hint=-1):
        return self.req.readlines(hint)


class ModPythonGateway(WSGIGateway):

    wsgi_multithread = apache.mpm_query(apache.AP_MPMQ_IS_THREADED) > 0
    wsgi_multiprocess = apache.mpm_query(apache.AP_MPMQ_IS_FORKED) > 0

    def __init__(self, req, options):
        environ = {}
        environ.update(apache.build_cgi_env(req))
        environ['mod_python.options'] = options
        environ['mod_python.subprocess_env'] = req.subprocess_env
        WSGIGateway.__init__(self, environ, InputWrapper(req),
                             _ErrorsWrapper(lambda x: req.log_error(x)))
        self.req = req

    def _send_headers(self):
        assert self.headers_set, 'Response not started'

        if not self.headers_sent:
            status, headers = self.headers_sent = self.headers_set
            self.req.status = int(status[:3])
            for name, value in headers:
                if name.lower() == 'content-length':
                    self.req.set_content_length(int(value))
                elif name.lower() == 'content-type':
                    self.req.content_type = value
                else:
                    self.req.headers_out.add(name, value)

    def _sendfile(self, fileobj):
        self._send_headers()
        self.req.sendfile(fileobj.name)

    def _write(self, data):
        self._send_headers()
        try:
            self.req.write(data)
        except IOError, e:
            if 'client closed connection' not in str(e):
                raise


def handler(req):
    options = req.get_options()
    gateway = ModPythonGateway(req, options)
    gateway.run(dispatch_request)
    return apache.OK
