from trac.config import Configuration
from trac.ticket.model import Ticket, Component, Priority
from trac.test import EnvironmentStub

import unittest


class TicketModelTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        self.env.config.set('ticket-custom', 'foo', 'text')
        self.env.config.set('ticket-custom', 'cbon', 'checkbox')
        self.env.config.set('ticket-custom', 'cboff', 'checkbox')

    def _insert_ticket(self, summary, **kw):
        """Helper for inserting a ticket into the database"""
        ticket = Ticket(self.env)
        for k,v in kw.items():
            ticket[k] = v
        return ticket.insert()

    def test_create_ticket(self):
        # Multiple test in one method, this sucks
        # 1. Creating ticket
        ticket = Ticket(self.env)
        ticket['reporter'] = 'santa'
        ticket['summary'] = 'Foo'
        ticket['foo'] = 'This is a custom field'
        self.assertEqual('santa', ticket['reporter'])
        self.assertEqual('Foo', ticket['summary'])
        self.assertEqual('This is a custom field', ticket['foo'])
        ticket.insert()

        # Retrieving ticket
        ticket2 = Ticket(self.env, 1)
        self.assertEqual(1, ticket2.id)
        self.assertEqual('santa', ticket2['reporter'])
        self.assertEqual('Foo', ticket2['summary'])
        self.assertEqual('This is a custom field', ticket2['foo'])

        # Modifying ticket
        ticket2['summary'] = 'Bar'
        ticket2['foo'] = 'New value'
        ticket2.save_changes('santa', 'this is my comment')

        # Retrieving ticket
        ticket3 = Ticket(self.env, 1)
        self.assertEqual(1, ticket3.id)
        self.assertEqual(ticket3['reporter'], 'santa')
        self.assertEqual(ticket3['summary'], 'Bar')
        self.assertEqual(ticket3['foo'], 'New value')

        # Testing get_changelog()
        log = ticket3.get_changelog()
        self.assertEqual(len(log), 3)
        ok_vals = ['foo', 'summary', 'comment']
        self.failUnless(log[0][2] in ok_vals)
        self.failUnless(log[1][2] in ok_vals)
        self.failUnless(log[2][2] in ok_vals)

    def test_ticket_default_values(self):
        """
        Verify that a ticket uses default values specified in the configuration
        when created.
        """
        # Set defaults for some standard fields
        self.env.config.set('ticket', 'default_type', 'defect')
        self.env.config.set('ticket', 'default_component', 'component1')

        # Add a custom field of type 'text' with a default value
        self.env.config.set('ticket-custom', 'foo', 'text')
        self.env.config.set('ticket-custom', 'foo.value', 'Something')

        # Add a custom field of type 'select' with a default value specified as
        # the value itself
        self.env.config.set('ticket-custom', 'bar', 'select')
        self.env.config.set('ticket-custom', 'bar.options', 'one|two|three')
        self.env.config.set('ticket-custom', 'bar.value', 'two')

        # Add a custom field of type 'select' with a default value specified as
        # index into the options list
        self.env.config.set('ticket-custom', 'baz', 'select')
        self.env.config.set('ticket-custom', 'baz.options', 'one|two|three')
        self.env.config.set('ticket-custom', 'baz.value', '2')

        ticket = Ticket(self.env)
        self.assertEqual('defect', ticket['type'])
        self.assertEqual('component1', ticket['component'])
        self.assertEqual('Something', ticket['foo'])
        self.assertEqual('two', ticket['bar'])
        self.assertEqual('three', ticket['baz'])

    def test_owner_from_component(self):
        """
        Verify that the owner of a new ticket is set to the owner of the
        component.
        """
        component = Component(self.env)
        component.name = 'test'
        component.owner = 'joe'
        component.insert()

        ticket = Ticket(self.env)
        ticket['reporter'] = 'santa'
        ticket['summary'] = 'Foo'
        ticket['component'] = 'test'
        ticket.insert()
        self.assertEqual('joe', ticket['owner'])

    def test_owner_from_changed_component(self):
        """
        Verify that the owner of a new ticket is updated when the component is
        changed.
        """
        component1 = Component(self.env)
        component1.name = 'test1'
        component1.owner = 'joe'
        component1.insert()

        component2 = Component(self.env)
        component2.name = 'test2'
        component2.owner = 'kate'
        component2.insert()

        ticket = Ticket(self.env)
        ticket['reporter'] = 'santa'
        ticket['summary'] = 'Foo'
        ticket['component'] = 'test1'
        ticket['status'] = 'new'
        tktid = ticket.insert()

        ticket = Ticket(self.env, tktid)
        ticket['component'] = 'test2'
        ticket.save_changes('jane', 'Testing')
        self.assertEqual('kate', ticket['owner'])

    def test_populate_ticket(self):
        data = {'summary': 'Hello world', 'reporter': 'john', 'foo': 'bar',
                'foo': 'bar', 'checkbox_cbon': '', 'cbon': 'on',
                'checkbox_cboff': ''}
        ticket = Ticket(self.env)
        ticket.populate(data)

        # Standard fields
        self.assertEqual('Hello world', ticket['summary'])
        self.assertEqual('john', ticket['reporter'])

        # An unknown field
        self.assertRaises(KeyError, ticket.__getitem__, 'bar')

        # Custom field
        self.assertEqual('bar', ticket['foo'])

        # Custom field of type 'checkbox'
        self.assertEqual('on', ticket['cbon'])
        self.assertEqual('0', ticket['cboff'])

    def test_changelog(self):
        tkt_id = self._insert_ticket('Test', reporter='joe', component='foo',
                                     milestone='bar')
        ticket = Ticket(self.env, tkt_id)
        ticket['component'] = 'bar'
        ticket['milestone'] = 'foo'
        ticket.save_changes('jane', 'Testing', when=42)
        for t, author, field, old, new in ticket.get_changelog():
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
        ticket = Ticket(self.env, tkt_id)
        ticket['component'] = 'bar'
        ticket['component'] = 'foo'
        ticket.save_changes('jane', 'Testing', when=42)
        for t, author, field, old, new in ticket.get_changelog():
            self.assertEqual((42, 'jane'), (t, author))
            if field == 'comment':
                self.assertEqual(('', 'Testing'), (old, new))
            else:
                self.fail('Unexpected change (%s)'
                          % ((t, author, field, old, new),))

    def test_abstractenum(self):
        """
        Verify basic AbstractEnum functionality.
        """
        p = Priority(self.env, 'major')
        self.assertEqual(p.name, 'major')
        self.assertEqual(p.value, '3')
        p = Priority(self.env)
        p.name = 'foo'
        p.insert()
        p = Priority(self.env)
        p.name = 'bar'
        p.value = 100
        p.insert()
        p = Priority(self.env, 'foo')
        p.name = 'foo2'
        p.update()
        p = Priority(self.env, 'foo2')
        p.delete()        
        p = Priority(self.env, 'bar')
        p.delete()        

def suite():
    return unittest.makeSuite(TicketModelTestCase, 'test')

if __name__ == '__main__':
    unittest.main()
