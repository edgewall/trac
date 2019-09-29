# -*- coding: utf-8 -*-
#
# Copyright (C) 2015-2019 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

import os
import tempfile
import unittest

from trac.admin.web_ui import AdminModule, PermissionAdminPanel, \
                              PluginAdminPanel
from trac.core import Component, TracError
from trac.perm import PermissionError, PermissionSystem
from trac.loader import load_components
from trac.test import EnvironmentStub, MockRequest, mkdtemp
from trac.util import create_file
from trac.web.api import RequestDone


class PermissionAdminPanelTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        self.panel = PermissionAdminPanel(self.env)

    def tearDown(self):
        self.env.reset_db()

    def _test_invalid_user(self, subject='', action='', target='', group=''):
        req = MockRequest(self.env, method='POST', args={
            'add': True, 'subject': subject, 'target': target, 'group': group,
            'action': action})

        with self.assertRaises(TracError) as cm:
            self.panel.render_admin_panel(req, 'general', 'perm', None)

        self.assertEqual("All upper-cased tokens are reserved for permission "
                         "names.", unicode(cm.exception))

    def test_grant_permission_invalid_username(self):
        self._test_invalid_user(subject='USER', action='WIKI_VIEW')

    def test_add_subject_to_group_invalid_subject_or_group(self):
        self._test_invalid_user(subject='user', group='GROUP')
        self._test_invalid_user(subject='USER', group='group')

    def test_copy_permissions_invalid_subject_or_target(self):
        self._test_invalid_user(subject='user1', target='USER2')
        self._test_invalid_user(subject='USER1', target='user2')

    def test_grant_permission_action_already_granted(self):
        """Warning is added when granting an action that has already
        been granted.
        """
        req = MockRequest(self.env, method='POST', args={
            'add': True, 'subject': 'anonymous', 'action': 'WIKI_VIEW'})

        with self.assertRaises(RequestDone):
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

        with self.assertRaises(RequestDone):
            self.panel.render_admin_panel(req, 'general', 'perm', None)

        self.assertIn("The user user1 is already in the group group1.",
                      req.chrome['warnings'])

    def test_grant_permission_with_permission_grant(self):
        """User can only grant permissions they possess."""
        ps = PermissionSystem(self.env)
        ps.grant_permission('user1', 'PERMISSION_GRANT')
        ps.grant_permission('group1', 'WIKI_ADMIN')
        req = MockRequest(self.env, method='POST', authname='user1', args={
            'add': True, 'subject': 'user2', 'group': 'group1'})

        with self.assertRaises(PermissionError) as cm:
            self.panel.render_admin_panel(req, 'general', 'perm', None)

        self.assertEqual("The subject user2 was not added to the group "
                         "group1. The group has WIKI_ADMIN permission and "
                         "you cannot grant permissions you don't possess.",
                         unicode(cm.exception))

    def test_grant_undefined_permission_with_permission_grant(self):
        """Undefined permission is granted without checking granter."""
        ps = PermissionSystem(self.env)
        ps.grant_permission('user1', 'PERMISSION_GRANT')
        self.env.db_transaction("""
            INSERT INTO permission VALUES ('group1', 'TEST_PERM')
            """)
        req = MockRequest(self.env, method='POST', authname='user1', args={
            'add': True, 'subject': 'user2', 'group': 'group1'})

        with self.assertRaises(RequestDone):
            self.panel.render_admin_panel(req, 'general', 'perm', None)

        self.assertIn('TEST_PERM',
                      ps.get_user_permissions('group1', undefined=True))
        self.assertIn('user2', ps.get_groups_dict()['group1'])

    def test_copy_permissions_to_subject(self):
        """Copy permissions to subject.

        Undefined actions are skipped.
        """
        ps = PermissionSystem(self.env)
        ps.grant_permission('user1', 'WIKI_VIEW')
        ps.grant_permission('user1', 'TICKET_VIEW')
        self.env.db_transaction("""
            INSERT INTO permission VALUES ('user1', 'TEST_PERM')
            """)
        req = MockRequest(self.env, method='POST', args={
            'copy': True, 'subject': 'user1', 'target': 'user2'})

        with self.assertRaises(RequestDone):
            self.panel.render_admin_panel(req, 'general', 'perm', None)

        self.assertEqual(['TICKET_VIEW', 'WIKI_VIEW'],
                          ps.get_users_dict().get('user2'))
        self.assertEqual(2, len(req.chrome['notices']))
        self.assertIn("The subject user2 has been granted the permission "
                      "TICKET_VIEW.", req.chrome['notices'])
        self.assertIn("The subject user2 has been granted the permission "
                      "WIKI_VIEW.", req.chrome['notices'])
        self.assertIn(("WARNING", "Skipped granting TEST_PERM to user2: "
                                  "permission unavailable."),
                      self.env.log_messages)
        self.assertIn(("INFO", "Granted permission for TICKET_VIEW to user2"),
                       self.env.log_messages)
        self.assertIn(("INFO", "Granted permission for TICKET_VIEW to user2"),
                       self.env.log_messages)


class PluginAdminPanelTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(path=mkdtemp())

    def tearDown(self):
        self.env.reset_db_and_disk()

    def test_abstract_component_not_visible(self):
        class AbstractComponent(Component):
            abstract = True

        class NotAbstractComponent(Component):
            abstract = False

        req = MockRequest(self.env)
        panel = PluginAdminPanel(self.env)
        data = panel.render_admin_panel(req, 'general', 'plugin', None)[1]

        module_ = self.__class__.__module__
        components = []
        for plugin in data['plugins']:
            if module_ in plugin['modules']:
                components = plugin['modules'][module_]['components']
        self.assertNotIn('AbstractComponent', components)
        self.assertIn('NotAbstractComponent', components)

    def test_single_file_plugin_metadata(self):
        """Metadata is read from single-file plugins."""
        plugin_metadata = {
            'author': 'Trac Hacks',
            'author_email': 'trac-hacks@domain.com',
            'home_page': 'https://trac-hacks.org/wiki/SingleFilePlugin',
            'license': 'BSD',
            'summary': 'The single-file plugin',
            'trac': 'https://my.trac.com',
        }
        plugin_content = """\
from trac.core import Component

author = '%(author)s'
author_email = '%(author_email)s'
home_page = '%(home_page)s'
license = '%(license)s'
summary = '%(summary)s'
trac = '%(trac)s'


class SingleFilePlugin(Component):
    pass
""" % plugin_metadata

        file_path = os.path.join(self.env.plugins_dir, 'single_file_plugin.py')
        os.mkdir(self.env.plugins_dir)
        create_file(file_path, plugin_content)
        load_components(self.env, (self.env.plugins_dir,))

        req = MockRequest(self.env)
        panel = PluginAdminPanel(self.env)
        data = panel.render_admin_panel(req, 'general', 'plugin', None)[1]

        discovered_metadata = {}
        for item in data['plugins']:
            if item['name'] == 'single-file-plugin':
                discovered_metadata = item['info']

        for key, value in plugin_metadata.items():
            self.assertEqual(discovered_metadata[key], plugin_metadata[key])


class LoggingAdminPanelTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(path=tempfile.mkdtemp())
        os.mkdir(self.env.log_dir)

    def tearDown(self):
        self.env.reset_db_and_disk()

    def test_render_admin_panel(self):
        """GET request for admin panel."""
        req = MockRequest(self.env, path_info='/admin/general/logging',
                          method='GET')
        mod = AdminModule(self.env)

        self.assertTrue(mod.match_request(req))
        data = mod.process_request(req)[1]

        self.assertEqual('none', data['log']['type'])
        self.assertEqual(['none', 'stderr', 'file', 'syslog', 'eventlog'],
                         [t['name'] for t in data['log']['types']])
        self.assertEqual('DEBUG', data['log']['level'])
        self.assertEqual(['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG'],
                         data['log']['levels'])
        self.assertEqual('trac.log', data['log']['file'])
        self.assertEqual(self.env.log_dir, data['log']['dir'])

    def test_invalid_log_type_raises(self):
        """Invalid log type raises TracError."""
        req = MockRequest(self.env, path_info='/admin/general/logging',
                          method='POST', args={'log_type': 'invalid'})
        mod = AdminModule(self.env)

        self.assertTrue(mod.match_request(req))
        self.assertRaises(TracError, mod.process_request, req)

    def test_invalid_log_level_raises(self):
        """Invalid log level raises TracError."""
        req = MockRequest(self.env, path_info='/admin/general/logging',
                          method='POST',
                          args={'log_type': 'stderr',
                                'log_level': 'INVALID'})
        mod = AdminModule(self.env)

        self.assertTrue(mod.match_request(req))
        self.assertRaises(TracError, mod.process_request, req)

    def test_empty_log_file_raises(self):
        """Empty log file raises TracError."""
        req = MockRequest(self.env, path_info='/admin/general/logging',
                          method='POST',
                          args={'log_type': 'file',
                                'log_level': 'DEBUG',
                                'log_file': ''})
        mod = AdminModule(self.env)

        self.assertTrue(mod.match_request(req))
        self.assertRaises(TracError, mod.process_request, req)

    def test_invalid_log_configuration_not_saved(self):
        """Invalid log configuration is reverted and not saved."""
        logging_config = self.env.config['logging']
        log_type = logging_config.get('log_type')
        log_file = logging_config.get('log_file')
        log_level = logging_config.get('log_level')
        req = MockRequest(self.env, path_info='/admin/general/logging',
                          method='POST',
                          args={'log_type': 'file',
                                'log_level': log_level,
                                'log_file': '/path/to/invalid/file'})
        mod = AdminModule(self.env)

        self.assertTrue(mod.match_request(req))
        self.assertRaises(RequestDone, mod.process_request, req)

        self.assertEqual(1, len(req.chrome['warnings']))
        self.assertIn('Changes not saved. Logger configuration error:',
                      req.chrome['warnings'][0])
        self.assertNotEqual('file', log_type)
        self.assertEqual(log_type, logging_config.get('log_type'))
        self.assertEqual(log_level, logging_config.get('log_level'))
        self.assertEqual(log_file, logging_config.get('log_file'))

    def test_log_type_none(self):
        """When log type is none, TracError is not raised even if log level and
        log file in the parameters are missing.
        """
        logging_config = self.env.config['logging']
        logging_config.set('log_type', 'file')
        logging_config.set('log_level', 'WARN')
        logging_config.set('log_file', os.devnull)
        mod = AdminModule(self.env)

        req = MockRequest(self.env, path_info='/admin/general/logging')
        self.assertTrue(mod.match_request(req))
        data = mod.process_request(req)[1]
        self.assertEqual('WARNING', data['log']['level'])
        self.assertIn('WARNING', data['log']['levels'])

        req = MockRequest(self.env, path_info='/admin/general/logging',
                          method='POST', args={'log_type': 'none'})
        self.assertTrue(mod.match_request(req))
        self.assertRaises(RequestDone, mod.process_request, req)
        self.assertEqual('none', logging_config.get('log_type'))
        self.assertEqual('WARN', logging_config.get('log_level'))
        self.assertEqual(os.devnull, logging_config.get('log_file'))

    def test_change_log_type(self):
        """Change the log type."""
        logging_config = self.env.config['logging']
        log_type = logging_config.get('log_type')
        log_file = logging_config.get('log_file')
        log_level = logging_config.get('log_level')
        req = MockRequest(self.env, path_info='/admin/general/logging',
                          method='POST',
                          args={'log_type': 'file',
                                'log_level': log_level,
                                'log_file': log_file})
        mod = AdminModule(self.env)

        self.assertTrue(mod.match_request(req))
        self.assertRaises(RequestDone, mod.process_request, req)

        self.assertEqual(0, len(req.chrome['warnings']))
        self.assertNotEqual('file', log_type)
        self.assertEqual('file', logging_config.get('log_type'))
        self.assertEqual(log_level, logging_config.get('log_level'))
        self.assertEqual(log_file, logging_config.get('log_file'))

    def test_change_log_level(self):
        """Change the log level."""
        logging_config = self.env.config['logging']
        log_type = 'stderr'
        logging_config.set('log_type', log_type)
        log_level = logging_config.get('log_level')
        log_file = logging_config.get('log_file')
        req = MockRequest(self.env, path_info='/admin/general/logging',
                          method='POST',
                          args={'log_type': log_type,
                                'log_level': 'ERROR',
                                'log_file': log_file})
        mod = AdminModule(self.env)

        self.assertTrue(mod.match_request(req))
        self.assertRaises(RequestDone, mod.process_request, req)

        self.assertEqual(0, len(req.chrome['warnings']))
        self.assertEqual(log_type, logging_config.get('log_type'))
        self.assertNotEqual('ERROR', log_level)
        self.assertEqual('ERROR', logging_config.get('log_level'))
        self.assertEqual(log_file, logging_config.get('log_file'))

    def test_change_log_file(self):
        """Change the log file."""
        logging_config = self.env.config['logging']
        log_type = 'file'
        logging_config.set('log_type', log_type)
        log_level = logging_config.get('log_level')
        log_file = logging_config.get('log_file')
        req = MockRequest(self.env, path_info='/admin/general/logging',
                          method='POST',
                          args={'log_type': log_type,
                                'log_level': log_level,
                                'log_file': 'trac.log.1'})
        mod = AdminModule(self.env)

        self.assertTrue(mod.match_request(req))
        self.assertRaises(RequestDone, mod.process_request, req)

        self.assertEqual(0, len(req.chrome['warnings']))
        self.assertEqual(log_type, logging_config.get('log_type'))
        self.assertEqual(log_level, logging_config.get('log_level'))
        self.assertNotEqual('trac.log.1', log_file)
        self.assertEqual('trac.log.1', logging_config.get('log_file'))


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(PermissionAdminPanelTestCase))
    suite.addTest(unittest.makeSuite(PluginAdminPanelTestCase))
    suite.addTest(unittest.makeSuite(LoggingAdminPanelTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
