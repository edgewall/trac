# -*- coding: utf-8 -*-

import os
import unittest

from trac.db.api import _parse_db_str
from trac.test import EnvironmentStub


class ParseConnectionStringTestCase(unittest.TestCase):

    def test_sqlite_relative(self):
        # Default syntax for specifying DB path relative to the environment
        # directory
        self.assertEqual(('sqlite', {'path': 'db/trac.db'}),
                         _parse_db_str('sqlite:db/trac.db'))

    def test_sqlite_absolute(self):
        # Standard syntax
        self.assertEqual(('sqlite', {'path': '/var/db/trac.db'}),
                         _parse_db_str('sqlite:///var/db/trac.db'))
        # Legacy syntax
        self.assertEqual(('sqlite', {'path': '/var/db/trac.db'}),
                         _parse_db_str('sqlite:/var/db/trac.db'))

    def test_sqlite_with_timeout_param(self):
        # In-memory database
        self.assertEqual(('sqlite', {'path': 'db/trac.db',
                                     'params': {'timeout': '10000'}}),
                         _parse_db_str('sqlite:db/trac.db?timeout=10000'))

    def test_sqlite_windows_path(self):
        # In-memory database
        os_name = os.name
        try:
            os.name = 'nt'
            self.assertEqual(('sqlite', {'path': 'C:/project/db/trac.db'}),
                             _parse_db_str('sqlite:C|/project/db/trac.db'))
        finally:
            os.name = os_name

    def test_postgres_simple(self):
        self.assertEqual(('postgres', {'host': 'localhost', 'path': '/trac'}),
                         _parse_db_str('postgres://localhost/trac'))

    def test_postgres_with_port(self):
        self.assertEqual(('postgres', {'host': 'localhost', 'port': 9431,
                                       'path': '/trac'}),
                         _parse_db_str('postgres://localhost:9431/trac'))

    def test_postgres_with_creds(self):
        self.assertEqual(('postgres', {'user': 'john', 'password': 'letmein',
                                       'host': 'localhost', 'port': 9431,
                                       'path': '/trac'}),
                 _parse_db_str('postgres://john:letmein@localhost:9431/trac'))

    def test_postgres_with_quoted_password(self):
        self.assertEqual(('postgres', {'user': 'john', 'password': ':@/',
                                       'host': 'localhost', 'path': '/trac'}),
                     _parse_db_str('postgres://john:%3a%40%2f@localhost/trac'))

    def test_mysql_simple(self):
        self.assertEqual(('mysql', {'host': 'localhost', 'path': '/trac'}),
                     _parse_db_str('mysql://localhost/trac'))

    def test_mysql_with_creds(self):
        self.assertEqual(('mysql', {'user': 'john', 'password': 'letmein',
                                    'host': 'localhost', 'port': 3306,
                                    'path': '/trac'}),
                     _parse_db_str('mysql://john:letmein@localhost:3306/trac'))


class StringsTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()

    def test_insert_unicode(self):
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute('INSERT INTO system (name,value) VALUES (%s,%s)',
                       ('test-unicode', u'ünicöde'))
        db.commit()
        cursor = db.cursor()
        cursor.execute("SELECT value FROM system WHERE name='test-unicode'")
        self.assertEqual([(u'ünicöde',)], cursor.fetchall())

    def test_insert_empty(self):
        from trac.util.text import empty
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute('INSERT INTO system (name,value) VALUES (%s,%s)',
                       ('test-empty', empty))
        db.commit()
        cursor = db.cursor()
        cursor.execute("SELECT value FROM system WHERE name='test-empty'")
        self.assertEqual([(u'',)], cursor.fetchall())

    def test_insert_markup(self):
        from genshi.core import Markup
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute('INSERT INTO system (name,value) VALUES (%s,%s)',
                       ('test-markup', Markup(u'<em>märkup</em>')))
        db.commit()
        cursor = db.cursor()
        cursor.execute("SELECT value FROM system WHERE name='test-markup'")
        self.assertEqual([(u'<em>märkup</em>',)], cursor.fetchall())


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(ParseConnectionStringTestCase, 'test'))
    suite.addTest(unittest.makeSuite(StringsTestCase, 'test'))
    return suite

if __name__ == '__main__':
    unittest.main()
