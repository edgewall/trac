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

import trac.tests.compat
from trac.admin.web_ui import PluginAdminPanel
from trac.core import Component
from trac.test import EnvironmentStub, Mock, MockPerm, locale_en
from trac.util.datefmt import utc


class PluginAdminPanelTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.req = Mock(args={}, chrome={'notices': []}, href=self.env.href,
                        lc_time=locale_en, method=None, perm=MockPerm(),
                        session={}, tz=utc)

    def tearDown(self):
        self.env.reset_db()

    def test_abstract_component_not_visible(self):
        class AbstractComponent(Component):
            abstract = True
        class NotAbstractComponent(Component):
            abstract = False

        panel = PluginAdminPanel(self.env)
        data = panel.render_admin_panel(self.req, 'general', 'plugin', None)[1]

        module = self.__class__.__module__
        components = []
        for plugin in data['plugins']:
            if module in plugin['modules'].keys():
                components = plugin['modules'][module]['components'].keys()
        self.assertNotIn('AbstractComponent', components)
        self.assertIn('NotAbstractComponent', components)


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(PluginAdminPanelTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
