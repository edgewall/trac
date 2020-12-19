# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2020 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

import io
import os
import tempfile
import unittest
import zipfile
from datetime import datetime
from xml.dom import minidom

from trac.admin.api import console_datetime_format
from trac.admin.console import TracAdmin
from trac.admin.test import TracAdminTestCaseBase
from trac.attachment import Attachment, AttachmentModule, \
                            IAttachmentChangeListener, LegacyAttachmentPolicy
from trac.core import Component, ComponentMeta, implements, TracError
from trac.perm import IPermissionPolicy, PermissionCache
from trac.resource import IResourceManager, Resource, resource_exists
from trac.test import EnvironmentStub, Mock, MockRequest, mkdtemp
from trac.util.datefmt import format_datetime, to_utimestamp, utc
from trac.web.api import HTTPBadRequest, RequestDone
from trac.web.chrome import Chrome


hashes = {
    '42': '92cfceb39d57d914ed8b14d0e37643de0797ae56',
    'Foo.Mp3': '95797b6eb253337ff2c54e0881e2b747ec394f51',
    'SomePage': 'd7e80bae461ca8568e794792f5520b603f540e06',
    'Teh bar.jpg': 'ed9102c4aa099e92baf1073f824d21c5e4be5944',
    'Teh foo.txt': 'ab97ba98d98fcf72b92e33a66b07077010171f70',
    'bar.7z': '6c9600ad4d59ac864e6f0d2030c1fc76b4b406cb',
    'bar.jpg': 'ae0faa593abf2b6f8871f6f32fe5b28d1c6572be',
    'foo.$$$': 'eefc6aa745dbe129e8067a4a57637883edd83a8a',
    'foo.2.txt': 'a8fcfcc2ef4e400ee09ae53c1aabd7f5a5fda0c7',
    'foo.txt': '9206ac42b532ef8e983470c251f4e1a365fd636c',
    'bar.aäc': '70d0e3b813fdc756602d82748719a3ceb85cbf29',
    'ÜberSicht': 'a16c6837f6d3d2cc3addd68976db1c55deb694c8',
}


class TicketOnlyViewsTicket(Component):
    implements(IPermissionPolicy)

    def check_permission(self, action, username, resource, perm):
        if action.startswith('TICKET_'):
            return resource.realm == 'ticket'
        else:
            return None


class ResourceManagerStub(Component):
    """Fake implementation of IResourceManager."""

    implements(IResourceManager)

    def get_resource_realms(self):
        yield 'parent_realm'

    def get_resource_url(self, resource, href, **kwargs):
        return href(resource.realm, resource.id, version=resource.version)

    def get_resource_description(self, resource, format='default',
                                 context=None, **kwargs):
        pass

    def resource_exists(self, resource):
        return resource.id == 'parent_id'


class AttachmentTestCase(unittest.TestCase):

    attachment_change_listeners = []

    @classmethod
    def setUpClass(cls):
        class AttachmentChangeListener(Component):
            implements(IAttachmentChangeListener)

            def __init__(self):
                self.added_call_count = 0
                self.deleted_call_count = 0
                self.moved_call_count = 0
                self.reparented_call_count = 0
                self.moved_old_parent_realm = None
                self.moved_old_parent_id = None
                self.moved_old_filename = None
                self.reparented_old_parent_realm = None
                self.reparented_old_parent_id = None

            def attachment_added(self, attachment):
                self.added_call_count += 1

            def attachment_deleted(self, attachment):
                self.deleted_call_count += 1

            def attachment_moved(self, attachment, old_parent_realm,
                                 old_parent_id, old_filename):
                self.moved_call_count += 1
                self.moved_old_parent_realm = old_parent_realm
                self.moved_old_parent_id = old_parent_id
                self.moved_old_filename = old_filename

        class LegacyChangeListener(Component):
            implements(IAttachmentChangeListener)

            def __init__(self):
                self.added_called = 0
                self.deleted_called = 0

            def attachment_added(self, attachment):
                self.added_called += 1

            def attachment_deleted(self, attachment):
                self.deleted_called += 1

        cls.attachment_change_listeners = [AttachmentChangeListener,
                                           LegacyChangeListener]

    @classmethod
    def tearDownClass(cls):
        for listener in cls.attachment_change_listeners:
            ComponentMeta.deregister(listener)

    def setUp(self):
        self.env = EnvironmentStub(enable=('trac.*', TicketOnlyViewsTicket))
        self.env.path = mkdtemp()
        self.env.config.set('trac', 'permission_policies',
                            'TicketOnlyViewsTicket, LegacyAttachmentPolicy')
        self.env.config.set('attachment', 'max_size', 512)

        self.perm = PermissionCache(self.env)
        self.datetime = datetime(2001, 1, 1, 1, 1, 1, 0, utc)
        with self.env.db_transaction as db:
            db("INSERT INTO wiki (name,version) VALUES ('WikiStart',1)")
            db("INSERT INTO wiki (name,version) VALUES ('SomePage',1)")
            db("INSERT INTO ticket (id) VALUES (42)")
            db("INSERT INTO ticket (id) VALUES (43)")
            db("INSERT INTO attachment VALUES (%s,%s,%s,%s,%s,%s,%s)",
               ('ticket', '43', 'foo.txt', 8, to_utimestamp(self.datetime),
                'A comment', 'joe'))

    def tearDown(self):
        self.env.reset_db_and_disk()

    def test_new_attachment(self):
        attachment = Attachment(self.env, 'ticket', 42)
        self.assertIsNone(attachment.filename)
        self.assertIsNone(attachment.description)
        self.assertIsNone(attachment.size)
        self.assertIsNone(attachment.date)
        self.assertIsNone(attachment.author)
        self.assertEqual('<Attachment None>', repr(attachment))

    def test_existing_attachment(self):
        attachment = Attachment(self.env, 'ticket', 43, 'foo.txt')
        self.assertEqual('foo.txt', attachment.filename)
        self.assertEqual('A comment', attachment.description)
        self.assertEqual(8, attachment.size)
        self.assertEqual(self.datetime, attachment.date)
        self.assertEqual('joe', attachment.author)
        self.assertEqual("<Attachment 'foo.txt'>", repr(attachment))

    def test_existing_attachment_from_resource(self):
        resource = Resource('ticket', 43).child('attachment', 'foo.txt')
        attachment = Attachment(self.env, resource)
        self.assertEqual('foo.txt', attachment.filename)
        self.assertEqual('A comment', attachment.description)
        self.assertEqual(8, attachment.size)
        self.assertEqual(self.datetime, attachment.date)
        self.assertEqual('joe', attachment.author)
        self.assertEqual("<Attachment 'foo.txt'>", repr(attachment))

    def test_get_path(self):
        attachment = Attachment(self.env, 'ticket', 42)
        attachment.filename = 'foo.txt'
        self.assertEqual(os.path.join(self.env.attachments_dir, 'ticket',
                                      hashes['42'][0:3], hashes['42'],
                                      hashes['foo.txt'] + '.txt'),
                         attachment.path)
        attachment = Attachment(self.env, 'wiki', 'SomePage')
        attachment.filename = 'bar.jpg'
        self.assertEqual(os.path.join(self.env.attachments_dir, 'wiki',
                                      hashes['SomePage'][0:3],
                                      hashes['SomePage'],
                                      hashes['bar.jpg'] + '.jpg'),
                         attachment.path)

    def test_path_extension(self):
        attachment = Attachment(self.env, 'ticket', 42)
        attachment.filename = 'Foo.Mp3'
        self.assertEqual(os.path.join(self.env.attachments_dir, 'ticket',
                                      hashes['42'][0:3], hashes['42'],
                                      hashes['Foo.Mp3'] + '.Mp3'),
                         attachment.path)
        attachment = Attachment(self.env, 'wiki', 'SomePage')
        attachment.filename = 'bar.7z'
        self.assertEqual(os.path.join(self.env.attachments_dir, 'wiki',
                                      hashes['SomePage'][0:3],
                                      hashes['SomePage'],
                                      hashes['bar.7z'] + '.7z'),
                         attachment.path)
        attachment = Attachment(self.env, 'ticket', 42)
        attachment.filename = 'foo.$$$'
        self.assertEqual(os.path.join(self.env.attachments_dir, 'ticket',
                                      hashes['42'][0:3], hashes['42'],
                                      hashes['foo.$$$']),
                         attachment.path)
        attachment = Attachment(self.env, 'wiki', 'SomePage')
        attachment.filename = 'bar.aäc'
        self.assertEqual(os.path.join(self.env.attachments_dir, 'wiki',
                                      hashes['SomePage'][0:3],
                                      hashes['SomePage'],
                                      hashes['bar.aäc']),
                         attachment.path)

    def test_get_path_encoded(self):
        attachment = Attachment(self.env, 'ticket', 42)
        attachment.filename = 'Teh foo.txt'
        self.assertEqual(os.path.join(self.env.attachments_dir, 'ticket',
                                      hashes['42'][0:3], hashes['42'],
                                      hashes['Teh foo.txt'] + '.txt'),
                         attachment.path)
        attachment = Attachment(self.env, 'wiki', 'ÜberSicht')
        attachment.filename = 'Teh bar.jpg'
        self.assertEqual(os.path.join(self.env.attachments_dir, 'wiki',
                                      hashes['ÜberSicht'][0:3],
                                      hashes['ÜberSicht'],
                                      hashes['Teh bar.jpg'] + '.jpg'),
                         attachment.path)

    def test_select_empty(self):
        with self.assertRaises(StopIteration):
            next(Attachment.select(self.env, 'ticket', 42))
        with self.assertRaises(StopIteration):
            next(Attachment.select(self.env, 'wiki', 'SomePage'))

    def test_insert(self):
        attachment = Attachment(self.env, 'ticket', 42)
        attachment.insert('foo.txt', io.BytesIO(), 0, 1)
        attachment = Attachment(self.env, 'ticket', 42)
        attachment.insert('bar.jpg', io.BytesIO(), 0, 2)

        attachments = Attachment.select(self.env, 'ticket', 42)
        self.assertEqual('foo.txt', next(attachments).filename)
        self.assertEqual('bar.jpg', next(attachments).filename)
        with self.assertRaises(StopIteration):
            next(attachments)

    def test_insert_unique(self):
        attachment = Attachment(self.env, 'ticket', 42)
        attachment.insert('foo.txt', io.BytesIO(), 0)
        self.assertEqual('foo.txt', attachment.filename)
        attachment = Attachment(self.env, 'ticket', 42)
        attachment.insert('foo.txt', io.BytesIO(), 0)
        self.assertEqual('foo.2.txt', attachment.filename)
        self.assertEqual(os.path.join(self.env.attachments_dir, 'ticket',
                                      hashes['42'][0:3], hashes['42'],
                                      hashes['foo.2.txt'] + '.txt'),
                         attachment.path)
        self.assertTrue(os.path.exists(attachment.path))

    def test_insert_outside_attachments_dir(self):
        attachment = Attachment(self.env, '../../../../../sth/private', 42)
        with self.assertRaises(TracError):
            attachment.insert('foo.txt', io.BytesIO(), 0)

    def test_delete(self):
        attachment1 = Attachment(self.env, 'wiki', 'SomePage')
        attachment1.insert('foo.txt', io.BytesIO(), 0)
        attachment2 = Attachment(self.env, 'wiki', 'SomePage')
        attachment2.insert('bar.jpg', io.BytesIO(), 0)

        attachments = Attachment.select(self.env, 'wiki', 'SomePage')
        self.assertEqual(2, len(list(attachments)))

        attachment1.delete()
        attachment2.delete()

        self.assertFalse(os.path.exists(attachment1.path))
        self.assertFalse(os.path.exists(attachment2.path))

        attachments = Attachment.select(self.env, 'wiki', 'SomePage')
        self.assertEqual(0, len(list(attachments)))

    def test_delete_file_gone(self):
        """
        Verify that deleting an attachment works even if the referenced file
        doesn't exist for some reason.
        """
        attachment = Attachment(self.env, 'wiki', 'SomePage')
        attachment.insert('foo.txt', io.BytesIO(), 0)
        os.unlink(attachment.path)

        attachment.delete()

    def test_rename(self):
        """Rename an attachment."""
        attachment = Attachment(self.env, 'wiki', 'SomePage')
        attachment.insert('foo.txt', io.BytesIO(), 0)
        original_path = attachment.path
        self.assertTrue(os.path.exists(original_path))
        attachments = Attachment.select(self.env, 'wiki', 'SomePage')
        self.assertEqual(1, len(list(attachments)))

        attachment.move(new_filename='bar.txt')

        attachments = Attachment.select(self.env, 'wiki', 'SomePage')
        self.assertEqual(1, len(list(attachments)))
        self.assertEqual('wiki', attachment.parent_realm)
        self.assertEqual('SomePage', attachment.parent_id)
        self.assertEqual('bar.txt', attachment.filename)
        self.assertFalse(os.path.exists(original_path))
        self.assertTrue(os.path.exists(attachment.path))

    def test_move_nonexistent_attachment_raises(self):
        """TracError is raised when moving a non-existent attachment."""
        attachment = Attachment(self.env, 'wiki', 'SomePage')

        with self.assertRaises(TracError) as cm:
            attachment.move(attachment.parent_realm, attachment.parent_id,
                            attachment.filename)
        self.assertEqual("Cannot rename non-existent attachment",
                         str(cm.exception))

    def test_move_attachment_not_modified_raises(self):
        """TracError is raised when attachment not modified on move."""
        attachment = Attachment(self.env, 'wiki', 'SomePage')
        attachment.insert('foo.txt', io.BytesIO(), 0)

        with self.assertRaises(TracError) as cm:
            attachment.move(attachment.parent_realm, attachment.parent_id,
                            attachment.filename)
        self.assertEqual("Attachment not modified", str(cm.exception))

    def test_move_attachment_to_nonexistent_resource_raises(self):
        """TracError is raised moving an attachment to nonexistent resource
        """
        attachment = Attachment(self.env, 'wiki', 'SomePage')
        attachment.insert('foo.txt', io.BytesIO(), 0)

        with self.assertRaises(TracError) as cm:
            attachment.move('wiki', 'NonExistentPage')
        self.assertEqual("NonExistentPage doesn't exist, can't move attachment",
                         str(cm.exception))

    def test_move_attachment_to_existing_path_raises(self):
        """TracError is raised if target already exists"""
        attachment1 = Attachment(self.env, 'wiki', 'SomePage')
        attachment1.insert('foo.txt', io.BytesIO(), 0)
        attachment2 = Attachment(self.env, 'wiki', 'SomePage')
        attachment2.insert('bar.txt', io.BytesIO(), 0)

        with self.assertRaises(TracError) as cm:
            attachment1.move(new_filename=attachment2.filename)
        self.assertEqual('Cannot move attachment "foo.txt" to "wiki:SomePage: '
                         'bar.txt" as it already exists', str(cm.exception))

    def test_attachment_change_listeners_called(self):
        """The move method calls attachment change listeners"""
        attachment = Attachment(self.env, 'wiki', 'SomePage')
        attachment.insert('foo.txt', io.BytesIO(), 0)
        attachment.move(new_realm='ticket', new_id=42)
        attachment.delete()

        modern_listener = self.attachment_change_listeners[0](self.env)
        self.assertEqual(1, modern_listener.added_call_count)
        self.assertEqual(1, modern_listener.deleted_call_count)
        self.assertEqual(1, modern_listener.moved_call_count)
        self.assertEqual('wiki', modern_listener.moved_old_parent_realm)
        self.assertEqual('SomePage', modern_listener.moved_old_parent_id)
        self.assertEqual('foo.txt', modern_listener.moved_old_filename)
        legacy_listener = self.attachment_change_listeners[0](self.env)
        self.assertEqual(1, legacy_listener.added_call_count)
        self.assertEqual(1, legacy_listener.deleted_call_count)

    def test_attachment_reparented_not_called_on_rename(self):
        attachment = Attachment(self.env, 'wiki', 'SomePage')
        attachment.insert('foo.txt', io.BytesIO(), 0)
        attachment.move(new_filename='bar.txt')

        modern_listener = self.attachment_change_listeners[0](self.env)
        self.assertEqual(1, modern_listener.moved_call_count)
        self.assertEqual(0, modern_listener.reparented_call_count)

    def test_reparent(self):
        """Change the parent realm and parent id of an attachment
        """
        attachment1 = Attachment(self.env, 'wiki', 'SomePage')
        attachment1.insert('foo.txt', io.BytesIO(), 0)
        path1 = attachment1.path
        attachment2 = Attachment(self.env, 'wiki', 'SomePage')
        attachment2.insert('bar.jpg', io.BytesIO(), 0)

        attachments = Attachment.select(self.env, 'wiki', 'SomePage')
        self.assertEqual(2, len(list(attachments)))
        attachments = Attachment.select(self.env, 'ticket', 42)
        self.assertEqual(0, len(list(attachments)))
        self.assertTrue(os.path.exists(path1) and os.path.exists(attachment2.path))

        attachment1.move('ticket', 42)
        self.assertEqual('ticket', attachment1.parent_realm)
        self.assertEqual('ticket', attachment1.resource.parent.realm)
        self.assertEqual('42', attachment1.parent_id)
        self.assertEqual('42', attachment1.resource.parent.id)

        attachments = Attachment.select(self.env, 'wiki', 'SomePage')
        self.assertEqual(1, len(list(attachments)))
        attachments = Attachment.select(self.env, 'ticket', 42)
        self.assertEqual(1, len(list(attachments)))
        self.assertFalse(os.path.exists(path1) and os.path.exists(attachment1.path))
        self.assertTrue(os.path.exists(attachment2.path))

    def test_reparent_all_to_unknown_realm(self):
        """TracError is raised when reparenting an attachment unknown realm
        """
        attachment = Attachment(self.env, 'wiki', 'SomePage')
        attachment.insert('foo.txt', io.BytesIO(), 0)
        attachment = Attachment(self.env, 'wiki', 'SomePage')
        attachment.insert('bar.txt', io.BytesIO(), 0)

        with self.assertRaises(TracError) as cm:
            Attachment.reparent_all(self.env, 'wiki', 'SomePage',
                                    'unknown_realm', 'UnknownId')
        self.assertEqual("unknown_realm doesn't exist, can't move attachment",
                         str(cm.exception))

    def test_reparent_all(self):
        """Change the parent realm and parent id of multiple attachments.
        """
        attachment = Attachment(self.env, 'wiki', 'SomePage')
        attachment.insert('foo.txt', io.BytesIO(), 0)
        attachment = Attachment(self.env, 'wiki', 'SomePage')
        attachment.insert('bar.txt', io.BytesIO(), 0)
        attachments = Attachment.select(self.env, 'wiki', 'SomePage')
        self.assertEqual(2, len(list(attachments)))
        attachments = Attachment.select(self.env, 'wiki', 'WikiStart')
        self.assertEqual(0, len(list(attachments)))

        Attachment.reparent_all(self.env, 'wiki', 'SomePage',
                                'wiki', 'WikiStart')

        attachments = Attachment.select(self.env, 'wiki', 'SomePage')
        self.assertEqual(0, len(list(attachments)))
        attachments = Attachment.select(self.env, 'wiki', 'WikiStart')
        self.assertEqual(2, len(list(attachments)))

    def test_legacy_permission_on_parent(self):
        """Ensure that legacy action tests are done on parent.  As
        `ATTACHMENT_VIEW` maps to `TICKET_VIEW`, the `TICKET_VIEW` is tested
        against the ticket's resource."""
        attachment = Attachment(self.env, 'ticket', 42)
        self.assertIn('ATTACHMENT_VIEW', self.perm(attachment.resource))

    def test_resource_exists(self):
        att = Attachment(self.env, 'wiki', 'WikiStart')
        att.insert('file.txt', io.BytesIO(), 1)
        self.assertTrue(resource_exists(self.env, att.resource))


class AttachmentModuleTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(enable=('trac.*', ResourceManagerStub,))
        self.env.path = mkdtemp()

    def tearDown(self):
        self.env.reset_db_and_disk()

    def test_invalid_post_request_raises_exception(self):

        path_info = '/attachment/parent_realm/parent_id/attachment_id'
        attachment = Attachment(self.env, 'parent_realm', 'parent_id')
        attachment.insert('attachment_id', io.BytesIO(), 0, 1)
        req = MockRequest(self.env, method='POST', action=None,
                          path_info=path_info)
        module = AttachmentModule(self.env)

        self.assertTrue(module.match_request(req))
        with self.assertRaises(HTTPBadRequest):
            module.process_request(req)

    def test_post_request_without_attachment_raises_exception(self):
        """TracError is raised for POST request with no file."""
        path_info = '/attachment/parent_realm/parent_id'
        req = MockRequest(self.env, path_info=path_info, method='POST',
                          args={'action': 'new'})
        module = AttachmentModule(self.env)

        self.assertTrue(module.match_request(req))
        with self.assertRaises(TracError) as cm:
            module.process_request(req)
        self.assertEqual("No file uploaded", str(cm.exception))

    def test_post_request_with_empty_attachment_raises_exception(self):
        """TracError is raised for POST request with empty file."""
        module = AttachmentModule(self.env)
        path_info = '/attachment/parent_realm/parent_id'
        with tempfile.NamedTemporaryFile('rb', dir=self.env.path) as file_:
            upload = Mock(filename=file_.name, file=file_)
            req = MockRequest(self.env, path_info=path_info, method='POST',
                              args={'action': 'new', 'attachment': upload})

            self.assertTrue(module.match_request(req))
            with self.assertRaises(TracError) as cm:
                module.process_request(req)
        self.assertEqual("Can't upload empty file", str(cm.exception))

    def test_post_request_exceeding_max_size_raises_exception(self):
        """TracError is raised for file exceeding max size"""
        self.env.config.set('attachment', 'max_size', 10)
        module = AttachmentModule(self.env)
        path_info = '/attachment/parent_realm/parent_id'
        with tempfile.NamedTemporaryFile('w+b', dir=self.env.path) as file_:
            file_.write(b' ' * (module.max_size + 1))
            file_.flush()
            upload = Mock(filename=file_.name, file=file_)
            req = MockRequest(self.env, path_info=path_info, method='POST',
                              args={'action': 'new', 'attachment': upload})

            self.assertTrue(module.match_request(req))
            with self.assertRaises(TracError) as cm:
                module.process_request(req)
        self.assertEqual("Maximum attachment size: 10 bytes",
                         str(cm.exception))

    def test_attachment_parent_realm_raises_exception(self):
        """TracError is raised when 'attachment' is the resource parent
        realm.
        """
        path_info = '/attachment/attachment/parent_id/attachment_id'
        req = MockRequest(self.env, path_info=path_info)
        module = AttachmentModule(self.env)

        self.assertTrue(module.match_request(req))
        with self.assertRaises(TracError):
            module.process_request(req)

    def test_resource_doesnt_exist(self):
        """Non-existent resource returns False from resource_exists."""
        parent = Resource('parent_realm', 'parent_id')
        self.assertTrue(resource_exists(self.env, parent))
        r = parent.child('attachment', 'file.txt')
        self.assertFalse(resource_exists(self.env, r))

    def test_download_zip(self):
        att = Attachment(self.env, 'parent_realm', 'parent_id')
        att.description = 'Bláh błah'
        att.insert('föö.txt', io.BytesIO(b'foo'), 3,
                   datetime(2016, 9, 23, 12, 34, 56, tzinfo=utc))
        att = Attachment(self.env, 'parent_realm', 'parent_id')
        att.insert('bar.jpg', io.BytesIO(b'bar'), 3,
                   datetime(2016, 12, 14, 23, 56, 30, tzinfo=utc))
        module = AttachmentModule(self.env)
        req = MockRequest(self.env, args={'format': 'zip'},
                          path_info='/attachment/parent_realm/parent_id/')

        self.assertTrue(module.match_request(req))
        self.assertRaises(RequestDone, module.process_request, req)
        z = zipfile.ZipFile(req.response_sent, 'r')
        self.assertEqual(['bar.jpg', 'föö.txt'],
                         sorted(i.filename for i in z.infolist()))

        zinfo = z.getinfo('föö.txt')
        self.assertEqual(b'foo', z.read('föö.txt'))
        self.assertEqual(3, zinfo.file_size)
        self.assertEqual((2016, 9, 23, 12, 34, 56), zinfo.date_time)
        self.assertEqual('Bláh błah'.encode('utf-8'), zinfo.comment)

        zinfo = z.getinfo('bar.jpg')
        self.assertEqual(b'bar', z.read('bar.jpg'))
        self.assertEqual(3, zinfo.file_size)
        self.assertEqual((2016, 12, 14, 23, 56, 30), zinfo.date_time)
        self.assertEqual(b'', zinfo.comment)

    def test_preview_valid_xhtml(self):
        chrome = Chrome(self.env)
        module = AttachmentModule(self.env)

        def render(attachment):
            path_info = '/attachment/%s/%s/%s' % (attachment.parent_realm,
                                                  attachment.parent_id,
                                                  attachment.filename)
            req = MockRequest(self.env, path_info=path_info)
            self.assertTrue(module.match_request(req))
            template, data = module.process_request(req)
            return chrome.render_template(req, template, data,
                                          {'fragment': True})

        # empty file
        attachment = Attachment(self.env, 'parent_realm', 'parent_id')
        attachment.insert('empty', io.BytesIO(), 0, 1)
        result = render(attachment)
        self.assertIn(b'<strong>(The file is empty)</strong>', result)
        xml = minidom.parseString(result)

        # text file
        attachment = Attachment(self.env, 'parent_realm', 'parent_id')
        attachment.insert('foo.txt', io.BytesIO(b'text'), 4, 1)
        result = render(attachment)
        self.assertIn(b'<tr><th id="L1"><a href="#L1">1</a></th>'
                      b'<td>text</td></tr>', result)
        xml = minidom.parseString(result)

        # preview unavailable
        attachment = Attachment(self.env, 'parent_realm', 'parent_id')
        attachment.insert('foo.dat', io.BytesIO(b'\x00\x00\x01\xb3'), 4, 1)
        result = render(attachment)
        self.assertIn(b'<strong>HTML preview not available</strong>', result)
        xml = minidom.parseString(result)


class LegacyAttachmentPolicyTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(enable=('trac.attachment.*', 'trac.perm.*',
                                           ResourceManagerStub),
                                   path=mkdtemp())
        self.env.config.set('trac', 'permission_policies',
                            'DefaultPermissionPolicy,LegacyAttachmentPolicy')
        self.policy = LegacyAttachmentPolicy(self.env)

    def tearDown(self):
        self.env.reset_db_and_disk()

    def _insert_attachment(self, author):
        parent_resource = Resource('parent_realm', 'parent_id')
        att = Attachment(self.env, 'parent_realm', 'parent_id')
        att.author = author
        att.insert('file.txt', io.BytesIO(), 1)
        return Resource('attachment', 'file.txt', parent=parent_resource)

    def test_authenticated_can_delete_own_attachments(self):
        """Authenticated user can delete their own attachments."""
        resource = self._insert_attachment(author='user1')
        perm_cache = PermissionCache(self.env, 'user1', resource)
        action = 'ATTACHMENT_DELETE'

        self.assertIn(action, perm_cache)
        self.assertTrue(self.policy.check_permission(
            action, perm_cache.username, resource, perm_cache))

    def test_authenticated_cannot_delete_other_attachments(self):
        """Authenticated user cannot delete other attachments."""
        resource = self._insert_attachment(author='user1')
        perm_cache = PermissionCache(self.env, 'user2', resource)
        action = 'ATTACHMENT_DELETE'

        self.assertNotIn(action, perm_cache)
        self.assertIsNone(self.policy.check_permission(
            action, perm_cache.username, resource, perm_cache))

    def test_anonymous_cannot_delete_attachments(self):
        """Anonymous user cannot delete attachments."""
        resource = self._insert_attachment(author='anonymous')
        perm_cache = PermissionCache(self.env, 'anonymous', resource)
        action = 'ATTACHMENT_DELETE'

        self.assertNotIn(action, perm_cache)
        self.assertIsNone(self.policy.check_permission(
            action, perm_cache.username, resource, perm_cache))


class TracAdminTestCase(TracAdminTestCaseBase):
    """
    Tests the output of trac-admin and is meant to be used with
    .../trac/tests.py.
    """

    expected_results_filename = 'attachment-console-tests.txt'

    def setUp(self):
        self.env = EnvironmentStub(default_data=True, enable=('trac.*',),
                                   disable=('trac.tests.*',))
        self.env.path = mkdtemp()
        self.admin = TracAdmin()
        self.admin.env_set('', self.env)
        self.datetime = datetime(2001, 1, 1, 1, 1, 1, 0, utc)
        with self.env.db_transaction as db:
            db("INSERT INTO wiki (name,version) VALUES ('WikiStart',1)")
            db("INSERT INTO wiki (name,version) VALUES ('SomePage',1)")
            db("INSERT INTO ticket (id) VALUES (42)")
            db("INSERT INTO ticket (id) VALUES (43)")
            db("INSERT INTO attachment VALUES (%s,%s,%s,%s,%s,%s,%s)",
               ('ticket', '43', 'foo.txt', 8, to_utimestamp(self.datetime),
                'A comment', 'joe'))

    def tearDown(self):
        self.env.reset_db_and_disk()

    def test_attachment_list(self):
        """Attachment list command."""
        attachment = Attachment(self.env, 'wiki', 'SomePage')
        attachment.insert('foo.txt', io.BytesIO(), 0)
        rv, output = self.execute('attachment list wiki:SomePage')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output, {
            'date': format_datetime(attachment.date, console_datetime_format)
        })

    def test_attachment_list_empty(self):
        """Attachment list command with no output."""
        rv, output = self.execute('attachment list wiki:WikiStart')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_attachment_add_nonexistent_resource(self):
        """Error raised when adding an attachment to a non-existent resource.
        """
        rv, output = self.execute('attachment add wiki:NonExistentPage "%s"'
                                  % __file__)
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_attachment_rename(self):
        """Rename attachment."""
        attachment = Attachment(self.env, 'wiki', 'SomePage')
        attachment.insert('foo.txt', io.BytesIO(), 0)

        rv, output = self.execute('attachment move wiki:SomePage foo.txt '
                                  'wiki:SomePage bar.txt')
        self.assertEqual(0, rv, output)
        self.assertEqual('', output)
        rv, output = self.execute('attachment list wiki:SomePage')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output, {
            'date': format_datetime(attachment.date, console_datetime_format)
        })

    def test_attachment_reparent(self):
        """Reparent attachment to another resource."""
        attachment = Attachment(self.env, 'wiki', 'SomePage')
        attachment.insert('foo.txt', io.BytesIO(), 0)

        rv, output = self.execute('attachment move wiki:SomePage foo.txt '
                                  'wiki:WikiStart foo.txt')
        self.assertEqual(0, rv, output)
        self.assertEqual('', output)
        rv, output = self.execute('attachment list wiki:SomePage')
        self.assertEqual(0, rv, output)
        rv, output = self.execute('attachment list wiki:WikiStart')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output, {
            'date': format_datetime(attachment.date, console_datetime_format)
        })

    def test_attachment_move_nonexistent_resource(self):
        """Error raised when reparenting attachment to another resource."""
        attachment = Attachment(self.env, 'wiki', 'SomePage')
        attachment.insert('foo.txt', io.BytesIO(), 0)

        rv, output = self.execute('attachment move wiki:SomePage foo.txt '
                                  'wiki:NonExistentPage foo.txt')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(AttachmentTestCase))
    suite.addTest(unittest.makeSuite(AttachmentModuleTestCase))
    suite.addTest(unittest.makeSuite(LegacyAttachmentPolicyTestCase))
    suite.addTest(unittest.makeSuite(TracAdminTestCase))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
