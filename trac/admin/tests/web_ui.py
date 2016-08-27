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

from trac.admin.web_ui import PermissionAdminPanel, PluginAdminPanel
from trac.core import Component
from trac.perm import PermissionSystem
from trac.test import EnvironmentStub, MockRequest


class PermissionAdminPanelTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        self.panel = PermissionAdminPanel(self.env)

    def tearDown(self):
        self.env.reset_db()

    def test_grant_permission_action_already_granted(self):
        """Warning is added when granting an action that has already
        been granted.
        """
        req = MockRequest(self.env, method='POST', args={
            'add': True, 'subject': 'anonymous', 'action': 'WIKI_VIEW'})

        self.panel.render_admin_panel(req, 'general', 'perm', None)

        self.assertIn("The user anonymous already has permission WIKI_VIEW.",
                      req.chrome['warnings'])

    def test_grant_permission_group_already_granted(self):
        """Warning is added when adding a subject to a group and the
        subject is already a member of the group.
        """
        PermissionSystem(self.env).grant_permission('user1', 'group1')
        req = MockRequest(self.env, method='POST', args={
            'add': True, 'subject': 'user1', 'group': 'group1'})

        self.panel.render_admin_panel(req, 'general', 'perm', None)

        self.assertIn("The user user1 is already in the group group1.",
                      req.chrome['warnings'])


class PluginAdminPanelTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.req = MockRequest(self.env)

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


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(PermissionAdminPanelTestCase))
    suite.addTest(unittest.makeSuite(PluginAdminPanelTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
