from trac import db_default, test, Logging
from trac.env import Environment

import os
import unittest
import tempfile
import shutil


class EnvironmentTestCase(unittest.TestCase):

    def setUp(self):
        env_path = os.path.join(tempfile.gettempdir(), 'trac-tempenv')
        self.env = Environment(env_path, create=1)
        self.env.insert_default_data()
        self.db = self.env.get_db_cnx()

    def tearDown(self):
        shutil.rmtree(self.env.path)

    def test_get_version(self):
        """Testing env.get_version"""
        assert self.env.get_version() == db_default.db_version

    def test_attachment(self):
        """Testing env.get/add/delete_attachment"""
        class Attachment:
            def __init__(self):
                self.filename = 'foo.txt'
                self.file = tempfile.TemporaryFile()
                
        assert self.env.get_attachments(self.db, 'wiki', 'SomePage') == []
        self.env.create_attachment(self.db, 'wiki', 'SomePage', Attachment(),
                                   'descr', 'author', '127.0.0.1')
        self.env.create_attachment(self.db, 'wiki', 'SomePage', Attachment(),
                                   'descr2', 'author2', '127.0.0.2')
        result = self.env.get_attachments(self.db, 'wiki', 'SomePage')
        assert result[0][0:4] == ('foo.txt', 'descr', 'wiki', 0)
        assert result[1][0:4] == ('foo.2.txt', 'descr2', 'wiki', 0)
        self.env.delete_attachment(self.db, 'wiki', 'SomePage', 'foo.txt')
        result = self.env.get_attachments(self.db, 'wiki', 'SomePage')
        assert result[0][0:4] == ('foo.2.txt', 'descr2', 'wiki', 0)
        self.env.delete_attachment(self.db, 'wiki', 'SomePage', 'foo.2.txt')
        assert self.env.get_attachments(self.db, 'wiki', 'SomePage') == []


def suite():
    return unittest.makeSuite(EnvironmentTestCase,'test')

if __name__ == '__main__':
    unittest.main()
