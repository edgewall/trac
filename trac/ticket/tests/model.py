# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2019 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

from datetime import datetime, timedelta
import io
import unittest

from trac import core
from trac.attachment import Attachment
from trac.core import TracError, implements
from trac.resource import Resource, ResourceExistsError, ResourceNotFound
from trac.test import EnvironmentStub, mkdtemp
from trac.ticket.api import (
    IMilestoneChangeListener, ITicketChangeListener, TicketSystem
)
from trac.ticket.model import (
    Component, Milestone, Priority, Report, Ticket, Version
)
from trac.ticket.roadmap import MilestoneModule
from trac.ticket.test import insert_ticket
from trac.util.datefmt import datetime_now, from_utimestamp, to_utimestamp, utc


class TicketTestCase(unittest.TestCase):

    ticket_change_listeners = []

    @classmethod
    def setUpClass(cls):
        class LegacyTicketChangeListener(core.Component):
            """The legacy listener doesn't have the `ticket_comment_modified`
            and `ticket_change_deleted` methods.
            """
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

        cls.ticket_change_listeners = [LegacyTicketChangeListener]

    @classmethod
    def tearDownClass(cls):
        for listener in cls.ticket_change_listeners:
            core.ComponentMeta.deregister(listener)

    def setUp(self):
        self.env = EnvironmentStub(default_data=True,
                                   enable=['trac.ticket.*'] +
                                           self.ticket_change_listeners)
        self.env.config.set('ticket-custom', 'foo', 'text')
        self.env.config.set('ticket-custom', 'cbon', 'checkbox')
        self.env.config.set('ticket-custom', 'cboff', 'checkbox')

    def tearDown(self):
        self.env.reset_db()

    def _insert_ticket(self, summary, **kw):
        """Helper for inserting a ticket into the database"""
        ticket = insert_ticket(self.env, summary=summary, **kw)
        return ticket.id

    def _create_a_ticket(self):
        ticket = Ticket(self.env)
        ticket['reporter'] = 'santa'
        ticket['summary'] = 'Foo'
        ticket['foo'] = 'This is a custom field'
        return ticket

    def test_resource_id_is_none(self):
        ticket = Ticket(self.env)
        self.assertEqual(Resource('ticket'), ticket.resource)

    def test_resource_exists(self):
        ticket_id = self._insert_ticket('Foo')
        ticket = Ticket(self.env, ticket_id)
        self.assertEqual(Resource('ticket', 1), ticket.resource)

    def test_invalid_ticket_id(self):
        self.assertEqual(Ticket.id_is_valid(-1), False)
        self.assertEqual(Ticket.id_is_valid(0), False)
        self.assertEqual(Ticket.id_is_valid(1), True)
        self.assertEqual(Ticket.id_is_valid(1 << 31), True)
        self.assertEqual(Ticket.id_is_valid(1 << 32), False)
        self.assertRaises(ResourceNotFound, Ticket, self.env, -1)
        self.assertRaises(ResourceNotFound, Ticket, self.env, 1 << 32)

    def test_repr(self):
        ticket = self._create_a_ticket()
        self.assertEqual("<Ticket None>", repr(ticket))
        ticket.insert()
        self.assertEqual("<Ticket 1>", repr(ticket))

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
        self.assertIn(log[0][2], ok_vals)
        self.assertIn(log[1][2], ok_vals)
        self.assertIn(log[2][2], ok_vals)

    def test_create_ticket_5(self):
        ticket3 = self._modify_a_ticket()
        # Testing delete()
        ticket3.delete()
        log = ticket3.get_changelog()
        self.assertEqual(len(log), 0)
        self.assertRaises(TracError, Ticket, self.env, 1)

    def _test_empty_strings_stored_as_null(self, ticket):
        """Ticket fields that contain empty strings are stored as NULLs
        in the database. NULLs are cast to empty strings on fetch.
        """
        std_fields = [name for name in ticket.std_fields
                           if name not in ticket.protected_fields]
        cst_fields = [name for name in ticket.custom_fields
                           if name not in ticket.protected_fields]

        # Values are stored as NULL in the database
        self.assertEqual([(None,) * len(std_fields)],
                         self.env.db_query("""
                            SELECT %s FROM ticket WHERE id=%%s
                            """ % ','.join(std_fields), (ticket.id,)))
        self.assertEqual([(None,)] * len(cst_fields),
                         self.env.db_query("""
                            SELECT value FROM ticket_custom
                            WHERE ticket=%%s AND name IN (%s)
                            """ % ','.join(['%s'] * len(cst_fields)),
                            [ticket.id] + cst_fields))
        # Values are returned from the model as empty strings
        for name in ticket.editable_fields:
            self.assertEqual('', ticket[name], name)

    def test_create_empty_strings_stored_as_null(self):
        """Ticket fields with empty strings are NULL when creating ticket.
        """
        self.env.config.set('ticket-custom', 'time1', 'time')
        self.env.config.save()
        ticket = Ticket(self.env)
        ticket.populate({name: '' for name in ticket.editable_fields})
        ticket.insert()

        self._test_empty_strings_stored_as_null(ticket)

    def test_change_empty_strings_stored_as_null(self):
        """Ticket fields with empty strings are NULL when changing ticket.
        """
        self.env.config.set('ticket-custom', 'time1', 'time')
        self.env.config.save()
        ticket = insert_ticket(self.env)
        ticket.populate({name: '' for name in ticket.editable_fields})
        ticket.save_changes()

        self._test_empty_strings_stored_as_null(ticket)

    def test_whitespace_stripped_from_text_field(self):
        """Whitespace is stripped from text fields.
        Test for regression of #11891.
        """
        ticket = insert_ticket(self.env, keywords='kw1', milestone='milestone1')
        ticket['keywords'] = '  kw1'
        ticket['milestone'] = 'milestone2'
        ticket.save_changes()
        changes = self.env.db_query("""
            SELECT oldvalue, newvalue FROM ticket_change
            """)

        self.assertEqual('kw1', ticket['keywords'])
        self.assertEqual('milestone2', ticket['milestone'])
        self.assertEqual(2, len(changes))
        self.assertIn(('milestone1', 'milestone2'), changes)
        self.assertIn(('1', None), changes)

    def test_ticket_id_is_always_int(self):
        ticket_id = self._insert_ticket('Foo')
        self.assertEqual(ticket_id, int(ticket_id))
        ticket = Ticket(self.env, str(ticket_id))
        self.assertEqual(ticket_id, ticket.id)
        self.assertEqual(ticket.resource.id, ticket_id)

    def test_resource_not_found_for_invalid_ticket_id(self):
        try:
            Ticket(self.env, '42')
            self.fail('ResourceNotFound not raised')
        except ResourceNotFound as e:
            self.assertEqual(u'Ticket 42 does not exist.', unicode(e))
        try:
            Ticket(self.env, 'blah')
            self.fail('ResourceNotFound not raised')
        except ResourceNotFound as e:
            self.assertEqual(u'Ticket blah does not exist.', unicode(e))

    def test_can_save_ticket_without_explicit_comment(self):
        ticket = insert_ticket(self.env)

        ticket['summary'] = 'another summary'
        ticket.save_changes('foo')

        changes = ticket.get_changelog()
        comment_change = [c for c in changes if c[2] == 'comment'][0]
        self.assertEqual('1', comment_change[3])
        self.assertEqual('', comment_change[4])

    def test_can_save_ticket_without_explicit_username(self):
        ticket = insert_ticket(self.env)

        ticket['summary'] = 'another summary'
        ticket.save_changes()

        for change in ticket.get_changelog():
            self.assertIsNone(change[1])

    def test_comment_with_whitespace_only_is_not_saved(self):
        ticket = insert_ticket(self.env)

        ticket.save_changes(comment='\n \n ')
        self.assertEqual(0, len(ticket.get_changelog()))

    def test_prop_whitespace_change_is_not_saved(self):
        ticket = insert_ticket(self.env, summary='ticket summary')

        ticket['summary'] = ' ticket summary '
        ticket.save_changes()
        self.assertEqual(0, len(ticket.get_changelog()))

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

    def test_ticket_custom_field_default_values(self):
        """Ticket created before a custom field is added will have the
        default value for the custom field.
        """
        tid = self._insert_ticket("The summary")
        self.env.config.set('ticket-custom', 'baz', 'text')
        self.env.config.set('ticket-custom', 'baz.value', 'Something')
        self.env.config.set('ticket-custom', 'bar', 'select')
        self.env.config.set('ticket-custom', 'bar.options', 'one|two|three')
        self.env.config.set('ticket-custom', 'bar.value', 'two')
        TicketSystem(self.env).reset_ticket_fields()
        del TicketSystem(self.env).custom_fields
        ticket = Ticket(self.env, tid)

        self.assertEqual('Something', ticket['baz'])
        self.assertEqual('two', ticket['bar'])

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
        self.assertIsNone(ticket['bar'])

        # Custom field
        self.assertEqual('bar', ticket['foo'])

        # Custom field of type 'checkbox'
        self.assertEqual('on', ticket['cbon'])
        self.assertEqual('0', ticket['cboff'])

    def test_custom_time(self):
        # Add a custom field of type 'time'
        self.env.config.set('ticket-custom', 'due', 'time')
        self.env.config.set('ticket-custom', 'start', 'time')
        self.env.config.set('ticket-custom', 'start.value', '20111130T0000Z')
        start_default = datetime(2011, 11, 30, 0, 0, 0, 0, utc)
        ticket = Ticket(self.env)
        self.assertNotIn('due', ticket.std_fields)
        self.assertIn('due', ticket.time_fields)
        self.assertNotIn('start', ticket.std_fields)
        self.assertIn('start', ticket.time_fields)

        ticket['reporter'] = 'john'
        ticket['summary'] = 'Time custom field'
        tktid = ticket.insert()
        ticket = Ticket(self.env, tktid)
        self.assertIsNone(ticket['due'])
        self.assertEqual(start_default, ticket['start'])

        ts = datetime(2011, 11, 11, 0, 0, 0, 0, utc)
        ticket['due'] = ts
        t1 = datetime(2001, 1, 1, 1, 1, 1, 0, utc)
        ticket.save_changes('joe', when=t1)
        self.assertEqual(ts, ticket['due'])
        self.assertEqual(2, len(ticket.get_changelog()))

        ticket['due'] = None
        ticket['start'] = None
        t2 = datetime(2001, 1, 1, 1, 1, 2, 0, utc)
        ticket.save_changes('joe', when=t2)
        self.assertIsNone(ticket['due'])
        self.assertIsNone(ticket['start'])
        self.assertEqual(5, len(ticket.get_changelog()))

        # Check regression from #13133: ticket change log entry must be
        # saved when time custom field changed from None to default value
        ticket['start'] = start_default
        t3 = datetime(2001, 1, 1, 1, 1, 3, 0, utc)
        ticket.save_changes('user', when=t3)
        self.assertEqual(start_default, ticket['start'])
        changelog = ticket.get_changelog()
        self.assertEqual(7, len(changelog))
        self.assertEqual((t3, 'user', 'start', '', start_default, 1),
                         changelog[6])

    def test_changelog(self):
        tkt_id = self._insert_ticket('Test', reporter='joe', component='foo',
                                     milestone='bar')
        ticket = Ticket(self.env, tkt_id)
        ticket['component'] = 'bar'
        ticket['milestone'] = 'foo'
        now = datetime(2001, 1, 1, 1, 1, 1, 0, utc)
        ticket.save_changes('jane', 'Testing', now)
        changelog = ticket.get_changelog()
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
        self.env.db_transaction("""
            INSERT INTO attachment (type, id, filename, size, time,
                                    description, author)
            VALUES ('ticket',%s,'file.txt',1234,%s, 'My file','mark')
            """, (str(tkt_id), to_utimestamp(t2)))
        t3 = datetime(2001, 1, 1, 1, 1, 3, 0, utc)
        ticket.save_changes('jim', 'Other', t3)
        log = ticket.get_changelog()
        self.assertEqual(4, len(log))
        self.assertEqual((t1, 'jane', 'comment', '1', 'Testing', True), log[0])
        self.assertEqual([(t2, 'mark', 'attachment', '', 'file.txt', False),
                          (t2, 'mark', 'comment', '', 'My file', False)],
                          log[1:3])
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

    def test_changelog_for_new_custom_field(self):
        """Ticket change entry is not added for a custom field with
        default value that is added after the ticket is created.
        """
        tkt_id = self._insert_ticket('Test')
        self.env.config.set('ticket-custom', 'text1', 'text')
        self.env.config.set('ticket-custom', 'checkbox1', 'checkbox')
        self.env.config.set('ticket-custom', 'checkbox1.value', '1')
        self.env.config.set('ticket-custom', 'date1', 'time')
        self.env.config.set('ticket-custom', 'date1.value', 'Aug 5, 2019')
        self.env.config.set('ticket-custom', 'date1.format', 'date')
        self.env.config.save()
        TicketSystem(self.env).reset_ticket_fields()
        del TicketSystem(self.env).custom_fields

        ticket = Ticket(self.env, tkt_id)
        ticket.save_changes('jane', 'Change 1')
        ticket_changes = list(ticket.get_changelog())

        self.assertEqual(1, len(ticket_changes))
        self.assertEqual('comment', ticket_changes[0][2])

    def test_change_listener_created(self):
        ts = TicketSystem(self.env)
        listener = ts.change_listeners[0]
        ticket = self._create_a_ticket()
        ticket.insert()

        self.assertEqual(1, len(ts.change_listeners))
        self.assertEqual('created', listener.action)
        self.assertEqual(ticket, listener.ticket)
        self.assertEqual(ticket.id, ticket.resource.id)

    def test_change_listener_changed(self):
        ts = TicketSystem(self.env)
        listener = ts.change_listeners[0]
        data = {'component': 'foo', 'milestone': 'bar'}
        tkt_id = self._insert_ticket('Hello World', reporter='john', **data)

        ticket = Ticket(self.env, tkt_id)
        ticket['component'] = 'new component'
        ticket['milestone'] = 'new milestone'

        comment = 'changing ticket'
        ticket.save_changes('author', comment)

        self.assertEqual(1, len(ts.change_listeners))
        self.assertEqual('changed', listener.action)
        self.assertEqual(comment, listener.comment)
        self.assertEqual('author', listener.author)
        for key, value in data.iteritems():
            self.assertEqual(value, listener.old_values[key])

    def test_change_listener_deleted(self):
        ts = TicketSystem(self.env)
        listener = ts.change_listeners[0]
        ticket = self._create_a_ticket()
        ticket.insert()
        ticket.delete()

        self.assertEqual(1, len(ts.change_listeners))
        self.assertEqual('deleted', listener.action)
        self.assertEqual(ticket, listener.ticket)


class TicketCommentTestCase(unittest.TestCase):

    ticket_change_listeners = []

    @classmethod
    def setUpClass(cls):
        class AllMethodTicketChangeListener(core.Component):
            """Ticket change listener that implements all methods of the
            interface.
            """
            implements(ITicketChangeListener)

            def ticket_created(self, ticket):
                pass

            def ticket_changed(self, ticket, comment, author, old_values):
                pass

            def ticket_deleted(self, ticket):
                pass

            def ticket_comment_modified(self, ticket, cdate, author, comment,
                                        old_comment):
                self.action = 'comment_modified'
                self.ticket = ticket
                self.cdate = cdate
                self.author = author
                self.comment = comment
                self.old_comment = old_comment

            def ticket_change_deleted(self, ticket, cdate, changes):
                self.action = 'change_deleted'
                self.ticket = ticket
                self.cdate = cdate
                self.changes = changes

        cls.ticket_change_listeners = [AllMethodTicketChangeListener]

    @classmethod
    def tearDownClass(cls):
        for listener in cls.ticket_change_listeners:
            core.ComponentMeta.deregister(listener)

    def _insert_ticket(self, summary, when, **kwargs):
        ticket = insert_ticket(self.env, summary=summary, when=when, **kwargs)
        self.id = ticket.id

    def _modify_ticket(self, author, comment, when, replyto=None, **kwargs):
        ticket = Ticket(self.env, self.id)
        for k, v in kwargs.iteritems():
            ticket[k] = v
        ticket.save_changes(author, comment, when, replyto)

    def _find_change(self, ticket, cnum):
        (ts, author, comment) = ticket._find_change(cnum)
        return from_utimestamp(ts)

    def assertChange(self, ticket, cnum, date, author, **fields):
        change = ticket.get_change(cnum=cnum)
        self.assertEqual(dict(date=date, author=author, fields=fields), change)


class TicketCommentEditTestCase(TicketCommentTestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True,
                                   enable=['trac.ticket.*'] +
                                          self.ticket_change_listeners)
        self.created = datetime(2001, 1, 1, 1, 0, 0, 0, utc)
        self._insert_ticket('Test ticket', self.created,
                            owner='john', keywords='a, b, c')
        self.t1 = self.created + timedelta(seconds=1)
        self._modify_ticket('jack', 'Comment 1', self.t1)
        self.t2 = self.created + timedelta(seconds=2)
        self._modify_ticket('john', 'Comment 2', self.t2, '1',
                            owner='jack')
        self.t3 = self.created + timedelta(seconds=3)
        self._modify_ticket('jim', 'Comment 3', self.t3,
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
        self.env.db_transaction(
            "UPDATE ticket_change SET oldvalue='' WHERE oldvalue='3'")
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
        self.env.db_transaction("""
            DELETE FROM ticket_change WHERE field='comment' AND oldvalue='1.2'
            """)
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
        with self.env.db_transaction as db:
            db("UPDATE ticket_change SET oldvalue='' WHERE oldvalue='1'")
            db("""DELETE FROM ticket_change
                  WHERE field='comment' AND oldvalue='1.2'""")
            db("UPDATE ticket_change SET oldvalue='' WHERE oldvalue='3'")

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

        self.env.db_transaction(
            "DELETE FROM ticket_change WHERE field='_comment0'")

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
        for i in xrange(1, 32):
            t.append(self.created + timedelta(minutes=i))
            ticket.modify_comment(self._find_change(ticket, 1),
                                  'joe (%d)' % i,
                                  'Comment 1 (%d)' % i, t[-1])
        history = ticket.get_comment_history(cnum=1)
        self.assertEqual((0, t[0], 'jack', 'Comment 1'), history[0])
        for i in xrange(1, len(history)):
            self.assertEqual((i, t[i], 'joe (%d)' % i,
                             'Comment 1 (%d)' % i), history[i])
        history = ticket.get_comment_history(cdate=self.t1)
        self.assertEqual((0, t[0], 'jack', 'Comment 1'), history[0])
        for i in xrange(1, len(history)):
            self.assertEqual((i, t[i], 'joe (%d)' % i,
                             'Comment 1 (%d)' % i), history[i])

    def test_change_listener_comment_modified(self):
        ts = TicketSystem(self.env)
        listener = ts.change_listeners[0]
        ticket = Ticket(self.env, self.id)
        ticket.modify_comment(cdate=self.t2, author='jack',
                              comment='New Comment 2', when=datetime_now(utc))

        self.assertEqual(1, len(ts.change_listeners))
        self.assertEqual('comment_modified', listener.action)
        self.assertEqual(ticket, listener.ticket)
        self.assertEqual(self.t2, listener.cdate)
        self.assertEqual('jack', listener.author)
        self.assertEqual('New Comment 2', listener.comment)
        self.assertEqual('Comment 2', listener.old_comment)

    def test_get_comment_number(self):
        ticket = Ticket(self.env, self.id)
        self.assertEqual(1, ticket.get_comment_number(self.created +
                                                      timedelta(seconds=1)))
        self.assertEqual(2, ticket.get_comment_number(self.created +
                                                      timedelta(seconds=2)))
        self.assertEqual(3, ticket.get_comment_number(self.created +
                                                      timedelta(seconds=3)))


class TicketCommentDeleteTestCase(TicketCommentTestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True,
                                   enable=['trac.ticket.*'] +
                                          self.ticket_change_listeners)
        self.env.config.set('ticket-custom', 'foo', 'text')
        self.created = datetime(2001, 1, 1, 1, 0, 0, 0, utc)
        self._insert_ticket('Test ticket', self.created,
                            owner='john', keywords='a, b, c', foo='initial')
        self.t1 = self.created + timedelta(seconds=1)
        self._modify_ticket('jack', 'Comment 1', self.t1,
                            foo='change 1')
        self.t2 = self.created + timedelta(seconds=2)
        self._modify_ticket('john', 'Comment 2', self.t2, '1',
                            owner='jack', foo='change2')
        self.t3 = self.created + timedelta(seconds=3)
        self._modify_ticket('jim', 'Comment 3', self.t3,
                            keywords='a, b', foo='change3')
        self.t4 = self.created + timedelta(seconds=4)
        self._modify_ticket('joe', 'Comment 4', self.t4,
                            keywords='a', foo='change4')

    def tearDown(self):
        self.env.reset_db()

    def test_delete_last_comment(self):
        ticket = Ticket(self.env, self.id)
        self.assertEqual('a', ticket['keywords'])
        self.assertEqual('change4', ticket['foo'])
        t = datetime_now(utc)
        ticket.delete_change(cnum=4, when=t)
        self.assertEqual('a, b', ticket['keywords'])
        self.assertEqual('change3', ticket['foo'])
        self.assertIsNone(ticket.get_change(cnum=4))
        self.assertIsNotNone(ticket.get_change(cnum=3))
        self.assertEqual(t, ticket['changetime'])

    def test_delete_last_comment_when_custom_field_gone(self):
        """Regression test for https://trac.edgewall.org/ticket/10858"""
        ticket = Ticket(self.env, self.id)
        self.assertEqual('a', ticket['keywords'])
        self.assertEqual('change4', ticket['foo'])
        # we simulate the removal of the definition of the 'foo' custom field
        self.env.config.remove('ticket-custom', 'foo')
        del TicketSystem(self.env).fields
        del TicketSystem(self.env).custom_fields
        ticket = Ticket(self.env, self.id)
        #
        t = datetime_now(utc)
        ticket.delete_change(cnum=4, when=t)
        self.assertEqual('a, b', ticket['keywords'])
        # 'foo' is no longer defined for the ticket
        self.assertIsNone(ticket['foo'])
        # however, 'foo=change3' is still in the database
        self.assertEqual([('change3',)], self.env.db_query("""
            SELECT value FROM ticket_custom WHERE ticket=%s AND name='foo'
            """, (self.id,)))
        self.assertIsNone(ticket.get_change(cnum=4))
        self.assertIsNotNone(ticket.get_change(cnum=3))
        self.assertEqual(t, ticket['changetime'])

    def test_delete_last_comment_by_date(self):
        ticket = Ticket(self.env, self.id)
        self.assertEqual('a', ticket['keywords'])
        self.assertEqual('change4', ticket['foo'])
        t = datetime_now(utc)
        ticket.delete_change(cdate=self.t4, when=t)
        self.assertEqual('a, b', ticket['keywords'])
        self.assertEqual('change3', ticket['foo'])
        self.assertIsNone(ticket.get_change(cdate=self.t4))
        self.assertIsNotNone(ticket.get_change(cdate=self.t3))
        self.assertEqual(t, ticket['changetime'])

    def test_delete_mid_comment(self):
        ticket = Ticket(self.env, self.id)
        self.assertChange(ticket, 4, self.t4, 'joe',
            comment=dict(author='joe', old='4', new='Comment 4'),
            keywords=dict(author='joe', old='a, b', new='a'),
            foo=dict(author='joe', old='change3', new='change4'))
        t = datetime_now(utc)
        ticket.delete_change(cnum=3, when=t)
        self.assertIsNone(ticket.get_change(cnum=3))
        self.assertEqual('a', ticket['keywords'])
        self.assertChange(ticket, 4, self.t4, 'joe',
            comment=dict(author='joe', old='4', new='Comment 4'),
            keywords=dict(author='joe', old='a, b, c', new='a'),
            foo=dict(author='joe', old='change2', new='change4'))
        self.assertEqual(t, ticket['changetime'])

    def test_delete_mid_comment_by_date(self):
        ticket = Ticket(self.env, self.id)
        self.assertChange(ticket, 4, self.t4, 'joe',
            comment=dict(author='joe', old='4', new='Comment 4'),
            keywords=dict(author='joe', old='a, b', new='a'),
            foo=dict(author='joe', old='change3', new='change4'))
        t = datetime_now(utc)
        ticket.delete_change(cdate=self.t3, when=t)
        self.assertIsNone(ticket.get_change(cdate=self.t3))
        self.assertEqual('a', ticket['keywords'])
        self.assertChange(ticket, 4, self.t4, 'joe',
            comment=dict(author='joe', old='4', new='Comment 4'),
            keywords=dict(author='joe', old='a, b, c', new='a'),
            foo=dict(author='joe', old='change2', new='change4'))
        self.assertEqual(t, ticket['changetime'])

    def test_delete_mid_comment_inconsistent(self):
        # Make oldvalue on keywords for change 4 inconsistent. This should
        # result in no change in oldvalue when deleting change 3. The
        # oldvalue of foo should change normally.
        self.env.db_transaction("""
            UPDATE ticket_change SET oldvalue='1, 2'
            WHERE field='keywords' AND oldvalue='a, b'
            """)
        ticket = Ticket(self.env, self.id)
        self.assertChange(ticket, 4, self.t4, 'joe',
            comment=dict(author='joe', old='4', new='Comment 4'),
            keywords=dict(author='joe', old='1, 2', new='a'),
            foo=dict(author='joe', old='change3', new='change4'))
        ticket.delete_change(3)
        self.assertIsNone(ticket.get_change(3))
        self.assertEqual('a', ticket['keywords'])
        self.assertChange(ticket, 4, self.t4, 'joe',
            comment=dict(author='joe', old='4', new='Comment 4'),
            keywords=dict(author='joe', old='1, 2', new='a'),
            foo=dict(author='joe', old='change2', new='change4'))

    def test_delete_all_comments(self):
        ticket = Ticket(self.env, self.id)
        ticket.delete_change(4)
        ticket.delete_change(3)
        ticket.delete_change(2)
        t = datetime_now(utc)
        ticket.delete_change(1, when=t)
        self.assertEqual(t, ticket['changetime'])

    def test_ticket_change_deleted(self):
        ts = TicketSystem(self.env)
        listener = ts.change_listeners[0]
        ticket = Ticket(self.env, self.id)

        ticket.delete_change(cdate=self.t3, when=datetime_now(utc))
        self.assertEqual(1, len(ts.change_listeners))
        self.assertEqual('change_deleted', listener.action)
        self.assertEqual(ticket, listener.ticket)
        self.assertEqual(self.t3, listener.cdate)
        self.assertEqual(dict(keywords=('a, b, c', 'a, b'),
                              foo=('change2', 'change3')),
                         listener.changes)

        ticket.delete_change(cnum=2, when=datetime_now(utc))
        self.assertEqual('change_deleted', listener.action)
        self.assertEqual(ticket, listener.ticket)
        self.assertEqual(self.t2, listener.cdate)
        self.assertEqual(dict(owner=('john', 'jack'),
                              foo=('change 1', 'change2')),
                         listener.changes)


class EnumTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)

    def tearDown(self):
        self.env.reset_db()

    def test_repr(self):
        self.assertEqual("<Priority None None>", repr(Priority(self.env)))
        self.assertEqual("<Priority 'major' u'3'>",
                         repr(Priority(self.env, 'major')))

    def test_priority_fetch(self):
        priority = Priority(self.env, 'major')
        self.assertEqual('major', priority.name)
        self.assertEqual('3', priority.value)
        self.assertEqual('', priority.description)

    def test_priority_insert(self):
        priority = Priority(self.env)
        priority.name = 'foo'
        priority.description = 'the description'
        priority.insert()
        self.assertTrue(priority.exists)
        self.assertEqual(1, self.env.db_query("""
            SELECT COUNT(*) FROM enum
            WHERE type='priority' AND name='foo' AND value='6'
             AND description='the description'
            """)[0][0])

    def test_priority_insert_with_value(self):
        priority = Priority(self.env)
        priority.name = 'bar'
        priority.value = 100
        priority.description = 'the description'
        priority.insert()
        self.assertTrue(priority.exists)
        self.assertEqual(1, self.env.db_query("""
            SELECT COUNT(*) FROM enum
            WHERE type='priority' AND name='bar' AND value='100'
             AND description='the description'
            """)[0][0])

    def test_priority_insert_empty_description_stored_as_null(self):
        """Empty description is stored as NULL."""
        priority = Priority(self.env)
        priority.name = 'baz'
        priority.description = ''
        priority.insert()
        self.assertTrue(priority.exists)
        self.assertEqual(1, self.env.db_query("""
            SELECT COUNT(*) FROM enum
            WHERE type='priority' AND name='baz' AND value='6'
             AND description IS NULL
            """)[0][0])

    def test_priority_update(self):
        priority = Priority(self.env, 'major')
        priority.name = 'foo'
        priority.update()
        self.assertTrue(Priority(self.env, 'foo').exists)
        self.assertRaises(TracError, Priority, self.env, 'major')

    def test_priority_update_empty_description_stored_as_null(self):
        """Empty description is stored as NULL."""
        priority = Priority(self.env)
        priority.name = 'baz'
        priority.description = 'the description'
        priority.insert()
        priority.description = ''
        priority.update()
        self.assertTrue(priority.exists)
        self.assertEqual(1, self.env.db_query("""
            SELECT COUNT(*) FROM enum
            WHERE type='priority' AND name='baz' AND value='6'
             AND description IS NULL
            """)[0][0])

    def test_priority_delete(self):
        """Delete an enum from the database."""
        def get_count():
            return self.env.db_query("""
                SELECT COUNT(*) FROM enum
                WHERE type='priority' AND name='major'
                """)[0][0]

        priority = Priority(self.env, 'major')
        self.assertEqual('3', priority.value)
        self.assertEqual(1, get_count())
        self.assertTrue(priority.exists)
        priority.delete()
        self.assertEqual(0, get_count())
        self.assertFalse(priority.exists)

    def test_priority_delete_nonexistent_raises(self):
        """Deleting non-existent priority raises a TracError."""
        priority = Priority(self.env)
        priority.name = 'foo'

        with self.assertRaises(TracError):
            priority.delete()

    def test_select(self):
        priorities = list(Priority.select(self.env))
        names = ('blocker', 'critical', 'major', 'minor', 'trivial')
        for i, name in enumerate(names):
            self.assertEqual(name, priorities[i].name)
            self.assertEqual(unicode(i + 1), priorities[i].value)
            self.assertEqual('', priorities[i].description)


class MilestoneTestCase(unittest.TestCase):

    milestone_change_listeners = []

    @classmethod
    def setUpClass(cls):
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

        cls.milestone_change_listeners = [TestMilestoneChangeListener]

    @classmethod
    def tearDownClass(cls):
        for listener in cls.milestone_change_listeners:
            core.ComponentMeta.deregister(listener)

    def setUp(self):
        self.env = EnvironmentStub(default_data=True,
                                   enable=['trac.ticket.*'] +
                                          self.milestone_change_listeners)
        self.env.path = mkdtemp()
        self.created_at = datetime(2001, 1, 1, tzinfo=utc)
        self.updated_at = self.created_at + timedelta(seconds=1)

    def tearDown(self):
        self.env.reset_db_and_disk()

    def _create_milestone(self, **values):
        milestone = Milestone(self.env)
        for k, v in values.iteritems():
            setattr(milestone, k, v)
        return milestone

    def _insert_ticket(self, when=None, **kwargs):
        return insert_ticket(self.env, when=when or self.created_at, **kwargs)

    def _update_ticket(self, ticket, author=None, comment=None, when=None,
                       **kwargs):
        for name, value in kwargs.iteritems():
            ticket[name] = value
        ticket.save_changes(author, comment, when or self.updated_at)

    def test_new_milestone(self):
        milestone = Milestone(self.env)
        self.assertFalse(milestone.exists)
        self.assertIsNone(milestone.name)
        self.assertIsNone(milestone.due)
        self.assertIsNone(milestone.completed)
        self.assertEqual('', milestone.description)
        self.assertEqual("<Milestone None>", repr(milestone))

    def test_new_milestone_empty_name(self):
        """
        Verifies that specifying an empty milestone name results in the
        milestone being correctly detected as non-existent.
        """
        milestone = Milestone(self.env, '')
        self.assertFalse(milestone.exists)
        self.assertIsNone(milestone.name)
        self.assertIsNone(milestone.due)
        self.assertIsNone(milestone.completed)
        self.assertEqual('', milestone.description)
        self.assertEqual("<Milestone None>", repr(milestone))

    def test_existing_milestone(self):
        self.env.db_transaction("INSERT INTO milestone (name) VALUES ('Test')")

        milestone = Milestone(self.env, 'Test')
        self.assertTrue(milestone.exists)
        self.assertEqual('Test', milestone.name)
        self.assertIsNone(milestone.due)
        self.assertIsNone(milestone.completed)
        self.assertEqual('', milestone.description)
        self.assertEqual("<Milestone u'Test'>", repr(milestone))

    def test_create_and_update_milestone(self):
        milestone = Milestone(self.env)
        milestone.name = 'Test'
        milestone.insert()

        self.assertEqual([('Test', 0, 0, '')], self.env.db_query("""
            SELECT name, due, completed, description FROM milestone
            WHERE name='Test'
            """))

        # Use the same model object to update the milestone
        milestone.description = 'Some text'
        milestone.update()
        self.assertEqual([('Test', 0, 0, 'Some text')], self.env.db_query("""
            SELECT name, due, completed, description FROM milestone
            WHERE name='Test'
            """))

    def test_move_tickets(self):
        self.env.db_transaction.executemany(
            "INSERT INTO milestone (name) VALUES (%s)",
            [('Test',), ('Testing',)])
        tkt1 = self._insert_ticket(status='new', summary='Foo',
                                   milestone='Test')
        tkt2 = self._insert_ticket(status='new', summary='Bar',
                                   milestone='Test')
        self._update_ticket(tkt2, status='closed', resolution='fixed')
        milestone = Milestone(self.env, 'Test')
        milestone.move_tickets('Testing', 'anonymous', 'Move tickets')

        tkt1 = Ticket(self.env, tkt1.id)
        tkt2 = Ticket(self.env, tkt2.id)
        self.assertEqual('Testing', tkt1['milestone'])
        self.assertEqual('Testing', tkt2['milestone'])
        self.assertEqual(tkt1['changetime'], tkt2['changetime'])
        self.assertNotEqual(self.updated_at, tkt1['changetime'])

    def test_move_tickets_exclude_closed(self):
        self.env.db_transaction.executemany(
            "INSERT INTO milestone (name) VALUES (%s)",
            [('Test',), ('Testing',)])
        tkt1 = self._insert_ticket(status='new', summary='Foo',
                                   milestone='Test')
        tkt2 = self._insert_ticket(status='new', summary='Bar',
                                   milestone='Test')
        self._update_ticket(tkt2, status='closed', resolution='fixed')
        milestone = Milestone(self.env, 'Test')
        milestone.move_tickets('Testing', 'anonymous', 'Move tickets',
                               exclude_closed=True)

        tkt1 = Ticket(self.env, tkt1.id)
        tkt2 = Ticket(self.env, tkt2.id)
        self.assertEqual('Testing', tkt1['milestone'])
        self.assertEqual('Test', tkt2['milestone'])
        self.assertNotEqual(self.updated_at, tkt1['changetime'])
        self.assertEqual(self.updated_at, tkt2['changetime'])

    def test_move_tickets_target_doesnt_exist(self):
        self.env.db_transaction("INSERT INTO milestone (name) VALUES ('Test')")
        tkt1 = self._insert_ticket(status='new', summary='Foo',
                                   milestone='Test')
        tkt2 = self._insert_ticket(status='new', summary='Bar',
                                   milestone='Test')
        milestone = Milestone(self.env, 'Test')
        self.assertRaises(ResourceNotFound, milestone.move_tickets,
                          'Testing', 'anonymous')

        tkt1 = Ticket(self.env, tkt1.id)
        tkt2 = Ticket(self.env, tkt2.id)
        self.assertEqual('Test', tkt1['milestone'])
        self.assertEqual('Test', tkt2['milestone'])
        self.assertNotEqual(self.updated_at, tkt1['changetime'])
        self.assertNotEqual(self.updated_at, tkt2['changetime'])

    def test_create_milestone_without_name(self):
        milestone = Milestone(self.env)
        self.assertRaises(TracError, milestone.insert)

    def test_delete_milestone(self):
        self.env.db_transaction("INSERT INTO milestone (name) VALUES ('Test')")
        tkt1 = self._insert_ticket(status='new', summary='Foo',
                                   milestone='Test')
        tkt2 = self._insert_ticket(status='new', summary='Bar',
                                   milestone='Test')
        self._update_ticket(tkt2, status='closed', resolution='fixed')
        milestone = Milestone(self.env, 'Test')
        milestone.move_tickets(None, 'user')
        milestone.delete()
        self.assertFalse(milestone.exists)
        self.assertEqual([], self.env.db_query("""
            SELECT * FROM milestone WHERE name='Test'
            """))

        tkt1 = Ticket(self.env, tkt1.id)
        tkt2 = Ticket(self.env, tkt2.id)
        self.assertEqual('', tkt1['milestone'])
        self.assertEqual('', tkt2['milestone'])
        self.assertEqual(tkt1['changetime'], tkt2['changetime'])
        self.assertNotEqual(self.updated_at, tkt1['changetime'])

    def test_delete_milestone_with_attachment(self):
        milestone = Milestone(self.env)
        milestone.name = 'MilestoneWithAttachment'
        milestone.insert()

        attachment = Attachment(self.env, 'milestone', milestone.name)
        attachment.insert('foo.txt', io.BytesIO(), 0, 1)

        milestone.delete()
        self.assertFalse(milestone.exists)

        attachments = Attachment.select(self.env, 'milestone', milestone.name)
        self.assertRaises(StopIteration, next, attachments)

    def test_delete_milestone_retarget_tickets(self):
        self.env.db_transaction.executemany(
            "INSERT INTO milestone (name) VALUES (%s)",
            [('Test',), ('Other',)])
        tkt1 = self._insert_ticket(status='new', summary='Foo',
                                   milestone='Test')
        tkt2 = self._insert_ticket(status='new', summary='Bar',
                                   milestone='Test')
        self._update_ticket(tkt2, status='closed', resolution='fixed')
        milestone = Milestone(self.env, 'Test')
        milestone.move_tickets('Other', 'user')
        milestone.delete()
        self.assertFalse(milestone.exists)

        tkt1 = Ticket(self.env, tkt1.id)
        tkt2 = Ticket(self.env, tkt2.id)
        self.assertEqual('Other', tkt1['milestone'])
        self.assertEqual('Other', tkt2['milestone'])
        self.assertEqual(tkt1['changetime'], tkt2['changetime'])
        self.assertNotEqual(self.updated_at, tkt1['changetime'])

    def test_update_milestone(self):
        self.env.db_transaction("INSERT INTO milestone (name) VALUES ('Test')")

        milestone = Milestone(self.env, 'Test')
        t1 = datetime(2001, 1, 1, tzinfo=utc)
        t2 = datetime(2002, 2, 2, tzinfo=utc)
        milestone.due = t1
        milestone.completed = t2
        milestone.description = 'Foo bar'
        milestone.update()

        self.assertEqual(
            [('Test', to_utimestamp(t1), to_utimestamp(t2), 'Foo bar')],
            self.env.db_query("SELECT * FROM milestone WHERE name='Test'"))

    def test_update_milestone_without_name(self):
        self.env.db_transaction("INSERT INTO milestone (name) VALUES ('Test')")

        milestone = Milestone(self.env, 'Test')
        milestone.name = None
        self.assertRaises(TracError, milestone.update)

    def test_rename_milestone(self):
        milestone = Milestone(self.env)
        milestone.name = 'OldName'
        milestone.insert()

        attachment = Attachment(self.env, 'milestone', 'OldName')
        attachment.insert('foo.txt', io.BytesIO(), 0, 1)

        milestone = Milestone(self.env, 'OldName')
        milestone.name = 'NewName'
        milestone.update()

        self.assertRaises(ResourceNotFound, Milestone, self.env, 'OldName')
        self.assertEqual('NewName', Milestone(self.env, 'NewName').name)

        attachments = Attachment.select(self.env, 'milestone', 'OldName')
        self.assertRaises(StopIteration, next, attachments)
        attachments = Attachment.select(self.env, 'milestone', 'NewName')
        self.assertEqual('foo.txt', next(attachments).filename)
        self.assertRaises(StopIteration, next, attachments)

    def test_rename_milestone_retarget_tickets(self):
        self.env.db_transaction("INSERT INTO milestone (name) VALUES ('Test')")
        tkt1 = self._insert_ticket(status='new', summary='Foo',
                                   milestone='Test')
        tkt2 = self._insert_ticket(status='new', summary='Bar',
                                   milestone='Test')
        self._update_ticket(tkt2, status='closed', resolution='fixed')
        milestone = Milestone(self.env, 'Test')
        milestone.name = 'Testing'
        milestone.update()

        tkt1 = Ticket(self.env, tkt1.id)
        tkt2 = Ticket(self.env, tkt2.id)
        self.assertEqual('Testing', tkt1['milestone'])
        self.assertEqual('Testing', tkt2['milestone'])
        self.assertEqual(tkt1['changetime'], tkt2['changetime'])
        self.assertNotEqual(self.updated_at, tkt1['changetime'])

    def test_select_milestones(self):
        self.env.db_transaction.executemany(
            "INSERT INTO milestone (name) VALUES (%s)",
            [('1.0',), ('2.0',)])

        milestones = list(Milestone.select(self.env))
        self.assertEqual('1.0', milestones[0].name)
        self.assertTrue(milestones[0].exists)
        self.assertEqual('2.0', milestones[1].name)
        self.assertTrue(milestones[1].exists)

    def test_change_listener_created(self):
        ts = TicketSystem(self.env)
        listener = ts.milestone_change_listeners[0]
        milestone = self._create_milestone(name='Milestone 1')
        milestone.insert()

        self.assertEqual(1, len(ts.milestone_change_listeners))
        self.assertEqual('created', listener.action)
        self.assertEqual(milestone, listener.milestone)

    def test_change_listener_changed(self):
        ts = TicketSystem(self.env)
        listener = ts.milestone_change_listeners[0]
        milestone = self._create_milestone(
            name='Milestone 1',
            due=datetime(2001, 1, 1, tzinfo=utc),
            description='The milestone description')
        milestone.insert()

        milestone.name = 'Milestone 2'
        milestone.completed = datetime(2001, 2, 3, tzinfo=utc)
        milestone.description = 'The changed description'
        milestone.update()

        self.assertEqual(1, len(ts.milestone_change_listeners))
        self.assertEqual('changed', listener.action)
        self.assertEqual(milestone, listener.milestone)
        self.assertEqual({'name': 'Milestone 1', 'completed': None,
                          'description': 'The milestone description'},
                         listener.old_values)

    def test_change_listener_deleted(self):
        ts = TicketSystem(self.env)
        listener = ts.milestone_change_listeners[0]
        milestone = self._create_milestone(name='Milestone 1')
        self.assertEqual(1, len(ts.milestone_change_listeners))
        milestone.insert()
        self.assertTrue(milestone.exists)
        milestone.delete()
        self.assertEqual('Milestone 1', milestone.name)
        self.assertFalse(milestone.exists)
        self.assertEqual('deleted', listener.action)
        self.assertEqual(milestone, listener.milestone)


class ComponentTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        with self.env.db_transaction as db:
            db.executemany("""
                INSERT INTO component (name, owner, description)
                VALUES (%s, %s, %s)
                """, [('component1', 'the owner', 'the description'),
                      ('component2', None, None)])

    def tearDown(self):
        self.env.reset_db()

    def _get_component_ticket_field(self):
        for field in TicketSystem(self.env).fields:
            if field['name'] == 'component':
                return field
        return None

    def test_init(self):
        """Initialize existing component."""
        component1 = Component(self.env, 'component1')
        component2 = Component(self.env, 'component2')

        self.assertTrue(component1.exists)
        self.assertEqual('component1', component1.name)
        self.assertEqual(component1.name, component1._old_name)
        self.assertEqual('the owner', component1.owner)
        self.assertEqual('the description', component1.description)
        self.assertTrue(component2.exists)
        self.assertEqual('component2', component2.name)
        self.assertEqual(component2.name, component2._old_name)
        self.assertEqual('', component2.owner)
        self.assertEqual('', component2.description)

    def test_init_nonexistent_name_raises(self):
        """ResourceNotFound raised calling initializer with
        non-existent name.
        """
        with self.assertRaises(ResourceNotFound) as cm:
            Component(self.env, 'none')

        self.assertEqual("Component none does not exist.",
                         unicode(cm.exception))

    def test_repr(self):
        """Return string representation of object."""
        self.assertEqual("<Component None>", repr(Component(self.env)))
        self.assertEqual("<Component 'component1'>",
                         repr(Component(self.env, 'component1')))

    def test_delete(self):
        """Delete existing component."""
        component1 = Component(self.env, 'component1')

        component1.delete()

        self.assertFalse(component1.exists)
        self.assertIsNone(component1.name)
        self.assertEqual([], self.env.db_query("""
            SELECT * FROM component WHERE name='component1'
            """))

    def test_delete_resets_cached_ticket_fields(self):
        """Deleting component resets cached ticket fields."""
        component1 = Component(self.env, 'component1')

        component1.delete()
        component_field = self._get_component_ticket_field()

        self.assertIsNotNone(component_field)
        self.assertNotIn('component1', component_field['options'])

    def test_delete_updates_tickets(self):
        """Tickets are updated when component is deleted."""
        insert_ticket(self.env, component='component1')
        component1 = Component(self.env, 'component1')

        component1.delete()

        # Skip test: FIXME #11367
        # self.assertIsNone(Ticket(self.env, 1)['component'])

    def test_delete_nonexistent_raises(self):
        """TracError is raised when deleting a non-existent component.
        The component may not have been inserted, or may have already
        been deleted.
        """
        component0 = Component(self.env)
        component0.name = 'component0'
        component1 = Component(self.env, 'component1')
        component1.delete()

        with self.assertRaises(TracError) as cm0:
            component0.delete()
        with self.assertRaises(TracError) as cm1:
            component1.delete()

        exc_message = "Cannot delete non-existent component."
        self.assertEqual(exc_message, unicode(cm0.exception))
        self.assertFalse(component0.exists)
        self.assertEqual(exc_message, unicode(cm1.exception))
        self.assertFalse(component1.exists)

    def test_insert(self):
        """Insert a new component."""
        component = Component(self.env)
        component.name = 'component3'
        component.insert()
        component_field = self._get_component_ticket_field()

        self.assertEqual(component.name, component._old_name)
        self.assertEqual([('component3', None, None)], self.env.db_query("""
            SELECT name, owner, description FROM component
            WHERE name='component3'"""))
        self.assertIsNotNone(component_field)
        self.assertIn('component3', component_field['options'])

    def test_insert_whitespace_removed(self):
        """Whitespace is stripped from text fields when inserting component.
        """
        component = Component(self.env)
        component.name = ' component3 '
        component.owner = ' '
        component.description = ' '
        component.insert()

        self.assertEqual([('component3', None, ' ')], self.env.db_query("""
            SELECT name, owner, description FROM component
            WHERE name='component3'"""))

    def test_insert_invalid_name_raises(self):
        """TracError is raised when inserting component with empty name.
        """
        component1 = Component(self.env)
        component1.name = None
        component2 = Component(self.env)
        component2.name = ''
        component3 = Component(self.env)
        component3.name = ' '

        with self.assertRaises(TracError) as cm1:
            component1.insert()
        with self.assertRaises(TracError) as cm2:
            component2.insert()
        with self.assertRaises(TracError) as cm3:
            component3.insert()

        exc_message = "Invalid component name."
        self.assertEqual(exc_message, unicode(cm1.exception))
        self.assertEqual(exc_message, unicode(cm2.exception))
        self.assertEqual(exc_message, unicode(cm3.exception))

    def test_insert_existing_raises(self):
        """ResourceExistsError is raised when `insert`ing an existing
        component.
        """
        component = Component(self.env)
        component.name = 'component1'

        with self.assertRaises(ResourceExistsError) as cm:
            component.insert()

        self.assertEqual('Component "component1" already exists.',
                         unicode(cm.exception))

    def test_insert_existing_renamed_raises(self):
        """ResourceExistsError is raised when `insert`ing existing renamed
        component.
        """
        component = Component(self.env, 'component1')
        component.name = 'component3'

        with self.assertRaises(ResourceExistsError) as cm:
            component.insert()

        self.assertEqual('Component "component3" already exists.',
                         unicode(cm.exception))

    def test_update(self):
        """Update existing component."""
        component = Component(self.env, 'component1')
        component.owner = 'the new owner'
        component.description = 'the new description'
        component.update()

        self.assertEqual([('component1', 'the new owner',
                           'the new description')], self.env.db_query("""
            SELECT name, owner, description FROM component
            WHERE name='component1'"""))

    def test_update_nonexistent_raises(self):
        """TracError is raised when updating a non-existent component.
        """
        component = Component(self.env)
        component.name = 'component3'

        self.assertFalse(component.exists)
        self.assertRaises(TracError, component.update)

    def test_update_invalid_name_raises(self):
        """TracError is raised when `update`ing component with empty name.
        """
        component1 = Component(self.env)
        component1.name = None
        component2 = Component(self.env)
        component2.name = ''
        component3 = Component(self.env)
        component3.name = ' '

        self.assertRaises(TracError, component1.update)
        self.assertRaises(TracError, component2.update)
        self.assertRaises(TracError, component3.update)

    def test_update_empty_strings_to_null(self):
        """Empty strings are converted to NULL."""
        component = Component(self.env, 'component1')
        component.name = 'component1'
        component.owner = ''
        component.description = ''
        component.update()

        self.assertEqual([('component1', None, None)], self.env.db_query("""
            SELECT name, owner, description FROM component
            WHERE name='component1'"""))

    def test_update_whitespace_removed(self):
        """Whitespace is stripped from text fields when updating component.
        """
        component = Component(self.env, 'component1')
        component.name = ' component1 '
        component.owner = ' owner '
        component.description = ' text '
        component.update()

        self.assertEqual([('component1', 'owner', ' text ')],
                         self.env.db_query("""
                SELECT name, owner, description FROM component
                WHERE name='component1'"""))

    def test_rename(self):
        """Rename a component."""
        insert_ticket(self.env, component='component1')
        component = Component(self.env, 'component1')
        component.name = 'component3'
        component.update()
        component_field = self._get_component_ticket_field()

        self.assertEqual([('component3', 'the owner', 'the description')],
                         self.env.db_query("""
            SELECT name, owner, description FROM component
            WHERE name='component3'"""))
        self.assertEqual(component.name, component._old_name)
        self.assertTrue(Component(self.env, 'component3').exists)
        self.assertRaises(ResourceNotFound, Component, self.env, 'component1')
        self.assertIsNotNone(component_field)
        self.assertIn('component3', component_field['options'])
        self.assertEqual('component3', Ticket(self.env, 1)['component'])

    def test_rename_new_name_exists_raises(self):
        """TracError is raised when renamed component exists."""
        component = Component(self.env, 'component1')
        component.name = 'component2'

        self.assertRaises(ResourceExistsError, component.update)

    def test_select(self):
        components = []
        for c in Component.select(self.env):
            components.append(c)

        self.assertEqual(2, len(components))
        self.assertTrue(components[0].exists)
        self.assertEqual('component1', components[0].name)
        self.assertEqual('the owner', components[0].owner)
        self.assertEqual('the description', components[0].description)
        self.assertTrue(components[1].exists)
        self.assertEqual('component2', components[1].name)
        self.assertEqual('', components[1].owner)
        self.assertEqual('', components[1].description)


class ReportTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)

    def tearDown(self):
        self.env.reset_db()

    def test_repr(self):
        report = Report(self.env)
        report.query = "SELECT 1"
        report.insert()
        self.assertEqual("<Report 1>", repr(Report(self.env, 1)))
        self.assertEqual("<Report None>", repr(Report(self.env)))

    def test_create(self):
        report = Report(self.env, 4)
        self.assertTrue(report.exists)
        self.assertEqual(4, report.id)
        self.assertEqual("Accepted, Active Tickets by Owner", report.title)
        self.assertEqual("List accepted tickets, group by ticket owner, "
                         "sorted by priority.\n", report.description)
        self.assertIn("SELECT p.value AS __color__,", report.query)

    def test_create_exists_false(self):
        self.assertRaises(ResourceNotFound, Report, self.env, 9)

    def test_insert(self):
        report = Report(self.env)
        report.title = "The report"
        report.description = "The description"
        report.query = "SELECT 1"
        report.insert()
        self.assertEqual(9, report.id)

    def test_insert_query_is_empty(self):
        """TracError is raised when query attribute is empty."""
        report = Report(self.env)
        report.title = "The report"
        report.description = "The description"
        report.query = ""

        with self.assertRaises(TracError) as cm:
            report.insert()
        self.assertIsNone(report.id)
        self.assertEqual("Query cannot be empty.",
                         unicode(cm.exception))

    def test_insert_existing_report(self):
        report = Report(self.env, 1)
        self.assertRaises(AssertionError, report.insert)

    def test_delete(self):
        report = Report(self.env, 1)
        report.delete()
        self.assertFalse(report.exists)
        self.assertRaises(ResourceNotFound, Report, self.env, 1)

    def test_delete_not_exists(self):
        report = Report(self.env)
        self.assertRaises(AssertionError, report.delete)

    def test_update(self):
        report = Report(self.env, 1)
        title, description, query = \
            report.title, report.description, report.query
        report.title = "The report"
        report.description = "The description"
        report.query = "SELECT 1"
        report.update()

        report = Report(self.env, 1)
        self.assertNotEqual(title, report.title)
        self.assertNotEqual(description, report.description)
        self.assertNotEqual(query, report.query)
        self.assertEqual("The report", report.title)
        self.assertEqual("The description", report.description)
        self.assertEqual("SELECT 1", report.query)

    def test_update_query_is_empty(self):
        """TracError is raised when query attribute is empty."""
        report = Report(self.env, 1)
        report.query = ""

        with self.assertRaises(TracError) as cm:
            report.update()
        self.assertEqual("Query cannot be empty.",
                         unicode(cm.exception))

    def test_select(self):
        reports = list(Report.select(self.env))
        self.assertEqual(1, reports[0].id)
        self.assertEqual('Active Tickets', reports[0].title)
        self.assertEqual(" * List all active tickets by priority.\n"
                         " * Color each row based on priority.\n",
                         reports[0].description)
        self.assertIn("SELECT p.value AS __color__", reports[0].query)
        self.assertEqual(8, len(reports))
        self.assertEqual(1, reports[0].id)
        self.assertEqual(8, reports[-1].id)

    def test_select_sort_desc(self):
        reports = list(Report.select(self.env, asc=False))
        self.assertEqual(8, len(reports))
        self.assertEqual(8, reports[0].id)
        self.assertEqual(1, reports[-1].id)

    def test_select_order_by_title(self):
        reports = list(Report.select(self.env, sort='title'))
        self.assertEqual(8, len(reports))
        self.assertEqual(4, reports[0].id)
        self.assertEqual(7, reports[-1].id)


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
        https://trac.edgewall.org/ticket/4247
        """
        for v in Version.select(self.env):
            self.assertEqual(v.exists, True)

    def test_repr(self):
        self.assertEqual('<Version None>', repr(Version(self.env)))
        self.assertEqual("<Version '1.0'>", repr(Version(self.env, '1.0')))

    def test_create_and_update(self):
        version = Version(self.env)
        version.name = 'Test'
        version.insert()

        self.assertEqual([('Test', 0, None)], self.env.db_query(
            "SELECT name, time, description FROM version WHERE name='Test'"))

        # Use the same model object to update the version
        version.description = 'Some text'
        version.update()
        self.assertEqual([('Test', 0, 'Some text')], self.env.db_query(
            "SELECT name, time, description FROM version WHERE name='Test'"))


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TicketTestCase))
    suite.addTest(unittest.makeSuite(TicketCommentEditTestCase))
    suite.addTest(unittest.makeSuite(TicketCommentDeleteTestCase))
    suite.addTest(unittest.makeSuite(EnumTestCase))
    suite.addTest(unittest.makeSuite(MilestoneTestCase))
    suite.addTest(unittest.makeSuite(ComponentTestCase))
    suite.addTest(unittest.makeSuite(ReportTestCase))
    suite.addTest(unittest.makeSuite(VersionTestCase))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
