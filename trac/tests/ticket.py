import os
import tempfile
import unittest

from Ticket import Ticket
from environment import EnvironmentTestBase


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
        self.assertEqual(log[0][2], 'foo')
        self.assertEqual(log[1][2], 'summary')
        self.assertEqual(log[2][2], 'comment')

def suite():
    return unittest.makeSuite(TicketTestCase,'test')
