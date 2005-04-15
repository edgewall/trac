from trac.Ticket import Ticket, available_actions
from trac.test import Mock

import unittest


class TicketTestCase(unittest.TestCase):

    def setUp(self):
        from trac.test import InMemoryDatabase
        self.db = InMemoryDatabase()

    def test_create_ticket(self):
        """Testing Ticket.insert()"""
        # Multiple test in one method, this sucks
        # 1. Creating ticket
        ticket = Ticket()
        ticket['reporter'] = 'santa'
        ticket['summary'] = 'Foo'
        ticket['custom_foo'] = 'This is a custom field'
        self.assertEqual('santa', ticket['reporter'])
        self.assertEqual('Foo', ticket['summary'])
        self.assertEqual('This is a custom field', ticket['custom_foo'])
        ticket.insert(self.db)

        # Retrieving ticket
        ticket2 = Ticket(self.db, 1)
        self.assertEqual(1, ticket2['id'])
        self.assertEqual('santa', ticket2['reporter'])
        self.assertEqual('Foo', ticket2['summary'])
        self.assertEqual('This is a custom field', ticket2['custom_foo'])

        # Modifying ticket
        ticket2['summary'] = 'Bar'
        ticket2['custom_foo'] = 'New value'
        ticket2.save_changes(self.db, 'santa', 'this is my comment')

        # Retrieving ticket
        ticket3 = Ticket(self.db, 1)
        self.assertEqual(1, ticket3['id'])
        self.assertEqual(ticket3['reporter'], 'santa')
        self.assertEqual(ticket3['summary'], 'Bar')
        self.assertEqual(ticket3['custom_foo'], 'New value')

        # Testing get_changelog()
        log = ticket3.get_changelog(self.db)
        self.assertEqual(len(log), 3)
        ok_vals = ['foo', 'summary', 'comment']
        self.failUnless(log[0][2] in ok_vals)
        self.failUnless(log[1][2] in ok_vals)
        self.failUnless(log[2][2] in ok_vals)

    def test_available_actions_full_perms(self):
        perm = Mock(has_permission=lambda x: 1)
        self.assertEqual(['leave', 'resolve', 'reassign', 'accept'],
                         available_actions({'status': 'new'}, perm))
        self.assertEqual(['leave', 'resolve', 'reassign'],
                         available_actions({'status': 'assigned'}, perm))
        self.assertEqual(['leave', 'resolve', 'reassign'],
                         available_actions({'status': 'reopened'}, perm))
        self.assertEqual(['leave', 'reopen'],
                         available_actions({'status': 'closed'}, perm))

    def test_available_actions_no_perms(self):
        perm = Mock(has_permission=lambda x: 0)
        self.assertEqual(['leave'],
                         available_actions({'status': 'new'}, perm))
        self.assertEqual(['leave'],
                         available_actions({'status': 'assigned'}, perm))
        self.assertEqual(['leave'],
                         available_actions({'status': 'reopened'}, perm))
        self.assertEqual(['leave'],
                         available_actions({'status': 'closed'}, perm))

    def test_available_actions_create_only(self):
        perm = Mock(has_permission=lambda x: x == 'TICKET_CREATE')
        self.assertEqual(['leave'],
                         available_actions({'status': 'new'}, perm))
        self.assertEqual(['leave'],
                         available_actions({'status': 'assigned'}, perm))
        self.assertEqual(['leave'],
                         available_actions({'status': 'reopened'}, perm))
        self.assertEqual(['leave', 'reopen'],
                         available_actions({'status': 'closed'}, perm))

    def test_available_actions_chgprop_only(self):
        perm = Mock(has_permission=lambda x: x == 'TICKET_CHGPROP')
        self.assertEqual(['leave', 'reassign', 'accept'],
                         available_actions({'status': 'new'}, perm))
        self.assertEqual(['leave', 'reassign'],
                         available_actions({'status': 'assigned'}, perm))
        self.assertEqual(['leave', 'reassign'],
                         available_actions({'status': 'reopened'}, perm))
        self.assertEqual(['leave'],
                         available_actions({'status': 'closed'}, perm))


def suite():
    return unittest.makeSuite(TicketTestCase,'test')

if __name__ == '__main__':
    unittest.main()
