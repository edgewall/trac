import os
import unittest
import tempfile

from Environment import Environment, db_default


class EnvironmentTestCase(unittest.TestCase):
    def setUp(self):
        self.env = Environment(self._get_envpath(), create=1)
        self.env.insert_default_data()
        self.db = self.env.get_db_cnx()

    def tearDown(self):
        self.env = None
        self._removeall(self._get_envpath())

    def _get_envpath(self):
        return os.path.join(tempfile.gettempdir(), 'trac-tempenv')
    
    def _removeall(self, path):
        """Delete a directory and all it's files and subdirectories"""
        files = os.listdir(path)
        for name in files:
            fullpath = os.path.join(path, name)
            if os.path.isfile(fullpath):
                os.unlink(fullpath)
            elif os.path.isdir(fullpath):
                self._removeall(fullpath)
        os.rmdir(path)

    def test_get_version(self):
        """Testing env.get_version"""
        assert self.env.get_version() == db_default.db_version

    def test_config(self):
        """Testing env.get/set_config"""
        assert self.env.get_config('trac', 'database') == 'sqlite:db/trac.db'
        self.env.set_config('foo', 'bar', 'baz')
        self.env.save_config()
        assert self.env.get_config('foo', 'bar') == 'baz'
        assert self.env.get_config('non', 'existent') == ''
        assert self.env.get_config('non', 'existent', None) == None
        assert self.env.get_config('non', 'existent', 'default') == 'default'

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
