from trac.perm import PermissionCache, PermissionSystem
from trac.ticket.api import TicketSystem
from trac.ticket.model import Ticket
from trac.test import EnvironmentStub, Mock

import unittest


class TicketSystemTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.perm = PermissionSystem(self.env)
        self.ticket_system = TicketSystem(self.env)
        self.req = Mock()

    def tearDown(self):
        self.env.reset_db()

    def _get_actions(self, ticket_dict):
        ts = TicketSystem(self.env)
        ticket = Ticket(self.env)
        ticket.populate(ticket_dict)
        id = ticket.insert()
        return ts.get_available_actions(self.req, Ticket(self.env, id))

    def test_custom_field_text(self):
        self.env.config.set('ticket-custom', 'test', 'text')
        self.env.config.set('ticket-custom', 'test.label', 'Test')
        self.env.config.set('ticket-custom', 'test.value', 'Foo bar')
        self.env.config.set('ticket-custom', 'test.format', 'wiki')
        fields = TicketSystem(self.env).get_custom_fields()
        self.assertEqual({'name': 'test', 'type': 'text', 'label': 'Test',
                          'value': 'Foo bar', 'order': 0, 'format': 'wiki'},
                         fields[0])

    def test_custom_field_select(self):
        self.env.config.set('ticket-custom', 'test', 'select')
        self.env.config.set('ticket-custom', 'test.label', 'Test')
        self.env.config.set('ticket-custom', 'test.value', '1')
        self.env.config.set('ticket-custom', 'test.options', 'option1|option2')
        fields = TicketSystem(self.env).get_custom_fields()
        self.assertEqual({'name': 'test', 'type': 'select', 'label': 'Test',
                          'value': '1', 'options': ['option1', 'option2'],
                          'order': 0},
                         fields[0])

    def test_custom_field_optional_select(self):
        self.env.config.set('ticket-custom', 'test', 'select')
        self.env.config.set('ticket-custom', 'test.label', 'Test')
        self.env.config.set('ticket-custom', 'test.value', '1')
        self.env.config.set('ticket-custom', 'test.options', '|option1|option2')
        fields = TicketSystem(self.env).get_custom_fields()
        self.assertEqual({'name': 'test', 'type': 'select', 'label': 'Test',
                          'value': '1', 'options': ['option1', 'option2'],
                          'order': 0, 'optional': True},
                         fields[0])

    def test_custom_field_textarea(self):
        self.env.config.set('ticket-custom', 'test', 'textarea')
        self.env.config.set('ticket-custom', 'test.label', 'Test')
        self.env.config.set('ticket-custom', 'test.value', 'Foo bar')
        self.env.config.set('ticket-custom', 'test.cols', '60')
        self.env.config.set('ticket-custom', 'test.rows', '4')
        self.env.config.set('ticket-custom', 'test.format', 'wiki')
        fields = TicketSystem(self.env).get_custom_fields()
        self.assertEqual({'name': 'test', 'type': 'textarea', 'label': 'Test',
                          'value': 'Foo bar', 'width': 60, 'height': 4,
                          'order': 0, 'format': 'wiki'},
                         fields[0])

    def test_custom_field_order(self):
        self.env.config.set('ticket-custom', 'test1', 'text')
        self.env.config.set('ticket-custom', 'test1.order', '2')
        self.env.config.set('ticket-custom', 'test2', 'text')
        self.env.config.set('ticket-custom', 'test2.order', '1')
        fields = TicketSystem(self.env).get_custom_fields()
        self.assertEqual('test2', fields[0]['name'])
        self.assertEqual('test1', fields[1]['name'])

    def test_available_actions_full_perms(self):
        self.perm.grant_permission('anonymous', 'TICKET_CREATE')
        self.perm.grant_permission('anonymous', 'TICKET_MODIFY')
        self.req.perm = PermissionCache(self.env)
        self.assertEqual(['leave', 'resolve', 'reassign', 'accept'],
                         self._get_actions({'status': 'new'}))
        self.assertEqual(['leave', 'resolve', 'reassign', 'accept'],
                         self._get_actions({'status': 'assigned'}))
        self.assertEqual(['leave', 'resolve', 'reassign', 'accept'],
                         self._get_actions({'status': 'accepted'}))
        self.assertEqual(['leave', 'resolve', 'reassign', 'accept'],
                         self._get_actions({'status': 'reopened'}))
        self.assertEqual(['leave', 'reopen'], 
                         self._get_actions({'status': 'closed'}))

    def test_available_actions_no_perms(self):
        self.req.perm = PermissionCache(self.env)
        self.assertEqual(['leave'], self._get_actions({'status': 'new'}))
        self.assertEqual(['leave'], self._get_actions({'status': 'assigned'}))
        self.assertEqual(['leave'], self._get_actions({'status': 'accepted'}))
        self.assertEqual(['leave'], self._get_actions({'status': 'reopened'}))
        self.assertEqual(['leave'], self._get_actions({'status': 'closed'}))

    def test_available_actions_create_only(self):
        self.perm.grant_permission('anonymous', 'TICKET_CREATE')
        self.req.perm = PermissionCache(self.env)
        self.assertEqual(['leave'], self._get_actions({'status': 'new'}))
        self.assertEqual(['leave'], self._get_actions({'status': 'assigned'}))
        self.assertEqual(['leave'], self._get_actions({'status': 'accepted'}))
        self.assertEqual(['leave'], self._get_actions({'status': 'reopened'}))
        self.assertEqual(['leave', 'reopen'],
                         self._get_actions({'status': 'closed'}))

    def test_available_actions_chgprop_only(self):
        # CHGPROP is not enough for changing a ticket's state (#3289)
        self.perm.grant_permission('anonymous', 'TICKET_CHGPROP')
        self.req.perm = PermissionCache(self.env)
        self.assertEqual(['leave'], self._get_actions({'status': 'new'}))
        self.assertEqual(['leave'], self._get_actions({'status': 'assigned'}))
        self.assertEqual(['leave'], self._get_actions({'status': 'accepted'}))
        self.assertEqual(['leave'], self._get_actions({'status': 'reopened'}))
        self.assertEqual(['leave'], self._get_actions({'status': 'closed'}))


def suite():
    return unittest.makeSuite(TicketSystemTestCase, 'test')

if __name__ == '__main__':
    unittest.main()
