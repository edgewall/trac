# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2016 Edgewall Software
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
import shutil
import tempfile
import unittest

from trac.test import EnvironmentStub
from trac.upgrades import db32
from trac.versioncontrol.api import RepositoryManager
from tracopt.versioncontrol.git.git_fs import GitwebProjectsRepositoryProvider

VERSION = 32


class UpgradeTestCase(unittest.TestCase):
    """Selectively move/rename the option:
    [trac] repository_sync_per_request ->
        [repositories] <name>.sync_per_request
    or if the repository is listed in [git] projects_list:
    [trac] repository_sync_per_request ->
        [gitweb-repositories] sync_per_request
    """

    def setUp(self):
        self.env = EnvironmentStub(path=os.path.realpath(tempfile.mkdtemp()))
        self.env.config.filename = os.path.join(self.env.path, 'trac.ini')
        self.env.config.set('trac', 'repository_sync_per_request',
                            'repos2, repos3')

    def tearDown(self):
        self.env.reset_db_and_disk()

    def test_saves_backup(self):
        """Backup file is saved during upgrade."""
        config = self.env.config
        db32.do_upgrade(self.env, VERSION, None)

        self.assertTrue(os.path.exists(config.filename + '.db32.bak'))

    def test_gitweb_values_moved(self):
        """Gitweb configuration is rewritten to the [gitweb-repositories]
        section.
        """
        self.projects_list = os.path.join(self.env.path, 'projects_list')
        self.projects_base = os.path.dirname(self.projects_list)
        self.projects_url = 'http://localhost/%s'
        with open(self.projects_list, 'w') as f:
            f.write("""
            repos1 user1+<user1@example.com>
            repos2
            """)
        self.env.config.set('git', 'projects_list', self.projects_list)
        self.env.config.set('git', 'projects_base', self.projects_base)
        self.env.config.set('git', 'projects_url', self.projects_url)

        db32.do_upgrade(self.env, VERSION, None)

        repos = RepositoryManager(self.env).get_all_repositories()
        self.assertIn('repos1', repos)
        self.assertFalse(repos['repos1']['sync_per_request'])
        self.assertEqual(os.path.join(self.projects_base, 'repos1'),
                         repos['repos1']['dir'])
        self.assertEqual('http://localhost/repos1', repos['repos1']['url'])
        self.assertIn('repos2', repos)
        self.assertTrue(repos['repos2']['sync_per_request'])
        self.assertEqual(os.path.join(self.projects_base, 'repos2'),
                         repos['repos2']['dir'])
        self.assertEqual('http://localhost/repos2', repos['repos2']['url'])
        self.assertEqual('', self.env.config.get('git', 'projects_list'))
        self.assertEqual('', self.env.config.get('git', 'projects_base'))
        self.assertEqual('', self.env.config.get('git', 'projects_url'))
        self.assertEqual('', self.env.config.get('trac', 'repository_sync_per_request'))


def test_suite():
    return unittest.makeSuite(UpgradeTestCase)


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')