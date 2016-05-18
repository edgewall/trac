# -*- coding: utf-8 -*-
#
# Copyright (C) 2014-2015 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

from datetime import datetime, timedelta
import unittest

from trac.core import Component, TracError, implements
from trac.perm import IPermissionPolicy
from trac.resource import Resource
from trac.test import MockRequest
from trac.util.datefmt import utc
from trac.versioncontrol.api import (
    Changeset, DbRepositoryProvider, IRepositoryConnector, Node,
    NoSuchChangeset, Repository)
from trac.versioncontrol.web_ui.log import LogModule
from trac.web.api import parse_arg_list
from trac.web.chrome import web_context
from trac.web.tests.api import RequestHandlerPermissionsTestCaseBase
from trac.wiki.formatter import format_to_oneliner


mock_repotype = 'mock:' + __name__


class MockRepositoryConnector(Component):

    implements(IRepositoryConnector)

    def get_supported_types(self):
        yield mock_repotype, 8

    def get_repository(self, repos_type, repos_dir, params):
        return MockRepository('mock:' + repos_dir, params, self.log)


class TestLogModulePermissionPolicy(Component):

    implements(IPermissionPolicy)

    def check_permission(self, action, username, resource, perm):
        if action == 'LOG_VIEW' and resource.realm == 'repository':
            return username != 'anonymous'


class MockRepository(Repository):

    has_linear_changesets = True

    def get_youngest_rev(self):
        return 100

    def normalize_path(self, path):
        return path.strip('/') if path else ''

    def normalize_rev(self, rev):
        if rev is None or rev == '':
            return self.youngest_rev
        try:
            nrev = int(rev)
        except:
            raise NoSuchChangeset(rev)
        else:
            if not (1 <= nrev <= self.youngest_rev) or nrev % 3 != 1:
                raise NoSuchChangeset(rev)
            return nrev

    def get_node(self, path, rev):
        assert rev % 3 == 1  # allow only 3n + 1
        assert path in ('file', 'file-old')
        return MockNode(self, path, rev, Node.FILE)

    def get_changeset(self, rev):
        assert rev % 3 == 1  # allow only 3n + 1
        return MockChangeset(self, rev, 'message-%d' % rev, 'author-%d' % rev,
                             datetime(2001, 1, 1, tzinfo=utc) +
                             timedelta(seconds=rev))

    def previous_rev(self, rev, path=''):
        assert rev % 3 == 1  # allow only 3n + 1
        return rev - 3 if rev > 0 else None

    def get_path_history(self, path, rev=None, limit=None):
        histories = [(path,         100, Changeset.DELETE),
                     (path,          40, Changeset.MOVE),
                     (path + '-old',  1, Changeset.ADD)]
        for history in histories:
            if limit is not None and limit <= 0:
                break
            if rev is None or rev >= history[1]:
                yield history
                if limit is not None:
                    limit -= 1

    def rev_older_than(self, rev1, rev2):
        return self.normalize_rev(rev1) < self.normalize_rev(rev2)

    def close(self):
        pass

    def _not_implemented(self, *args, **kwargs):
        raise NotImplementedError

    get_changes = _not_implemented
    get_oldest_rev = _not_implemented
    next_rev = _not_implemented


class MockChangeset(Changeset):

    def get_changes(self):
        raise StopIteration


class MockNode(Node):

    def __init__(self, repos, path, rev, kind):
        super(MockNode, self).__init__(repos, path, rev, kind)
        self.created_path = path
        self.created_rev = rev

    def get_history(self, limit=None):
        youngest_rev = self.repos.youngest_rev
        rev = self.rev
        path = self.path
        while rev > 0:
            if limit is not None:
                if limit <= 0:
                    return
                limit -= 1
            if rev == 1:
                change = Changeset.ADD
            elif rev == 40:
                change = Changeset.MOVE
            elif rev == youngest_rev:
                change = Changeset.DELETE
            else:
                change = Changeset.EDIT
            yield path, rev, change
            if rev == 40:
                path += '-old'
            rev -= 3

    def _not_implemented(self, *args, **kwargs):
        raise NotImplementedError

    get_annotations = _not_implemented
    get_content = _not_implemented
    get_content_length = _not_implemented
    get_content_type = _not_implemented
    get_entries = _not_implemented
    get_last_modified = _not_implemented
    get_properties = _not_implemented


class LogModuleTestCase(RequestHandlerPermissionsTestCaseBase):

    def setUp(self):
        self._super = super(LogModuleTestCase, self)
        self._super.setUp(LogModule)
        provider = DbRepositoryProvider(self.env)
        provider.add_repository('mock', '/', mock_repotype)

    def test_default_repository_not_configured(self):
        """Test for regression of http://trac.edgewall.org/ticket/11599."""
        req = MockRequest(self.env, path_info='/log/', args={'new_path': '/'})
        self.assertRaises(TracError, self.process_request, req)

    def test_without_rev(self):
        req = MockRequest(self.env, path_info='/log/mock/file',
                          args={'limit': '4'})
        template, data, ctype = self.process_request(req)
        self.assertEqual('revisionlog.html', template)
        items = data['items']
        self.assertEqual(5, len(items))
        self.assertEqual([100, 97, 94, 91, 88],
                         [item['rev'] for item in items])
        self.assertEqual(['delete'] + ['edit'] * 3 + [None],
                         [item['change'] for item in items])
        links = req.chrome['links']['next']
        self.assertEqual('/trac.cgi/log/mock/file?limit=4&rev=88&'
                         'mode=stop_on_copy', links[0]['href'])
        self.assertEqual(1, len(links))

    def test_with_rev(self):
        req = MockRequest(self.env, path_info='/log/mock/file',
                          args={'rev': '49'})
        template, data, ctype = self.process_request(req)
        items = data['items']
        self.assertEqual(5, len(items))
        self.assertEqual([49, 46, 43, 40, 37],
                         [item['rev'] for item in items])
        self.assertEqual(['file'] * 4 + ['file-old'],
                         [item['path'] for item in items])
        self.assertEqual(['edit'] * 3 + ['move', 'edit'],
                         [item['change'] for item in items])
        self.assertNotIn('next', req.chrome['links'])

    def test_with_rev_and_limit(self):
        req = MockRequest(self.env, path_info='/log/mock/file',
                          args={'rev': '49', 'limit': '4'})
        template, data, ctype = self.process_request(req)
        items = data['items']
        self.assertEqual(5, len(items))
        self.assertEqual([49, 46, 43, 40, 37],
                         [item['rev'] for item in items])
        self.assertEqual(['file'] * 4 + ['file-old'],
                         [item['path'] for item in items])
        self.assertEqual([1] * 4 + [2], [item['depth'] for item in items])
        self.assertEqual([None] * 4 + ['file-old'],
                         [item.get('copyfrom_path') for item in items])
        self.assertEqual(['edit'] * 3 + ['move', None],
                         [item['change'] for item in items])
        links = req.chrome['links']['next']
        self.assertEqual('/trac.cgi/log/mock/file-old?limit=4&rev=37&'
                         'mode=stop_on_copy', links[0]['href'])
        self.assertEqual(1, len(links))

    def test_with_rev_on_start(self):
        req = MockRequest(self.env, path_info='/log/mock/file-old',
                          args={'rev': '10'})
        template, data, ctype = self.process_request(req)
        items = data['items']
        self.assertEqual(4, len(items))
        self.assertEqual([10, 7, 4, 1],
                         [item['rev'] for item in items])
        self.assertEqual(['file-old'] * 4, [item['path'] for item in items])
        self.assertEqual([1] * 4, [item['depth'] for item in items])
        self.assertEqual([None] * 4,
                         [item.get('copyfrom_path') for item in items])
        self.assertEqual(['edit'] * 3 + ['add'],
                         [item['change'] for item in items])
        self.assertNotIn('next', req.chrome['links'])

    def test_with_rev_and_limit_on_start(self):
        req = MockRequest(self.env, path_info='/log/mock/file-old',
                          args={'rev': '10', 'limit': '4'})
        template, data, ctype = self.process_request(req)
        items = data['items']
        self.assertEqual(4, len(items))
        self.assertEqual([10, 7, 4, 1],
                         [item['rev'] for item in items])
        self.assertEqual(['file-old'] * 4, [item['path'] for item in items])
        self.assertEqual([1] * 4, [item['depth'] for item in items])
        self.assertEqual([None] * 4,
                         [item.get('copyfrom_path') for item in items])
        self.assertEqual(['edit'] * 3 + ['add'],
                         [item['change'] for item in items])
        self.assertNotIn('next', req.chrome['links'])

    def test_with_invalid_rev(self):
        def fn(message, **kwargs):
            req = MockRequest(self.env, path_info='/log/mock/file', **kwargs)
            try:
                self.process_request(req)
            except NoSuchChangeset as e:
                self.assertEqual(message, unicode(e))

        fn('No changeset 101 in the repository', args={'rev': '101'})
        fn('No changeset 0 in the repository', args={'rev': '0'})
        fn('No changeset 43-46 in the repository', args={'rev': '43-46'})

    def test_revranges_1(self):
        req = MockRequest(self.env, path_info='/log/mock/file',
                          args={'revs': '70,79-82,94-100'})
        template, data, ctype = self.process_request(req)
        items = data['items']
        self.assertEqual(9, len(items))
        self.assertEqual([100, 97, 94, 91, 82, 79, 76, 70, 67],
                         [item['rev'] for item in items])
        self.assertEqual(['file'] * 9,
                         [item['path'] for item in items])
        self.assertEqual([1] * 9, [item['depth'] for item in items])
        self.assertEqual([None] * 9,
                         [item.get('copyfrom_path') for item in items])
        self.assertEqual(['delete', 'edit', 'edit', None, 'edit', 'edit', None,
                          'edit', None],
                         [item['change'] for item in items])
        self.assertNotIn('next', req.chrome['links'])

    def test_revranges_2(self):
        req = MockRequest(self.env, path_info='/log/mock/file',
                          args={'revs': '22-49'})
        template, data, ctype = self.process_request(req)
        items = data['items']
        self.assertEqual(5, len(items))
        self.assertEqual([49, 46, 43, 40, 37],
                         [item['rev'] for item in items])
        self.assertEqual(['file'] * 4 + ['file-old'],
                         [item['path'] for item in items])
        self.assertEqual([1] * 4 + [2], [item['depth'] for item in items])
        self.assertEqual([None] * 4 + ['file-old'],
                         [item.get('copyfrom_path') for item in items])
        self.assertEqual(['edit'] * 3 + ['move', 'edit'],
                         [item['change'] for item in items])
        self.assertNotIn('next', req.chrome['links'])

    def test_revranges_3(self):
        req = MockRequest(self.env, path_info='/log/mock/file',
                          args={'revs': '22-46,55-61'})
        template, data, ctype = self.process_request(req)
        items = data['items']
        self.assertEqual(8, len(items))
        self.assertEqual([61, 58, 55, 52, 46, 43, 40, 37],
                         [item['rev'] for item in items])
        self.assertEqual(['file'] * 7 + ['file-old'],
                         [item['path'] for item in items])
        self.assertEqual([1] * 7 + [2], [item['depth'] for item in items])
        self.assertEqual([None] * 7 + ['file-old'],
                         [item.get('copyfrom_path') for item in items])
        self.assertEqual(['edit', 'edit', 'edit', None,
                          'edit', 'edit', 'move', 'edit'],
                         [item['change'] for item in items])
        self.assertNotIn('next', req.chrome['links'])

    def test_revranges_4(self):
        req = MockRequest(self.env, path_info='/log/mock/file',
                          args={'revs': '40-46,55-61'})
        template, data, ctype = self.process_request(req)
        items = data['items']
        self.assertEqual(8, len(items))
        self.assertEqual([61, 58, 55, 52, 46, 43, 40, 37],
                         [item['rev'] for item in items])
        self.assertEqual(['file'] * 7 + ['file-old'],
                         [item['path'] for item in items])
        self.assertEqual([1] * 7 + [2], [item['depth'] for item in items])
        self.assertEqual([None] * 7 + ['file-old'],
                         [item.get('copyfrom_path') for item in items])
        self.assertEqual(['edit', 'edit', 'edit', None,
                          'edit', 'edit', 'move', None],
                         [item['change'] for item in items])
        self.assertNotIn('next', req.chrome['links'])

    def test_revranges_1_with_limit(self):
        req = MockRequest(self.env, path_info='/log/mock/file',
                          args={'revs': '70,79-82,94-100', 'limit': '4'})
        template, data, ctype = self.process_request(req)
        items = data['items']
        self.assertEqual(6, len(items))
        self.assertEqual([100, 97, 94, 91, 82, 79],
                         [item['rev'] for item in items])
        self.assertEqual(['file'] * 6,
                         [item['path'] for item in items])
        self.assertEqual([1] * 6, [item['depth'] for item in items])
        self.assertEqual([None] * 6,
                         [item.get('copyfrom_path') for item in items])
        self.assertEqual(['delete', 'edit', 'edit', None, 'edit', None],
                         [item['change'] for item in items])
        self.assertIn('next', req.chrome['links'])
        links = req.chrome['links']['next']
        self.assertEqual('/trac.cgi/log/mock/file?limit=4&revs=70%2C79&'
                         'rev=79&mode=stop_on_copy', links[0]['href'])
        self.assertEqual(1, len(links))

    def test_revranges_1_next_link_with_limits(self):
        def next_link_args(limit):
            req = MockRequest(self.env, path_info='/log/mock/file',
                              args={'revs': '70,79-82,94-100',
                                    'limit': str(limit)})
            template, data, ctype = self.process_request(req)
            links = req.chrome['links']
            if 'next' in links:
                link = links['next'][0]['href']
                path_info, query_string = link.split('?', 1)
                return dict(parse_arg_list(query_string))
            else:
                return None

        self.assertEqual({'limit': '1', 'rev': '97', 'revs': '70,79-82,94-97',
                          'mode': 'stop_on_copy'}, next_link_args(1))
        self.assertEqual({'limit': '2', 'rev': '94', 'revs': '70,79-82,94',
                          'mode': 'stop_on_copy'}, next_link_args(2))
        self.assertEqual({'limit': '3', 'rev': '91', 'revs': '70,79-82',
                          'mode': 'stop_on_copy'}, next_link_args(3))
        self.assertEqual({'limit': '4', 'rev': '79', 'revs': '70,79',
                          'mode': 'stop_on_copy'}, next_link_args(4))
        self.assertEqual({'limit': '5', 'rev': '76', 'revs': '70',
                          'mode': 'stop_on_copy'}, next_link_args(5))
        self.assertEqual(None, next_link_args(6))

    def test_revranges_2_with_limit(self):
        req = MockRequest(self.env, path_info='/log/mock/file',
                          args={'revs': '22-49', 'limit': '4'})
        template, data, ctype = self.process_request(req)
        items = data['items']
        self.assertEqual(5, len(items))
        self.assertEqual([49, 46, 43, 40, 37],
                         [item['rev'] for item in items])
        self.assertEqual(['file'] * 4 + ['file-old'],
                         [item['path'] for item in items])
        self.assertEqual([1] * 4 + [2], [item['depth'] for item in items])
        self.assertEqual([None] * 4 + ['file-old'],
                         [item.get('copyfrom_path') for item in items])
        self.assertEqual(['edit'] * 3 + ['move', None],
                         [item['change'] for item in items])
        self.assertIn('next', req.chrome['links'])
        links = req.chrome['links']['next']
        self.assertEqual('/trac.cgi/log/mock/file-old?limit=4&revs=22-37&'
                         'rev=37&mode=stop_on_copy', links[0]['href'])
        self.assertEqual(1, len(links))

    def test_revranges_3_with_limit(self):
        req = MockRequest(self.env, path_info='/log/mock/file',
                          args={'revs': '22-46,55-61', 'limit': '7'})
        template, data, ctype = self.process_request(req)
        items = data['items']
        self.assertEqual(8, len(items))
        self.assertEqual([61, 58, 55, 52, 46, 43, 40, 37],
                         [item['rev'] for item in items])
        self.assertEqual(['file'] * 7 + ['file-old'],
                         [item['path'] for item in items])
        self.assertEqual([1] * 7 + [2], [item['depth'] for item in items])
        self.assertEqual([None] * 7 + ['file-old'],
                         [item.get('copyfrom_path') for item in items])
        self.assertEqual(['edit', 'edit', 'edit', None,
                          'edit', 'edit', 'move', 'edit'],
                         [item['change'] for item in items])
        self.assertNotIn('next', req.chrome['links'])

    def test_revranges_4_with_limit(self):
        req = MockRequest(self.env, path_info='/log/mock/file',
                          args={'revs': '40-46,55-61', 'limit': '7'})
        template, data, ctype = self.process_request(req)
        items = data['items']
        self.assertEqual(8, len(items))
        self.assertEqual([61, 58, 55, 52, 46, 43, 40, 37],
                         [item['rev'] for item in items])
        self.assertEqual(['file'] * 7 + ['file-old'],
                         [item['path'] for item in items])
        self.assertEqual([1] * 7 + [2], [item['depth'] for item in items])
        self.assertEqual([None] * 7 + ['file-old'],
                         [item.get('copyfrom_path') for item in items])
        self.assertEqual(['edit', 'edit', 'edit', None,
                          'edit', 'edit', 'move', None],
                         [item['change'] for item in items])
        self.assertNotIn('next', req.chrome['links'])

    def test_invalid_revranges(self):
        def fn(message, **kwargs):
            req = MockRequest(self.env, path_info='/log/mock/file', **kwargs)
            try:
                self.process_request(req)
            except NoSuchChangeset as e:
                self.assertEqual(message, unicode(e))

        fn('No changeset 101 in the repository', args={'revs': '101'})
        fn('No changeset 0 in the repository', args={'revs': '0'})
        fn('No changeset 0 in the repository', args={'revs': '0-43'})
        fn('No changeset 101 in the repository', args={'revs': '43-101'})
        fn('No changeset 43-46-49 in the repository',
           args={'revs': '43-46-49'})
        fn('No changeset 50 in the repository',
           args={'revs': '43-46,50,52-55'})

    def test_follow_copy(self):
        req = MockRequest(self.env, path_info='/log/mock/file',
                          args={'rev': '43', 'limit': '4',
                                'mode': 'follow_copy'})
        template, data, ctype = self.process_request(req)
        items = data['items']
        self.assertEqual(5, len(items))
        self.assertEqual([43, 40, 37, 34, 31],
                         [item['rev'] for item in items])
        self.assertEqual(['file', 'file', 'file-old', 'file-old', 'file-old'],
                         [item['path'] for item in items])
        self.assertEqual([1, 1, 2, 2, 2], [item['depth'] for item in items])
        self.assertEqual([None, None, 'file-old', None, None],
                         [item.get('copyfrom_path') for item in items])
        self.assertEqual(['edit', 'move', 'edit', 'edit', None],
                         [item['change'] for item in items])
        links = req.chrome['links']['next']
        self.assertEqual('/trac.cgi/log/mock/file-old?limit=4&rev=31&'
                         'mode=follow_copy', links[0]['href'])
        self.assertEqual(1, len(links))

    def test_path_history(self):
        req = MockRequest(self.env, path_info='/log/mock/file',
                          args={'mode': 'path_history'})
        template, data, ctype = self.process_request(req)
        items = data['items']
        self.assertEqual(3, len(items))
        self.assertEqual(['delete', 'move', 'add'],
                         [item['change'] for item in items])
        self.assertNotIn('next', req.chrome['links'])

    def test_log_link_checking_repository_resource(self):
        self.env.config.set('trac', 'permission_policies',
            'TestLogModulePermissionPolicy, DefaultPermissionPolicy')
        resource = Resource('wiki', 'WikiStart')

        req = MockRequest(self.env, authname='anonymous')
        rendered = unicode(format_to_oneliner(self.env,
                                              web_context(req, resource),
                                              'log:mock@42-43'))
        self.assertIn(' title="No permission to view change log"', rendered)

        req = MockRequest(self.env, authname='blah')
        rendered = unicode(format_to_oneliner(self.env,
                                              web_context(req, resource),
                                              'log:mock@42-43'))
        self.assertIn(' href="/trac.cgi/log/mock/?revs=42-43"', rendered)


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(LogModuleTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
