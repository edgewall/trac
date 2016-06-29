# -*- coding: utf-8 -*-
#
# Copyright (C) 2016 Edgewall Software
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
from trac.upgrades import db31

VERSION = 31


class UpgradeTestCase(unittest.TestCase):
    """Move definition of default repository from [trac] repository_dir to
    [repositories] section.
    """

    def setUp(self):
        self.env = EnvironmentStub(path=tempfile.mkdtemp())
        self.env.config.filename = os.path.join(self.env.path, 'trac.ini')

    def tearDown(self):
        self.env.reset_db_and_disk()

    def test_saves_backup(self):
        """Backup file is saved during upgrade."""
        config = self.env.config

        db31.do_upgrade(self.env, VERSION, None)

        self.assertTrue(os.path.exists(config.filename + '.db31.bak'))

    def test_repository_dir_option_moved_to_repositories_section(self):
        """[trac] repository_dir is moved to [repositories] section."""
        repository_dir = os.path.join(self.env.path, 'repos1')
        self.env.config.set('trac', 'repository_dir', repository_dir)

        db31.do_upgrade(self.env, VERSION, None)

        repositories_section = self.env.config['repositories']
        self.assertEqual(1, len(list(repositories_section.options())))
        self.assertEqual(repository_dir, repositories_section.get('.dir'))
        self.assertNotIn('repository_dir', self.env.config['trac'])

    def test_repositories_section_not_overwritten(self):
        """Existing [repositories] .dir option is not overwritten."""
        repository_dir = os.path.join(self.env.path, 'repos1')
        repositories_dir = os.path.join(self.env.path, 'repos2')
        self.env.config.set('trac', 'repository_dir', repository_dir)
        self.env.config.set('repositories', '.dir', repositories_dir)

        db31.do_upgrade(self.env, VERSION, None)

        repositories_section = self.env.config['repositories']
        self.assertEqual(1, len(list(repositories_section.options())))
        self.assertEqual(repositories_dir, repositories_section.get('.dir'))
        self.assertNotIn('repository_dir', self.env.config['trac'])

    def test_empty_repository_dir_option_is_removed(self):
        """Empty [trac] repository_dir option is removed from trac.ini"""
        self.env.config.set('trac', 'repository_dir', '')

        db31.do_upgrade(self.env, VERSION, None)

        repositories_section = self.env.config['repositories']
        self.assertEqual(0, len(list(repositories_section.options())))
        self.assertNotIn('repository_dir', self.env.config['trac'])


def test_suite():
    return unittest.makeSuite(UpgradeTestCase)


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
