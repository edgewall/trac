from datetime import datetime, timedelta
import os.path
from StringIO import StringIO
import tempfile
import shutil
import unittest

from trac import core
from trac.attachment import Attachment
from trac.core import TracError, implements
from trac.resource import ResourceNotFound
from trac.ticket.model import Ticket, Component, Milestone, Priority, Type, Version
from trac.ticket.api import IMilestoneChangeListener, ITicketChangeListener
from trac.test import EnvironmentStub
from trac.util.datefmt import from_utimestamp, to_utimestamp, utc


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
        for k, v in kw.items():
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
        self.assertEqual(1, ticket.id)
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

    def test_ticket_id_is_always_int(self):
        ticket_id = self._insert_ticket('Foo')
        self.assertEqual(ticket_id, int(ticket_id))
        ticket = Ticket(self.env, str(ticket_id))
        self.assertEqual(ticket_id, ticket.id)
        self.assertEqual(ticket.resource.id, ticket_id)

    def test_can_save_ticket_without_explicit_comment(self):
        ticket = Ticket(self.env)
        ticket.insert()
        
        ticket['summary'] = 'another summary'
        ticket.save_changes('foo')
        
        changes = ticket.get_changelog()
        comment_change = [c for c in changes if c[2] == 'comment'][0]
        self.assertEqual('1', comment_change[3])
        self.assertEqual('', comment_change[4])

    def test_can_save_ticket_without_explicit_username(self):
        ticket = Ticket(self.env)
        ticket.insert()
        
        ticket['summary'] = 'another summary'
        ticket.save_changes()
        
        for change in ticket.get_changelog():
            self.assertEqual(None, change[1])

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

    def test_no_disown_from_changed_component(self):
        """
        Verify that a ticket is not disowned when the component is changed to
        a non-assigned component.
        """
        component1 = Component(self.env)
        component1.name = 'test1'
        component1.owner = 'joe'
        component1.insert()

        component2 = Component(self.env)
        component2.name = 'test2'
        component2.owner = ''
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
        self.assertEqual('joe', ticket['owner'])

    def test_populate_ticket(self):
        data = {'summary': 'Hello world', 'reporter': 'john',
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
        changelog = sorted(ticket.get_changelog())
        self.assertEqual([(now, 'jane', 'comment', '1', 'Testing', True),
                          (now, 'jane', 'component', 'foo', 'bar', True),
                          (now, 'jane', 'milestone', 'bar', 'foo', True)],
                         changelog)

    def test_changelog_with_attachment(self):
        """Verify ordering of attachments and comments in the changelog."""
        tkt_id = self._insert_ticket('Test', reporter='joe', component='foo')
        ticket = Ticket(self.env, tkt_id)
        t1 = datetime(2001, 1, 1, 1, 1, 1, 0, utc)
        ticket.save_changes('jane', 'Testing', t1)
        t2 = datetime(2001, 1, 1, 1, 1, 2, 0, utc)
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("INSERT INTO attachment (type,id,filename,size,time,"
                       "                        description,author,ipnr) "
                       "VALUES ('ticket',%s,'file.txt',1234,%s,"
                       "        'My file','mark','')",
                       (str(tkt_id), to_utimestamp(t2)))
        db.commit()
        t3 = datetime(2001, 1, 1, 1, 1, 3, 0, utc)
        ticket.save_changes('jim', 'Other', t3)
        log = ticket.get_changelog()
        self.assertEqual(4, len(log))
        self.assertEqual((t1, 'jane', 'comment', '1', 'Testing', True), log[0])
        self.assertEqual([(t2, 'mark', 'attachment', '', 'file.txt', False),
                          (t2, 'mark', 'comment', '', 'My file', False)],
                          sorted(log[1:3]))
        self.assertEqual((t3, 'jim', 'comment', '2', 'Other', True), log[3])

    def test_subsecond_change(self):
        """Perform two ticket changes within a second."""
        tkt_id = self._insert_ticket('Test', reporter='joe', component='foo')
        ticket = Ticket(self.env, tkt_id)
        t1 = datetime(2001, 1, 1, 1, 1, 1, 123456, utc)
        ticket.save_changes('jane', 'Testing', t1)
        t2 = datetime(2001, 1, 1, 1, 1, 1, 123789, utc)
        ticket.save_changes('jim', 'Other', t2)
        log = ticket.get_changelog()
        self.assertEqual(2, len(log))
        self.assertEqual((t1, 'jane', 'comment', '1', 'Testing', True), log[0])
        self.assertEqual((t2, 'jim', 'comment', '2', 'Other', True), log[1])

    def test_changelog_with_reverted_change(self):
        tkt_id = self._insert_ticket('Test', reporter='joe', component='foo')
        ticket = Ticket(self.env, tkt_id)
        ticket['component'] = 'bar'
        ticket['component'] = 'foo'
        now = datetime(2001, 1, 1,  1, 1, 1, 0, utc)
        ticket.save_changes('jane', 'Testing', now)
        self.assertEqual([(now, 'jane', 'comment', '1', 'Testing', True)],
                         list(ticket.get_changelog()))

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


class TicketCommentTestCase(unittest.TestCase):
    
    def _insert_ticket(self, summary, when, **kwargs):
        ticket = Ticket(self.env)
        for k, v in kwargs.iteritems():
            ticket[k] = v
        self.id = ticket.insert(when)

    def _modify_ticket(self, author, comment, when, cnum, **kwargs):
        ticket = Ticket(self.env, self.id)
        for k, v in kwargs.iteritems():
            ticket[k] = v
        ticket.save_changes(author, comment, when, cnum=cnum)
    
    def _find_change(self, ticket, cnum):
        (ts, author, comment) = ticket._find_change(cnum, self.db)
        return from_utimestamp(ts)
    
    def assertChange(self, ticket, cnum, date, author, **fields):
        change = ticket.get_change(cnum)
        self.assertEqual(dict(date=date, author=author, fields=fields), change)
    

class TicketCommentEditTestCase(TicketCommentTestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        self.db = self.env.get_db_cnx()
        self.created = datetime(2001, 1, 1, 1, 0, 0, 0, utc)
        self._insert_ticket('Test ticket', self.created,
                            owner='john', keywords='a, b, c')
        self.t1 = self.created + timedelta(seconds=1)
        self._modify_ticket('jack', 'Comment 1', self.t1, '1')
        self.t2 = self.created + timedelta(seconds=2)
        self._modify_ticket('john', 'Comment 2', self.t2, '1.2',
                            owner='jack')
        self.t3 = self.created + timedelta(seconds=3)
        self._modify_ticket('jim', 'Comment 3', self.t3, '3',
                            keywords='a, b')

    def tearDown(self):
        self.env.reset_db()

    def test_modify_comment(self):
        """Check modification of a "standalone" comment"""
        ticket = Ticket(self.env, self.id)
        self.assertChange(ticket, 1, self.t1, 'jack',
            comment=dict(author='jack', old='1', new='Comment 1'))
        self.assertChange(ticket, 2, self.t2, 'john',
            owner=dict(author='john', old='john', new='jack'),
            comment=dict(author='john', old='1.2', new='Comment 2'))
        self.assertChange(ticket, 3, self.t3, 'jim',
            keywords=dict(author='jim', old='a, b, c', new='a, b'),
            comment=dict(author='jim', old='3', new='Comment 3'))
        
        t = self.created + timedelta(seconds=10)
        ticket.modify_comment(self._find_change(ticket, 1),
                              'joe', 'New comment 1', t)
        self.assertChange(ticket, 1, self.t1, 'jack',
            comment=dict(author='jack', old='1', new='New comment 1'),
            _comment0=dict(author='joe', old='Comment 1',
                           new=str(to_utimestamp(t))))
        self.assertEqual(t, Ticket(self.env, self.id)['changetime'])

    def test_threading(self):
        """Check modification of a "threaded" comment"""
        ticket = Ticket(self.env, self.id)
        t = self.created + timedelta(seconds=20)
        ticket.modify_comment(self._find_change(ticket, 2),
                              'joe', 'New comment 2', t)
        self.assertChange(ticket, 2, self.t2, 'john',
            owner=dict(author='john', old='john', new='jack'),
            comment=dict(author='john', old='1.2', new='New comment 2'),
            _comment0=dict(author='joe', old='Comment 2',
                           new=str(to_utimestamp(t))))
        
    def test_modify_missing_cnum(self):
        """Editing a comment with no cnum in oldvalue"""
        cursor = self.db.cursor()
        cursor.execute("UPDATE ticket_change SET oldvalue='' "
                       "WHERE oldvalue='3'")
        self.db.commit()

        ticket = Ticket(self.env, self.id)
        t = self.created + timedelta(seconds=30)
        ticket.modify_comment(self._find_change(ticket, 3),
                              'joe', 'New comment 3', t)
        self.assertChange(ticket, 3, self.t3, 'jim',
            keywords=dict(author='jim', old='a, b, c', new='a, b'),
            comment=dict(author='jim', old='', new='New comment 3'),
            _comment0=dict(author='joe', old='Comment 3',
                           new=str(to_utimestamp(t))))
        
    def test_modify_missing_comment(self):
        """Editing a comment where the comment field is missing"""
        cursor = self.db.cursor()
        cursor.execute("DELETE FROM ticket_change "
                       "WHERE field='comment' AND oldvalue='1.2'")
        self.db.commit()

        ticket = Ticket(self.env, self.id)
        t = self.created + timedelta(seconds=40)
        ticket.modify_comment(self._find_change(ticket, 2),
                              'joe', 'New comment 2', t)
        self.assertChange(ticket, 2, self.t2, 'john',
            owner=dict(author='john', old='john', new='jack'),
            comment=dict(author='john', old='', new='New comment 2'),
            _comment0=dict(author='joe', old='',
                           new=str(to_utimestamp(t))))
        
    def test_modify_missing_cnums_and_comment(self):
        """Editing a comment when all cnums are missing and one comment
        field is missing
        """
        cursor = self.db.cursor()
        cursor.execute("UPDATE ticket_change SET oldvalue='' "
                       "WHERE oldvalue='1'")
        cursor.execute("DELETE FROM ticket_change "
                       "WHERE field='comment' AND oldvalue='1.2'")
        cursor.execute("UPDATE ticket_change SET oldvalue='' "
                       "WHERE oldvalue='3'")
        self.db.commit()

        # Modify after missing comment
        ticket = Ticket(self.env, self.id)
        t = self.created + timedelta(seconds=50)
        ticket.modify_comment(self._find_change(ticket, 3),
                              'joe', 'New comment 3', t)
        self.assertChange(ticket, 3, self.t3, 'jim',
            keywords=dict(author='jim', old='a, b, c', new='a, b'),
            comment=dict(author='jim', old='', new='New comment 3'),
            _comment0=dict(author='joe', old='Comment 3',
                           new=str(to_utimestamp(t))))

        # Modify missing comment
        t = self.created + timedelta(seconds=60)
        ticket.modify_comment(self._find_change(ticket, 2),
                              'joe', 'New comment 2', t)
        self.assertChange(ticket, 2, self.t2, 'john',
            owner=dict(author='john', old='john', new='jack'),
            comment=dict(author='john', old='', new='New comment 2'),
            _comment0=dict(author='joe', old='',
                           new=str(to_utimestamp(t))))

    def test_missing_comment_edit(self):
        """Modify a comment where one edit is missing"""
        ticket = Ticket(self.env, self.id)
        t1 = self.created + timedelta(seconds=70)
        ticket.modify_comment(self._find_change(ticket, 1),
                              'joe', 'New comment 1', t1)
        t2 = self.created + timedelta(seconds=80)
        ticket.modify_comment(self._find_change(ticket, 1),
                              'joe', 'Other comment 1', t2)

        self.assertChange(ticket, 1, self.t1, 'jack',
            comment=dict(author='jack', old='1', new='Other comment 1'),
            _comment0=dict(author='joe', old='Comment 1',
                           new=str(to_utimestamp(t1))),
            _comment1=dict(author='joe', old='New comment 1',
                           new=str(to_utimestamp(t2))))
        
        cursor = self.db.cursor()
        cursor.execute("DELETE FROM ticket_change "
                       "WHERE field='_comment0'")
        self.db.commit()

        t3 = self.created + timedelta(seconds=90)
        ticket.modify_comment(self._find_change(ticket, 1),
                              'joe', 'Newest comment 1', t3)
        
        self.assertChange(ticket, 1, self.t1, 'jack',
            comment=dict(author='jack', old='1', new='Newest comment 1'),
            _comment1=dict(author='joe', old='New comment 1',
                           new=str(to_utimestamp(t2))),
            _comment2=dict(author='joe', old='Other comment 1',
                           new=str(to_utimestamp(t3))))

    def test_comment_history(self):
        """Check the generation of the comment history"""
        ticket = Ticket(self.env, self.id)
        t = [self.t1]
        for i in range(1, 32):
            t.append(self.created + timedelta(minutes=i))
            ticket.modify_comment(self._find_change(ticket, 1),
                                  'joe (%d)' % i,
                                  'Comment 1 (%d)' % i, t[-1])
        history = ticket.get_comment_history(1)
        self.assertEqual((0, t[0], 'jack', 'Comment 1'), history[0])
        for i in range(1, len(history)):
            self.assertEqual((i, t[i], 'joe (%d)' % i,
                             'Comment 1 (%d)' % i), history[i])


class TicketCommentDeleteTestCase(TicketCommentTestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        self.env.config.set('ticket-custom', 'foo', 'text')
        self.db = self.env.get_db_cnx()
        self.created = datetime(2001, 1, 1, 1, 0, 0, 0, utc)
        self._insert_ticket('Test ticket', self.created,
                            owner='john', keywords='a, b, c', foo='initial')
        self.t1 = self.created + timedelta(seconds=1)
        self._modify_ticket('jack', 'Comment 1', self.t1, '1',
                            foo='change 1')
        self.t2 = self.created + timedelta(seconds=2)
        self._modify_ticket('john', 'Comment 2', self.t2, '1.2',
                            owner='jack', foo='change2')
        self.t3 = self.created + timedelta(seconds=3)
        self._modify_ticket('jim', 'Comment 3', self.t3, '3',
                            keywords='a, b', foo='change3')
        self.t4 = self.created + timedelta(seconds=4)
        self._modify_ticket('joe', 'Comment 4', self.t4, '4',
                            keywords='a', foo='change4')

    def tearDown(self):
        self.env.reset_db()

    def test_delete_last_comment(self):
        ticket = Ticket(self.env, self.id)
        self.assertEqual('a', ticket['keywords'])
        self.assertEqual('change4', ticket['foo'])
        ticket.delete_change(4)
        self.assertEqual('a, b', ticket['keywords'])
        self.assertEqual('change3', ticket['foo'])
        self.assertEqual(None, ticket.get_change(4))
        self.assertNotEqual(None, ticket.get_change(3))
        self.assertEqual(self.t3, ticket.time_changed)
    
    def test_delete_mid_comment(self):
        ticket = Ticket(self.env, self.id)
        self.assertChange(ticket, 4, self.t4, 'joe',
            comment=dict(author='joe', old='4', new='Comment 4'),
            keywords=dict(author='joe', old='a, b', new='a'),
            foo=dict(author='joe', old='change3', new='change4'))
        ticket.delete_change(3)
        self.assertEqual(None, ticket.get_change(3))
        self.assertEqual('a', ticket['keywords'])
        self.assertChange(ticket, 4, self.t4, 'joe',
            comment=dict(author='joe', old='4', new='Comment 4'),
            keywords=dict(author='joe', old='a, b, c', new='a'),
            foo=dict(author='joe', old='change2', new='change4'))
        self.assertEqual(self.t4, ticket.time_changed)
        
    def test_delete_mid_comment_inconsistent(self):
        # Make oldvalue on keywords for change 4 inconsistent. This should
        # result in no change in oldvalue when deleting change 3. The
        # oldvalue of foo should change normally.
        cursor = self.db.cursor()
        cursor.execute("UPDATE ticket_change SET oldvalue='1, 2' "
                       "WHERE field='keywords' AND oldvalue='a, b'")
        self.db.commit()

        ticket = Ticket(self.env, self.id)
        self.assertChange(ticket, 4, self.t4, 'joe',
            comment=dict(author='joe', old='4', new='Comment 4'),
            keywords=dict(author='joe', old='1, 2', new='a'),
            foo=dict(author='joe', old='change3', new='change4'))
        ticket.delete_change(3)
        self.assertEqual(None, ticket.get_change(3))
        self.assertEqual('a', ticket['keywords'])
        self.assertChange(ticket, 4, self.t4, 'joe',
            comment=dict(author='joe', old='4', new='Comment 4'),
            keywords=dict(author='joe', old='1, 2', new='a'),
            foo=dict(author='joe', old='change2', new='change4'))
        
    def test_delete_all_comments(self):
        # See ticket:10338
        ticket = Ticket(self.env, self.id)
        ticket.delete_change(4)
        ticket.delete_change(3)
        ticket.delete_change(2)
        ticket.delete_change(1)
        self.assertEquals(ticket['time'], ticket['changetime'])


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


class TestMilestoneChangeListener(core.Component):
    implements(IMilestoneChangeListener)

    def milestone_created(self, milestone):
        self.action = 'created'
        self.milestone = milestone

    def milestone_changed(self, milestone, old_values):
        self.action = 'changed'
        self.milestone = milestone
        self.old_values = old_values
        
    def milestone_deleted(self, milestone):
        self.action = 'deleted'
        self.milestone = milestone


class MilestoneTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        self.env.path = os.path.join(tempfile.gettempdir(), 'trac-tempenv')
        os.mkdir(self.env.path)
        self.db = self.env.get_db_cnx()

    def tearDown(self):
        shutil.rmtree(self.env.path)
        self.env.reset_db()

    def _create_milestone(self, **values):
        milestone = Milestone(self.env)
        for k, v in values.iteritems():
            setattr(milestone, k, v)
        return milestone

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

    def test_create_and_update_milestone(self):
        milestone = Milestone(self.env)
        milestone.name = 'Test'
        milestone.insert()

        cursor = self.db.cursor()
        cursor.execute("SELECT name,due,completed,description FROM milestone "
                       "WHERE name='Test'")
        self.assertEqual(('Test', 0, 0, ''), cursor.fetchone())
        
        # Use the same model object to update the milestone
        milestone.description = 'Some text'
        milestone.update()
        cursor.execute("SELECT name,due,completed,description FROM milestone "
                       "WHERE name='Test'")
        self.assertEqual(('Test', 0, 0, 'Some text'), cursor.fetchone())

    def test_create_milestone_without_name(self):
        milestone = Milestone(self.env)
        self.assertRaises(TracError, milestone.insert)

    def test_delete_milestone(self):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO milestone (name) VALUES ('Test')")
        cursor.close()

        milestone = Milestone(self.env, 'Test')
        milestone.delete()
        self.assertEqual(False, milestone.exists)

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
        self.assertEqual(False, milestone.exists)

        self.assertEqual('Other', Ticket(self.env, tkt1.id)['milestone'])
        self.assertEqual('Other', Ticket(self.env, tkt2.id)['milestone'])

    def test_update_milestone(self):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO milestone (name) VALUES ('Test')")
        cursor.close()

        milestone = Milestone(self.env, 'Test')
        t1 = datetime(2001, 01, 01, tzinfo=utc)
        t2 = datetime(2002, 02, 02, tzinfo=utc)
        milestone.due = t1
        milestone.completed = t2
        milestone.description = 'Foo bar'
        milestone.update()

        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM milestone WHERE name='Test'")
        self.assertEqual(('Test', to_utimestamp(t1), to_utimestamp(t2),
                          'Foo bar'),
                         cursor.fetchone())

    def test_update_milestone_without_name(self):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO milestone (name) VALUES ('Test')")
        cursor.close()

        milestone = Milestone(self.env, 'Test')
        milestone.name = None
        self.assertRaises(TracError, milestone.update)

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

    def test_rename_milestone(self):
        milestone = Milestone(self.env)
        milestone.name = 'OldName'
        milestone.insert()
        
        attachment = Attachment(self.env, 'milestone', 'OldName')
        attachment.insert('foo.txt', StringIO(), 0, 1)
        
        milestone = Milestone(self.env, 'OldName')
        milestone.name = 'NewName'
        milestone.update()
        
        self.assertRaises(ResourceNotFound, Milestone, self.env, 'OldName')
        self.assertEqual('NewName', Milestone(self.env, 'NewName').name)

        attachments = Attachment.select(self.env, 'milestone', 'OldName')
        self.assertRaises(StopIteration, attachments.next)
        attachments = Attachment.select(self.env, 'milestone', 'NewName')
        self.assertEqual('foo.txt', attachments.next().filename)
        self.assertRaises(StopIteration, attachments.next)
        
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

    def test_change_listener_created(self):
        listener = TestMilestoneChangeListener(self.env)
        milestone = self._create_milestone(name='Milestone 1')
        milestone.insert()
        self.assertEqual('created', listener.action)
        self.assertEqual(milestone, listener.milestone)

    def test_change_listener_changed(self):
        listener = TestMilestoneChangeListener(self.env)
        milestone = self._create_milestone(
            name='Milestone 1',
            due=datetime(2001, 01, 01, tzinfo=utc),
            description='The milestone description')
        milestone.insert()
        
        milestone.name = 'Milestone 2'
        milestone.completed = datetime(2001, 02, 03, tzinfo=utc)
        milestone.description = 'The changed description'
        milestone.update()
        
        self.assertEqual('changed', listener.action)
        self.assertEqual(milestone, listener.milestone)
        self.assertEqual({'name': 'Milestone 1', 'completed': None,
                          'description': 'The milestone description'},
                         listener.old_values)

    def test_change_listener_deleted(self):
        listener = TestMilestoneChangeListener(self.env)
        milestone = self._create_milestone(name='Milestone 1')
        milestone.insert()
        self.assertEqual(True, milestone.exists)
        milestone.delete()
        self.assertEqual('Milestone 1', milestone.name)
        self.assertEqual(False, milestone.exists)
        self.assertEqual('deleted', listener.action)
        self.assertEqual(milestone, listener.milestone)


class ComponentTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        self.db = self.env.get_db_cnx()

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

    def test_create_and_update(self):
        component = Component(self.env)
        component.name = 'Test'
        component.insert()
        
        cursor = self.db.cursor()
        cursor.execute("SELECT name,owner,description FROM component "
                       "WHERE name='Test'")
        self.assertEqual(('Test', None, None), cursor.fetchone())
        
        # Use the same model object to update the component
        component.owner = 'joe'
        component.update()
        cursor.execute("SELECT name,owner,description FROM component "
                       "WHERE name='Test'")
        self.assertEqual(('Test', 'joe', None), cursor.fetchone())


class VersionTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        self.db = self.env.get_db_cnx()

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

    def test_create_and_update(self):
        version = Version(self.env)
        version.name = 'Test'
        version.insert()
        
        cursor = self.db.cursor()
        cursor.execute("SELECT name,time,description FROM version "
                       "WHERE name='Test'")
        self.assertEqual(('Test', 0, None), cursor.fetchone())
        
        # Use the same model object to update the version
        version.description = 'Some text'
        version.update()
        cursor.execute("SELECT name,time,description FROM version "
                       "WHERE name='Test'")
        self.assertEqual(('Test', 0, 'Some text'), cursor.fetchone())


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TicketTestCase, 'test'))
    suite.addTest(unittest.makeSuite(TicketCommentEditTestCase, 'test'))
    suite.addTest(unittest.makeSuite(TicketCommentDeleteTestCase, 'test'))
    suite.addTest(unittest.makeSuite(EnumTestCase, 'test'))
    suite.addTest(unittest.makeSuite(MilestoneTestCase, 'test'))
    suite.addTest(unittest.makeSuite(ComponentTestCase, 'test'))
    suite.addTest(unittest.makeSuite(VersionTestCase, 'test'))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
