# -*- coding: utf-8 -*-
#
# Copyright (C) 2014-2020 Edgewall Software
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

import trac.tests.compat
from trac.config import ConfigurationError
from trac.perm import PermissionCache, PermissionSystem
from trac.test import EnvironmentStub, Mock, MockRequest
from trac.ticket.api import TicketSystem
from trac.ticket.batch import BatchModifyModule
from trac.ticket.model import Ticket
from trac.ticket.default_workflow import ConfigurableTicketWorkflow


class ConfigurableTicketWorkflowTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.ctlr = TicketSystem(self.env).action_controllers[0]

    def tearDown(self):
        self.env.reset_db()

    def _reload_workflow(self):
        self.ctlr.actions = self.ctlr.get_all_actions()

    def test_status_change_with_operation(self):
        """Status change with operation."""
        ticket = Ticket(self.env)
        ticket['new'] = 'status1'
        ticket['owner'] = 'user1'
        ticket.insert()
        req = MockRequest(self.env, path_info='/ticket', authname='user2',
                          method='POST')

        label, control, hints = \
            self.ctlr.render_ticket_action_control(req, ticket, 'accept')

        self.assertEqual('accept', label)
        self.assertEqual('', unicode(control))
        self.assertEqual("The owner will be changed from user1 to user2. "
                         "Next status will be 'accepted'.", unicode(hints))

    def test_status_change_with_no_operation(self):
        """Status change with no operation."""
        config = self.env.config
        config.set('ticket-workflow', 'change_status', 'status1 -> status2')
        self._reload_workflow()
        ticket = Ticket(self.env)
        ticket['status'] = 'status1'
        ticket.insert()
        req = MockRequest(self.env, path_info='/ticket', method='POST')

        label, control, hints = \
            self.ctlr.render_ticket_action_control(req, ticket,
                                                   'change_status')

        self.assertEqual('change_status', label)
        self.assertEqual('', unicode(control))
        self.assertEqual("Next status will be 'status2'.", unicode(hints))

    def test_operation_with_no_status_change(self):
        """Operation with no status change."""
        config = self.env.config
        config.set('ticket-workflow', 'change_owner', 'closed -> closed')
        config.set('ticket-workflow', 'change_owner.operations', 'set_owner')

        self._reload_workflow()
        ticket = Ticket(self.env)
        ticket['status'] = 'closed'
        ticket['owner'] = 'user2'
        ticket.insert()
        req = MockRequest(self.env, path_info='/ticket', method='POST',
                          authname='user1')

        label, control, hints = \
            self.ctlr.render_ticket_action_control(req, ticket,
                                                   'change_owner')

        self.assertEqual('change_owner', label)
        self.assertEqual(
            'to <input type="text" name="action_change_owner_reassign_owner" '
            'value="user1" id="action_change_owner_reassign_owner"/>',
            unicode(control))
        self.assertEqual("The owner will be changed from user2 to the "
                         "specified user.", unicode(hints))

    def test_transition_to_star(self):
        """Action not rendered by CTW for transition to *

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

        self.assertIsNone(label)
        self.assertEqual('', unicode(control))
        self.assertEqual('', unicode(hints))

    def test_transition_to_star_with_leave_operation(self):
        """Action is rendered by CTW for transition to * with leave_status
        """
        config = self.env.config
        config.set('ticket-workflow', 'change_owner', 'assigned,closed -> *')
        config.set('ticket-workflow', 'change_owner.operations',
                   'leave_status,set_owner')

        self._reload_workflow()
        status = ['assigned', 'closed']
        for s in status:
            ticket = Ticket(self.env)
            ticket['status'] = s
            ticket['owner'] = 'user2'
            ticket.insert()
            req = MockRequest(self.env, path_info='/ticket', method='POST',
                              authname='user1')

            label, control, hints = \
                self.ctlr.render_ticket_action_control(req, ticket,
                                                       'change_owner')
            self.assertEqual('change_owner', label)
            self.assertEqual(
                'to <input type="text" '
                'name="action_change_owner_reassign_owner" '
                'value="user1" id="action_change_owner_reassign_owner"/>',
                unicode(control))
            self.assertEqual("The owner will be changed from user2 to the "
                             "specified user.", unicode(hints))

    def test_leave_operation(self):
        ticket = Ticket(self.env)
        ticket['status'] = 'assigned'
        ticket['owner'] = 'user2'
        ticket.insert()
        req = MockRequest(self.env, path_info='/ticket', method='POST',
                          authname='user1')

        label, control, hints = \
            self.ctlr.render_ticket_action_control(req, ticket,
                                                   'leave')

        self.assertEqual('leave', label)
        self.assertEqual('as assigned', unicode(control))
        self.assertEqual("The owner will remain user2.", unicode(hints))


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


class SetResolutionAttributeTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        for ctlr in TicketSystem(self.env).action_controllers:
            if isinstance(ctlr, ConfigurableTicketWorkflow):
                self.ctlr = ctlr

    def tearDown(self):
        self.env.reset_db()

    def _reload_workflow(self):
        self.ctlr.actions = self.ctlr.get_all_actions()

    def test_empty_set_resolution(self):
        config = self.env.config['ticket-workflow']
        config.set('resolve.set_resolution', '')
        self._reload_workflow()
        ticket = Ticket(self.env)
        ticket.populate({'summary': '#12882', 'status': 'new'})
        ticket.insert()
        req = MockRequest(self.env, path_info='/ticket/%d' % ticket.id)
        try:
            self.ctlr.render_ticket_action_control(req, ticket, 'resolve')
            self.fail('ConfigurationError not raised')
        except ConfigurationError, e:
            self.assertIn('but none is defined', unicode(e))

    def test_undefined_resolutions(self):
        config = self.env.config['ticket-workflow']
        ticket = Ticket(self.env)
        ticket.populate({'summary': '#12882', 'status': 'new'})
        ticket.insert()
        req = MockRequest(self.env, path_info='/ticket/%d' % ticket.id)

        config.set('resolve.set_resolution',
                   'fixed,invalid,wontfix,,duplicate,worksforme,,,,,')
        self._reload_workflow()
        self.ctlr.render_ticket_action_control(req, ticket, 'resolve')

        config.set('resolve.set_resolution', 'undefined,fixed')
        self._reload_workflow()
        try:
            self.ctlr.render_ticket_action_control(req, ticket, 'resolve')
            self.fail('ConfigurationError not raised')
        except ConfigurationError, e:
            self.assertIn('but uses undefined resolutions', unicode(e))


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(ConfigurableTicketWorkflowTestCase))
    suite.addTest(unittest.makeSuite(ResetActionTestCase))
    suite.addTest(unittest.makeSuite(SetResolutionAttributeTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
