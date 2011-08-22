# -*- coding: utf-8 -*-

from datetime import datetime
import os.path
import shutil
from StringIO import StringIO
import tempfile
import unittest

from trac.attachment import Attachment
from trac.core import *
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

    def wiki_page_added(self, page):
        self.added.append(page)

    def wiki_page_changed(self, page, version, t, comment, author, ipnr):
        self.changed.append((page, version, t, comment, author, ipnr))

    def wiki_page_deleted(self, page):
        self.deleted.append(page)

    def wiki_page_version_deleted(self, page):
        self.deleted_version.append(page)

    def wiki_page_renamed(self, page, old_name):
        self.renamed.append((page, old_name))


class WikiPageTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.env.path = os.path.join(tempfile.gettempdir(), 'trac-tempenv')
        os.mkdir(self.env.path)
        self.db = self.env.get_db_cnx()

    def tearDown(self):
        shutil.rmtree(self.env.path)
        self.env.reset_db()

    def test_new_page(self):
        page = WikiPage(self.env)
        self.assertEqual(False, page.exists)
        self.assertEqual(None, page.name)
        self.assertEqual(0, page.version)
        self.assertEqual('', page.text)
        self.assertEqual(0, page.readonly)
        self.assertEqual('', page.author)
        self.assertEqual('', page.comment)
        self.assertEqual(None, page.time)

    def test_existing_page(self):
        t = datetime(2001, 1, 1, 1, 1, 1, 0, utc)
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO wiki VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                       ('TestPage', 1, to_utimestamp(t), 'joe', '::1',
                        'Bla bla', 'Testing', 0))

        page = WikiPage(self.env, 'TestPage')
        self.assertEqual(True, page.exists)
        self.assertEqual('TestPage', page.name)
        self.assertEqual(1, page.version)
        self.assertEqual(None, page.resource.version)   # FIXME: Intentional?
        self.assertEqual('Bla bla', page.text)
        self.assertEqual(0, page.readonly)
        self.assertEqual('joe', page.author)
        self.assertEqual('Testing', page.comment)
        self.assertEqual(t, page.time)
        
        history = list(page.get_history())
        self.assertEqual(1, len(history))
        self.assertEqual((1, t, 'joe', 'Testing', '::1'), history[0])
        
        page = WikiPage(self.env, 'TestPage', 1)
        self.assertEqual(1, page.resource.version)

    def test_create_page(self):
        page = WikiPage(self.env)
        page.name = 'TestPage'
        page.text = 'Bla bla'
        t = datetime(2001, 1, 1, 1, 1, 1, 0, utc)
        page.save('joe', 'Testing', '::1', t)
        
        self.assertEqual(True, page.exists)
        self.assertEqual(1, page.version)
        self.assertEqual(1, page.resource.version)
        self.assertEqual(0, page.readonly)
        self.assertEqual('joe', page.author)
        self.assertEqual('Testing', page.comment)
        self.assertEqual(t, page.time)

        cursor = self.db.cursor()
        cursor.execute("SELECT version,time,author,ipnr,text,comment,"
                       "readonly FROM wiki WHERE name=%s", ('TestPage',))
        self.assertEqual((1, to_utimestamp(t), 'joe', '::1', 'Bla bla',
                          'Testing', 0),
                         cursor.fetchone())

        listener = TestWikiChangeListener(self.env)
        self.assertEqual(page, listener.added[0])

    def test_update_page(self):
        cursor = self.db.cursor()
        t = datetime(2001, 1, 1, 1, 1, 1, 0, utc)
        t2 = datetime(2002, 1, 1, 1, 1, 1, 0, utc)
        cursor.execute("INSERT INTO wiki VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                       ('TestPage', 1, to_utimestamp(t), 'joe', '::1',
                        'Bla bla', 'Testing', 0))

        page = WikiPage(self.env, 'TestPage')
        page.text = 'Bla'
        page.save('kate', 'Changing', '192.168.0.101', t2)

        self.assertEqual(2, page.version)
        self.assertEqual(2, page.resource.version)
        self.assertEqual(0, page.readonly)
        self.assertEqual('kate', page.author)
        self.assertEqual('Changing', page.comment)
        self.assertEqual(t2, page.time)

        cursor.execute("SELECT version,time,author,ipnr,text,comment,"
                       "readonly FROM wiki WHERE name=%s", ('TestPage',))
        self.assertEqual((1, to_utimestamp(t), 'joe', '::1', 'Bla bla',
                          'Testing', 0),
                         cursor.fetchone())
        self.assertEqual((2, to_utimestamp(t2), 'kate', '192.168.0.101', 'Bla',
                          'Changing', 0), cursor.fetchone())

        listener = TestWikiChangeListener(self.env)
        self.assertEqual((page, 2, t2, 'Changing', 'kate', '192.168.0.101'),
                         listener.changed[0])

        page = WikiPage(self.env, 'TestPage')
        history = list(page.get_history())
        self.assertEqual(2, len(history))
        self.assertEqual((2, t2, 'kate', 'Changing', '192.168.0.101'),
                         history[0])
        self.assertEqual((1, t, 'joe', 'Testing', '::1'), history[1])

    def test_delete_page(self):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO wiki VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                       ('TestPage', 1, 42, 'joe', '::1', 'Bla bla', 'Testing',
                        0))

        page = WikiPage(self.env, 'TestPage')
        page.delete()

        self.assertEqual(False, page.exists)

        cursor.execute("SELECT version,time,author,ipnr,text,comment,"
                       "readonly FROM wiki WHERE name=%s", ('TestPage',))
        self.assertEqual(None, cursor.fetchone())

        listener = TestWikiChangeListener(self.env)
        self.assertEqual(page, listener.deleted[0])

    def test_delete_page_version(self):
        cursor = self.db.cursor()
        cursor.executemany("INSERT INTO wiki VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                           [('TestPage', 1, 42, 'joe', '::1', 'Bla bla',
                            'Testing', 0),
                            ('TestPage', 2, 43, 'kate', '192.168.0.101', 'Bla',
                            'Changing', 0)])

        page = WikiPage(self.env, 'TestPage')
        page.delete(version=2)

        self.assertEqual(True, page.exists)

        cursor.execute("SELECT version,time,author,ipnr,text,comment,"
                       "readonly FROM wiki WHERE name=%s", ('TestPage',))
        self.assertEqual((1, 42, 'joe', '::1', 'Bla bla', 'Testing', 0),
                         cursor.fetchone())
        self.assertEqual(None, cursor.fetchone())

        listener = TestWikiChangeListener(self.env)
        self.assertEqual(page, listener.deleted_version[0])

    def test_delete_page_last_version(self):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO wiki VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                       ('TestPage', 1, 42, 'joe', '::1', 'Bla bla', 'Testing',
                        0))

        page = WikiPage(self.env, 'TestPage')
        page.delete(version=1)

        self.assertEqual(False, page.exists)

        cursor.execute("SELECT version,time,author,ipnr,text,comment,"
                       "readonly FROM wiki WHERE name=%s", ('TestPage',))
        self.assertEqual(None, cursor.fetchone())

        listener = TestWikiChangeListener(self.env)
        self.assertEqual(page, listener.deleted[0])

    def test_rename_page(self):
        cursor = self.db.cursor()
        data = (1, 42, 'joe', '::1', 'Bla bla', 'Testing', 0)
        cursor.execute("INSERT INTO wiki VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                       ('TestPage',) + data)
        attachment = Attachment(self.env, 'wiki', 'TestPage')
        attachment.insert('foo.txt', StringIO(), 0, 1)
        
        page = WikiPage(self.env, 'TestPage')
        page.rename('PageRenamed')
        self.assertEqual('PageRenamed', page.name)
        
        cursor.execute("SELECT version,time,author,ipnr,text,comment,"
                       "readonly FROM wiki WHERE name=%s", ('PageRenamed',))
        self.assertEqual(data, cursor.fetchone())
        self.assertEqual(None, cursor.fetchone())
        
        attachments = Attachment.select(self.env, 'wiki', 'PageRenamed')
        self.assertEqual('foo.txt', attachments.next().filename)
        self.assertRaises(StopIteration, attachments.next)
        Attachment.delete_all(self.env, 'wiki', 'PageRenamed', self.db)

        old_page = WikiPage(self.env, 'TestPage')
        self.assertEqual(False, old_page.exists)
        
        cursor.execute("SELECT version,time,author,ipnr,text,comment,"
                       "readonly FROM wiki WHERE name=%s", ('TestPage',))
        self.assertEqual(None, cursor.fetchone())
        
        listener = TestWikiChangeListener(self.env)
        self.assertEqual((page, 'TestPage'), listener.renamed[0])

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


def suite():
    return unittest.makeSuite(WikiPageTestCase, 'test')

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
