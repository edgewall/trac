from trac.attachment import Attachment
from trac.config import Configuration
from trac.log import logger_factory
from trac.test import InMemoryDatabase, Mock

import os
import shutil
import tempfile
import unittest


class AttachmentTestCase(unittest.TestCase):

    def setUp(self):
        self.env_path = os.path.join(tempfile.gettempdir(), 'trac-tempenv')
        os.mkdir(self.env_path)
        self.db = InMemoryDatabase()
        self.attachments_dir = os.path.join(self.env_path, 'attachments')
        config = Configuration(None)
        config.setdefault('attachment', 'max_size', 512)
        self.env = Mock(config=config, log=logger_factory('test'),
                        get_attachments_dir=lambda: self.attachments_dir,
                        get_db_cnx=lambda: self.db)
        self.perm = Mock(assert_permission=lambda x: None,
                         has_permission=lambda x: True)

    def tearDown(self):
        shutil.rmtree(self.env_path)


    def test_get_path(self):
        attachment = Attachment(self.env, 'ticket', 42)
        attachment.filename = 'foo.txt'
        self.assertEqual(os.path.join(self.attachments_dir, 'ticket', '42', 'foo.txt'),
                         attachment.path)
        attachment = Attachment(self.env, 'wiki', 'SomePage')
        attachment.filename = 'bar.jpg'
        self.assertEqual(os.path.join(self.attachments_dir, 'wiki', 'SomePage', 'bar.jpg'),
                         attachment.path)

    def test_get_path_encoded(self):
        attachment = Attachment(self.env, 'ticket', 42)
        attachment.filename = 'Teh foo.txt'
        self.assertEqual(os.path.join(self.attachments_dir, 'ticket', '42', 'Teh%20foo.txt'),
                         attachment.path)
        attachment = Attachment(self.env, 'wiki', '\xdcberSicht')
        attachment.filename = 'Teh bar.jpg'
        self.assertEqual(os.path.join(self.attachments_dir, 'wiki', '%DCberSicht', 'Teh%20bar.jpg'),
                         attachment.path)

    def test_select_empty(self):
        self.assertRaises(StopIteration,
                          Attachment.select(self.env, 'ticket', 42).next)
        self.assertRaises(StopIteration,
                          Attachment.select(self.env, 'wiki', 'SomePage').next)

    def test_insert(self):
        attachment = Attachment(self.env, 'ticket', 42)
        attachment.insert('foo.txt', tempfile.TemporaryFile(), 0)
        attachment = Attachment(self.env, 'ticket', 42)
        attachment.insert('bar.jpg', tempfile.TemporaryFile(), 0)

        attachments = Attachment.select(self.env, 'ticket', 42)
        self.assertEqual('foo.txt', attachments.next().filename)
        self.assertEqual('bar.jpg', attachments.next().filename)
        self.assertRaises(StopIteration, attachments.next)

    def test_insert_unique(self):
        attachment = Attachment(self.env, 'ticket', 42)
        attachment.insert('foo.txt', tempfile.TemporaryFile(), 0)
        self.assertEqual('foo.txt', attachment.filename)
        attachment = Attachment(self.env, 'ticket', 42)
        attachment.insert('foo.txt', tempfile.TemporaryFile(), 0)
        self.assertEqual('foo.2.txt', attachment.filename)

    def test_delete(self):
        attachment1 = Attachment(self.env, 'wiki', 'SomePage')
        attachment1.insert('foo.txt', tempfile.TemporaryFile(), 0)
        attachment2 = Attachment(self.env, 'wiki', 'SomePage')
        attachment2.insert('bar.jpg', tempfile.TemporaryFile(), 0)

        attachments = Attachment.select(self.env, 'wiki', 'SomePage')
        self.assertEqual(2, len(list(attachments)))

        attachment1.delete()
        attachment2.delete()

        attachments = Attachment.select(self.env, 'wiki', 'SomePage')
        self.assertEqual(0, len(list(attachments)))


def suite():
    return unittest.makeSuite(AttachmentTestCase, 'test')

if __name__ == '__main__':
    unittest.main()
