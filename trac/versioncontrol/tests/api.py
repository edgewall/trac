# -*- coding: utf-8 -*-
#
# Copyright (C) 2007-2018 Edgewall Software
# Copyright (C) 2007 CommProve, Inc. <eli.carter@commprove.com>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.
#
# Author: Eli Carter <eli.carter@commprove.com>

import unittest
from datetime import datetime

from trac.core import TracError
from trac.resource import Resource, get_resource_description, get_resource_url
from trac.test import EnvironmentStub, Mock, MockRequest
from trac.util.datefmt import utc
from trac.versioncontrol.api import Changeset, DbRepositoryProvider, \
                                    EmptyChangeset, Node, Repository, \
                                    RepositoryManager


class ApiTestCase(unittest.TestCase):

    def test_changeset_raises(self):
        """Abstract base class raises a TypeError when instantiated
        directly."""
        self.assertRaises(TypeError, Node)

    def test_node_raises(self):
        """Abstract base class raises a TypeError when instantiated
        directly."""
        self.assertRaises(TypeError, Changeset)

    def test_repository_raises(self):
        """Abstract base class raises a TypeError when instantiated
        directly."""
        self.assertRaises(TypeError, Repository)

    def test_empty_changeset(self):
        repos = Mock()
        changeset = EmptyChangeset(repos, 1)

        self.assertEqual(repos, changeset.repos)
        self.assertEqual(1, changeset.rev)
        self.assertEqual('', changeset.author)
        self.assertEqual('', changeset.message)
        self.assertEqual(datetime(1970, 1, 1, tzinfo=utc), changeset.date)
        self.assertEqual([], list(changeset.get_changes()))

    def test_repository_repr(self):
        repos = Mock(Repository, 'testrepo',
                     {'name': 'testrepo', 'id': 1}, None)
        self.assertEqual("<Mock 1 'testrepo' '/'>", repr(repos))

    def test_node_repr(self):
        repos = Mock(Repository, 'testrepo',
                     {'name': 'testrepo', 'id': 1}, None)
        node1 = Mock(Node, repos, '/trunk', None, Node.DIRECTORY)
        node2 = Mock(Node, repos, '/trunk', 1, Node.DIRECTORY)
        self.assertEqual("<Mock u'testrepo:/trunk'>", repr(node1))
        self.assertEqual("<Mock u'testrepo:/trunk@1'>", repr(node2))

    def test_changeset_repr(self):
        repo = Mock(Repository, 'testrepo',
                    {'name': 'testrepo', 'id': 1}, None)
        changeset = Mock(Changeset, repo, 1, 'Test commit',
                         'user@example.com', None)
        self.assertEqual("<Mock u'testrepo@1'>", repr(changeset))


class ResourceManagerTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)

    def test_resource_changeset(self):
        res = Resource('changeset', '42')
        self.assertEqual('Changeset 42', get_resource_description(self.env, res))
        self.assertEqual('/trac.cgi/changeset/42',
                         get_resource_url(self.env, res, self.env.href))

        repo = Resource('repository', 'repo')
        res = Resource('changeset', '42', parent=repo)
        self.assertEqual('Changeset 42 in repo',
                         get_resource_description(self.env, res))
        self.assertEqual('/trac.cgi/changeset/42/repo',
                         get_resource_url(self.env, res, self.env.href))

    def test_resource_source(self):
        res = Resource('source', '/trunk/src')
        self.assertEqual('path /trunk/src',
                         get_resource_description(self.env, res))
        self.assertEqual('/trac.cgi/browser/trunk/src',
                         get_resource_url(self.env, res, self.env.href))

        repo = Resource('repository', 'repo')
        res = Resource('source', '/trunk/src', parent=repo)
        self.assertEqual('path /trunk/src in repo',
                         get_resource_description(self.env, res))
        self.assertEqual('/trac.cgi/browser/repo/trunk/src',
                         get_resource_url(self.env, res, self.env.href))

        repo = Resource('repository', 'repo')
        res = Resource('source', '/trunk/src', version=42, parent=repo)
        self.assertEqual('path /trunk/src@42 in repo',
                         get_resource_description(self.env, res))
        self.assertEqual('/trac.cgi/browser/repo/trunk/src?rev=42',
                         get_resource_url(self.env, res, self.env.href))


    def test_resource_repository(self):
        res = Resource('repository', 'testrepo')
        self.assertEqual('Repository testrepo',
                         get_resource_description(self.env, res))
        self.assertEqual('/trac.cgi/browser/testrepo',
                         get_resource_url(self.env, res, self.env.href))

        res = Resource('repository', '')  # default repository
        self.assertEqual('Default repository',
                         get_resource_description(self.env, res))
        self.assertEqual('/trac.cgi/browser',
                         get_resource_url(self.env, res, self.env.href))


class DbRepositoryProviderTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.db_provider = DbRepositoryProvider(self.env)

    def tearDown(self):
        self.env.reset_db()

    def verify_raises(self, exc, message, func, *args, **kwargs):
        try:
            func(*args, **kwargs)
            self.fail('%s not raised' % exc.__name__)
        except exc as e:
            self.assertEqual(message, unicode(e))

    def do_remove(self, reponame, message):
        self.verify_raises(TracError, message,
                           self.db_provider.remove_repository, reponame)

    def do_modify(self, reponame, changes, message):
        self.verify_raises(TracError, message,
                           self.db_provider.modify_repository, reponame,
                           changes)

    def do_alias(self, reponame, target, message):
        self.verify_raises(TracError, message, self.db_provider.add_alias,
                           reponame, target)

    def test_add_alias(self):
        self.db_provider.add_repository('', '/path/to/repos')
        self.db_provider.add_repository('target', '/path/to/repos')
        self.db_provider.add_alias('blah1', '')
        self.db_provider.add_alias('blah2', '(default)')
        self.db_provider.add_alias('blah3', 'target')
        repositories = RepositoryManager(self.env).get_all_repositories()
        self.assertEqual(['', 'blah1', 'blah2', 'blah3', 'target'],
                         sorted(repositories))
        self.assertEqual('', repositories['blah1']['alias'])
        self.assertEqual('', repositories['blah2']['alias'])
        self.assertEqual('target', repositories['blah3']['alias'])

    def test_add_alias_to_non_existent_repository(self):
        self.do_alias('', '',
                      'Repository "(default)" doesn\'t exist')
        self.do_alias('', '(default)',
                      'Repository "(default)" doesn\'t exist')
        self.do_alias('blah', '',
                      'Repository "(default)" doesn\'t exist')
        self.do_alias('blah', '(default)',
                      'Repository "(default)" doesn\'t exist')
        self.do_alias('blah', 'blah', 'Repository "blah" doesn\'t exist')
        self.do_alias('', 'blah', 'Repository "blah" doesn\'t exist')
        self.do_alias('(default)', 'blah', 'Repository "blah" doesn\'t exist')

    def test_add_alias_to_repository_in_tracini(self):
        config = self.env.config
        config.set('repositories', '.dir', '/path/to/repos')
        config.set('repositories', '.type', '')
        config.set('repositories', 'target.dir', '/path/to/repos')
        config.set('repositories', 'target.type', '')
        config.set('repositories', 'alias-default.alias', '')
        config.set('repositories', 'alias-target.alias', 'target')
        self.db_provider.add_alias('blah1', '')
        self.db_provider.add_alias('blah2', 'target')
        self.assertRaises(TracError, self.db_provider.add_alias, 'blah3',
                          'notfound')
        repositories = RepositoryManager(self.env).get_all_repositories()
        self.assertEqual(['', 'alias-default', 'alias-target', 'blah1',
                          'blah2', 'target'], sorted(repositories))
        self.assertEqual('', repositories['blah1']['alias'])
        self.assertEqual('target', repositories['blah2']['alias'])

    def test_add_alias_to_alias(self):
        config = self.env.config
        config.set('repositories', 'target.dir', '/path/to/repos')
        config.set('repositories', 'target.type', '')
        config.set('repositories', '.alias', 'target')
        config.set('repositories', 'alias.alias', 'target')
        self.do_alias('blah', '',
                      'Cannot create an alias to the alias "(default)"')
        self.do_alias('blah', '(default)',
                      'Cannot create an alias to the alias "(default)"')
        self.do_alias('blah', 'alias',
                      'Cannot create an alias to the alias "alias"')

    def test_remove_repository_used_in_aliases(self):
        self.db_provider.add_repository('', '/path/to/repos')
        self.db_provider.add_repository('blah', '/path/to/repos')
        self.db_provider.add_alias('alias-blah', 'blah')
        self.db_provider.add_alias('alias-default', '')
        self.do_remove('', 'Cannot remove the repository "(default)" used in '
                           'aliases')
        self.do_remove('(default)', 'Cannot remove the repository "(default)" '
                                    'used in aliases')
        self.do_remove('blah', 'Cannot remove the repository "blah" used in '
                               'aliases')

    def test_modify_repository_used_in_aliases(self):
        self.db_provider.add_repository('', '/path/to/repos')
        self.db_provider.add_repository('blah', '/path/to/repos')
        self.db_provider.add_alias('alias-blah', 'blah')
        self.db_provider.add_alias('alias-default', '')
        self.do_modify('', {'name': 'new-name'},
                       'Cannot rename the repository "(default)" used in '
                       'aliases')
        self.do_modify('(default)', {'name': 'new-name'},
                       'Cannot rename the repository "(default)" used in '
                       'aliases')
        self.do_modify('blah', {'name': 'new-name'},
                       'Cannot rename the repository "blah" used in aliases')
        self.db_provider.modify_repository('', {'dir': '/path/to/new-path'})


class RepositoryManagerTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()

    def test_pre_process_request_sync_skipped_for_invalid_connector(self):
        """Repository synchronization is skipped for an invalid connector."""
        self.env.config.set('repositories', 'repos.dir', '/some/path')
        self.env.config.set('repositories', 'repos.type', 'invalid')
        self.env.config.set('repositories', 'repos.sync_per_request', True)
        req = MockRequest(self.env)
        handler = Mock()
        repos_manager = RepositoryManager(self.env)

        repos_manager.pre_process_request(req, handler)

        self.assertNotIn('invalid', repos_manager.get_supported_types())
        self.assertEqual([], req.chrome['warnings'])


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(ApiTestCase))
    suite.addTest(unittest.makeSuite(ResourceManagerTestCase))
    suite.addTest(unittest.makeSuite(DbRepositoryProviderTestCase))
    suite.addTest(unittest.makeSuite(RepositoryManagerTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
