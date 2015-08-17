# -*- coding: utf-8 -*-
#
# Copyright (C) 2007-2013 Edgewall Software
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

from trac.core import TracError
from trac.resource import Resource, get_resource_description, get_resource_url
from trac.test import EnvironmentStub
from trac.versioncontrol.api import DbRepositoryProvider, Repository, \
                                    RepositoryManager


class ApiTestCase(unittest.TestCase):

    def setUp(self):
        self.repo_base = Repository('testrepo', {'name': 'testrepo', 'id': 1},
                                    None)

    def test_raise_NotImplementedError_close(self):
        self.assertRaises(NotImplementedError, self.repo_base.close)

    def test_raise_NotImplementedError_get_changeset(self):
        self.assertRaises(NotImplementedError, self.repo_base.get_changeset, 1)

    def test_raise_NotImplementedError_get_node(self):
        self.assertRaises(NotImplementedError, self.repo_base.get_node, 'path')

    def test_raise_NotImplementedError_get_oldest_rev(self):
        self.assertRaises(NotImplementedError, self.repo_base.get_oldest_rev)

    def test_raise_NotImplementedError_get_youngest_rev(self):
        self.assertRaises(NotImplementedError, self.repo_base.get_youngest_rev)

    def test_raise_NotImplementedError_previous_rev(self):
        self.assertRaises(NotImplementedError, self.repo_base.previous_rev, 1)

    def test_raise_NotImplementedError_next_rev(self):
        self.assertRaises(NotImplementedError, self.repo_base.next_rev, 1)

    def test_raise_NotImplementedError_rev_older_than(self):
        self.assertRaises(NotImplementedError, self.repo_base.rev_older_than, 1, 2)

    def test_raise_NotImplementedError_get_path_history(self):
        self.assertRaises(NotImplementedError, self.repo_base.get_path_history, 'path')

    def test_raise_NotImplementedError_normalize_path(self):
        self.assertRaises(NotImplementedError, self.repo_base.normalize_path, 'path')

    def test_raise_NotImplementedError_normalize_rev(self):
        self.assertRaises(NotImplementedError, self.repo_base.normalize_rev, 1)

    def test_raise_NotImplementedError_get_changes(self):
        self.assertRaises(NotImplementedError, self.repo_base.get_changes, 'path', 1, 'path', 2)


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
        except exc, e:
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


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(ApiTestCase))
    suite.addTest(unittest.makeSuite(ResourceManagerTestCase))
    suite.addTest(unittest.makeSuite(DbRepositoryProviderTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
