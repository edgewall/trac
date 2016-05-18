# -*- coding: utf-8 -*-
#
# Copyright (C) 2014 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

import unittest

from trac.core import TracError
from trac.test import EnvironmentStub, MockRequest
from trac.versioncontrol.web_ui.changeset import ChangesetModule


class ChangesetModuleTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.cm = ChangesetModule(self.env)

    def test_default_repository_not_configured(self):
        """Test for regression of http://trac.edgewall.org/ticket/11599."""
        req = MockRequest(self.env, args={'new_path': '/'})
        self.assertRaises(TracError, self.cm.process_request, req)


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(ChangesetModuleTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
