from trac.db import _parse_db_str

import unittest


class DBTestCase(unittest.TestCase):

    def test_db_str_sqlite_relative(self):
        # Default syntax for specifying DB path relative to the environment
        # directory
        self.assertEqual(('sqlite', {'path': 'db/trac.db'}),
                         _parse_db_str('sqlite:db/trac.db'))

    def test_db_str_sqlite_absolute(self):
        # Standard syntax
        self.assertEqual(('sqlite', {'path': '/var/db/trac.db'}),
                         _parse_db_str('sqlite:///var/db/trac.db'))
        # Legacy syntax
        self.assertEqual(('sqlite', {'path': '/var/db/trac.db'}),
                         _parse_db_str('sqlite:/var/db/trac.db'))

    def test_db_str_sqlite_with_timeout_param(self):
        # In-memory database
        self.assertEqual(('sqlite', {'path': 'db/trac.db',
                                     'params': {'timeout': '10000'}}),
                         _parse_db_str('sqlite:db/trac.db?timeout=10000'))

    def test_db_str_postgres_simple(self):
        self.assertEqual(('postgres', {'host': 'localhost', 'path': '/trac'}),
                         _parse_db_str('postgres://localhost/trac'))

    def test_db_str_postgres_with_port(self):
        self.assertEqual(('postgres', {'host': 'localhost', 'port': 9431,
                                       'path': '/trac'}),
                         _parse_db_str('postgres://localhost:9431/trac'))

    def test_db_str_postgres_with_creds(self):
        self.assertEqual(('postgres', {'user': 'john', 'password': 'letmein',
                                       'host': 'localhost', 'port': 9431,
                                       'path': '/trac'}),
                         _parse_db_str('postgres://john:letmein@localhost:9431/trac'))


def suite():
    return unittest.makeSuite(DBTestCase,'test')

if __name__ == '__main__':
    unittest.main()
