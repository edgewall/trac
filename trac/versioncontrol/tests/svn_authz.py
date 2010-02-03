# -*- coding: utf-8 -*-
#
# Copyright (C) 2010 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import os.path
import tempfile
import unittest

from trac.resource import Resource
from trac.test import EnvironmentStub
from trac.util import create_file
from trac.versioncontrol.svn_authz import AuthzSourcePolicy, ParseError, \
                                          parse


class AuthzParserTestCase(unittest.TestCase):

    def test_parse_file(self):
        authz = parse("""\
[groups]
developers = foo, bar
users = @developers, &baz

[aliases]
baz = CN=Hàröld Hacker,OU=Enginéers,DC=red-bean,DC=com

# Applies to all repositories
[/]
* = r

[/trunk]
@developers = rw
&baz = 
@users = r

[/branches]
bar = rw

; Applies only to module
[module:/trunk]
foo = rw
&baz = r
""")
        self.assertEqual({
            '': {
                '/': {
                    '*': True,
                },
                '/trunk': {
                    'foo': True,
                    'bar': True,
                    u'CN=Hàröld Hacker,OU=Enginéers,DC=red-bean,DC=com': False,
                },
                '/branches': {
                    'bar': True,
                },
            },
            'module': {
                '/trunk': {
                    'foo': True,
                    u'CN=Hàröld Hacker,OU=Enginéers,DC=red-bean,DC=com': True,
                },
            },
        }, authz)

    def test_parse_errors(self):
        self.assertRaises(ParseError, parse, """\
user = r

[module:/trunk]
user = r
""")
        self.assertRaises(ParseError, parse, """\
[module:/trunk]
user
""")


class AuthzSourcePolicyTestCase(unittest.TestCase):

    def setUp(self):
        tmpdir = os.path.realpath(tempfile.gettempdir())
        self.authz = os.path.join(tmpdir, 'trac-authz')
        create_file(self.authz, """\
[groups]
group1 = user
group2 = @group1

cycle1 = @cycle2
cycle2 = @cycle3
cycle3 = @cycle1, user

alias1 = &jekyll
alias2 = @alias1

[aliases]
jekyll = Mr Hyde

# Read / write permissions
[/readonly]
user = r
[/writeonly]
user = w
[/readwrite]
user = rw
[/empty]
user =

# Trailing slashes
[/trailing_a]
user = r
[/trailing_b/]
user = r

# Sub-paths
[/sub/path]
user = r

# Module usage
[module:/module_a]
user = r
[other:/module_b]
user = r
[/module_c]
user = r
[module:/module_d]
user =
[/module_d]
user = r

# Wildcards
[/wildcard]
* = r

# Groups
[/groups_a]
@group1 = r
[/groups_b]
@group2 = r
[/cyclic]
@cycle1 = r

# Precedence
[module:/precedence_a]
user =
[/precedence_a]
user = r
[/precedence_b]
user = r
[/precedence_b/sub]
user =
[/precedence_b/sub/test]
user = r
[/precedence_c]
user =
@group1 = r
[/precedence_d]
@group1 = r
user =

# Aliases
[/aliases_a]
&jekyll = r
[/aliases_b]
@alias2 = r
""")
        self.env = EnvironmentStub(enable=[AuthzSourcePolicy])
        self.env.config.set('trac', 'authz_file', self.authz)
        self.policy = AuthzSourcePolicy(self.env)

    def tearDown(self):
        self.env.reset_db()
        os.remove(self.authz)

    def assertPermission(self, result, user, reponame, path):
        """Assert that `user` is granted access `result` to `path` within
        the repository `reponame`.
        """
        resource = Resource('source', path,
                            parent=Resource('repository', reponame))
        check = self.policy.check_permission('FILE_VIEW', user, resource, None)
        self.assertEqual(result, check)
        
    def test_default_permission(self):
        # By default, no permission is granted
        self.assertPermission(False, 'joe', '', '/not_defined')
        self.assertPermission(False, 'jane', 'repo', '/not/defined/either')

    def test_read_write(self):
        # Allow 'r' and 'rw' entries, deny 'w' and empty entries
        self.assertPermission(True, 'user', '', '/readonly')
        self.assertPermission(True, 'user', '', '/readwrite')
        self.assertPermission(False, 'user', '', '/writeonly')
        self.assertPermission(False, 'user', '', '/empty')

    def test_trailing_slashes(self):
        # Combinations of trailing slashes in the file and in the path
        self.assertPermission(True, 'user', '', '/trailing_a')
        self.assertPermission(True, 'user', '', '/trailing_a/')
        self.assertPermission(True, 'user', '', '/trailing_b')
        self.assertPermission(True, 'user', '', '/trailing_b/')

    def test_sub_path(self):
        # Permissions are inherited from containing directories
        self.assertPermission(True, 'user', '', '/sub/path')
        self.assertPermission(True, 'user', '', '/sub/path/test')
        self.assertPermission(True, 'user', '', '/sub/path/other/sub')
        
    def test_module_usage(self):
        # If a module name is specified, the rules are specific to the module
        self.assertPermission(True, 'user', 'module', '/module_a')
        self.assertPermission(False, 'user', 'module', '/module_b')
        # If a module is specified, but the configuration contains a non-module
        # path, the non-module path can still apply
        self.assertPermission(True, 'user', 'module', '/module_c')
        # The module-specific rule takes precedence
        self.assertPermission(False, 'user', 'module', '/module_d')

    def test_wildcard(self):
        # The * wildcard matches all users
        self.assertPermission(True, 'joe', '', '/wildcard')
        self.assertPermission(True, 'jane', '', '/wildcard')

    def test_groups(self):
        # Groups are specified in a separate section and used with an @ prefix
        self.assertPermission(True, 'user', '', '/groups_a')
        # Groups can also be members of other groups
        self.assertPermission(True, 'user', '', '/groups_b')
        # Groups should not be defined cyclically, but they are still handled
        # correctly to avoid infinite loops
        self.assertPermission(True, 'user', '', '/cyclic')

    def test_precedence(self):
        # Module-specific sections take precedence over non-module sections
        self.assertPermission(False, 'user', 'module', '/precedence_a')
        # The most specific section applies
        self.assertPermission(True, 'user', '', '/precedence_b/sub/test')
        self.assertPermission(False, 'user', '', '/precedence_b/sub')
        self.assertPermission(True, 'user', '', '/precedence_b')
        # Within a section, the first matching rule applies
        self.assertPermission(False, 'user', '', '/precedence_c')
        self.assertPermission(True, 'user', '', '/precedence_d')

    def test_aliases(self):
        # Aliases are specified in a separate section and used with an & prefix
        self.assertPermission(True, 'Mr Hyde', '', '/aliases_a')
        # Aliases can also be used in groups
        self.assertPermission(True, 'Mr Hyde', '', '/aliases_b')


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(AuthzParserTestCase, 'test'))
    suite.addTest(unittest.makeSuite(AuthzSourcePolicyTestCase, 'test'))
    return suite


if __name__ == '__main__':
    runner = unittest.TextTestRunner()
    runner.run(suite())

