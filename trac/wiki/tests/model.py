from datetime import datetime
import unittest

from trac.core import *
from trac.test import EnvironmentStub
from trac.util.datefmt import utc, to_timestamp
from trac.wiki import WikiPage, IWikiChangeListener


class TestWikiChangeListener(Component):
    implements(IWikiChangeListener)
    def __init__(self):
        self.added = []
        self.changed = []
        self.deleted = []
        self.deleted_version = []

    def wiki_page_added(self, page):
        self.added.append(page)

    def wiki_page_changed(self, page, version, t, comment, author, ipnr):
        self.changed.append((page, version, t, comment, author, ipnr))

    def wiki_page_deleted(self, page):
        self.deleted.append(page)

    def wiki_page_version_deleted(self, page):
        self.deleted_version.append(page)


class WikiPageTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.db = self.env.get_db_cnx()

    def test_new_page(self):
        page = WikiPage(self.env)
        self.assertEqual(False, page.exists)
        self.assertEqual(None, page.name)
        self.assertEqual(0, page.version)
        self.assertEqual('', page.text)
        self.assertEqual(0, page.readonly)

    def test_existing_page(self):
        t = datetime(2001, 1, 1, 1, 1, 1, 0, utc)
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO wiki VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                       ('TestPage', 0, to_timestamp(t), 'joe', '::1', 'Bla bla',
                        'Testing', 0))

        page = WikiPage(self.env, 'TestPage')
        self.assertEqual('TestPage', page.name)
        self.assertEqual(0, page.version)
        self.assertEqual('Bla bla', page.text)
        self.assertEqual(False, page.readonly)
        history = list(page.get_history())
        self.assertEqual(1, len(history))
        self.assertEqual((0, t, 'joe', 'Testing', '::1'), history[0])

    def test_create_page(self):
        page = WikiPage(self.env)
        page.name = 'TestPage'
        page.text = 'Bla bla'
        t = datetime(2001, 1, 1, 1, 1, 1, 0, utc)
        page.save('joe', 'Testing', '::1', t)

        cursor = self.db.cursor()
        cursor.execute("SELECT version,time,author,ipnr,text,comment,"
                       "readonly FROM wiki WHERE name=%s", ('TestPage',))
        self.assertEqual((1, to_timestamp(t), 'joe', '::1', 'Bla bla', 'Testing', 0),
                         cursor.fetchone())

        listener = TestWikiChangeListener(self.env)
        self.assertEqual(page, listener.added[0])

    def test_update_page(self):
        cursor = self.db.cursor()
        t = datetime(2001, 1, 1, 1, 1, 1, 0, utc)
        t2 = datetime(2002, 1, 1, 1, 1, 1, 0, utc)
        cursor.execute("INSERT INTO wiki VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                       ('TestPage', 1, to_timestamp(t), 'joe', '::1', 'Bla bla',
                        'Testing', 0))

        page = WikiPage(self.env, 'TestPage')
        page.text = 'Bla'
        page.save('kate', 'Changing', '192.168.0.101', t2)
        self.assertEqual(2, page.resource.version)

        cursor.execute("SELECT version,time,author,ipnr,text,comment,"
                       "readonly FROM wiki WHERE name=%s", ('TestPage',))
        self.assertEqual((1, to_timestamp(t), 'joe', '::1', 'Bla bla', 'Testing', 0),
                         cursor.fetchone())
        self.assertEqual((2, to_timestamp(t2), 'kate', '192.168.0.101', 'Bla',
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


def suite():
    return unittest.makeSuite(WikiPageTestCase, 'test')

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
