from trac import db_default
from trac.env import Environment

import os.path
import unittest
import tempfile
import shutil


class EnvironmentTestCase(unittest.TestCase):

    def setUp(self):
        env_path = os.path.join(tempfile.gettempdir(), 'trac-tempenv')
        self.env = Environment(env_path, create=True)
        self.db = self.env.get_db_cnx()

    def tearDown(self):
        self.db.close()
        self.env.shutdown() # really closes the db connections
        shutil.rmtree(self.env.path)

    def test_get_version(self):
        """Testing env.get_version"""
        assert self.env.get_version() == db_default.db_version

    def test_get_known_users(self):
        """Testing env.get_known_users"""
        cursor = self.db.cursor()
        cursor.executemany("INSERT INTO session VALUES (%s,%s,0)",
                           [('123', 0),('tom', 1), ('joe', 1), ('jane', 1)])
        cursor.executemany("INSERT INTO session_attribute VALUES (%s,%s,%s,%s)",
                           [('123', 0, 'email', 'a@example.com'),
                            ('tom', 1, 'name', 'Tom'),
                            ('tom', 1, 'email', 'tom@example.com'),
                            ('joe', 1, 'email', 'joe@example.com'),
                            ('jane', 1, 'name', 'Jane')])
        users = {}
        for username, name, email in self.env.get_known_users(self.db):
            users[username] = (name, email)

        assert not users.has_key('anonymous')
        self.assertEqual(('Tom', 'tom@example.com'), users['tom'])
        self.assertEqual((None, 'joe@example.com'), users['joe'])
        self.assertEqual(('Jane', None), users['jane'])


def suite():
    return unittest.makeSuite(EnvironmentTestCase,'test')

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
