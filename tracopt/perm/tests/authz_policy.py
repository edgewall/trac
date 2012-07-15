# -*- coding: utf-8 -*-
#
# Copyright (C) 2012 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import os
import tempfile
import unittest
try:
    from configobj import ConfigObj
except ImportError:
    ConfigObj = None

from trac.resource import Resource
from trac.test import EnvironmentStub
from trac.util import create_file
from tracopt.perm.authz_policy import AuthzPolicy


class AuthzPolicyTestCase(unittest.TestCase):

    def setUp(self):
        tmpdir = os.path.realpath(tempfile.gettempdir())
        self.authz_file = os.path.join(tmpdir, 'trac-authz-policy')
        create_file(self.authz_file, """\
# Unicode user names
[groups]
administrators = éat

[wiki:WikiStart]
änon = WIKI_VIEW
@administrators = WIKI_VIEW
* =

# Unicode page names
[wiki:résumé]
änon =
@administrators = WIKI_VIEW
* =
""")
        self.env = EnvironmentStub(enable=[AuthzPolicy])
        self.env.config.set('authz_policy', 'authz_file', self.authz_file)
        self.authz_policy = AuthzPolicy(self.env)

    def tearDown(self):
        self.env.reset_db()
        os.remove(self.authz_file)

    def check_permission(self, action, user, resource, perm):
        return self.authz_policy.check_permission(action, user, resource, perm)

    def test_unicode_username(self):
        resource = Resource('wiki', 'WikiStart')
        self.assertEqual(
            False,
            self.check_permission('WIKI_VIEW', 'anonymous', resource, None))
        self.assertEqual(
            True,
            self.check_permission('WIKI_VIEW', u'änon', resource, None))

    def test_unicode_resource_name(self):
        resource = Resource('wiki', u'résumé')
        self.assertEqual(
            False,
            self.check_permission('WIKI_VIEW', 'anonymous', resource, None))
        self.assertEqual(
            False,
            self.check_permission('WIKI_VIEW', u'änon', resource, None))
        self.assertEqual(
            True,
            self.check_permission('WIKI_VIEW', u'éat', resource, None))


def suite():
    suite = unittest.TestSuite()
    if ConfigObj:
        suite.addTest(unittest.makeSuite(AuthzPolicyTestCase, 'test'))
    else:
        print "SKIP: tracopt/perm/tests/authz_policy.py (no configobj " + \
              "installed)"
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
