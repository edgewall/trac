# -*- coding: utf-8 -*-
#
# Copyright (C) 2016 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import unittest

from trac.test import EnvironmentStub, MockRequest
from trac.web.api import HTTPBadRequest
from trac.wiki.web_ui import WikiModule


class WikiModuleTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()

    def test_invalid_post_request_raises_exception(self):
        req = MockRequest(self.env, method='POST', action=None)

        self.assertRaises(HTTPBadRequest,
                          WikiModule(self.env).process_request, req)


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(WikiModuleTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
