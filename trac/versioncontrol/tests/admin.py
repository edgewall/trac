# -*- coding: utf-8 -*-
#
# Copyright (C) 2015 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import unittest

from trac.core import Component, implements
from trac.test import EnvironmentStub, MockRequest
from trac.versioncontrol.api import DbRepositoryProvider, IRepositoryConnector
from trac.versioncontrol.admin import RepositoryAdminPanel


class RepositoryAdminPanelTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(enable=('trac.versioncontrol.admin.*',))

    def tearDown(self):
        self.env.reset_db()

    def test_panel_not_exists_when_no_repository_connectors(self):
        """Repositories admin panel is not present when there are
        no repository connectors enabled.
        """
        req = MockRequest(self.env)
        rap = RepositoryAdminPanel(self.env)
        panels = [panel for panel in rap.get_admin_panels(req)]

        self.assertEqual(0, len(panels))

    def test_panel_exists_when_repository_connectors(self):
        """Repositories admin panel is present when there are
        repository connectors enabled.
        """
        class RepositoryConnector(Component):
            implements(IRepositoryConnector)

            def get_supported_types(self):
                yield 'RepositoryConnector', 1

            def get_repository(self, repos_type, repos_dir, params):
                pass

        self.env.enable_component(RepositoryConnector)
        req = MockRequest(self.env)
        rap = RepositoryAdminPanel(self.env)
        panels = [panel for panel in rap.get_admin_panels(req)]

        self.assertEqual(1, len(panels))


class VersionControlAdminTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()

    def tearDown(self):
        self.env.reset_db()

    def test_render_admin_with_alias_to_default_repos(self):
        with self.env.db_transaction as db:
            # Add aliases to non-existent default repository
            db.executemany(
                "INSERT INTO repository (id, name, value) VALUES (%s, %s, %s)",
                [(1, 'name', ''),     (1, 'dir', None), (1, 'alias', ''),
                 (2, 'name', 'blah'), (2, 'dir', None), (2, 'alias', '')])

        panel = RepositoryAdminPanel(self.env)
        req = MockRequest(self.env)
        template, data = panel.render_admin_panel(req, 'versioncontrol',
                                                  'repository', '')
        repositories = data['repositories']
        self.assertNotEqual({}, repositories)
        self.assertEqual('', repositories['']['name'])
        self.assertEqual('', repositories['']['alias'])
        self.assertEqual('blah', repositories['blah']['name'])
        self.assertEqual('', repositories['blah']['alias'])


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(RepositoryAdminPanelTestCase))
    suite.addTest(unittest.makeSuite(VersionControlAdminTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
