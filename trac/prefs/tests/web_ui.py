# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2020 Edgewall Software
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
import unittest

from trac.core import Component, TracValueError, implements
from trac.prefs.api import IPreferencePanelProvider
from trac.prefs.web_ui import PreferencesModule
from trac.test import EnvironmentStub, MockRequest, mkdtemp
from trac.util import create_file
from trac.util.html import Markup
from trac.web.api import RequestDone


class PreferencePanelTestCase(unittest.TestCase):

    path_info = None

    def setUp(self):
        self.env = EnvironmentStub()

    def tearDown(self):
        self.env.reset_db()

    def _process_request(self, req):
        mod = PreferencesModule(self.env)
        self.assertTrue(mod.match_request(req))
        try:
            data = mod.process_request(req)[1]
        except RequestDone:
            return None
        else:
            return data

    def _prepare_prefs_post_request(self, args):
        args['action'] = 'save'
        return MockRequest(self.env, method='POST',
                           path_info=self.path_info,
                           cookie='trac_session=1234567890abcdef;',
                           args=args)

    def _prepare_prefs_get_request(self):
        return MockRequest(self.env, method='GET',
                           path_info=self.path_info,
                           cookie='trac_session=1234567890abcdef;')


class AdvancedPreferencePanelTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()

    def _insert_session(self):
        sid = '1234567890abcdef'
        name = 'First Last'
        email = 'first.last@example.com'
        self.env.insert_users([(sid, name, email, 0)])
        return sid, name, email

    def test_change_session_key(self):
        """Change session key."""
        old_sid, name, email = self._insert_session()
        new_sid = 'a' * 24
        req = MockRequest(self.env, method='POST',
                          path_info='/prefs/advanced',
                          cookie='trac_session=%s;' % old_sid,
                          args={'newsid': new_sid})
        module = PreferencesModule(self.env)

        self.assertEqual(old_sid, req.session.sid)
        self.assertEqual(name, req.session.get('name'))
        self.assertEqual(email, req.session.get('email'))
        self.assertTrue(module.match_request(req))
        with self.assertRaises(RequestDone):
            module.process_request(req)
        self.assertIn("Your preferences have been saved.",
                      req.chrome['notices'])
        self.assertEqual(new_sid, req.session.sid)
        self.assertEqual(name, req.session.get('name'))
        self.assertEqual(email, req.session.get('email'))

    def test_change_to_invalid_session_key_raises_exception(self):
        """Changing session key with invalid session key raises
        TracValueError.
        """
        req = MockRequest(self.env, method='POST',
                          path_info='/prefs/advanced',
                          args={'newsid': 'a' * 23 + '$'})
        module = PreferencesModule(self.env)

        self.assertTrue(module.match_request(req))
        with self.assertRaises(TracValueError) as cm:
            module.process_request(req)
        self.assertEqual("Session ID must be alphanumeric.", str(cm.exception))

    def test_load_session_key(self):
        """Load session key."""
        old_sid = 'a' * 24
        new_sid, name, email = self._insert_session()
        req = MockRequest(self.env, method='POST',
                          path_info='/prefs/advanced',
                          cookie='trac_session=%s;' % old_sid,
                          args={'loadsid': new_sid, 'restore': True})
        module = PreferencesModule(self.env)

        self.assertEqual(old_sid, req.session.sid)
        self.assertIsNone(req.session.get('name'))
        self.assertIsNone(req.session.get('email'))
        self.assertTrue(module.match_request(req))
        module.process_request(req)
        self.assertIn("The session has been loaded.", req.chrome['notices'])
        self.assertEqual(new_sid, req.session.sid)
        self.assertEqual(name, req.session.get('name'))
        self.assertEqual(email, req.session.get('email'))

    def test_load_invalid_session_key_raises_exception(self):
        """Loading session key with invalid session key raises
        TracValueError.
        """
        req = MockRequest(self.env, method='POST',
                          path_info='/prefs/advanced',
                          args={'loadsid': 'a' * 23 + '$', 'restore': True})
        module = PreferencesModule(self.env)

        self.assertTrue(module.match_request(req))
        with self.assertRaises(TracValueError) as cm:
            module.process_request(req)
        self.assertEqual("Session ID must be alphanumeric.", str(cm.exception))


class UserInterfacePreferencePanelTestCase(PreferencePanelTestCase):

    path_info = '/prefs/userinterface'

    def _test_auto_preview_timeout(self, timeout):
        args = {'ui.auto_preview_timeout': timeout}
        req = self._prepare_prefs_post_request(args)

        self._process_request(req)

        self.assertEqual(1, len(req.chrome['notices']))
        self.assertEqual("Your preferences have been saved.",
                         req.chrome['notices'][0])
        return req

    def test_save_auto_preview_timeout(self):
        timeout = '3'
        req = self._test_auto_preview_timeout(timeout)

        self.assertEqual(timeout, req.session['ui.auto_preview_timeout'])

    def _test_auto_preview_timeout_value_invalid(self, val):
        timeout = '3'
        req = self._test_auto_preview_timeout(timeout)
        req.session.save()
        req = self._test_auto_preview_timeout(val)

        self.assertEqual(1, len(req.chrome['warnings']))
        self.assertEqual('Discarded invalid value "%s" for auto preview '
                         'timeout.' % val, req.chrome['warnings'][0])
        self.assertEqual(timeout, req.session['ui.auto_preview_timeout'])

    def test_auto_preview_timeout_value_is_char(self):
        self._test_auto_preview_timeout_value_invalid('A')

    def test_auto_preview_timeout_value_is_inf(self):
        self._test_auto_preview_timeout_value_invalid('inf')

    def test_auto_preview_timeout_value_is_nan(self):
        self._test_auto_preview_timeout_value_invalid('NaN')

    def test_delete_auto_preview_timeout(self):
        self._test_auto_preview_timeout('1')
        req = self._test_auto_preview_timeout('')

        self.assertNotIn('ui.auto_preview_timeout', req.session)

    def _test_default_handler(self, default_handler):
        args = {'default_handler': default_handler}
        req = self._prepare_prefs_post_request(args)

        self._process_request(req)

        self.assertEqual(0, len(req.chrome['warnings']))
        self.assertEqual(1, len(req.chrome['notices']))
        self.assertEqual("Your preferences have been saved.",
                         req.chrome['notices'][0])
        return req

    def test_get_template_data_default_values_in_config(self):
        req = self._prepare_prefs_get_request()
        data = self._process_request(req)

        self.assertEqual('WikiModule', data['project_default_handler'])
        self.assertEqual(['AboutModule', 'AdminModule', 'AnyDiffModule',
            'BrowserModule', 'ChangesetModule', 'LogModule',
            'MilestoneModule', 'PreferencesModule', 'ReportModule',
            'RoadmapModule', 'SearchModule', 'TimelineModule',
            'WikiModule'], data['valid_default_handlers'])
        self.assertEqual(2.0, data['default_auto_preview_timeout'])

    def test_get_template_data_empty_values_in_config(self):
        self.env.config.set('trac', 'default_handler', '')
        self.env.config.set('trac', 'auto_preview_timeout', '')
        req = self._prepare_prefs_get_request()
        data = self._process_request(req)

        self.assertEqual('WikiModule', data['project_default_handler'])
        self.assertEqual(0, data['default_auto_preview_timeout'])

    def test_get_template_data_custom_values_in_config(self):
        self.env.config.set('trac', 'default_handler', 'TimelineModule')
        self.env.config.set('trac', 'auto_preview_timeout', '3.0')
        req = self._prepare_prefs_get_request()
        data = self._process_request(req)

        self.assertEqual('TimelineModule', data['project_default_handler'])
        self.assertEqual(3.0, data['default_auto_preview_timeout'])

    def test_set_default_handler(self):
        default_handler = 'TimelineModule'
        req = self._test_default_handler(default_handler)
        self.assertEqual(default_handler, req.session['default_handler'])

        req = self._test_default_handler('')
        self.assertNotIn('default_handler', req.session)


class PreferencesModuleTestCase(unittest.TestCase):

    panel_providers = []

    @classmethod
    def setUpClass(cls):
        class ParentPanel(Component):
            implements(IPreferencePanelProvider)

            def get_preference_panels(self, req):
                yield 'panel1', 'Panel One'

            def render_preference_panel(self, req, panel):
                return 'prefs_panel_1.html', {}, None

        cls.child_template = '<h2>${title}</h2>'
        cls.child1_template_name = 'prefs_child_1.html'

        class Child1Panel(Component):
            implements(IPreferencePanelProvider)

            def get_preference_panels(self, req):
                yield 'child1', 'Child 1', 'panel1'

            def render_preference_panel(self, req, panel):
                return cls.child1_template_name, {'title': 'Child 1'}

        cls.child2_template_name = 'prefs_child_2.html'

        class Child2Panel(Component):
            implements(IPreferencePanelProvider)

            def get_preference_panels(self, req):
                yield 'child2', 'Child 2', 'panel1'

            def render_preference_panel(self, req, panel):
                return cls.child2_template_name, {'title': 'Child 2'}

        cls.panel_providers = [ParentPanel, Child1Panel, Child2Panel]

    @classmethod
    def tearDownClass(cls):
        from trac.core import ComponentMeta
        for component in cls.panel_providers:
            ComponentMeta.deregister(component)

    def setUp(self):
        self.env = EnvironmentStub(path=mkdtemp())
        self.templates_dir = os.path.join(self.env.path, 'templates')
        os.mkdir(self.templates_dir)

    def tearDown(self):
        self.env.reset_db_and_disk()

    def test_render_child_preferences_panels(self):
        create_file(os.path.join(self.templates_dir, self.child1_template_name),
                    self.child_template)
        create_file(os.path.join(self.templates_dir, self.child2_template_name),
                    self.child_template)

        req = MockRequest(self.env, path_info='/prefs/panel1')
        mod = PreferencesModule(self.env)

        self.assertTrue(mod.match_request(req))
        resp = mod.process_request(req)

        self.assertEqual('prefs_panel_1.html', resp[0])
        self.assertEqual(2, len(resp[1]['children']))
        self.assertEqual(('child1', 'Child 1', Markup('<h2>Child 1</h2>')),
                         resp[1]['children'][0])
        self.assertEqual(('child2', 'Child 2', Markup('<h2>Child 2</h2>')),
                         resp[1]['children'][1])


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(AdvancedPreferencePanelTestCase))
    suite.addTest(unittest.makeSuite(UserInterfacePreferencePanelTestCase))
    suite.addTest(unittest.makeSuite(PreferencesModuleTestCase))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
