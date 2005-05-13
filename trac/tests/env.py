from trac import db_default
from trac.env import Environment

import os.path
import unittest
import tempfile
import shutil


class EnvironmentTestCase(unittest.TestCase):

    def setUp(self):
        env_path = os.path.join(tempfile.gettempdir(), 'trac-tempenv')
        self.env = Environment(env_path, create=True, db_str='sqlite:db/trac.db')
        self.db = self.env.get_db_cnx()

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.env.path)

    def test_get_version(self):
        """Testing env.get_version"""
        assert self.env.get_version() == db_default.db_version

    def test_get_known_users(self):
        """Testing env.get_known_users"""
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO session "
                       "VALUES ('123',0,'email','a@example.com')")
        cursor.executemany("INSERT INTO session VALUES (%s,1,%s,%s)",
                           [('tom', 'name', 'Tom'),
                            ('tom', 'email', 'tom@example.com'),
                            ('joe', 'email', 'joe@example.com'),
                            ('jane', 'name', 'Jane')])
        users = {}
        for username,name,email in self.env.get_known_users(self.db):
            users[username] = (name, email)

        assert not users.has_key('anonymous')
        self.assertEqual(('Tom', 'tom@example.com'), users['tom'])
        self.assertEqual((None, 'joe@example.com'), users['joe'])
        self.assertEqual(('Jane', None), users['jane'])


def suite():
    return unittest.makeSuite(EnvironmentTestCase,'test')

if __name__ == '__main__':
    unittest.main()
