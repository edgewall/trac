# -*- coding: utf-8 -*-
#
# Copyright (C) 2014 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

from __future__ import print_function

import os
import tempfile
import unittest
try:
    from configobj import ConfigObj
except ImportError:
    ConfigObj = None

import trac.tests.compat
from trac.perm import PermissionCache, PermissionSystem
from trac.test import EnvironmentStub, Mock
from trac.ticket.api import TicketSystem
from trac.ticket.model import Ticket
from trac.util import create_file
from tracopt.perm.authz_policy import AuthzPolicy


class ResetActionTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        self.perm_sys = PermissionSystem(self.env)
        self.ctlr = TicketSystem(self.env).action_controllers[0]
        self.req1 = Mock(authname='user1', args={},
                         perm=PermissionCache(self.env, 'user1'))
        self.req2 = Mock(authname='user2', args={},
                         perm=PermissionCache(self.env, 'user2'))
        self.ticket = Ticket(self.env)
        self.ticket['status'] = 'invalid'
        self.ticket.insert()

    def tearDown(self):
        self.env.reset_db()

    def _reload_workflow(self):
        self.ctlr.actions = self.ctlr.get_all_actions()

    def test_default_reset_action(self):
        """Default reset action."""
        self.perm_sys.grant_permission('user2', 'TICKET_ADMIN')
        self._reload_workflow()

        actions1 = self.ctlr.get_ticket_actions(self.req1, self.ticket)
        actions2 = self.ctlr.get_ticket_actions(self.req2, self.ticket)
        chgs2 = self.ctlr.get_ticket_changes(self.req2, self.ticket, '_reset')

        self.assertEqual(1, len(actions1))
        self.assertNotIn((0, '_reset'), actions1)
        self.assertEqual(2, len(actions2))
        self.assertIn((0, '_reset'), actions2)
        self.assertEqual('new', chgs2['status'])

    def test_custom_reset_action(self):
        """Custom reset action in [ticket-workflow] section."""
        config = self.env.config['ticket-workflow']
        config.set('_reset', '-> review')
        config.set('_reset.operations', 'reset_workflow')
        config.set('_reset.permissions', 'TICKET_BATCH_MODIFY')
        config.set('_reset.default', 2)
        self.perm_sys.grant_permission('user2', 'TICKET_BATCH_MODIFY')
        self._reload_workflow()

        actions1 = self.ctlr.get_ticket_actions(self.req1, self.ticket)
        actions2 = self.ctlr.get_ticket_actions(self.req2, self.ticket)
        chgs2 = self.ctlr.get_ticket_changes(self.req2, self.ticket, '_reset')

        self.assertEqual(1, len(actions1))
        self.assertNotIn((2, '_reset'), actions1)
        self.assertEqual(2, len(actions2))
        self.assertIn((2, '_reset'), actions2)
        self.assertEqual('review', chgs2['status'])


class SetOwnerAttributeTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        self.perm_sys = PermissionSystem(self.env)
        self.ctlr = TicketSystem(self.env).action_controllers[0]
        self.ticket = Ticket(self.env)
        self.ticket['status'] = 'new'
        self.ticket.insert()
        with self.env.db_transaction as db:
            for user in ('user1', 'user2', 'user3', 'user4'):
                db("INSERT INTO session VALUES (%s, %s, %s)", (user, 1, 0))
        permissions = [
            ('user1', 'TICKET_EDIT_CC'),
            ('user2', 'TICKET_EDIT_CC'),
            ('user2', 'TICKET_BATCH_MODIFY'),
            ('user3', 'TICKET_ADMIN'),
            ('user4', 'TICKET_VIEW'),
            ('user1', 'group1'),
            ('user2', 'group1'),
            ('user2', 'group2'),
            ('user3', 'group2'),
            ('user4', 'group3')
        ]
        for perm in permissions:
            self.perm_sys.grant_permission(*perm)
        self.req = Mock(authname='user1', args={},
                        perm=PermissionCache(self.env, 'user0'))
        self.expected = """\
to <select name="action_reassign_reassign_owner" \
id="action_reassign_reassign_owner"><option selected="True" \
value="user1">user1</option><option value="user2">user2</option>\
<option value="user3">user3</option></select>"""

    def _reload_workflow(self):
        self.ctlr.actions = self.ctlr.get_all_actions()

    def tearDown(self):
        self.env.reset_db()

    def test_users(self):
        self.env.config.set('ticket-workflow', 'reassign.set_owner',
                            'user1, user2, user3')
        self._reload_workflow()

        args = self.req, self.ticket, 'reassign'
        label, control, hints = self.ctlr.render_ticket_action_control(*args)

        self.assertEqual(self.expected, str(control))

    def test_groups(self):
        self.env.config.set('ticket-workflow', 'reassign.set_owner',
                            'group1, group2')
        self._reload_workflow()

        args = self.req, self.ticket, 'reassign'
        label, control, hints = self.ctlr.render_ticket_action_control(*args)

        self.assertEqual(self.expected, str(control))

    def test_permission(self):
        self.env.config.set('ticket-workflow', 'reassign.set_owner',
                            'TICKET_EDIT_CC, TICKET_BATCH_MODIFY')
        self._reload_workflow()

        args = self.req, self.ticket, 'reassign'
        label, control, hints = self.ctlr.render_ticket_action_control(*args)

        self.assertEqual(self.expected, str(control))


class RestrictOwnerTestCase(unittest.TestCase):

    def setUp(self):
        tmpdir = os.path.realpath(tempfile.gettempdir())
        self.env = EnvironmentStub(enable=['trac.*', AuthzPolicy], path=tmpdir)
        self.env.config.set('trac', 'permission_policies',
                            'AuthzPolicy, DefaultPermissionPolicy')
        self.env.config.set('ticket', 'restrict_owner', True)

        self.perm_sys = PermissionSystem(self.env)
        self.env.insert_known_users([
            ('user1', '', ''), ('user2', '', ''),
            ('user3', '', ''), ('user4', '', '')
        ])
        self.perm_sys.grant_permission('user1', 'TICKET_MODIFY')
        self.perm_sys.grant_permission('user2', 'TICKET_VIEW')
        self.perm_sys.grant_permission('user3', 'TICKET_MODIFY')
        self.perm_sys.grant_permission('user4', 'TICKET_MODIFY')
        self.authz_file = os.path.join(tmpdir, 'trac-authz-policy')
        create_file(self.authz_file)
        self.env.config.set('authz_policy', 'authz_file', self.authz_file)
        self.ctlr = TicketSystem(self.env).action_controllers[0]
        self.req1 = Mock(authname='user1', args={},
                         perm=PermissionCache(self.env, 'user1'))
        self.ticket = Ticket(self.env)
        self.ticket['status'] = 'new'
        self.ticket.insert()

    def tearDown(self):
        self.env.reset_db()
        os.remove(self.authz_file)

    def _reload_workflow(self):
        self.ctlr.actions = self.ctlr.get_all_actions()

    def test_set_owner(self):
        """Restricted owners list contains users with TICKET_MODIFY.
        """
        ctrl = self.ctlr.render_ticket_action_control(self.req1, self.ticket,
                                                      'reassign')

        self.assertEqual('reassign', ctrl[0])
        self.assertIn('value="user1">user1</option>', str(ctrl[1]))
        self.assertNotIn('value="user2">user2</option>', str(ctrl[1]))
        self.assertIn('value="user3">user3</option>', str(ctrl[1]))
        self.assertIn('value="user4">user4</option>', str(ctrl[1]))

    def test_set_owner_fine_grained_permissions(self):
        """Fine-grained permission checks when populating the restricted
        owners list (#10833).
        """
        create_file(self.authz_file, """\
[ticket:1]
user4 = !TICKET_MODIFY
""")

        ctrl = self.ctlr.render_ticket_action_control(self.req1, self.ticket,
                                                      'reassign')

        self.assertEqual('reassign', ctrl[0])
        self.assertIn('value="user1">user1</option>', str(ctrl[1]))
        self.assertNotIn('value="user2">user2</option>', str(ctrl[1]))
        self.assertIn('value="user3">user3</option>', str(ctrl[1]))
        self.assertNotIn('value="user4">user4</option>', str(ctrl[1]))


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(ResetActionTestCase))
    suite.addTest(unittest.makeSuite(SetOwnerAttributeTestCase))
    if ConfigObj:
        suite.addTest(unittest.makeSuite(RestrictOwnerTestCase))
    else:
        print("SKIP:", __file__, "(no configobj installed)")
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
