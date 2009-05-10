from trac import core
from trac.core import TracError, implements
from trac.resource import ResourceNotFound
from trac.ticket.model import Ticket, Component, Milestone, Priority, Type, Version
from trac.ticket.api import ITicketChangeListener
from trac.test import EnvironmentStub
from trac.util.datefmt import utc, to_timestamp

from datetime import datetime
import unittest

class TestTicketChangeListener(core.Component):
    implements(ITicketChangeListener)

    def ticket_created(self, ticket):
        self.action = 'created'
        self.ticket = ticket
        self.resource = ticket.resource

    def ticket_changed(self, ticket, comment, author, old_values):
        self.action = 'changed'
        self.ticket = ticket
        self.comment = comment
        self.author = author
        self.old_values = old_values
        
    def ticket_deleted(self, ticket):
        self.action = 'deleted'
        self.ticket = ticket


class TicketTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        self.env.config.set('ticket-custom', 'foo', 'text')
        self.env.config.set('ticket-custom', 'cbon', 'checkbox')
        self.env.config.set('ticket-custom', 'cboff', 'checkbox')

    def tearDown(self):
        self.env.reset_db()

    def _insert_ticket(self, summary, **kw):
        """Helper for inserting a ticket into the database"""
        ticket = Ticket(self.env)
        for k,v in kw.items():
            ticket[k] = v
        return ticket.insert()

    def _create_a_ticket(self):
        # 1. Creating ticket
        ticket = Ticket(self.env)
        ticket['reporter'] = 'santa'
        ticket['summary'] = 'Foo'
        ticket['foo'] = 'This is a custom field'
        return ticket

    def test_invalid_ticket_id(self):
        self.assertEqual(Ticket.id_is_valid(-1), False)
        self.assertEqual(Ticket.id_is_valid(0), False)
        self.assertEqual(Ticket.id_is_valid(1), True)
        self.assertEqual(Ticket.id_is_valid(1L << 31), True)
        self.assertEqual(Ticket.id_is_valid(1L << 32), False)
        self.assertRaises(ResourceNotFound, Ticket, self.env, -1)
        self.assertRaises(ResourceNotFound, Ticket, self.env, 1L << 32)

    def test_create_ticket_1(self):
        ticket = self._create_a_ticket()
        self.assertEqual('santa', ticket['reporter'])
        self.assertEqual('Foo', ticket['summary'])
        self.assertEqual('This is a custom field', ticket['foo'])
        ticket.insert()

    def test_create_ticket_2(self):
        ticket = self._create_a_ticket()
        ticket.insert()
        # Retrieving ticket
        ticket2 = Ticket(self.env, 1)
        self.assertEqual(1, ticket2.id)
        self.assertEqual('santa', ticket2['reporter'])
        self.assertEqual('Foo', ticket2['summary'])
        self.assertEqual('This is a custom field', ticket2['foo'])

    def _modify_a_ticket(self):
        ticket2 = self._create_a_ticket()
        ticket2.insert()
        ticket2['summary'] = 'Bar'
        ticket2['foo'] = 'New value'
        ticket2.save_changes('santa', 'this is my comment')
        return ticket2

    def test_create_ticket_3(self):
        self._modify_a_ticket()
        # Retrieving ticket
        ticket3 = Ticket(self.env, 1)
        self.assertEqual(1, ticket3.id)
        self.assertEqual(ticket3['reporter'], 'santa')
        self.assertEqual(ticket3['summary'], 'Bar')
        self.assertEqual(ticket3['foo'], 'New value')

    def test_create_ticket_4(self):
        ticket3 = self._modify_a_ticket()
        # Testing get_changelog()
        log = ticket3.get_changelog()
        self.assertEqual(len(log), 3)
        ok_vals = ['foo', 'summary', 'comment']
        self.failUnless(log[0][2] in ok_vals)
        self.failUnless(log[1][2] in ok_vals)
        self.failUnless(log[2][2] in ok_vals)

    def test_create_ticket_5(self):
        ticket3 = self._modify_a_ticket()
        # Testing delete()
        ticket3.delete()
        log = ticket3.get_changelog()
        self.assertEqual(len(log), 0)
        self.assertRaises(TracError, Ticket, self.env, 1)

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

    def test_set_field_stripped(self):
        """
        Verify that whitespace around ticket fields is stripped, except for
        textarea fields.
        """
        ticket = Ticket(self.env)
        ticket['component'] = '  foo  '
        ticket['description'] = '  bar  '
        self.assertEqual('foo', ticket['component'])
        self.assertEqual('  bar  ', ticket['description'])

    def test_set_field_multi(self):
        """
        Ticket fields can't yet be multi-valued
        """
        ticket = Ticket(self.env)
        def set_multi_valued():
            ticket['component'] = ['  foo  ',  '  bar  ']
        self.assertRaises(TracError, set_multi_valued)

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
        assert ticket['bar'] is None

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
        now = datetime(2001, 1, 1, 1, 1, 1, 0, utc)
        ticket.save_changes('jane', 'Testing', now)
        for t, author, field, old, new, permanent in ticket.get_changelog():
            self.assertEqual((now, 'jane', True), (t, author, permanent))
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
        now = datetime(2001, 1, 1,  1, 1, 1, 0, utc)
        ticket.save_changes('jane', 'Testing', now)
        for t, author, field, old, new, permanent in ticket.get_changelog():
            self.assertEqual((now, 'jane', True), (t, author, permanent))
            if field == 'comment':
                self.assertEqual(('', 'Testing'), (old, new))
            else:
                self.fail('Unexpected change (%s)'
                          % ((t, author, field, old, new),))

    def test_change_listener_created(self):
        listener = TestTicketChangeListener(self.env)
        ticket = self._create_a_ticket()
        ticket.insert()
        self.assertEqual('created', listener.action)
        self.assertEqual(ticket, listener.ticket)
        self.assertEqual(ticket.id, ticket.resource.id)

    def test_change_listener_changed(self):
        listener = TestTicketChangeListener(self.env)
        data = {'component': 'foo', 'milestone': 'bar'}
        tkt_id = self._insert_ticket('Hello World', reporter='john', **data)

        ticket = Ticket(self.env, tkt_id)
        ticket['component'] = 'new component'
        ticket['milestone'] = 'new milestone'

        comment = 'changing ticket'
        ticket.save_changes('author', comment)

        self.assertEqual('changed', listener.action)
        self.assertEqual(comment, listener.comment)
        self.assertEqual('author', listener.author)
        for key, value in data.iteritems():
            self.assertEqual(value, listener.old_values[key])

    def test_change_listener_deleted(self):
        listener = TestTicketChangeListener(self.env)
        ticket = self._create_a_ticket()
        ticket.insert()
        ticket.delete()
        self.assertEqual('deleted', listener.action)
        self.assertEqual(ticket, listener.ticket)


class EnumTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)

    def tearDown(self):
        self.env.reset_db()

    def test_priority_fetch(self):
        prio = Priority(self.env, 'major')
        self.assertEqual(prio.name, 'major')
        self.assertEqual(prio.value, '3')

    def test_priority_insert(self):
        prio = Priority(self.env)
        prio.name = 'foo'
        prio.insert()
        self.assertEqual(True, prio.exists)

    def test_priority_insert_with_value(self):
        prio = Priority(self.env)
        prio.name = 'bar'
        prio.value = 100
        prio.insert()
        self.assertEqual(True, prio.exists)

    def test_priority_update(self):
        prio = Priority(self.env, 'major')
        prio.name = 'foo'
        prio.update()
        Priority(self.env, 'foo')
        self.assertRaises(TracError, Priority, self.env, 'major')

    def test_priority_delete(self):
        prio = Priority(self.env, 'major')
        self.assertEqual('3', prio.value)
        prio.delete()
        self.assertEqual(False, prio.exists)
        self.assertRaises(TracError, Priority, self.env, 'major')
        prio = Priority(self.env, 'minor')
        self.assertEqual('3', prio.value)

    def test_ticket_type_update(self):
        tkttype = Type(self.env, 'task')
        self.assertEqual(tkttype.name, 'task')
        self.assertEqual(tkttype.value, '3')
        tkttype.name = 'foo'
        tkttype.update()
        Type(self.env, 'foo')


class MilestoneTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        self.db = self.env.get_db_cnx()

    def tearDown(self):
        self.env.reset_db()

    def test_new_milestone(self):
        milestone = Milestone(self.env)
        self.assertEqual(False, milestone.exists)
        self.assertEqual(None, milestone.name)
        self.assertEqual(None, milestone.due)
        self.assertEqual(None, milestone.completed)
        self.assertEqual('', milestone.description)

    def test_new_milestone_empty_name(self):
        """
        Verifies that specifying an empty milestone name results in the
        milestone being correctly detected as non-existent.
        """
        milestone = Milestone(self.env, '')
        self.assertEqual(False, milestone.exists)
        self.assertEqual(None, milestone.name)
        self.assertEqual(None, milestone.due)
        self.assertEqual(None, milestone.completed)
        self.assertEqual('', milestone.description)

    def test_existing_milestone(self):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO milestone (name) VALUES ('Test')")
        cursor.close()

        milestone = Milestone(self.env, 'Test')
        self.assertEqual(True, milestone.exists)
        self.assertEqual('Test', milestone.name)
        self.assertEqual(None, milestone.due)
        self.assertEqual(None, milestone.completed)
        self.assertEqual('', milestone.description)

    def test_create_milestone(self):
        milestone = Milestone(self.env)
        milestone.name = 'Test'
        milestone.insert()

        cursor = self.db.cursor()
        cursor.execute("SELECT name,due,completed,description FROM milestone "
                       "WHERE name='Test'")
        self.assertEqual(('Test', 0, 0, ''), cursor.fetchone())

    def test_create_milestone_without_name(self):
        milestone = Milestone(self.env)
        self.assertRaises(AssertionError, milestone.insert)

    def test_delete_milestone(self):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO milestone (name) VALUES ('Test')")
        cursor.close()

        milestone = Milestone(self.env, 'Test')
        milestone.delete()

        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM milestone WHERE name='Test'")
        self.assertEqual(None, cursor.fetchone())

    def test_delete_milestone_retarget_tickets(self):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO milestone (name) VALUES ('Test')")
        cursor.close()

        tkt1 = Ticket(self.env)
        tkt1.populate({'summary': 'Foo', 'milestone': 'Test'})
        tkt1.insert()
        tkt2 = Ticket(self.env)
        tkt2.populate({'summary': 'Bar', 'milestone': 'Test'})
        tkt2.insert()

        milestone = Milestone(self.env, 'Test')
        milestone.delete(retarget_to='Other')

        self.assertEqual('Other', Ticket(self.env, tkt1.id)['milestone'])
        self.assertEqual('Other', Ticket(self.env, tkt2.id)['milestone'])

    def test_update_milestone(self):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO milestone (name) VALUES ('Test')")
        cursor.close()

        milestone = Milestone(self.env, 'Test')
        t1 = datetime(2001,01,01, tzinfo=utc)
        t2 = datetime(2002,02,02, tzinfo=utc)
        milestone.due = t1
        milestone.completed = t2
        milestone.description = 'Foo bar'
        milestone.update()

        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM milestone WHERE name='Test'")
        self.assertEqual(('Test', to_timestamp(t1), to_timestamp(t2), 'Foo bar'),
                         cursor.fetchone())

    def test_update_milestone_without_name(self):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO milestone (name) VALUES ('Test')")
        cursor.close()

        milestone = Milestone(self.env, 'Test')
        milestone.name = None
        self.assertRaises(AssertionError, milestone.update)

    def test_update_milestone_update_tickets(self):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO milestone (name) VALUES ('Test')")
        cursor.close()

        tkt1 = Ticket(self.env)
        tkt1.populate({'summary': 'Foo', 'milestone': 'Test'})
        tkt1.insert()
        tkt2 = Ticket(self.env)
        tkt2.populate({'summary': 'Bar', 'milestone': 'Test'})
        tkt2.insert()

        milestone = Milestone(self.env, 'Test')
        milestone.name = 'Testing'
        milestone.update()

        self.assertEqual('Testing', Ticket(self.env, tkt1.id)['milestone'])
        self.assertEqual('Testing', Ticket(self.env, tkt2.id)['milestone'])

    def test_select_milestones(self):
        cursor = self.db.cursor()
        cursor.executemany("INSERT INTO milestone (name) VALUES (%s)",
                           [('1.0',), ('2.0',)])
        cursor.close()

        milestones = list(Milestone.select(self.env))
        self.assertEqual('1.0', milestones[0].name)
        assert milestones[0].exists
        self.assertEqual('2.0', milestones[1].name)
        assert milestones[1].exists


class ComponentTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)

    def tearDown(self):
        self.env.reset_db()

    def test_exists_negative(self):
        def get_fake_component():
            return Component(self.env, "Shrubbery")
        self.assertRaises(TracError, get_fake_component)

    def test_exists(self):
        """
        http://trac.edgewall.org/ticket/4247
        """
        for c in Component.select(self.env):
            self.assertEqual(c.exists, True)


class VersionTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)

    def tearDown(self):
        self.env.reset_db()

    def test_exists_negative(self):
        def get_fake_version():
            return Version(self.env, "-1")
        self.assertRaises(TracError, get_fake_version)

    def test_exists(self):
        """
        http://trac.edgewall.org/ticket/4247
        """
        for v in Version.select(self.env):
            self.assertEqual(v.exists, True)

def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TicketTestCase, 'test'))
    suite.addTest(unittest.makeSuite(EnumTestCase, 'test'))
    suite.addTest(unittest.makeSuite(MilestoneTestCase, 'test'))
    suite.addTest(unittest.makeSuite(ComponentTestCase, 'test'))
    suite.addTest(unittest.makeSuite(VersionTestCase, 'test'))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
