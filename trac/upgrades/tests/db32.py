# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2018 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

import os
import tempfile
import unittest

from trac.test import EnvironmentStub
from trac.upgrades import db32
from trac.versioncontrol.api import DbRepositoryProvider, RepositoryManager
from tracopt.versioncontrol.git.git_fs import GitwebProjectsRepositoryProvider

VERSION = 32


class UpgradeTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(path=os.path.realpath(tempfile.mkdtemp()))
        self.env.config.filename = os.path.join(self.env.path, 'trac.ini')
        self.env.config.set('trac', 'repository_sync_per_request',
                            'repos1, repos3, repos5')

    def tearDown(self):
        self.env.reset_db_and_disk()

    def test_saves_backup(self):
        """Backup file is saved during upgrade."""
        config = self.env.config
        db32.do_upgrade(self.env, VERSION, None)

        self.assertTrue(os.path.exists(config.filename + '.db32.bak'))

    def test_repository_sync_per_request_default_value(self):
        """The default repository sync_per_request attribute is set to true
        when repository_sync_per_request is not set in trac.ini.
        """
        self.env.config.remove('trac', 'repository_sync_per_request')
        repositories = self.env.config['repositories']
        repositories.set('.dir', '/var/svn')
        repositories.set('.type', 'svn')
        repositories.set('git.dir', '/var/git')
        repositories.set('git.type', 'git')

        db32.do_upgrade(self.env, VERSION, None)

        repositories = self.env.config['repositories']
        self.assertIn('.sync_per_request', repositories)
        self.assertTrue(repositories.getbool('.sync_per_request'))
        self.assertNotIn('git.sync_per_request', repositories)
        self.assertFalse(repositories.getbool('git.sync_per_request'))

    def test_repository_sync_per_request_default_value_with_db(self):
        """The default repository sync_per_request attribute is set to
        true when repository_sync_per_request is not set in trac.ini.
        """
        self.env.config.remove('trac', 'repository_sync_per_request')
        # directly insert repository records instead of DbRepositoryProvider
        # to avoid a TracError "The repository type 'svn' is not supported"
        with self.env.db_transaction as db:
            db.executemany("""INSERT INTO repository (id,name,value)
                              VALUES (%s,%s,%s)""",
                           [(1, 'name', ''),
                            (1, 'dir', '/var/svn'),
                            (1, 'type', 'svn'),
                            (2, 'name', 'git'),
                            (2, 'dir', '/var/git'),
                            (2, 'type', 'git')])

        db32.do_upgrade(self.env, VERSION, None)

        repos = RepositoryManager(self.env).get_all_repositories()
        self.assertIn('', repos)
        self.assertTrue(repos['']['sync_per_request'])
        self.assertEqual('1', self.env.db_query("""
            SELECT value FROM repository
            WHERE id=1 AND name='sync_per_request'""")[0][0])
        self.assertIn('git', repos)
        self.assertFalse(repos['git']['sync_per_request'])
        self.assertIsNone(self.env.db_query("""
            SELECT value FROM repository
            WHERE id=2 AND name='sync_per_request'""")[0][0])

    def test_gitweb_configuration_moved(self):
        """The Gitweb configuration is moved from the [git] section to
        the [gitweb-repositories] section.
        """
        projects_list = os.path.join(self.env.path, 'projects_list')
        projects_base = os.path.dirname(projects_list)
        projects_url = 'http://localhost/%s'
        with open(projects_list, 'w') as f:
            f.write("""
            repos1 user1+<user1@example.com>
            repos2
            """)
        config = self.env.config['git']
        config.set('projects_list', projects_list)
        config.set('projects_base', projects_base)
        config.set('projects_url', projects_url)
        repos1_dir = os.path.join(projects_base, 'repos1')
        repos2_dir = os.path.join(projects_base, 'repos2')

        db32.do_upgrade(self.env, VERSION, None)

        repos = RepositoryManager(self.env).get_all_repositories()
        self.assertIn('repos1', repos)
        self.assertTrue(repos['repos1']['sync_per_request'])
        self.assertEqual(repos1_dir, repos['repos1']['dir'])
        self.assertEqual('http://localhost/repos1', repos['repos1']['url'])
        self.assertIn('repos2', repos)
        self.assertFalse(repos['repos2']['sync_per_request'])
        self.assertEqual(repos2_dir, repos['repos2']['dir'])
        self.assertEqual('http://localhost/repos2', repos['repos2']['url'])
        config = self.env.config['gitweb-repositories']
        self.assertNotIn('projects_list', self.env.config)
        self.assertNotIn('projects_base', self.env.config)
        self.assertNotIn('projects_url', self.env.config)
        self.assertNotIn('repository_sync_per_request', self.env.config)
        self.assertEqual(projects_list, config.get('projects_list'))
        self.assertEqual(projects_base, config.get('projects_base'))
        self.assertEqual(projects_url, config.get('projects_url'))
        self.assertEqual('repos1', config.get('sync_per_request'))

    def test_repository_providers_disabled(self):
        """Repository configuration is rewritten when repository providers
        are disabled.
        """
        projects_list = os.path.join(self.env.path, 'projects_list')
        projects_base = os.path.dirname(projects_list)
        projects_url = 'http://localhost/%s'
        with open(projects_list, 'w') as f:
            f.write("""
            repos1 user1+<user1@example.com>
            repos2
            """)
        config = self.env.config['git']
        config.set('projects_list', projects_list)
        config.set('projects_base', projects_base)
        config.set('projects_url', projects_url)
        db_provider = DbRepositoryProvider(self.env)
        db_provider.add_repository('repos3', '/var/git/repos3', 'git')
        db_provider.add_repository('repos4', '/var/git/repos4', 'git')
        config = self.env.config['repositories']
        config.set('repos5.dir', '/var/svn/repos4')
        config.set('repos5.type', 'svn')
        config.set('repos6.dir', '/var/svn/repos5')
        config.set('repos6.type', 'svn')
        self.env.disable_component(GitwebProjectsRepositoryProvider)
        self.env.disable_component(DbRepositoryProvider)
        self.env.disable_component(RepositoryManager)

        db32.do_upgrade(self.env, VERSION, None)

        self.env.enable_component(GitwebProjectsRepositoryProvider)
        self.env.enable_component(DbRepositoryProvider)
        self.env.enable_component(RepositoryManager)
        repos = RepositoryManager(self.env).get_all_repositories()
        config = self.env.config['gitweb-repositories']
        self.assertEqual(projects_list, config.get('projects_list'))
        self.assertEqual(projects_base, config.get('projects_base'))
        self.assertEqual(projects_url, config.get('projects_url'))
        self.assertEqual('repos1', config.get('sync_per_request'))
        self.assertIn('repos1', repos)
        self.assertTrue(repos['repos1']['sync_per_request'])
        self.assertIn('repos2', repos)
        self.assertFalse(repos['repos2']['sync_per_request'])
        self.assertIn('repos3', repos)
        self.assertTrue(repos['repos3']['sync_per_request'])
        self.assertIn('repos4', repos)
        self.assertFalse(repos['repos4']['sync_per_request'])
        self.assertIn('repos5', repos)
        self.assertTrue(repos['repos5']['sync_per_request'])
        self.assertIn('repos6', repos)
        self.assertFalse(repos['repos6']['sync_per_request'])


def test_suite():
    return unittest.makeSuite(UpgradeTestCase)


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
