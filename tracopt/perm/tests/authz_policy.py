# -*- coding: utf-8 -*-
#
# Copyright (C) 2012-2020 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

import os
import textwrap
import unittest

from trac.core import Component, ComponentMeta, implements
from trac.config import ConfigurationError
from trac.perm import IPermissionRequestor, PermissionCache
from trac.resource import Resource
from trac.test import EnvironmentStub, Mock, mkdtemp
from trac.util import create_file
from trac.versioncontrol.api import Repository
from tracopt.perm.authz_policy import AuthzPolicy


class AuthzPolicyTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        class TestPermissionRequestor(Component):
            implements(IPermissionRequestor)

            def get_permission_actions(self):
                perms = ['TEST_VIEW', 'TEST_CREATE', 'TEST_DELETE',
                         'TEST_MODIFY']
                return [('TEST_ADMIN', perms)] + perms

        cls.permission_requestors = [TestPermissionRequestor]

    @classmethod
    def tearDownClass(cls):
        for component in cls.permission_requestors:
            ComponentMeta.deregister(component)

    def setUp(self):
        temp_dir = mkdtemp()
        self.authz_file = os.path.join(temp_dir, 'trac-authz-policy')
        create_file(self.authz_file, textwrap.dedent("""\
            # -*- coding: utf-8 -*-
            # Unicode user names
            [groups]
            administrators = éat

            [wiki:WikiStart]
            änon = WIKI_VIEW
            John = WIKI_VIEW
            @administrators = WIKI_VIEW
            * =

            # Unicode page names
            [wiki:résumé]
            änon =
            @administrators = WIKI_VIEW
            * =

            # Tickets
            [ticket:43]
            änon = TICKET_VIEW
            @administrators =
            * =

            [ticket:*]
            änon =
            @administrators = TICKET_VIEW
            * =

            # Default repository
            [repository:@*]
            änon =
            @administrators = BROWSER_VIEW, FILE_VIEW
            * =

            # Non-default repository
            [repository:bláh@*]
            änon = BROWSER_VIEW, FILE_VIEW
            @administrators = BROWSER_VIEW, FILE_VIEW
            * =

            [milestone:milestone1]
            anonymous = MILESTONE_VIEW
            """))
        self.env = EnvironmentStub(enable=['trac.perm.*', AuthzPolicy] +
                                          self.permission_requestors,
                                   path=temp_dir,
                                   config=[('logging', 'log_level', 'WARNING')])
        self.env.config.set('trac', 'permission_policies',
                            'AuthzPolicy, DefaultPermissionPolicy')
        self.env.config.set('authz_policy', 'authz_file', self.authz_file)

    def tearDown(self):
        self.env.reset_db_and_disk()

    def check_permission(self, action, user, resource, perm=None):
        authz_policy = AuthzPolicy(self.env)
        return authz_policy.check_permission(action, user, resource, perm)

    def get_repository(self, reponame):
        params = {'id': 1, 'name': reponame}
        return Mock(Repository, 'mock', params, self.env.log)

    def get_perm(self, username, *args):
        perm = PermissionCache(self.env, username)
        if args:
            return perm(*args)
        return perm

    def test_unicode_username(self):
        resource = Resource('wiki', 'WikiStart')

        perm = self.get_perm('anonymous')
        self.assertFalse(
            self.check_permission('WIKI_VIEW', 'anonymous', resource, perm))
        self.assertNotIn('WIKI_VIEW', perm)
        self.assertNotIn('WIKI_VIEW', perm(resource))

        perm = self.get_perm('änon')
        self.assertTrue(
            self.check_permission('WIKI_VIEW', 'änon', resource, perm))
        self.assertNotIn('WIKI_VIEW', perm)
        self.assertIn('WIKI_VIEW', perm(resource))

    def test_case_sensitive_username(self):
        resource = Resource('wiki', 'WikiStart')

        perm = self.get_perm('john')
        self.assertFalse(
            self.check_permission('WIKI_VIEW', 'john', resource, perm))
        self.assertNotIn('WIKI_VIEW', perm)
        self.assertNotIn('WIKI_VIEW', perm(resource))

        perm = self.get_perm('John')
        self.assertTrue(
            self.check_permission('WIKI_VIEW', 'John', resource, perm))
        self.assertNotIn('WIKI_VIEW', perm)
        self.assertIn('WIKI_VIEW', perm(resource))

    def test_unicode_resource_name(self):
        resource = Resource('wiki', 'résumé')

        perm = self.get_perm('anonymous')
        self.assertFalse(
            self.check_permission('WIKI_VIEW', 'anonymous', resource, perm))
        self.assertNotIn('WIKI_VIEW', perm)
        self.assertNotIn('WIKI_VIEW', perm(resource))

        perm = self.get_perm('änon')
        self.assertFalse(
            self.check_permission('WIKI_VIEW', 'änon', resource, perm))
        self.assertNotIn('WIKI_VIEW', perm)
        self.assertNotIn('WIKI_VIEW', perm(resource))

        perm = self.get_perm('éat')
        self.assertTrue(
            self.check_permission('WIKI_VIEW', 'éat', resource, perm))
        self.assertNotIn('WIKI_VIEW', perm)
        self.assertIn('WIKI_VIEW', perm(resource))

    def test_resource_without_id(self):
        perm = self.get_perm('anonymous')
        self.assertNotIn('TICKET_VIEW', perm)
        self.assertNotIn('TICKET_VIEW', perm('ticket'))
        self.assertNotIn('TICKET_VIEW', perm('ticket', 42))
        self.assertNotIn('TICKET_VIEW', perm('ticket', 43))

        perm = self.get_perm('änon')
        self.assertNotIn('TICKET_VIEW', perm)
        self.assertNotIn('TICKET_VIEW', perm('ticket'))
        self.assertNotIn('TICKET_VIEW', perm('ticket', 42))
        self.assertIn('TICKET_VIEW', perm('ticket', 43))

        perm = self.get_perm('éat')
        self.assertNotIn('TICKET_VIEW', perm)
        self.assertIn('TICKET_VIEW', perm('ticket'))
        self.assertIn('TICKET_VIEW', perm('ticket', 42))
        self.assertNotIn('TICKET_VIEW', perm('ticket', 43))

    def test_default_repository(self):
        repos = self.get_repository('')
        self.assertFalse(repos.is_viewable(self.get_perm('anonymous')))
        self.assertFalse(repos.is_viewable(self.get_perm('änon')))
        self.assertTrue(repos.is_viewable(self.get_perm('éat')))

    def test_non_default_repository(self):
        repos = self.get_repository('bláh')
        self.assertFalse(repos.is_viewable(self.get_perm('anonymous')))
        self.assertTrue(repos.is_viewable(self.get_perm('änon')))
        self.assertTrue(repos.is_viewable(self.get_perm('éat')))

    def test_case_sensitive_resource(self):
        resource = Resource('WIKI', 'wikistart')
        self.assertIsNone(
            self.check_permission('WIKI_VIEW', 'anonymous', resource))
        self.assertIsNone(
            self.check_permission('WIKI_VIEW', 'änon', resource))

    def test_authenticated_inherits_anonymous_permission(self):
        """Metagroup authenticated inherits all permissions granted to
        anonymous.
        """
        resource = Resource('milestone', 'milestone1')
        self.assertTrue(self.check_permission('MILESTONE_VIEW',
                                              'anonymous', resource))
        self.assertTrue(self.check_permission('MILESTONE_VIEW',
                                              'authenticated', resource))
        self.assertIn('MILESTONE_VIEW', self.get_perm('anonymous',
                                                      resource))
        self.assertIn('MILESTONE_VIEW', self.get_perm('authenticated',
                                                      resource))

    def test_undefined_action_is_logged(self):
        """Undefined action is logged at warning level."""
        create_file(self.authz_file, textwrap.dedent("""\
            [groups]
            administrators = éat
            [wiki:WikiStart]
            änon = UNKNOWN_VIEW, TEST_CREATE, !TEST_MODIFY
            [milestone:milestone1]
            * = UNKNOWN_MODIFY, !TEST_VIEW
            """))
        authz_policy = AuthzPolicy(self.env)
        authz_policy.parse_authz()

        self.assertEqual(2, len(self.env.log_messages))
        self.assertIn(('WARNING',
                       'The action UNKNOWN_VIEW in the [wiki:WikiStart] '
                       'section of trac-authz-policy is not a valid action.'),
                      self.env.log_messages)
        self.assertIn(('WARNING',
                       'The action UNKNOWN_MODIFY in the [milestone:milestone1] '
                       'section of trac-authz-policy is not a valid action.'),
                      self.env.log_messages)

    def test_get_authz_file(self):
        """get_authz_file should resolve a relative path."""
        authz_policy = AuthzPolicy(self.env)
        authz_file = authz_policy.authz_file
        self.assertTrue(os.path.isabs(authz_file))

    def test_get_authz_file_notfound_raises(self):
        """ConfigurationError exception should be raised if file not found."""
        authz_file = os.path.join(self.env.path, 'some-nonexistent-file')
        self.env.config.set('authz_policy', 'authz_file', authz_file)
        self.assertRaises(ConfigurationError, self.check_permission,
                          'WIKI_VIEW', 'änon', None, None)

    def test_get_authz_file_notdefined_raises(self):
        """ConfigurationError exception should be raised if the option
        `[authz_policy] authz_file` is not specified in trac.ini."""
        self.env.config.remove('authz_policy', 'authz_file')
        self.assertRaises(ConfigurationError, self.check_permission,
                          'WIKI_VIEW', 'änon', None, None)

    def test_get_authz_file_empty_raises(self):
        """ConfigurationError exception should be raised if the option
        `[authz_policy] authz_file` is empty."""
        self.env.config.set('authz_policy', 'authz_file', '')
        self.assertRaises(ConfigurationError, self.check_permission,
                          'WIKI_VIEW', 'änon', None, None)

    def test_get_authz_file_removed_raises(self):
        """ConfigurationError exception is raised if file is removed."""
        os.remove(self.authz_file)
        self.assertRaises(ConfigurationError, self.check_permission,
                          'WIKI_VIEW', 'änon', None, None)

    def test_parse_authz_empty(self):
        """Allow the file to be empty."""
        create_file(self.authz_file, '')
        authz_policy = AuthzPolicy(self.env)
        authz_policy.parse_authz()
        self.assertEqual([], authz_policy.authz.sections())

    def test_parse_authz_no_settings(self):
        """Allow the file to have no settings."""
        create_file(self.authz_file, textwrap.dedent("""\
            # [wiki:WikiStart]
            # änon = WIKI_VIEW
            # * =
            """))
        authz_policy = AuthzPolicy(self.env)
        authz_policy.parse_authz()
        self.assertEqual([], authz_policy.authz.sections())

    def test_parse_authz_malformed_raises(self):
        """ConfigurationError should be raised if the file is malformed."""
        create_file(self.authz_file, textwrap.dedent("""\
            wiki:WikiStart]
            änon = WIKI_VIEW
            * =
            """))
        authz_policy = AuthzPolicy(self.env)
        self.assertRaises(ConfigurationError, authz_policy.parse_authz)

    # def test_parse_authz_duplicated_sections_raises(self):
    #     """ConfigurationError should be raised if the file has duplicate
    #     sections."""
    #     create_file(self.authz_file, textwrap.dedent("""\
    #         [wiki:WikiStart]
    #         änon = WIKI_VIEW
    #
    #         [wiki:WikiStart]
    #         änon = WIKI_VIEW
    #         """))
    #     authz_policy = AuthzPolicy(self.env)
    #     self.assertRaises(ConfigurationError, authz_policy.parse_authz)


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(AuthzPolicyTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
