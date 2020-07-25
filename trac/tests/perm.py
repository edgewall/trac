# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2020 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

import unittest

from trac import perm
from trac.admin.console import TracAdmin
from trac.admin.test import TracAdminTestCaseBase
from trac.core import Component, ComponentMeta, TracError, implements
from trac.resource import Resource
from trac.test import EnvironmentStub

# IPermissionRequestor implementations
import trac.about
import trac.admin.web_ui
import trac.perm
import trac.search.web_ui
import trac.ticket.api
import trac.ticket.batch
import trac.ticket.report
import trac.ticket.roadmap
import trac.timeline.web_ui
import trac.versioncontrol.admin
import trac.versioncontrol.web_ui.browser
import trac.versioncontrol.web_ui.changeset
import trac.versioncontrol.web_ui.log
import trac.web.chrome
import trac.wiki.web_ui


class DefaultPermissionStoreTestCase(unittest.TestCase):

    def setUp(self):
        self.env = \
            EnvironmentStub(enable=[perm.DefaultPermissionStore,
                                    perm.DefaultPermissionGroupProvider])
        self.store = perm.DefaultPermissionStore(self.env)

    def tearDown(self):
        self.env.reset_db()

    def test_simple_actions(self):
        self.env.db_transaction.executemany(
            "INSERT INTO permission VALUES (%s,%s)",
            [('john', 'WIKI_MODIFY'),
             ('john', 'REPORT_ADMIN'),
             ('kate', 'TICKET_CREATE')])
        self.assertEqual(['REPORT_ADMIN', 'WIKI_MODIFY'],
                         self.store.get_user_permissions('john'))
        self.assertEqual(['TICKET_CREATE'],
                         self.store.get_user_permissions('kate'))

    def test_simple_group(self):
        self.env.db_transaction.executemany(
            "INSERT INTO permission VALUES (%s,%s)",
            [('dev', 'WIKI_MODIFY'),
             ('dev', 'REPORT_ADMIN'),
             ('john', 'dev')])
        self.assertEqual(['REPORT_ADMIN', 'WIKI_MODIFY'],
                         self.store.get_user_permissions('john'))

    def test_nested_groups(self):
        self.env.db_transaction.executemany(
            "INSERT INTO permission VALUES (%s,%s)",
            [('dev', 'WIKI_MODIFY'),
             ('dev', 'REPORT_ADMIN'),
             ('admin', 'dev'),
             ('john', 'admin')])
        self.assertEqual(['REPORT_ADMIN', 'WIKI_MODIFY'],
                         self.store.get_user_permissions('john'))

    def test_mixed_case_group(self):
        self.env.db_transaction.executemany(
            "INSERT INTO permission VALUES (%s,%s)",
            [('Dev', 'WIKI_MODIFY'),
             ('Dev', 'REPORT_ADMIN'),
             ('Admin', 'Dev'),
             ('john', 'Admin')])
        self.assertEqual(['REPORT_ADMIN', 'WIKI_MODIFY'],
                         self.store.get_user_permissions('john'))

    def test_builtin_groups(self):
        self.env.db_transaction.executemany(
            "INSERT INTO permission VALUES (%s,%s)",
            [('authenticated', 'WIKI_MODIFY'),
             ('authenticated', 'REPORT_ADMIN'),
             ('anonymous', 'TICKET_CREATE')])
        self.assertEqual(['REPORT_ADMIN', 'TICKET_CREATE', 'WIKI_MODIFY'],
                         self.store.get_user_permissions('john'))
        self.assertEqual(['TICKET_CREATE'],
                         self.store.get_user_permissions('anonymous'))

    def test_get_all_permissions(self):
        self.env.db_transaction.executemany(
            "INSERT INTO permission VALUES (%s,%s)",
            [('dev', 'WIKI_MODIFY'),
             ('dev', 'REPORT_ADMIN'),
             ('john', 'dev')])
        expected = [('dev', 'WIKI_MODIFY'),
                    ('dev', 'REPORT_ADMIN'),
                    ('john', 'dev')]
        for res in self.store.get_all_permissions():
            self.assertIn(res, expected)

    def test_get_permission_groups(self):
        self.env.db_transaction.executemany(
            "INSERT INTO permission VALUES (%s,%s)",
            [('user1', 'group1'),
             ('group1', 'group2'),
             ('group2', 'group3'),
             ('user2', 'group4'),
             ('user1', 'group5'),
             ('group6', 'group7'),
             ('user3', 'group8'),  # test recursion
             ('group8', 'group9'),
             ('group9', 'group8'),
             ('user3', 'group11'),
             ('group11', 'group10'),  # test recursion
             ('group10', 'group11'),
             ('group10', 'group10')])
        self.assertEqual(['group1', 'group2', 'group3', 'group5'],
                         self.store.get_permission_groups('user1'))
        self.assertEqual(['group4'],
                         self.store.get_permission_groups('user2'))
        self.assertEqual(['group10', 'group11', 'group8', 'group9'],
                         self.store.get_permission_groups('user3'))


class BaseTestCase(unittest.TestCase):

    permission_requestors = []

    @classmethod
    def setUpClass(cls):
        class TestPermissionRequestor(Component):
            implements(perm.IPermissionRequestor)

            def get_permission_actions(self):
                return ['TEST_CREATE', 'TEST_DELETE', 'TEST_MODIFY',
                        ('TEST_CREATE', []),
                        ('TEST_ADMIN', ['TEST_CREATE', 'TEST_DELETE']),
                        ('TEST_ADMIN', ['TEST_MODIFY'])]

        cls.permission_requestors = [TestPermissionRequestor]

    @classmethod
    def tearDownClass(cls):
        for component in cls.permission_requestors:
            ComponentMeta.deregister(component)


class PermissionErrorTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()

    def test_default_message(self):
        permission_error = perm.PermissionError()
        self.assertIsNone(permission_error.action)
        self.assertIsNone(permission_error.resource)
        self.assertIsNone(permission_error.env)
        self.assertEqual("Insufficient privileges to perform this operation.",
                         unicode(permission_error))
        self.assertEqual("Forbidden", permission_error.title)
        self.assertEqual(unicode(permission_error), permission_error.message)

    def test_message_specified(self):
        message = "The message."
        permission_error = perm.PermissionError(msg=message)
        self.assertEqual(message, unicode(permission_error))

    def test_message_from_action(self):
        action = 'WIKI_VIEW'
        permission_error = perm.PermissionError(action)
        self.assertEqual(action, permission_error.action)
        self.assertIsNone(permission_error.resource)
        self.assertIsNone(permission_error.env)
        self.assertEqual("WIKI_VIEW privileges are required to perform this "
                         "operation. You don't have the required "
                         "permissions.", unicode(permission_error))

    def test_message_from_action_and_resource(self):
        action = 'WIKI_VIEW'
        resource = Resource('wiki', 'WikiStart')
        permission_error = perm.PermissionError(action, resource, self.env)
        self.assertEqual(action, permission_error.action)
        self.assertEqual(resource, permission_error.resource)
        self.assertEqual(self.env, permission_error.env)
        self.assertEqual("WIKI_VIEW privileges are required to perform this "
                         "operation on WikiStart. You don't have the "
                         "required permissions.", unicode(permission_error))

    def test_message_from_action_and_resource_without_id(self):
        action = 'TIMELINE_VIEW'
        resource = Resource('timeline')
        permission_error = perm.PermissionError(action, resource, self.env)
        self.assertEqual(action, permission_error.action)
        self.assertEqual(resource, permission_error.resource)
        self.assertEqual(self.env, permission_error.env)
        self.assertEqual("TIMELINE_VIEW privileges are required to perform "
                         "this operation. You don't have the required "
                         "permissions.", unicode(permission_error))


class PermissionSystemTestCase(BaseTestCase):

    def setUp(self):
        self.env = EnvironmentStub(enable=[perm.PermissionSystem,
                                           perm.DefaultPermissionGroupProvider,
                                           perm.DefaultPermissionStore] +
                                          self.permission_requestors)
        self.perm = perm.PermissionSystem(self.env)

    def tearDown(self):
        self.env.reset_db()

    def test_get_actions(self):
        tpr_perms = ['TEST_ADMIN', 'TEST_CREATE', 'TEST_DELETE', 'TEST_MODIFY']
        all_perms = tpr_perms + ['TRAC_ADMIN']
        self.assertEqual(all_perms, self.perm.get_actions())
        self.assertEqual(tpr_perms,
                         self.perm.get_actions(skip=self.perm))

    def test_actions(self):
        self.assertEqual(self.perm.get_actions(), self.perm.actions)

    def test_actions_is_lazy(self):
        actions = self.perm.actions
        self.assertEqual(id(actions), id(self.perm.actions))

    def test_get_actions_dict(self):
        self.assertEqual({
            'TEST_ADMIN': ['TEST_CREATE', 'TEST_DELETE', 'TEST_MODIFY'],
            'TEST_CREATE': [],
            'TEST_DELETE': [],
            'TEST_MODIFY': [],
            'TRAC_ADMIN': ['TEST_ADMIN', 'TEST_CREATE', 'TEST_DELETE',
                           'TEST_MODIFY'],
        }, self.perm.get_actions_dict())
        self.assertEqual({
            'TEST_ADMIN': ['TEST_CREATE', 'TEST_DELETE', 'TEST_MODIFY'],
            'TEST_CREATE': [],
            'TEST_DELETE': [],
            'TEST_MODIFY': [],
        }, self.perm.get_actions_dict(skip=self.perm))

    def test_all_permissions(self):
        self.assertEqual({'TRAC_ADMIN': True, 'TEST_CREATE': True,
                          'TEST_DELETE': True, 'TEST_MODIFY': True,
                          'TEST_ADMIN': True},
                         self.perm.get_user_permissions())

    def test_simple_permissions(self):
        self.perm.grant_permission('bob', 'TEST_CREATE')
        self.perm.grant_permission('jane', 'TEST_DELETE')
        self.perm.grant_permission('jane', 'TEST_MODIFY')
        self.assertEqual({'TEST_CREATE': True},
                         self.perm.get_user_permissions('bob'))
        self.assertEqual({'TEST_DELETE': True, 'TEST_MODIFY': True},
                         self.perm.get_user_permissions('jane'))

    def test_meta_permissions(self):
        self.perm.grant_permission('bob', 'TEST_CREATE')
        self.perm.grant_permission('jane', 'TEST_ADMIN')
        self.assertEqual({'TEST_CREATE': True},
                         self.perm.get_user_permissions('bob'))
        self.assertEqual({'TEST_CREATE': True, 'TEST_DELETE': True,
                          'TEST_MODIFY': True,  'TEST_ADMIN': True},
                         self.perm.get_user_permissions('jane'))

    def test_undefined_permissions(self):
        """Only defined actions are returned in the dictionary."""
        self.perm.grant_permission('bob', 'TEST_CREATE')
        self.perm.grant_permission('jane', 'TEST_DELETE')
        self.perm.grant_permission('jane', 'TEST_MODIFY')

        self.env.disable_component(self.permission_requestors[0])

        self.assertEqual({}, self.perm.get_user_permissions('bob'))
        self.assertEqual({}, self.perm.get_user_permissions('jane'))

    def test_grant_permission_differs_from_action_by_casing(self):
        """`TracError` is raised when granting a permission that differs
        from an action by casing.
        """
        self.assertRaises(TracError, self.perm.grant_permission, 'user1',
                          'Test_Create')

    def test_grant_permission_already_granted(self):
        """`PermissionExistsError` is raised when granting a permission
        that has already been granted.
        """
        self.perm.grant_permission('user1', 'TEST_CREATE')
        self.assertRaises(perm.PermissionExistsError,
                          self.perm.grant_permission, 'user1', 'TEST_CREATE')

    def test_grant_permission_already_in_group(self):
        """`PermissionExistsError` is raised when adding a user to
        a group of which they are already a member.
        """
        self.perm.grant_permission('user1', 'group1')
        self.assertRaises(perm.PermissionExistsError,
                          self.perm.grant_permission, 'user1', 'group1')

    def test_get_all_permissions(self):
        self.perm.grant_permission('bob', 'TEST_CREATE')
        self.perm.grant_permission('jane', 'TEST_ADMIN')
        expected = [('bob', 'TEST_CREATE'),
                    ('jane', 'TEST_ADMIN')]
        for res in self.perm.get_all_permissions():
            self.assertIn(res, expected)

    def test_get_groups_dict(self):
        permissions = [
            ('user2', 'group1'),
            ('user1', 'group1'),
            ('user3', 'group1'),
            ('user3', 'group2')
        ]
        for perm_ in permissions:
            self.perm.grant_permission(*perm_)

        groups = self.perm.get_groups_dict()
        self.assertEqual(2, len(groups))
        self.assertEqual(['user1', 'user2', 'user3'], groups['group1'])
        self.assertEqual(['user3'], groups['group2'])

    def test_get_users_dict(self):
        permissions = [
            ('user2', 'TEST_CREATE'),
            ('user1', 'TEST_DELETE'),
            ('user1', 'TEST_ADMIN'),
            ('user1', 'TEST_CREATE')
        ]
        for perm_ in permissions:
            self.perm.grant_permission(*perm_)

        users = self.perm.get_users_dict()
        self.assertEqual(2, len(users))
        self.assertEqual(['TEST_ADMIN', 'TEST_CREATE', 'TEST_DELETE'],
                         users['user1'])
        self.assertEqual(['TEST_CREATE'], users['user2'])

    def test_get_permission_groups(self):
        permissions = [
            ('user1', 'group1'),
            ('group1', 'group2'),
            ('group2', 'group3'),
            ('user2', 'group4'),
            ('user1', 'group5'),
            ('group6', 'group7'),
            ('user3', 'group8'), # test recursion
            ('group8', 'group9'),
            ('group9', 'group8'),
            ('user3', 'group11'),
            ('group11', 'group10'),  # test recursion
            ('group10', 'group11'),
            ('group10', 'group10'),
        ]
        for perm_ in permissions:
            self.perm.grant_permission(*perm_)

        self.assertEqual(['anonymous', 'authenticated', 'group1', 'group2',
                          'group3', 'group5'],
                         self.perm.get_permission_groups('user1'))
        self.assertEqual(['anonymous', 'authenticated', 'group4'],
                         self.perm.get_permission_groups('user2'))
        self.assertEqual(['anonymous', 'authenticated', 'group10', 'group11',
                          'group8', 'group9'],
                         self.perm.get_permission_groups('user3'))

    def test_expand_actions_iter_7467(self):
        # Check that expand_actions works with iterators (#7467)
        perms = ['TEST_ADMIN', 'TEST_CREATE', 'TEST_DELETE', 'TEST_MODIFY',
                 'TRAC_ADMIN']
        self.assertEqual(perms, self.perm.expand_actions(['TRAC_ADMIN']))
        self.assertEqual(perms, self.perm.expand_actions(iter(['TRAC_ADMIN'])))


class PermissionCacheTestCase(BaseTestCase):

    def setUp(self):
        self.env = EnvironmentStub(enable=[perm.DefaultPermissionStore,
                                           perm.DefaultPermissionPolicy] +
                                          self.permission_requestors)
        self.env.config.set('trac', 'permission_policies',
                            'DefaultPermissionPolicy')
        self.perm_system = perm.PermissionSystem(self.env)
        # by-pass DefaultPermissionPolicy cache:
        perm.DefaultPermissionPolicy.CACHE_EXPIRY = -1
        self.perm_system.grant_permission('testuser', 'TEST_MODIFY')
        self.perm_system.grant_permission('testuser', 'TEST_ADMIN')
        self.perm = perm.PermissionCache(self.env, 'testuser')

    def tearDown(self):
        self.env.reset_db()

    def test_contains(self):
        self.assertIn('TEST_MODIFY', self.perm)
        self.assertIn('TEST_ADMIN', self.perm)
        self.assertNotIn('TRAC_ADMIN', self.perm)

    def test_has_permission(self):
        self.assertTrue(self.perm.has_permission('TEST_MODIFY'))
        self.assertTrue(self.perm.has_permission('TEST_ADMIN'))
        self.assertFalse(self.perm.has_permission('TRAC_ADMIN'))

    def test_require(self):
        self.perm.require('TEST_MODIFY')
        self.perm.require('TEST_ADMIN')
        with self.assertRaises(perm.PermissionError):
            self.perm.require('TRAC_ADMIN')

    def test_assert_permission(self):
        self.perm.assert_permission('TEST_MODIFY')
        self.perm.assert_permission('TEST_ADMIN')
        with self.assertRaises(perm.PermissionError):
            self.perm.assert_permission('TRAC_ADMIN')

    def test_cache(self):
        self.perm.require('TEST_MODIFY')
        self.perm.require('TEST_ADMIN')
        self.perm_system.revoke_permission('testuser', 'TEST_ADMIN')
        # Using cached GRANT here
        self.perm.require('TEST_ADMIN')

    def test_cache_shared(self):
        # we need to start with an empty cache here (#7201)
        perm1 = perm.PermissionCache(self.env, 'testcache')
        perm1 = perm1('ticket', 1)
        perm2 = perm1('ticket', 1) # share internal cache
        self.perm_system.grant_permission('testcache', 'TEST_ADMIN')
        perm1.require('TEST_ADMIN')
        self.perm_system.revoke_permission('testcache', 'TEST_ADMIN')
        # Using cached GRANT here (from shared cache)
        perm2.require('TEST_ADMIN')

    def test_has_permission_on_resource_none(self):
        """'PERM' in perm(None) should cache the same value as
        'PERM' in perm(None) (#12597).
        """
        'TEST_ADMIN' in self.perm
        self.assertEqual(1, len(self.perm._cache))
        'TEST_ADMIN' in self.perm(None)
        self.assertEqual(1, len(self.perm._cache))


class TestPermissionPolicy(Component):
    implements(perm.IPermissionPolicy)

    def __init__(self):
        self.allowed = {}
        self.results = {}

    def grant(self, username, permissions):
        self.allowed.setdefault(username, set()).update(permissions)

    def revoke(self, username, permissions):
        self.allowed.setdefault(username, set()).difference_update(permissions)

    def check_permission(self, action, username, resource, perm):
        result = action in self.allowed.get(username, set()) or None
        self.results[(username, action)] = result
        return result


class PermissionPolicyTestCase(BaseTestCase):

    def setUp(self):
        self.env = EnvironmentStub(enable=[perm.DefaultPermissionStore,
                                           perm.DefaultPermissionPolicy,
                                           TestPermissionPolicy] +
                                          self.permission_requestors)
        self.env.config.set('trac', 'permission_policies',
                            'TestPermissionPolicy')
        self.policy = TestPermissionPolicy(self.env)
        self.perm = perm.PermissionCache(self.env, 'testuser')

    def tearDown(self):
        self.env.reset_db()

    def test_no_permissions(self):
        self.assertRaises(perm.PermissionError,
                          self.perm.require, 'TEST_MODIFY')
        self.assertRaises(perm.PermissionError,
                          self.perm.require, 'TEST_ADMIN')
        self.assertEqual(self.policy.results,
                         {('testuser', 'TEST_MODIFY'): None,
                          ('testuser', 'TEST_ADMIN'): None})

    def test_grant_revoke_permissions(self):
        self.policy.grant('testuser', ['TEST_MODIFY', 'TEST_ADMIN'])
        self.assertIn('TEST_MODIFY', self.perm)
        self.assertIn('TEST_ADMIN', self.perm)
        self.assertEqual(self.policy.results,
                         {('testuser', 'TEST_MODIFY'): True,
                          ('testuser', 'TEST_ADMIN'): True})

    def test_policy_chaining(self):
        self.env.config.set('trac', 'permission_policies',
                            'TestPermissionPolicy,DefaultPermissionPolicy')
        self.policy.grant('testuser', ['TEST_MODIFY'])
        system = perm.PermissionSystem(self.env)
        system.grant_permission('testuser', 'TEST_ADMIN')

        self.assertEqual(list(system.policies),
                         [self.policy,
                          perm.DefaultPermissionPolicy(self.env)])
        self.assertIn('TEST_MODIFY', self.perm)
        self.assertIn('TEST_ADMIN', self.perm)
        self.assertEqual(self.policy.results,
                         {('testuser', 'TEST_MODIFY'): True,
                          ('testuser', 'TEST_ADMIN'): None})


class RecursivePolicyTestCase(unittest.TestCase):
    """Test case for policies that perform recursive permission checks."""

    permission_policies = []
    decisions = []

    @classmethod
    def setUpClass(cls):

        class PermissionPolicy1(Component):

            implements(perm.IPermissionPolicy)

            def __init__(self):
                self.call_count = 0
                self.decisions = cls.decisions

            def check_permission(self, action, username, resource, perm):
                self.call_count += 1
                decision = None
                if 'ACTION_2' in perm(resource):
                    decision = None
                elif action == 'ACTION_1':
                    decision = username == 'user1'
                self.decisions.append(('policy1', action, decision))
                return decision

        class PermissionPolicy2(Component):

            implements(perm.IPermissionPolicy)

            def __init__(self):
                self.call_count = 0
                self.decisions = cls.decisions

            def check_permission(self, action, username, resource, perm):
                self.call_count += 1
                decision = None
                if action == 'ACTION_2':
                    decision = username == 'user2'
                self.decisions.append(('policy2', action, decision))
                return decision

        cls.permission_policies = [PermissionPolicy1, PermissionPolicy2]

    @classmethod
    def tearDownClass(cls):
        from trac.core import ComponentMeta
        for component in cls.permission_policies:
            ComponentMeta.deregister(component)

    def setUp(self):
        self.__class__.decisions = []
        self.env = EnvironmentStub(enable=self.permission_policies)
        self.env.config.set('trac', 'permission_policies',
                            'PermissionPolicy1, PermissionPolicy2')
        self.ps = perm.PermissionSystem(self.env)

    def tearDown(self):
        self.env.reset_db()

    def test_user1_allowed_by_policy1(self):
        """policy1 consulted for ACTION_1. policy1 and policy2 consulted
        for ACTION_2.
        """
        perm_cache = perm.PermissionCache(self.env, 'user1')
        self.assertIn('ACTION_1', perm_cache)
        self.assertEqual(2, self.ps.policies[0].call_count)
        self.assertEqual(1, self.ps.policies[1].call_count)
        self.assertEqual([
            ('policy1', 'ACTION_2', None),
            ('policy2', 'ACTION_2', False),
            ('policy1', 'ACTION_1', True),
        ], self.decisions)

    def test_user2_denied_by_no_decision(self):
        """policy1 and policy2 consulted for ACTION_1. policy1 and
        policy2 consulted for ACTION_2.
        """
        perm_cache = perm.PermissionCache(self.env, 'user2')
        self.assertNotIn('ACTION_1', perm_cache)
        self.assertEqual(2, self.ps.policies[0].call_count)
        self.assertEqual(2, self.ps.policies[1].call_count)
        self.assertEqual([
            ('policy1', 'ACTION_2', None),
            ('policy2', 'ACTION_2', True),
            ('policy1', 'ACTION_1', None),
            ('policy2', 'ACTION_1', None),
        ], self.decisions)

    def test_user1_denied_by_policy2(self):
        """policy1 consulted for ACTION_2. policy2 consulted for ACTION_2.
        """
        perm_cache = perm.PermissionCache(self.env, 'user1')
        self.assertNotIn('ACTION_2', perm_cache)
        self.assertEqual(1, self.ps.policies[0].call_count)
        self.assertEqual(1, self.ps.policies[1].call_count)
        self.assertEqual([
            ('policy1', 'ACTION_2', None),
            ('policy2', 'ACTION_2', False),
        ], self.decisions)

    def test_user1_allowed_by_policy2(self):
        """policy1 consulted for ACTION_2. policy2 consulted for ACTION_2.
        """
        perm_cache = perm.PermissionCache(self.env, 'user2')
        self.assertIn('ACTION_2', perm_cache)
        self.assertEqual(1, self.ps.policies[0].call_count)
        self.assertEqual(1, self.ps.policies[1].call_count)
        self.assertEqual([
            ('policy1', 'ACTION_2', None),
            ('policy2', 'ACTION_2', True),
        ], self.decisions)


class TracAdminTestCase(TracAdminTestCaseBase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        self.admin = TracAdmin()
        self.admin.env_set('', self.env)

    def tearDown(self):
        self.env.reset_db()
        self.env = None

    def test_permission_list_ok(self):
        """Tests the 'permission list' command in trac-admin."""
        rv, output = self.execute('permission list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_permission_list_includes_undefined_actions(self):
        """Undefined actions are included in the User Action table,
        but not in the Available Actions list.
        """
        self.env.disable_component(trac.search.web_ui.SearchModule)
        rv, output = self.execute('permission list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_permission_add_one_action_ok(self):
        """
        Tests the 'permission add' command in trac-admin.  This particular
        test passes valid arguments to add one permission and checks for
        success.
        """
        self.execute('permission add test_user WIKI_VIEW')
        rv, output = self.execute('permission list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_permission_add_multiple_actions_ok(self):
        """
        Tests the 'permission add' command in trac-admin.  This particular
        test passes valid arguments to add multiple permissions and checks for
        success.
        """
        self.execute('permission add test_user LOG_VIEW FILE_VIEW')
        rv, output = self.execute('permission list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_permission_add_already_exists(self):
        """
        Tests the 'permission add' command in trac-admin.  This particular
        test passes a permission that already exists and checks for the
        message. Other permissions passed are added.
        """
        rv, output = self.execute('permission add anonymous WIKI_CREATE '
                                   'WIKI_VIEW WIKI_MODIFY')
        self.assertEqual(0, rv, output)
        rv, output2 = self.execute('permission list')
        self.assertEqual(0, rv, output2)
        self.assertExpectedResult(output + output2)

    def test_permission_add_subject_already_in_group(self):
        """
        Tests the 'permission add' command in trac-admin.  This particular
        test passes a group that the subject is already a member of and
        checks for the message. Other permissions passed are added.
        """
        rv, output1 = self.execute('permission add user1 group2')
        self.assertEqual(0, rv, output1)
        rv, output2 = self.execute('permission add user1 group1 group2 '
                                    'group3')
        self.assertEqual(0, rv, output2)
        rv, output3 = self.execute('permission list')
        self.assertEqual(0, rv, output3)
        self.assertExpectedResult(output2 + output3)

    def test_permission_add_differs_from_action_by_casing(self):
        """
        Tests the 'permission add' command in trac-admin.  This particular
        test passes a permission that differs from an action by casing and
        checks for the message. None of the permissions in the list are
        granted.
        """
        rv, output = self.execute('permission add joe WIKI_CREATE '
                                   'Trac_Admin WIKI_MODIFY')
        self.assertEqual(2, rv, output)
        rv, output2 = self.execute('permission list')
        self.assertEqual(0, rv, output2)
        self.assertExpectedResult(output + output2)

    def test_permission_add_unknown_action(self):
        """
        Tests the 'permission add' command in trac-admin.  This particular
        test tries granting NOT_A_PERM to a user. NOT_A_PERM does not exist
        in the system. None of the permissions in the list are granted.
        """
        rv, output = self.execute('permission add joe WIKI_CREATE '
                                   'NOT_A_PERM WIKI_MODIFY')
        self.assertEqual(2, rv, output)
        rv, output2 = self.execute('permission list')
        self.assertEqual(0, rv, output2)
        self.assertExpectedResult(output + output2)

    def test_permission_remove_one_action_ok(self):
        """
        Tests the 'permission remove' command in trac-admin.  This particular
        test passes valid arguments to remove one permission and checks for
        success.
        """
        self.execute('permission remove anonymous TICKET_MODIFY')
        rv, output = self.execute('permission list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_permission_remove_multiple_actions_ok(self):
        """
        Tests the 'permission remove' command in trac-admin.  This particular
        test passes valid arguments to remove multiple permission and checks
        for success.
        """
        self.execute('permission remove anonymous WIKI_CREATE WIKI_MODIFY')
        rv, output = self.execute('permission list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_permission_remove_all_actions_for_user(self):
        """
        Tests the 'permission remove' command in trac-admin.  This particular
        test removes all permissions for anonymous.
        """
        self.execute('permission remove anonymous *')
        rv, output = self.execute('permission list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_permission_remove_action_for_all_users(self):
        """
        Tests the 'permission remove' command in trac-admin.  This particular
        test removes the TICKET_CREATE permission from all users.
        """
        self.execute('permission add anonymous TICKET_CREATE')
        self.execute('permission remove * TICKET_CREATE')
        rv, output = self.execute('permission list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_permission_remove_unknown_user(self):
        """
        Tests the 'permission remove' command in trac-admin.  This particular
        test tries removing a permission from an unknown user.
        """
        rv, output = self.execute('permission remove joe TICKET_VIEW')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_permission_remove_action_not_granted(self):
        """
        Tests the 'permission remove' command in trac-admin.  This particular
        test tries removing TICKET_CREATE from user anonymous, who doesn't
        have that permission.
        """
        rv, output = self.execute('permission remove anonymous TICKET_CREATE')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_permission_remove_action_granted_through_meta_permission(self):
        """
        Tests the 'permission remove' command in trac-admin.  This particular
        test tries removing WIKI_VIEW from a user. WIKI_VIEW has been granted
        through user anonymous."""
        self.execute('permission add joe TICKET_VIEW')
        rv, output = self.execute('permission remove joe WIKI_VIEW')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_permission_remove_unknown_action(self):
        """
        Tests the 'permission remove' command in trac-admin.  This particular
        test tries removing NOT_A_PERM from a user. NOT_A_PERM does not exist
        in the system."""
        rv, output = self.execute('permission remove joe NOT_A_PERM')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_permission_remove_unknown_action_granted(self):
        """
        Tests the 'permission remove' command in trac-admin.  This particular
        test tries removing NOT_A_PERM from a user. NOT_A_PERM does not exist
        in the system, but the user possesses the permission."""
        self.env.db_transaction("""
            INSERT INTO permission VALUES (%s, %s)
        """, ('joe', 'NOT_A_PERM'))
        rv, output = self.execute('permission remove joe NOT_A_PERM')
        self.assertEqual(0, rv, output)
        rv, output = self.execute('permission list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_permission_export_ok(self):
        """
        Tests the 'permission export' command in trac-admin.  This particular
        test exports the default permissions to stdout.
        """
        rv, output = self.execute('permission export')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_permission_import_ok(self):
        """
        Tests the 'permission import' command in trac-admin.  This particular
        test exports additional permissions, removes them and imports them back.
        """
        user = u'test_user\u0250'
        self.execute('permission add ' + user + ' WIKI_VIEW')
        self.execute('permission add ' + user + ' TICKET_VIEW')
        rv, output = self.execute('permission export')
        self.execute('permission remove ' + user + ' *')
        rv, output = self.execute('permission import', input=output)
        self.assertEqual(0, rv, output)
        self.assertEqual('', output)
        rv, output = self.execute('permission list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(DefaultPermissionStoreTestCase))
    suite.addTest(unittest.makeSuite(PermissionErrorTestCase))
    suite.addTest(unittest.makeSuite(PermissionSystemTestCase))
    suite.addTest(unittest.makeSuite(PermissionCacheTestCase))
    suite.addTest(unittest.makeSuite(PermissionPolicyTestCase))
    suite.addTest(unittest.makeSuite(RecursivePolicyTestCase))
    suite.addTest(unittest.makeSuite(TracAdminTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
