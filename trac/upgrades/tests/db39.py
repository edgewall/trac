# -*- coding: utf-8 -*-
#
# Copyright (C) 2015 Edgewall Software
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
from trac.upgrades import db39
from trac.versioncontrol.api import RepositoryManager
from trac.versioncontrol.svn_authz import AuthzSourcePolicy

VERSION = 39


class UpgradeTestCase(unittest.TestCase):
    """Move/rename the following options:
    [trac] authz_file -> [svn] authz_file
    [trac] authz_module_name -> [svn] authz_module_name
    [trac] repository_type -> [versioncontrol] default_repository_type
    """

    def setUp(self):
        self.env = EnvironmentStub(path=tempfile.mkdtemp())
        self.env.config.filename = os.path.join(self.env.path, 'trac.ini')
        AuthzSourcePolicy(self.env)
        RepositoryManager(self.env)

    def tearDown(self):
        self.env.reset_db_and_disk()

    def test_saves_backup(self):
        """Backup file is saved during upgrade."""
        config = self.env.config
        db39.do_upgrade(self.env, VERSION, None)

        self.assertTrue(os.path.exists(config.filename + '.db39.bak'))

    def test_old_options_not_in_registry(self):
        """Old options are not contained in the option registry."""
        config = self.env.config
        self.assertFalse(config.has_option('trac', 'authz_file'))
        self.assertFalse(config.has_option('trac', 'authz_module_name'))
        self.assertFalse(config.has_option('trac', 'repository_type'))

    def test_new_options_in_registry(self):
        """New options are contained in the option registry."""
        config = self.env.config
        self.assertTrue(config.has_option('svn', 'authz_file'))
        self.assertTrue(config.has_option('svn', 'authz_module_name'))
        self.assertTrue(config.has_option('versioncontrol',
                                          'default_repository_type'))

    def test_tracini_values_moved(self):
        """Values are moved in trac.ini file."""
        config = self.env.config
        config.set('trac', 'authz_file', 'authz.ini')
        config.set('trac', 'authz_module_name', 'amodule')
        config.set('trac', 'repository_type', 'git')
        config.save()
        db39.do_upgrade(self.env, VERSION, None)

        self.assertFalse(config.has_option('trac', 'authz_file'))
        self.assertFalse(config.has_option('trac', 'authz_module_name'))
        self.assertFalse(config.has_option('trac', 'repository_type'))
        self.assertEqual('authz.ini', config.get('svn', 'authz_file'))
        self.assertEqual('amodule', config.get('svn', 'authz_module_name'))
        self.assertEqual('git', config.get('versioncontrol',
                                           'default_repository_type'))

    def test_default_values_written_to_tracini(self):
        """Default values are written to trac.ini file."""
        config = self.env.config
        db39.do_upgrade(self.env, VERSION, None)

        self.assertFalse(config.has_option('trac', 'authz_file'))
        self.assertFalse(config.has_option('trac', 'authz_module_name'))
        self.assertFalse(config.has_option('trac', 'repository_type'))
        self.assertEqual('', config.get('svn', 'authz_file'))
        self.assertEqual('', config.get('svn', 'authz_module_name'))
        self.assertEqual('svn', config.get('versioncontrol',
                                           'default_repository_type'))


def test_suite():
    return unittest.makeSuite(UpgradeTestCase)


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
