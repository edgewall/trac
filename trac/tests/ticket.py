from trac.Ticket import Ticket
from trac.tests.environment import EnvironmentTestBase

import os
import tempfile
import unittest


class TicketTestCase(EnvironmentTestBase, unittest.TestCase):
    def test_create_ticket(self):
        """Testing Ticket.insert()"""
        # Multiple test in one method, this sucks
        # 1. Creating ticket
        ticket = Ticket()
        ticket['reporter'] = 'santa'
        ticket['summary'] = 'Foo'
        ticket['custom_foo'] = 'This is a custom field'
        assert ticket['reporter'] == 'santa'
        assert ticket['summary'] == 'Foo'
        assert ticket['custom_foo'] == 'This is a custom field'
        ticket.insert(self.db)
        # Retrieving ticket
        ticket2 = Ticket(self.db, 1)
        assert ticket2['id'] == 1
        assert ticket2['reporter'] == 'santa'
        assert ticket2['summary'] == 'Foo'
        assert ticket2['custom_foo'] == 'This is a custom field'
        # Modifying ticket
        ticket2['summary'] = 'Bar'
        ticket2['custom_foo'] = 'New value'
        ticket2.save_changes(self.db, 'santa', 'this is my comment')
        # Retrieving ticket
        ticket3 = Ticket(self.db, 1)
        assert ticket3['id'] == 1
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

def suite():
    return unittest.makeSuite(TicketTestCase,'test')

if __name__ == '__main__':
    unittest.main()
