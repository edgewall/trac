# -*- coding: utf-8 -*-
#
# Copyright (C) 2012-2013 Edgewall Software
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

from trac.tests import compat
from trac.config import ConfigurationError
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
        self.env = EnvironmentStub(enable=[AuthzPolicy], path=tmpdir)
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

    def test_get_authz_file(self):
        """get_authz_file should resolve a relative path and lazily compute.
        """
        authz_file = self.authz_policy.get_authz_file
        self.assertEqual(os.path.join(self.env.path, 'trac-authz-policy'),
                         authz_file)
        self.assertIs(authz_file, self.authz_policy.get_authz_file)

    def test_get_authz_file_notfound_raises(self):
        """ConfigurationError exception should be raised if file not found."""
        authz_file = os.path.join(self.env.path, 'some-nonexistent-file')
        self.env.config.set('authz_policy', 'authz_file', authz_file)
        self.assertRaises(ConfigurationError, getattr, self.authz_policy,
                          'get_authz_file')

    def test_get_authz_file_notdefined_raises(self):
        """ConfigurationError exception should be raised if the option
        `[authz_policy] authz_file` is not specified in trac.ini."""
        self.env.config.remove('authz_policy', 'authz_file')
        self.assertRaises(ConfigurationError, getattr, self.authz_policy,
                          'get_authz_file')

    def test_get_authz_file_empty_raises(self):
        """ConfigurationError exception should be raised if the option
        `[authz_policy] authz_file` is empty."""
        self.env.config.set('authz_policy', 'authz_file', '')
        self.assertRaises(ConfigurationError, getattr, self.authz_policy,
                          'get_authz_file')

    def test_parse_authz_empty_raises(self):
        """ConfigurationError should be raised if the file is empty."""
        create_file(self.authz_file, "")
        self.assertRaises(ConfigurationError, self.authz_policy.parse_authz)

    def test_parse_authz_malformed_raises(self):
        """ConfigurationError should be raised if the file is malformed."""
        create_file(self.authz_file, """\
wiki:WikiStart]
änon = WIKI_VIEW
* =
""")
        self.assertRaises(ConfigurationError, self.authz_policy.parse_authz)

    def test_parse_authz_duplicated_sections_raises(self):
        """ConfigurationError should be raised if the file has duplicate
        sections."""
        create_file(self.authz_file, """\
[wiki:WikiStart]
änon = WIKI_VIEW

[wiki:WikiStart]
änon = WIKI_VIEW
""")
        self.assertRaises(ConfigurationError, self.authz_policy.parse_authz)


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
