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

import trac.tests.compat
from trac.perm import PermissionSystem
from trac.test import EnvironmentStub, MockRequest
from trac.ticket.api import TicketSystem
from trac.ticket.batch import BatchModifyModule
from trac.ticket.model import Component, Ticket
from trac.ticket.web_ui import TicketModule
from trac.util import create_file
from trac.util.datefmt import to_utimestamp
from trac.web.api import RequestDone
from tracopt.perm.authz_policy import AuthzPolicy


class ConfigurableTicketWorkflowTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        config = self.env.config
        config.set('ticket-workflow', 'change_owner', 'new -> new')
        config.set('ticket-workflow', 'change_owner.operations', 'set_owner')
        self.ctlr = TicketSystem(self.env).action_controllers[0]
        self.ticket_module = TicketModule(self.env)

    def tearDown(self):
        self.env.reset_db()

    def _add_component(self, name='test', owner='owner1'):
        component = Component(self.env)
        component.name = name
        component.owner = owner
        component.insert()

    def _reload_workflow(self):
        self.ctlr.actions = self.ctlr.get_all_actions()

    def test_get_all_actions_custom_attribute(self):
        """Custom attribute in ticket-workflow."""
        config = self.env.config['ticket-workflow']
        config.set('resolve.set_milestone', 'reject')
        all_actions = self.ctlr.get_all_actions()

        resolve_action = None
        for name, attrs in all_actions.items():
            if name == 'resolve':
                resolve_action = attrs

        self.assertIsNotNone(resolve_action)
        self.assertIn('set_milestone', resolve_action.keys())
        self.assertEqual('reject', resolve_action['set_milestone'])

    def test_owner_from_component(self):
        """Verify that the owner of a new ticket is set to the owner
        of the component.
        """
        self._add_component('component3', 'cowner3')

        req = MockRequest(self.env, method='POST', args={
            'field_reporter': 'reporter1',
            'field_summary': 'the summary',
            'field_component': 'component3',
        })
        self.assertRaises(RequestDone, self.ticket_module.process_request, req)
        ticket = Ticket(self.env, 1)

        self.assertEqual('component3', ticket['component'])
        self.assertEqual('cowner3', ticket['owner'])

    def test_component_change(self):
        """New ticket owner is updated when the component is changed.
        """
        self._add_component('component3', 'cowner3')
        self._add_component('component4', 'cowner4')

        ticket = Ticket(self.env)
        ticket.populate({
            'reporter': 'reporter1',
            'summary': 'the summary',
            'component': 'component3',
            'owner': 'cowner3',
            'status': 'new',
        })
        tkt_id = ticket.insert()

        req = MockRequest(self.env, method='POST', args={
            'id': tkt_id,
            'field_component': 'component4',
            'submit': True,
            'action': 'leave',
            'view_time': str(to_utimestamp(ticket['changetime'])),
        })
        self.assertRaises(RequestDone, self.ticket_module.process_request, req)
        ticket = Ticket(self.env, tkt_id)

        self.assertEqual('component4', ticket['component'])
        self.assertEqual('cowner4', ticket['owner'])

    def test_component_change_and_owner_change(self):
        """New ticket owner is not updated if owner is explicitly
        changed.
        """
        self._add_component('component3', 'cowner3')
        self._add_component('component4', 'cowner4')

        ticket = Ticket(self.env)
        ticket.populate({
            'reporter': 'reporter1',
            'summary': 'the summary',
            'component': 'component3',
            'status': 'new',
        })
        tkt_id = ticket.insert()

        req = MockRequest(self.env, method='POST', args={
            'id': tkt_id,
            'field_component': 'component4',
            'submit': True,
            'action': 'change_owner',
            'action_change_owner_reassign_owner': 'owner1',
            'view_time': str(to_utimestamp(ticket['changetime'])),
        })
        self.assertRaises(RequestDone, self.ticket_module.process_request, req)
        ticket = Ticket(self.env, tkt_id)

        self.assertEqual('component4', ticket['component'])
        self.assertEqual('owner1', ticket['owner'])

    def test_old_owner_not_old_component_owner(self):
        """New ticket owner is not updated if old owner is not the owner
        of the old component.
        """
        self._add_component('component3', 'cowner3')
        self._add_component('component4', 'cowner4')

        ticket = Ticket(self.env)
        ticket.populate({
            'reporter': 'reporter1',
            'summary': 'the summary',
            'component': 'component3',
            'owner': 'owner1',
            'status': 'new',
        })
        tkt_id = ticket.insert()

        req = MockRequest(self.env, method='POST', args={
            'id': tkt_id,
            'field_component': 'component4',
            'submit': True,
            'action': 'leave',
            'view_time': str(to_utimestamp(ticket['changetime'])),
        })
        self.assertRaises(RequestDone, self.ticket_module.process_request, req)
        ticket = Ticket(self.env, tkt_id)

        self.assertEqual('component4', ticket['component'])
        self.assertEqual('owner1', ticket['owner'])

    def test_new_component_has_no_owner(self):
        """Ticket is not disowned when the component is changed to a
        component with no owner.
        """
        self._add_component('component3', 'cowner3')
        self._add_component('component4', '')

        ticket = Ticket(self.env)
        ticket.populate({
            'reporter': 'reporter1',
            'summary': 'the summary',
            'component': 'component3',
            'owner': 'cowner3',
            'status': 'new',
        })
        tkt_id = ticket.insert()

        req = MockRequest(self.env, method='POST', args={
            'id': tkt_id,
            'field_component': 'component4',
            'submit': True,
            'action': 'leave',
            'view_time': str(to_utimestamp(ticket['changetime'])),
        })
        self.assertRaises(RequestDone, self.ticket_module.process_request, req)
        ticket = Ticket(self.env, tkt_id)

        self.assertEqual('component4', ticket['component'])
        self.assertEqual('cowner3', ticket['owner'])

    def test_transition_to_star(self):
        """Workflow hint is not be added in a workflow transition to *,
        for example: <none> -> *

        AdvancedTicketWorkflow uses the behavior for the triage operation
        (see #12823)
        """
        config = self.env.config
        config.set('ticket-workflow', 'create_and_triage', '<none> -> *')
        config.set('ticket-workflow', 'create_and_triage.operations', 'triage')
        self._reload_workflow()
        ticket = Ticket(self.env)
        req = MockRequest(self.env, path_info='/newticket', method='POST')

        label, control, hints = \
            self.ctlr.render_ticket_action_control(req, ticket,
                                                   'create_and_triage')

        self.assertEqual('create and triage', label)
        self.assertEqual('', unicode(control))
        self.assertEqual('', unicode(hints))


class ResetActionTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        self.perm_sys = PermissionSystem(self.env)
        self.ctlr = TicketSystem(self.env).action_controllers[0]
        self.req1 = MockRequest(self.env, authname='user1')
        self.req2 = MockRequest(self.env, authname='user2')
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
        self.req = MockRequest(self.env, authname='user1')
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
        self.env.insert_users([('user1', 'User C', 'user1@example.org'),
                               ('user2', 'User A', 'user2@example.org'),
                               ('user3', 'User D', 'user3@example.org'),
                               ('user4', 'User B', 'user4@example.org')])
        self.perm_sys.grant_permission('user1', 'TICKET_MODIFY')
        self.perm_sys.grant_permission('user2', 'TICKET_VIEW')
        self.perm_sys.grant_permission('user3', 'TICKET_MODIFY')
        self.perm_sys.grant_permission('user4', 'TICKET_MODIFY')
        self.authz_file = os.path.join(tmpdir, 'trac-authz-policy')
        create_file(self.authz_file)
        self.env.config.set('authz_policy', 'authz_file', self.authz_file)
        self.ctlr = TicketSystem(self.env).action_controllers[0]
        self.req1 = MockRequest(self.env, authname='user1')
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
        self.env.config.set('trac', 'show_full_names', False)

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
        self.env.config.set('trac', 'show_full_names', False)
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

    def test_set_owner_show_fullnames(self):
        """Full names are sorted when [trac] show_full_names = True."""
        ctrl = self.ctlr.render_ticket_action_control(self.req1, self.ticket,
                                                      'reassign')

        self.assertEqual('reassign', ctrl[0])
        self.assertEqual("""\
to <select name="action_reassign_reassign_owner" \
id="action_reassign_reassign_owner">\
<option value="user4">User B</option>\
<option selected="True" value="user1">User C</option>\
<option value="user3">User D</option></select>\
""", str(ctrl[1]))


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(ConfigurableTicketWorkflowTestCase))
    suite.addTest(unittest.makeSuite(ResetActionTestCase))
    suite.addTest(unittest.makeSuite(SetOwnerAttributeTestCase))
    suite.addTest(unittest.makeSuite(RestrictOwnerTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
