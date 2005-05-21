from trac.config import Configuration
from trac.Ticket import Ticket, get_custom_fields, available_actions
from trac.test import Mock

import unittest


class TicketTestCase(unittest.TestCase):

    def setUp(self):
        from trac.test import InMemoryDatabase
        self.db = InMemoryDatabase()

    def _insert_ticket(self, summary, **kw):
        """Helper for inserting a ticket into the database"""
        ticket = Ticket()
        for k,v in kw.items():
            ticket[k] = v
        return ticket.insert(self.db)

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

    def test_populate_ticket(self):
        data = {'summary': 'Hello world', 'reporter': 'john', 'foo': 'bar',
                'custom_foo': 'bar', 'checkbox_cbon': '', 'custom_cbon': 'on',
                'checkbox_cboff': ''}
        ticket = Ticket()
        ticket.populate(data)

        # Standard fields
        self.assertEqual('Hello world', ticket['summary'])
        self.assertEqual('john', ticket['reporter'])

        # An unknown field
        self.assertRaises(KeyError, ticket.__getitem__, 'foo')

        # Custom field
        self.assertEqual('bar', ticket['custom_foo'])

        # Custom field of type 'checkbox'
        self.assertEqual('on', ticket['custom_cbon'])
        self.assertEqual('0', ticket['custom_cboff'])

    def test_changelog(self):
        tkt_id = self._insert_ticket('Test', reporter='joe', component='foo',
                                     milestone='bar')
        ticket = Ticket(self.db, tkt_id)
        ticket['component'] = 'bar'
        ticket['milestone'] = 'foo'
        ticket.save_changes(self.db, 'jane', 'Testing', when=42)
        for t, author, field, old, new in ticket.get_changelog(self.db):
            self.assertEqual((42, 'jane'), (t, author))
            if field == 'component':
                self.assertEqual(('foo', 'bar'), (old, new))
            elif field == 'milestone':
                self.assertEqual(('bar', 'foo'), (old, new))
            elif field == 'comment':
                self.assertEqual(('', 'Testing'), (old, new))
            else:
                self.fail('Unexpected change (%s)'
                          % ((t, author, field, old, new),))

    def test_changelog_with_reverted_change(self):
        tkt_id = self._insert_ticket('Test', reporter='joe', component='foo')
        ticket = Ticket(self.db, tkt_id)
        ticket['component'] = 'bar'
        ticket['component'] = 'foo'
        ticket.save_changes(self.db, 'jane', 'Testing', when=42)
        for t, author, field, old, new in ticket.get_changelog(self.db):
            self.assertEqual((42, 'jane'), (t, author))
            if field == 'comment':
                self.assertEqual(('', 'Testing'), (old, new))
            else:
                self.fail('Unexpected change (%s)'
                          % ((t, author, field, old, new),))

    def test_custom_field_text(self):
        env = Mock(config=Configuration(None))
        env.config.set('ticket-custom', 'test', 'text')
        env.config.set('ticket-custom', 'test.label', 'Test')
        env.config.set('ticket-custom', 'test.value', 'Foo bar')
        fields = get_custom_fields(env)
        self.assertEqual({'name': 'test', 'type': 'text', 'label': 'Test',
                          'value': 'Foo bar', 'order': 0},
                         fields[0])

    def test_custom_field_select(self):
        env = Mock(config=Configuration(None))
        env.config.set('ticket-custom', 'test', 'select')
        env.config.set('ticket-custom', 'test.label', 'Test')
        env.config.set('ticket-custom', 'test.value', '1')
        env.config.set('ticket-custom', 'test.options', 'option1|option2')
        fields = get_custom_fields(env)
        self.assertEqual({'name': 'test', 'type': 'select', 'label': 'Test',
                          'value': '1', 'options': ['option1', 'option2'],
                          'order': 0},
                         fields[0])

    def test_custom_field_textarea(self):
        env = Mock(config=Configuration(None))
        env.config.set('ticket-custom', 'test', 'textarea')
        env.config.set('ticket-custom', 'test.label', 'Test')
        env.config.set('ticket-custom', 'test.value', 'Foo bar')
        env.config.set('ticket-custom', 'test.cols', '60')
        env.config.set('ticket-custom', 'test.rows', '4')
        fields = get_custom_fields(env)
        self.assertEqual({'name': 'test', 'type': 'textarea', 'label': 'Test',
                          'value': 'Foo bar', 'width': '60', 'height': '4',
                          'order': 0},
                         fields[0])

    def test_custom_field_order(self):
        env = Mock(config=Configuration(None))
        env.config.set('ticket-custom', 'test1', 'text')
        env.config.set('ticket-custom', 'test1.order', '2')
        env.config.set('ticket-custom', 'test2', 'text')
        env.config.set('ticket-custom', 'test2.order', '1')
        fields = get_custom_fields(env)
        self.assertEqual('test2', fields[0]['name'])
        self.assertEqual('test1', fields[1]['name'])

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
