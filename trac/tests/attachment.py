# -*- encoding: utf-8 -*-
from trac.attachment import Attachment, AttachmentModule
from trac.config import Configuration
from trac.log import logger_factory
from trac.test import EnvironmentStub, Mock
from trac.wiki.formatter import Formatter

import os
import os.path
import shutil
import tempfile
import unittest
import time


def sleep_for_timestamps():
    granularity = 0.02
    time.sleep(granularity)
    

class AttachmentTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.env.path = os.path.join(tempfile.gettempdir(), 'trac-tempenv')
        os.mkdir(self.env.path)
        self.attachments_dir = os.path.join(self.env.path, 'attachments')
        self.env.config.set('attachment', 'max_size', 512)

        self.perm = Mock(assert_permission=lambda x: None,
                         has_permission=lambda x: True)

    def tearDown(self):
        shutil.rmtree(self.env.path)

    def test_get_path(self):
        attachment = Attachment(self.env, 'ticket', 42)
        attachment.filename = 'foo.txt'
        self.assertEqual(os.path.join(self.attachments_dir, 'ticket', '42',
                                      'foo.txt'),
                         attachment.path)
        attachment = Attachment(self.env, 'wiki', 'SomePage')
        attachment.filename = 'bar.jpg'
        self.assertEqual(os.path.join(self.attachments_dir, 'wiki', 'SomePage',
                                      'bar.jpg'),
                         attachment.path)

    def test_get_path_encoded(self):
        attachment = Attachment(self.env, 'ticket', 42)
        attachment.filename = 'Teh foo.txt'
        self.assertEqual(os.path.join(self.attachments_dir, 'ticket', '42',
                                      'Teh%20foo.txt'),
                         attachment.path)
        attachment = Attachment(self.env, 'wiki', u'ÜberSicht')
        attachment.filename = 'Teh bar.jpg'
        self.assertEqual(os.path.join(self.attachments_dir, 'wiki',
                                      '%C3%9CberSicht', 'Teh%20bar.jpg'),
                         attachment.path)

    def test_select_empty(self):
        self.assertRaises(StopIteration,
                          Attachment.select(self.env, 'ticket', 42).next)
        self.assertRaises(StopIteration,
                          Attachment.select(self.env, 'wiki', 'SomePage').next)

    def test_insert(self):
        attachment = Attachment(self.env, 'ticket', 42)
        attachment.insert('foo.txt', tempfile.TemporaryFile(), 0)
        sleep_for_timestamps()
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

    def test_insert_outside_attachments_dir(self):
        attachment = Attachment(self.env, '../../../../../sth/private', 42)
        self.assertRaises(AssertionError, attachment.insert, 'foo.txt',
                          tempfile.TemporaryFile(), 0)

    def test_delete(self):
        attachment1 = Attachment(self.env, 'wiki', 'SomePage')
        attachment1.insert('foo.txt', tempfile.TemporaryFile(), 0)
        attachment2 = Attachment(self.env, 'wiki', 'SomePage')
        attachment2.insert('bar.jpg', tempfile.TemporaryFile(), 0)

        attachments = Attachment.select(self.env, 'wiki', 'SomePage')
        self.assertEqual(2, len(list(attachments)))

        attachment1.delete()
        attachment2.delete()

        assert not os.path.exists(attachment1.path)
        assert not os.path.exists(attachment2.path)

        attachments = Attachment.select(self.env, 'wiki', 'SomePage')
        self.assertEqual(0, len(list(attachments)))

    def test_delete_file_gone(self):
        """
        Verify that deleting an attachment works even if the referenced file
        doesn't exist for some reason.
        """
        attachment = Attachment(self.env, 'wiki', 'SomePage')
        attachment.insert('foo.txt', tempfile.TemporaryFile(), 0)
        os.unlink(attachment.path)

        attachment.delete()


class AttachmentModuleTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.env.path = os.path.join(tempfile.gettempdir(), 'trac-tempenv')
        os.mkdir(self.env.path)
        self.attachments_dir = os.path.join(self.env.path, 'attachments')

    def tearDown(self):
        shutil.rmtree(self.env.path)

    def test_wiki_link_wikipage(self):
        attachment = Attachment(self.env, 'wiki', 'SomePage')
        attachment.insert('foo.txt', tempfile.TemporaryFile(), 0)

        ns, func = AttachmentModule(self.env).get_link_resolvers().next()
        self.assertEqual('attachment', ns)

        req = Mock(path_info='/wiki/SomePage')
        formatter = Formatter(self.env, req)
        self.assertEqual('<a class="attachment" title="Attachment SomePage: '
                         'foo.txt" href="/trac.cgi/attachment/wiki/SomePage/'
                         'foo.txt">Foo</a>',
                         func(formatter, ns, 'foo.txt', 'Foo'))
        self.assertEqual('<a class="attachment" title="Attachment SomePage: '
                         'foo.txt" href="/trac.cgi/attachment/wiki/SomePage/'
                         'foo.txt?format=raw">Foo</a>',
                         func(formatter, ns, 'foo.txt?format=raw', 'Foo'))

    def test_wiki_link_subpage(self):
        attachment = Attachment(self.env, 'wiki', 'SomePage/SubPage')
        attachment.insert('foo.txt', tempfile.TemporaryFile(), 0)

        ns, func = AttachmentModule(self.env).get_link_resolvers().next()
        self.assertEqual('attachment', ns)

        req = Mock(path_info='/wiki/SomePage/SubPage')
        formatter = Formatter(self.env, req)
        self.assertEqual('<a class="attachment" '
                         'title="Attachment SomePage/SubPage: foo.txt" '
                         'href="/trac.cgi/attachment/wiki/SomePage/SubPage/'
                         'foo.txt">Foo</a>',
                         func(formatter, ns, 'foo.txt', 'Foo'))

    def test_wiki_link_ticket(self):
        attachment = Attachment(self.env, 'ticket', 123)
        attachment.insert('foo.txt', tempfile.TemporaryFile(), 0)

        ns, func = AttachmentModule(self.env).get_link_resolvers().next()
        self.assertEqual('attachment', ns)

        req = Mock(path_info='/ticket/123')
        formatter = Formatter(self.env, req)
        self.assertEqual('<a class="attachment" title="Attachment #123: '
                         'foo.txt" href="/trac.cgi/attachment/ticket/123/'
                         'foo.txt">Foo</a>',
                         func(formatter, ns, 'foo.txt', 'Foo'))
        self.assertEqual('<a class="attachment" title="Attachment #123: '
                         'foo.txt" href="/trac.cgi/attachment/ticket/123/'
                         'foo.txt?format=raw">Foo</a>',
                         func(formatter, ns, 'foo.txt?format=raw', 'Foo'))

    def test_wiki_link_foreign(self):
        attachment = Attachment(self.env, 'ticket', 123)
        attachment.insert('foo.txt', tempfile.TemporaryFile(), 0)

        ns, func = AttachmentModule(self.env).get_link_resolvers().next()
        self.assertEqual('attachment', ns)

        req = Mock(path_info='/wiki')
        formatter = Formatter(self.env, req)
        self.assertEqual('<a class="attachment" title="Attachment #123: '
                         'foo.txt" href="/trac.cgi/attachment/ticket/123/'
                         'foo.txt">Foo</a>',
                         func(formatter, ns, 'ticket:123:foo.txt', 'Foo'))
        self.assertEqual('<a class="attachment" title="Attachment #123: '
                         'foo.txt" href="/trac.cgi/attachment/ticket/123/'
                         'foo.txt?format=raw">Foo</a>',
                         func(formatter, ns, 'ticket:123:foo.txt?format=raw',
                              'Foo'))


def suite():
    return unittest.makeSuite(AttachmentTestCase, 'test')

if __name__ == '__main__':
    unittest.main()
