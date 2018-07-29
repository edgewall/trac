# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2018 Edgewall Software
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

from trac.core import Component, TracValueError, implements
from trac.prefs.api import IPreferencePanelProvider
from trac.prefs.web_ui import PreferencesModule
from trac.test import EnvironmentStub, MockRequest
from trac.util import create_file
from trac.util.html import Markup
from trac.web.api import RequestDone


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
        self.assertRaises(RequestDone, module.process_request, req)
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
        try:
            module.process_request(req)
        except TracValueError as e:
            self.assertEqual("Session ID must be alphanumeric.", unicode(e))
        else:
            self.fail("TracValueError not raised.")

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
        try:
            module.process_request(req)
        except TracValueError as e:
            self.assertEqual("Session ID must be alphanumeric.", unicode(e))
        else:
            self.fail("TracValueError not raised.")


class PreferencesModuleTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(
            path=tempfile.mkdtemp(prefix='trac-tempenv-'))
        self.templates_dir = os.path.join(self.env.path, 'templates')
        os.mkdir(self.templates_dir)

    def tearDown(self):
        self.env.reset_db_and_disk()

    def test_render_child_preferences_panels(self):

        class ParentPanel(Component):
            implements(IPreferencePanelProvider)

            def get_preference_panels(self, req):
                yield 'panel1', 'Panel One'

            def render_preference_panel(self, req, panel):
                return 'prefs_panel_1.html', {}, None

        child_template = '<h2>${title}</h2>'
        child1_template_name = 'prefs_child_1.html'

        class Child1Panel(Component):
            implements(IPreferencePanelProvider)

            def get_preference_panels(self, req):
                yield 'child1', 'Child 1', 'panel1'

            def render_preference_panel(self, req, panel):
                return child1_template_name, {'title': 'Child 1'}

        child2_template_name = 'prefs_child_2.html'

        class Child2Panel(Component):
            implements(IPreferencePanelProvider)

            def get_preference_panels(self, req):
                yield 'child2', 'Child 2', 'panel1'

            def render_preference_panel(self, req, panel):
                return child2_template_name, {'title': 'Child 2'}

        create_file(os.path.join(self.templates_dir, child1_template_name),
                    child_template)
        create_file(os.path.join(self.templates_dir, child2_template_name),
                    child_template)

        req = MockRequest(self.env, path_info='/prefs/panel1')
        mod = PreferencesModule(self.env)

        self.assertTrue(mod.match_request(req))
        resp = mod.process_request(req)

        self.assertEqual('prefs_panel_1.html', resp[0])
        self.assertEqual(2, len(resp[1]['children']))
        self.assertEqual(('child1', 'Child 1', Markup(u'<h2>Child 1</h2>')),
                         resp[1]['children'][0])
        self.assertEqual(('child2', 'Child 2', Markup(u'<h2>Child 2</h2>')),
                         resp[1]['children'][1])


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(AdvancedPreferencePanelTestCase))
    suite.addTest(unittest.makeSuite(PreferencesModuleTestCase))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
