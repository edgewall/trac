# -*- coding: utf-8 -*-
#
# Copyright (C) 2014-2023 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/.

import unittest

from trac.core import TracError
from trac.test import EnvironmentStub, MockRequest, makeSuite
from trac.versioncontrol.web_ui.changeset import AnyDiffModule, ChangesetModule
from trac.web.api import RequestDone


class ChangesetModuleTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.cm = ChangesetModule(self.env)

    def test_default_repository_not_configured(self):
        """Test for regression of https://trac.edgewall.org/ticket/11599."""
        req = MockRequest(self.env, args={'new_path': '/'})
        self.assertRaises(TracError, self.cm.process_request, req)


class AnyDiffModuleTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.mod = AnyDiffModule(self.env)

    def test_normal(self):
        req = MockRequest(self.env, path_info='/diff', args={'term': '/'})
        req.environ['HTTP_X_REQUESTED_WITH'] = 'XMLHttpRequest'
        self.assertTrue(self.mod.match_request(req))
        self.assertRaises(RequestDone, self.mod.process_request, req)
        self.assertEqual(b'[]', req.response_sent.getvalue())
        self.assertEqual('application/json;charset=utf-8',
                         req.headers_sent.get('Content-Type'))

    def test_without_term(self):
        req = MockRequest(self.env, path_info='/diff')
        req.environ['HTTP_X_REQUESTED_WITH'] = 'XMLHttpRequest'
        self.assertTrue(self.mod.match_request(req))
        self.assertRaises(RequestDone, self.mod.process_request, req)
        self.assertEqual(b'[]', req.response_sent.getvalue())
        self.assertEqual('application/json;charset=utf-8',
                         req.headers_sent.get('Content-Type'))


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(makeSuite(ChangesetModuleTestCase))
    suite.addTest(makeSuite(AnyDiffModuleTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
