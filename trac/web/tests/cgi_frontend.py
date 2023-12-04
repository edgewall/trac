# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2023 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

import io
import sys
import unittest

from trac.test import makeSuite, mkdtemp, rmtree
from trac.web.cgi_frontend import CGIGateway
from trac.web.main import send_project_index


class CGIRequestTestCase(unittest.TestCase):

    def setUp(self):
        self.files = (sys.stdout, sys.stderr)
        self.outbuf = io.BytesIO()
        self.errbuf = io.BytesIO()
        sys.stdout = io.TextIOWrapper(self.outbuf, encoding='utf-8',
                                      newline='\n')
        sys.stderr = io.TextIOWrapper(self.errbuf, encoding='utf-8',
                                      newline='\n', write_through=True)
        self.tmpdir = mkdtemp()

    def tearDown(self):
        sys.stdout, sys.stderr = self.files
        self.outbuf.close()
        self.errbuf.close()
        rmtree(self.tmpdir)

    def test_write_project_index(self):

        # XXX invoke directly send_project_index() to avoid call of
        #     locale.setlocale() from dispatch_request
        def dispatch_request(environ, start_response):
            send_project_index(environ, start_response)
            return []

        gateway = CGIGateway()
        gateway.environ.update({
            'trac.env_parent_dir': self.tmpdir,
            'SERVER_PORT': '80',
            'SERVER_NAME': '127.0.0.1',
            'REQUEST_METHOD': 'GET',
            'PATH_INFO': '/',
        })
        gateway.run(dispatch_request)
        output = self.outbuf.getvalue()
        headers, body = output.split(b'\r\n\r\n', 1)
        self.assertIn(b'<!DOCTYPE html>', body)
        self.assertIn(b'<title>Available Projects</title>', body)
        self.assertIn(b'</html>', body)


def test_suite():
    return makeSuite(CGIRequestTestCase)


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
