import unittest

from trac.core import *
from trac.test import EnvironmentStub
from trac.wiki import WikiPage, IWikiChangeListener


class TestWikiChangeListener(Component):
    implements(IWikiChangeListener)
    def __init__(self):
        self.added = []
        self.changed = []
        self.deleted = []

    def wiki_page_added(self, page):
        self.added.append(page)

    def wiki_page_changed(self, page, version, t, comment, author, ipnr):
        self.changed.append((page, version, t, comment, author, ipnr))

    def wiki_page_deleted(self, page):
        self.deleted.append(page)



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
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO wiki VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                       ('TestPage', 0, 42, 'joe', '::1', 'Bla bla', 'Testing',
                        0))

        page = WikiPage(self.env, 'TestPage')
        self.assertEqual('TestPage', page.name)
        self.assertEqual(0, page.version)
        self.assertEqual('Bla bla', page.text)
        self.assertEqual(False, page.readonly)
        history = list(page.get_history())
        self.assertEqual(1, len(history))
        self.assertEqual((0, 42, 'joe', 'Testing', '::1'), history[0])

    def test_create_page(self):
        page = WikiPage(self.env)
        page.name = 'TestPage'
        page.text = 'Bla bla'
        page.save('joe', 'Testing', '::1', 42)

        cursor = self.db.cursor()
        cursor.execute("SELECT version,time,author,ipnr,text,comment,"
                       "readonly FROM wiki WHERE name=%s", ('TestPage',))
        self.assertEqual((1, 42, 'joe', '::1', 'Bla bla', 'Testing', 0),
                         cursor.fetchone())

        listener = TestWikiChangeListener(self.env)
        self.assertEqual(page, listener.added[0])

    def test_update_page(self):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO wiki VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                       ('TestPage', 1, 42, 'joe', '::1', 'Bla bla', 'Testing',
                        0))

        page = WikiPage(self.env, 'TestPage')
        page.text = 'Bla'
        page.save('kate', 'Changing', '192.168.0.101', 43)

        cursor.execute("SELECT version,time,author,ipnr,text,comment,"
                       "readonly FROM wiki WHERE name=%s", ('TestPage',))
        self.assertEqual((1, 42, 'joe', '::1', 'Bla bla', 'Testing', 0),
                         cursor.fetchone())
        self.assertEqual((2, 43, 'kate', '192.168.0.101', 'Bla',
                          'Changing', 0), cursor.fetchone())

        listener = TestWikiChangeListener(self.env)
        self.assertEqual((page, 2, 43, 'kate', 'Changing', '192.168.0.101'),
                         listener.changed[0])

        page = WikiPage(self.env, 'TestPage')
        history = list(page.get_history())
        self.assertEqual(2, len(history))
        self.assertEqual((2, 43, 'kate', 'Changing', '192.168.0.101'),
                         history[0])
        self.assertEqual((1, 42, 'joe', 'Testing', '::1'), history[1])

    def test_delete_page(self):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO wiki VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                       ('TestPage', 1, 42, 'joe', '::1', 'Bla bla', 'Testing',
                        0))

        page = WikiPage(self.env, 'TestPage')
        page.delete()

        self.assertFalse(page.exists)

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

        self.assertTrue(page.exists)

        cursor.execute("SELECT version,time,author,ipnr,text,comment,"
                       "readonly FROM wiki WHERE name=%s", ('TestPage',))
        self.assertEqual((1, 42, 'joe', '::1', 'Bla bla', 'Testing', 0),
                         cursor.fetchone())
        self.assertEqual(None, cursor.fetchone())

        listener = TestWikiChangeListener(self.env)
        self.assertEqual(0, len(listener.deleted))

    def test_delete_page_last_version(self):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO wiki VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                       ('TestPage', 1, 42, 'joe', '::1', 'Bla bla', 'Testing',
                        0))

        page = WikiPage(self.env, 'TestPage')
        page.delete(version=1)

        self.assertFalse(page.exists)

        cursor.execute("SELECT version,time,author,ipnr,text,comment,"
                       "readonly FROM wiki WHERE name=%s", ('TestPage',))
        self.assertEqual(None, cursor.fetchone())

        listener = TestWikiChangeListener(self.env)
        self.assertEqual(page, listener.deleted[0])


def suite():
    return unittest.makeSuite(WikiPageTestCase, 'test')

if __name__ == '__main__':
    unittest.main()
