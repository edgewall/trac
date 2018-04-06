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

import os
import tempfile
import unittest

import trac.tests.compat
from trac.admin.web_ui import AdminModule, PluginAdminPanel
from trac.core import Component, TracError
from trac.loader import load_components
from trac.test import EnvironmentStub, MockRequest
from trac.util import create_file
from trac.web.api import RequestDone


class PluginAdminPanelTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(path=tempfile.mkdtemp(prefix='trac-'))

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
            if module_ in plugin['modules'].keys():
                components = plugin['modules'][module_]['components'].keys()
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
        log_type = logging_config.get('log_type')
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
    suite.addTest(unittest.makeSuite(PluginAdminPanelTestCase))
    suite.addTest(unittest.makeSuite(LoggingAdminPanelTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
