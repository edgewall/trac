# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2018 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

from datetime import datetime
from StringIO import StringIO
import tempfile
import unittest

import trac.tests.compat
from trac.attachment import Attachment
from trac.core import *
from trac.resource import Resource
from trac.test import EnvironmentStub
from trac.util.datefmt import utc, to_utimestamp
from trac.wiki import WikiPage, IWikiChangeListener


class TestWikiChangeListener(Component):

    implements(IWikiChangeListener)

    def __init__(self):
        self.added = []
        self.changed = []
        self.deleted = []
        self.deleted_version = []
        self.renamed = []
        self.comment_modified = []

    def wiki_page_added(self, page):
        self.added.append(page)

    def wiki_page_changed(self, page, version, t, comment, author):
        self.changed.append((page, version, t, comment, author))

    def wiki_page_deleted(self, page):
        self.deleted.append(page)

    def wiki_page_version_deleted(self, page):
        self.deleted_version.append(page)

    def wiki_page_renamed(self, page, old_name):
        self.renamed.append((page, old_name))

    def wiki_page_comment_modified(self, page, old_comment):
        self.comment_modified.append((page, old_comment))


class TestLegacyWikiChangeListener(TestWikiChangeListener):

    def wiki_page_changed(self, page, version, t, comment, author, ipnr):
        self.changed.append((page, version, t, comment, author, ipnr))


class WikiPageTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.env.path = tempfile.mkdtemp(prefix='trac-tempenv-')

    def tearDown(self):
        self.env.reset_db_and_disk()

    def test_new_page(self):
        page = WikiPage(self.env)
        self.assertFalse(page.exists)
        self.assertIsNone(page.name)
        self.assertEqual(0, page.version)
        self.assertEqual('', page.text)
        self.assertEqual(0, page.readonly)
        self.assertEqual('', page.author)
        self.assertEqual('', page.comment)
        self.assertIsNone(page.time)
        self.assertEqual('<WikiPage None>', repr(page))

    def test_existing_page(self):
        t = datetime(2001, 1, 1, 1, 1, 1, 0, utc)
        self.env.db_transaction(
            "INSERT INTO wiki VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
            ('TestPage', 1, to_utimestamp(t), 'joe', '::1', 'Bla bla',
             'Testing', 0))

        page = WikiPage(self.env, 'TestPage')
        self.assertTrue(page.exists)
        self.assertEqual('TestPage', page.name)
        self.assertEqual(1, page.version)
        self.assertIsNone(page.resource.version)
        self.assertEqual('Bla bla', page.text)
        self.assertEqual(0, page.readonly)
        self.assertEqual('joe', page.author)
        self.assertEqual('Testing', page.comment)
        self.assertEqual(t, page.time)
        self.assertEqual("<WikiPage u'TestPage@1'>", repr(page))

        history = list(page.get_history())
        self.assertEqual(1, len(history))
        self.assertEqual((1, t, 'joe', 'Testing', '::1'), history[0])

        page = WikiPage(self.env, 'TestPage', 1)
        self.assertEqual(1, page.resource.version)
        self.assertEqual(1, page.version)

        resource = Resource('wiki', 'TestPage')
        page = WikiPage(self.env, resource, 1)
        self.assertEqual(1, page.version)

    def test_create_page(self):
        page = WikiPage(self.env)
        page.name = 'TestPage'
        page.text = 'Bla bla'
        t = datetime(2001, 1, 1, 1, 1, 1, 0, utc)
        page.save('joe', 'Testing', '::1', t)

        self.assertTrue(page.exists)
        self.assertEqual(1, page.version)
        self.assertIsNone(page.resource.version)
        self.assertEqual(0, page.readonly)
        self.assertEqual('joe', page.author)
        self.assertEqual('Testing', page.comment)
        self.assertEqual(t, page.time)

        self.assertEqual(
            [(1, to_utimestamp(t), 'joe', '::1', 'Bla bla', 'Testing', 0)],
            self.env.db_query("""
                SELECT version, time, author, ipnr, text, comment, readonly
                FROM wiki WHERE name=%s
                """, ('TestPage',)))

        listener = TestWikiChangeListener(self.env)
        self.assertEqual(page, listener.added[0])

    def test_update_page(self):
        t = datetime(2001, 1, 1, 1, 1, 1, 0, utc)
        t2 = datetime(2002, 1, 1, 1, 1, 1, 0, utc)
        self.env.db_transaction(
            "INSERT INTO wiki VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
            ('TestPage', 1, to_utimestamp(t), 'joe', '::1', 'Bla bla',
             'Testing', 0))

        page = WikiPage(self.env, 'TestPage')
        page.text = 'Bla'
        page.save('kate', 'Changing', '192.168.0.101', t2)

        self.assertEqual(2, page.version)
        self.assertIsNone(page.resource.version)
        self.assertEqual(0, page.readonly)
        self.assertEqual('kate', page.author)
        self.assertEqual('Changing', page.comment)
        self.assertEqual(t2, page.time)

        with self.env.db_query as db:
            rows = db("""
               SELECT version, time, author, ipnr, text, comment, readonly
               FROM wiki WHERE name=%s ORDER BY version
               """, ('TestPage',))
            self.assertEqual(2, len(rows))
            self.assertEqual((1, to_utimestamp(t), 'joe', '::1', 'Bla bla',
                              'Testing', 0), rows[0])
            self.assertEqual((2, to_utimestamp(t2), 'kate', '192.168.0.101',
                              'Bla', 'Changing', 0), rows[1])

        listener = TestLegacyWikiChangeListener(self.env)
        self.assertEqual((page, 2, t2, 'Changing', 'kate', '192.168.0.101'),
                         listener.changed[0])
        listener = TestWikiChangeListener(self.env)
        self.assertEqual((page, 2, t2, 'Changing', 'kate'),
                         listener.changed[0])

        page = WikiPage(self.env, 'TestPage')
        history = list(page.get_history())
        self.assertEqual(2, len(history))
        self.assertEqual((2, t2, 'kate', 'Changing', '192.168.0.101'),
                         history[0])
        self.assertEqual((1, t, 'joe', 'Testing', '::1'), history[1])

    def test_delete_page(self):
        self.env.db_transaction(
            "INSERT INTO wiki VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
            ('TestPage', 1, 42, 'joe', '::1', 'Bla bla', 'Testing', 0))

        page = WikiPage(self.env, 'TestPage')
        page.delete()

        self.assertFalse(page.exists)

        self.assertEqual([], self.env.db_query("""
            SELECT version, time, author, ipnr, text, comment, readonly
            FROM wiki WHERE name=%s
            """, ('TestPage',)))

        listener = TestWikiChangeListener(self.env)
        self.assertEqual(page, listener.deleted[0])

    def test_delete_page_version(self):
        self.env.db_transaction.executemany(
            "INSERT INTO wiki VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
            [('TestPage', 1, 42, 'joe', '::1', 'Bla bla', 'Testing', 0),
             ('TestPage', 2, 43, 'kate', '192.168.0.11', 'Bla', 'Changing', 0)])

        page = WikiPage(self.env, 'TestPage')
        page.delete(version=2)

        self.assertTrue(page.exists)
        self.assertEqual(
            [(1, 42, 'joe', '::1', 'Bla bla', 'Testing', 0)],
            self.env.db_query("""
                SELECT version, time, author, ipnr, text, comment, readonly
                FROM wiki WHERE name=%s
                """, ('TestPage',)))

        listener = TestWikiChangeListener(self.env)
        self.assertEqual(page, listener.deleted_version[0])

    def test_delete_page_last_version(self):
        self.env.db_transaction(
            "INSERT INTO wiki VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
            ('TestPage', 1, 42, 'joe', '::1', 'Bla bla', 'Testing', 0))

        page = WikiPage(self.env, 'TestPage')
        page.delete(version=1)

        self.assertFalse(page.exists)

        self.assertEqual([], self.env.db_query("""
            SELECT version, time, author, ipnr, text, comment, readonly
            FROM wiki WHERE name=%s
            """, ('TestPage',)))

        listener = TestWikiChangeListener(self.env)
        self.assertEqual(page, listener.deleted[0])

    def test_rename_page(self):
        data = (1, 42, 'joe', '::1', 'Bla bla', 'Testing', 0)
        self.env.db_transaction(
            "INSERT INTO wiki VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
            ('TestPage',) + data)
        attachment = Attachment(self.env, 'wiki', 'TestPage')
        attachment.insert('foo.txt', StringIO(), 0, 1)

        page = WikiPage(self.env, 'TestPage')
        page.rename('PageRenamed')
        self.assertEqual('PageRenamed', page.name)
        self.assertEqual('PageRenamed', page.resource.id)

        self.assertEqual([data], self.env.db_query("""
            SELECT version, time, author, ipnr, text, comment, readonly
            FROM wiki WHERE name=%s
            """, ('PageRenamed',)))

        attachments = Attachment.select(self.env, 'wiki', 'PageRenamed')
        self.assertEqual('foo.txt', attachments.next().filename)
        self.assertRaises(StopIteration, attachments.next)
        Attachment.delete_all(self.env, 'wiki', 'PageRenamed')

        old_page = WikiPage(self.env, 'TestPage')
        self.assertFalse(old_page.exists)

        self.assertEqual([], self.env.db_query("""
            SELECT version, time, author, ipnr, text, comment, readonly
            FROM wiki WHERE name=%s
            """, ('TestPage',)))

        listener = TestWikiChangeListener(self.env)
        self.assertEqual((page, 'TestPage'), listener.renamed[0])

    def test_edit_comment_of_page_version(self):
        self.env.db_transaction.executemany(
            "INSERT INTO wiki VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
            [('TestPage', 1, 42, 'joe', '::1', 'Bla bla', 'old 1', 0),
             ('TestPage', 2, 43, 'kate', '::11', 'Bla', 'old 2', 0)])

        page = WikiPage(self.env, 'TestPage')
        page.edit_comment('edited comment two')

        old_page = WikiPage(self.env, 'TestPage', 1)
        old_page.edit_comment('new comment one')

        self.assertEqual('edited comment two', page.comment)
        self.assertEqual('new comment one', old_page.comment)
        self.assertEqual(
            [(1, 42, 'joe', '::1', 'Bla bla', 'new comment one', 0),
             (2, 43, 'kate', '::11', 'Bla', 'edited comment two', 0)],
            self.env.db_query("""
                SELECT version, time, author, ipnr, text, comment, readonly
                FROM wiki WHERE name=%s
                ORDER BY version
                """, ('TestPage',)))

        listener = TestWikiChangeListener(self.env)
        self.assertEqual((page, 'old 2'), listener.comment_modified[0])
        self.assertEqual((old_page, 'old 1'), listener.comment_modified[1])

    def test_invalid_page_name(self):
        invalid_names = ('../Page', 'Page/..', 'Page/////SubPage',
                         'Page/./SubPage', '/PagePrefix', 'PageSuffix/')

        for name in invalid_names:
            page = WikiPage(self.env)
            page.name = name
            page.text = 'Bla bla'
            t = datetime(2001, 1, 1, 1, 1, 1, 0, utc)
            self.assertRaises(TracError, page.save, 'joe', 'Testing', '::1', t)

        page = WikiPage(self.env)
        page.name = 'TestPage'
        page.text = 'Bla bla'
        t = datetime(2001, 1, 1, 1, 1, 1, 0, utc)
        page.save('joe', 'Testing', '::1', t)
        for name in invalid_names:
            page = WikiPage(self.env, 'TestPage')
            self.assertRaises(TracError, page.rename, name)

    def test_invalid_version(self):
        data = [(1, 42, 'joe', '::1', 'First revision', 'Rev1', 0),
                (2, 42, 'joe', '::1', 'Second revision', 'Rev2', 0)]
        with self.env.db_transaction as db:
            for d in data:
                db("INSERT INTO wiki VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                   ('TestPage',) + d)

        page = WikiPage(self.env, 'TestPage', '1abc')
        self.assertEqual(2, page.version)

        resource = Resource('wiki', 'TestPage')
        page = WikiPage(self.env, resource, '1abc')
        self.assertEqual(2, page.version)

        resource = Resource('wiki', 'TestPage', '1abc')
        page = WikiPage(self.env, resource)
        self.assertEqual(2, page.version)

        resource = Resource('wiki', 'TestPage', 1)
        page = WikiPage(self.env, resource)
        self.assertEqual(1, page.version)

        resource = Resource('wiki', 'TestPage', 2)
        page = WikiPage(self.env, resource, 1)
        self.assertEqual(1, page.version)


def test_suite():
    return unittest.makeSuite(WikiPageTestCase)

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
