# -*- coding: utf-8 -*-
#
# Copyright (C) 2014 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

import posixpath
import unittest
import zipfile
from datetime import datetime
from cStringIO import StringIO

import trac.tests.compat
from trac.core import Component, TracError, implements
from trac.perm import PermissionError
from trac.resource import ResourceNotFound
from trac.test import Mock, MockRequest
from trac.util.datefmt import utc
from trac.util.text import to_utf8
from trac.versioncontrol.api import (
    Changeset, DbRepositoryProvider, IRepositoryConnector, Node, NoSuchNode,
    Repository, RepositoryManager)
from trac.versioncontrol.web_ui.browser import BrowserModule
from trac.web.api import RequestDone
from trac.web.chrome import Chrome
from trac.web.tests.api import RequestHandlerPermissionsTestCaseBase


class MockRepositoryConnector(Component):

    implements(IRepositoryConnector)

    def get_supported_types(self):
        yield 'mock', 8

    def get_repository(self, repos_type, repos_dir, params):
        t = datetime(2017, 3, 31, 12, 34, 56, tzinfo=utc)

        def get_changeset(rev):
            return Mock(Changeset, repos, rev, 'message', 'author', t)

        def get_node(path, rev):
            if 'missing' in path:
                raise NoSuchNode(path, rev)
            basename = posixpath.basename(path)
            if 'file' in basename:
                kind = Node.FILE
                entries = ()
                content = 'Contents for %s' % to_utf8(path)
                length = len(content)
            else:
                kind = Node.DIRECTORY
                if 'dir' in basename:
                    entries = ['file.txt']
                else:
                    entries = ['dir1', 'dir2']
                entries = [posixpath.join(path, entry) for entry in entries]
                content = length = None
            node = Mock(Node, repos, path, rev, kind,
                        created_path=path, created_rev=rev,
                        get_entries=lambda: iter(get_node(entry, rev)
                                                 for entry in entries),
                        get_properties=lambda: {},
                        get_content=lambda: content and StringIO(content),
                        get_content_length=lambda: length,
                        get_content_type=lambda: 'application/octet-stream',
                        get_last_modified=lambda: t)
            return node

        if params['name'] == 'raise':
            raise TracError("")
        else:
            repos = Mock(Repository, params['name'], params, self.log,
                         get_youngest_rev=lambda: 1,
                         get_changeset=get_changeset,
                         get_node=get_node,
                         previous_rev=lambda rev, path='': None,
                         next_rev=lambda rev, path='': None,
                         display_rev=lambda rev: str(rev))
        return repos


class BrowserModulePermissionsTestCase(RequestHandlerPermissionsTestCaseBase):

    authz_policy = """\
[repository:*allow*@*/source:*deny*]
anonymous = !BROWSER_VIEW, !FILE_VIEW

[repository:*deny*@*/source:*allow*]
anonymous = BROWSER_VIEW, FILE_VIEW

[repository:*allow*@*]
anonymous = BROWSER_VIEW, FILE_VIEW

[repository:*deny*@*]
anonymous = !BROWSER_VIEW, !FILE_VIEW

"""

    def setUp(self):
        super(BrowserModulePermissionsTestCase, self).setUp(BrowserModule)
        provider = DbRepositoryProvider(self.env)
        provider.add_repository('(default)', '/', 'mock')
        provider.add_repository('allow', '/', 'mock')
        provider.add_repository('deny', '/', 'mock')
        provider.add_repository('raise', '/', 'mock')

    def tearDown(self):
        RepositoryManager(self.env).reload_repositories()
        super(BrowserModulePermissionsTestCase, self).tearDown()

    def test_get_navigation_items_with_browser_view(self):
        self.grant_perm('anonymous', 'BROWSER_VIEW')
        provider = DbRepositoryProvider(self.env)
        req = MockRequest(self.env, path_info='/')
        self.assertEqual('browser', self.get_navigation_items(req).next()[1])

        provider.remove_repository('allow')
        self.assertEqual('browser', self.get_navigation_items(req).next()[1])

        provider.remove_repository('deny')
        self.assertEqual('browser', self.get_navigation_items(req).next()[1])

        provider.remove_repository('(default)')
        self.assertEqual([], list(self.get_navigation_items(req)))

    def test_get_navigation_items_without_browser_view(self):
        provider = DbRepositoryProvider(self.env)
        req = MockRequest(self.env, path_info='/')
        self.assertEqual('browser', self.get_navigation_items(req).next()[1])

        provider.remove_repository('(default)')
        self.assertEqual('browser', self.get_navigation_items(req).next()[1])

        provider.remove_repository('deny')
        self.assertEqual('browser', self.get_navigation_items(req).next()[1])

        provider.remove_repository('allow')
        self.assertEqual([], list(self.get_navigation_items(req)))

    def test_repository_with_browser_view(self):
        self.grant_perm('anonymous', 'BROWSER_VIEW')

        req = MockRequest(self.env, authname='anonymous',
                          path_info='/browser/')
        rv = self.process_request(req)
        self.assertEqual('', rv[1]['repos'].name)

        req = MockRequest(self.env, authname='anonymous',
                          path_info='/browser/allow')
        rv = self.process_request(req)
        self.assertEqual('allow', rv[1]['repos'].name)

        req = MockRequest(self.env, authname='anonymous',
                          path_info='/browser/deny')
        try:
            self.process_request(req)
            self.fail('PermissionError not raised')
        except PermissionError as e:
            self.assertEqual('BROWSER_VIEW', e.action)
            self.assertEqual('source', e.resource.realm)
            self.assertEqual('/', e.resource.id)
            self.assertEqual('repository', e.resource.parent.realm)
            self.assertEqual('deny', e.resource.parent.id)

        DbRepositoryProvider(self.env).remove_repository('(default)')
        req = MockRequest(self.env, path_info='/browser/')
        rv = self.process_request(req)
        self.assertEqual(None, rv[1]['repos'])

        req = MockRequest(self.env, path_info='/browser/blah-blah-file')
        try:
            self.process_request(req)
            self.fail('ResourceNotFound not raised')
        except ResourceNotFound as e:
            self.assertEqual('No node blah-blah-file', unicode(e))

    def test_repository_without_browser_view(self):
        req = MockRequest(self.env, authname='anonymous',
                          path_info='/browser/')
        rv = self.process_request(req)
        # cannot view default repository but don't raise PermissionError
        self.assertEqual(None, rv[1]['repos'])

        req = MockRequest(self.env, path_info='/browser/allow')
        rv = self.process_request(req)
        self.assertEqual('allow', rv[1]['repos'].name)

        req = MockRequest(self.env, authname='anonymous',
                          path_info='/browser/deny')
        try:
            self.process_request(req)
            self.fail('PermissionError not raised')
        except PermissionError as e:
            self.assertEqual('BROWSER_VIEW', e.action)
            self.assertEqual('source', e.resource.realm)
            self.assertEqual('/', e.resource.id)
            self.assertEqual('repository', e.resource.parent.realm)
            self.assertEqual('deny', e.resource.parent.id)

        DbRepositoryProvider(self.env).remove_repository('(default)')
        req = MockRequest(self.env, path_info='/browser/')
        rv = self.process_request(req)
        self.assertEqual(None, rv[1]['repos'])

        req = MockRequest(self.env, authname='anonymous',
                          path_info='/browser/blah-blah-file')
        try:
            self.process_request(req)
            self.fail('PermissionError not raised')
        except PermissionError as e:
            self.assertEqual('BROWSER_VIEW', e.action)
            self.assertEqual(None, e.resource)

    def test_node_with_file_view(self):
        self.grant_perm('anonymous', 'BROWSER_VIEW', 'FILE_VIEW')

        req = MockRequest(self.env, authname='anonymous',
                          path_info='/browser/file')
        rv = self.process_request(req)
        self.assertEqual('', rv[1]['repos'].name)
        self.assertEqual('file', rv[1]['path'])

        req = MockRequest(self.env, authname='anonymous',
                          path_info='/browser/allow-file')
        rv = self.process_request(req)
        self.assertEqual('', rv[1]['repos'].name)
        self.assertEqual('allow-file', rv[1]['path'])

        req = MockRequest(self.env, authname='anonymous',
                          path_info='/browser/deny-file')
        try:
            self.process_request(req)
            self.fail('PermissionError not raised')
        except PermissionError as e:
            self.assertEqual('FILE_VIEW', e.action)
            self.assertEqual('source', e.resource.realm)
            self.assertEqual('deny-file', e.resource.id)
            self.assertEqual('repository', e.resource.parent.realm)
            self.assertEqual('', e.resource.parent.id)

    def test_node_in_allowed_repos_with_file_view(self):
        self.grant_perm('anonymous', 'BROWSER_VIEW', 'FILE_VIEW')

        req = MockRequest(self.env, authname='anonymous',
                          path_info='/browser/allow/file')
        rv = self.process_request(req)
        self.assertEqual('allow', rv[1]['repos'].name)
        self.assertEqual('file', rv[1]['path'])

        req = MockRequest(self.env, authname='anonymous',
                          path_info='/browser/allow/allow-file')
        rv = self.process_request(req)
        self.assertEqual('allow', rv[1]['repos'].name)
        self.assertEqual('allow-file', rv[1]['path'])

        req = MockRequest(self.env, authname='anonymous',
                          path_info='/browser/allow/deny-file')
        try:
            self.process_request(req)
            self.fail('PermissionError not raised')
        except PermissionError as e:
            self.assertEqual('FILE_VIEW', e.action)
            self.assertEqual('source', e.resource.realm)
            self.assertEqual('deny-file', e.resource.id)
            self.assertEqual('repository', e.resource.parent.realm)
            self.assertEqual('allow', e.resource.parent.id)

    def test_node_in_denied_repos_with_file_view(self):
        self.grant_perm('anonymous', 'BROWSER_VIEW', 'FILE_VIEW')

        req = MockRequest(self.env, authname='anonymous',
                          path_info='/browser/deny/allow-file')
        rv = self.process_request(req)
        self.assertEqual('deny', rv[1]['repos'].name)
        self.assertEqual('allow-file', rv[1]['path'])

        for path in ('file', 'deny-file'):
            req = MockRequest(self.env, authname='anonymous',
                              path_info='/browser/deny/' + path)
            try:
                self.process_request(req)
                self.fail('PermissionError not raised (path: %r)' % path)
            except PermissionError as e:
                self.assertEqual('FILE_VIEW', e.action)
                self.assertEqual('source', e.resource.realm)
                self.assertEqual(path, e.resource.id)
                self.assertEqual('repository', e.resource.parent.realm)
                self.assertEqual('deny', e.resource.parent.id)

    def test_missing_node_with_browser_view(self):
        self.grant_perm('anonymous', 'BROWSER_VIEW')
        req = MockRequest(self.env, path_info='/browser/allow/missing')
        self.assertRaises(ResourceNotFound, self.process_request, req)
        req = MockRequest(self.env, path_info='/browser/deny/missing')
        self.assertRaises(ResourceNotFound, self.process_request, req)
        req = MockRequest(self.env, path_info='/browser/missing')
        self.assertRaises(ResourceNotFound, self.process_request, req)

    def test_missing_node_without_browser_view(self):
        req = MockRequest(self.env, path_info='/browser/allow/missing')
        self.assertRaises(ResourceNotFound, self.process_request, req)
        req = MockRequest(self.env, path_info='/browser/deny/missing')
        self.assertRaises(ResourceNotFound, self.process_request, req)
        req = MockRequest(self.env, path_info='/browser/missing')
        self.assertRaises(ResourceNotFound, self.process_request, req)

    def test_repository_index_with_hidden_default_repos(self):
        self.grant_perm('anonymous', 'BROWSER_VIEW', 'FILE_VIEW')
        provider = DbRepositoryProvider(self.env)
        provider.modify_repository('(default)', {'hidden': 'enabled'})
        req = MockRequest(self.env, authname='anonymous',
                          path_info='/browser/')
        template, data, content_type = self.process_request(req)
        self.assertEqual(None, data['repos'])
        repo_data = data['repo']  # for repository index
        self.assertEqual('allow', repo_data['repositories'][0][0])
        self.assertEqual('raise', repo_data['repositories'][1][0])
        self.assertEqual(2, len(repo_data['repositories']))

    def test_node_in_hidden_default_repos(self):
        self.grant_perm('anonymous', 'BROWSER_VIEW', 'FILE_VIEW')
        provider = DbRepositoryProvider(self.env)
        provider.modify_repository('(default)', {'hidden': 'enabled'})
        req = MockRequest(self.env, path_info='/browser/blah-blah-file')
        template, data, content_type = self.process_request(req)
        self.assertEqual('', data['reponame'])
        self.assertEqual('blah-blah-file', data['path'])

    def test_no_viewable_repositories_with_browser_view(self):
        self.grant_perm('anonymous', 'BROWSER_VIEW')
        provider = DbRepositoryProvider(self.env)

        provider.remove_repository('allow')
        provider.remove_repository('(default)')
        provider.remove_repository('raise')

        req = MockRequest(self.env, authname='anonymous',
                          path_info='/browser/')
        try:
            self.process_request(req)
            self.fail('ResourceNotFound not raised')
        except ResourceNotFound as e:
            self.assertEqual('No viewable repositories', unicode(e))
        req = MockRequest(self.env, path_info='/browser/allow/')
        try:
            self.process_request(req)
            self.fail('ResourceNotFound not raised')
        except ResourceNotFound as e:
            self.assertEqual('No node allow', unicode(e))
        req = MockRequest(self.env, authname='anonymous',
                          path_info='/browser/deny/')
        try:
            self.process_request(req)
            self.fail('PermissionError not raised')
        except PermissionError as e:
            self.assertEqual('BROWSER_VIEW', e.action)
            self.assertEqual('source', e.resource.realm)
            self.assertEqual('/', e.resource.id)
            self.assertEqual('repository', e.resource.parent.realm)
            self.assertEqual('deny', e.resource.parent.id)

        provider.remove_repository('deny')
        req = MockRequest(self.env, path_info='/browser/')
        try:
            self.process_request(req)
            self.fail('ResourceNotFound not raised')
        except ResourceNotFound as e:
            self.assertEqual('No viewable repositories', unicode(e))
        req = MockRequest(self.env, path_info='/browser/deny/')
        try:
            self.process_request(req)
            self.fail('ResourceNotFound not raised')
        except ResourceNotFound as e:
            self.assertEqual('No node deny', unicode(e))

    def test_no_viewable_repositories_without_browser_view(self):
        provider = DbRepositoryProvider(self.env)
        provider.remove_repository('allow')
        req = MockRequest(self.env, authname='anonymous',
                          path_info='/browser/')
        try:
            self.process_request(req)
            self.fail('PermissionError not raised')
        except PermissionError as e:
            self.assertEqual('BROWSER_VIEW', e.action)
            self.assertEqual(None, e.resource)
        provider.remove_repository('deny')
        provider.remove_repository('(default)')
        req = MockRequest(self.env, authname='anonymous',
                          path_info='/browser/')
        try:
            self.process_request(req)
            self.fail('PermissionError not raised')
        except PermissionError as e:
            self.assertEqual('BROWSER_VIEW', e.action)
            self.assertEqual(None, e.resource)

    def test_zip_archive(self):
        req = MockRequest(self.env, path_info='/browser/trunk',
                          args={'format': 'zip'})
        self.assertRaises(RequestDone, self.process_request, req)

        z = zipfile.ZipFile(req.response_sent, 'r')
        self.assertEqual(['trunk/dir1/', 'trunk/dir1/file.txt',
                          'trunk/dir2/', 'trunk/dir2/file.txt'],
                         sorted(i.filename for i in z.infolist()))

        zi = z.getinfo('trunk/dir1/')
        self.assertEqual((040755 << 16) | 0x10, zi.external_attr)

        zi = z.getinfo('trunk/dir1/file.txt')
        self.assertEqual(0644 << 16, zi.external_attr)
        self.assertEqual('Contents for trunk/dir1/file.txt',
                         z.read('trunk/dir1/file.txt'))
        self.assertEqual((2017, 3, 31, 12, 34, 56), zi.date_time)

        zi = z.getinfo('trunk/dir2/file.txt')
        self.assertEqual(0644 << 16, zi.external_attr)
        self.assertEqual('Contents for trunk/dir2/file.txt',
                         z.read('trunk/dir2/file.txt'))
        self.assertEqual((2017, 3, 31, 12, 34, 56), zi.date_time)

    def test_directory_content_length_in_browser(self):
        req = MockRequest(self.env, path_info='/browser')
        rv = self.process_request(req)
        rendered = Chrome(self.env).render_template(req, *rv)
        self.assertIn('>dir1</', rendered)
        self.assertIn('>dir2</', rendered)
        self.assertNotIn(' title="None bytes"', rendered)


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(BrowserModulePermissionsTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
