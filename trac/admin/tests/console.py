# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2019 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.
#
# Author: Tim Moloney <t.moloney@verizon.net>

import os
import textwrap
import unittest

# IAdminCommandProvider implementations
import trac.admin.api
import trac.attachment
import trac.perm
import trac.ticket.admin
import trac.versioncontrol.admin
import trac.versioncontrol.api
import trac.versioncontrol.web_ui
import trac.wiki.admin

from trac.admin.api import IAdminCommandProvider, get_console_locale
from trac.admin.console import TracAdmin, TracAdminHelpMacro
from trac.admin.test import TracAdminTestCaseBase
from trac.core import Component, ComponentMeta, implements
from trac.test import EnvironmentStub
from trac.util.datefmt import get_date_format_hint
from trac.util.translation import Locale, get_available_locales, has_babel
from trac.wiki.formatter import MacroError


class TracadminTestCase(TracAdminTestCaseBase):
    """
    Tests the output of trac-admin and is meant to be used with
    .../trac/tests.py.
    """

    def setUp(self):
        self.env = EnvironmentStub()
        self.admin = TracAdmin()
        self.admin.env_set('', self.env)

    def tearDown(self):
        self.env = None

    def test_help_ok(self):
        """
        Tests the 'help' command in trac-admin.  Since the 'help' command
        has no command arguments, it is hard to call it incorrectly.  As
        a result, there is only this one test.
        """
        rv, output = self.execute('help')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output, {
            'version': self.env.trac_version,
            'date_format_hint': get_date_format_hint()
        })
        self.assertTrue(all(len(line) < 80 for line in output.split('\n')),
                        "Lines should be less than 80 characters in length.")

    def _test_get_console_locale_with_babel(self):
        locales = get_available_locales()
        en_US = Locale.parse('en_US')
        de = Locale.parse('de')

        def unset_locale_envs():
            for name in ('LANGUAGE', 'LC_ALL', 'LC_MESSAGES', 'LANG'):
                if name in os.environ:
                    del os.environ[name]

        if 'de' in locales:
            unset_locale_envs()
            self.assertIsNone(get_console_locale(None, None))
            self.assertEqual(de, get_console_locale(None, 'de_DE.UTF8'))
            self.env.config.set('trac', 'default_language', 'de')
            self.assertEqual(de, get_console_locale(self.env, None))
            self.assertEqual(de, get_console_locale(self.env, 'C'))
            self.env.config.set('trac', 'default_language', 'en_US')
            self.assertEqual(en_US, get_console_locale(self.env, None))
            self.assertEqual(en_US, get_console_locale(self.env, 'C'))
            self.assertEqual(de, get_console_locale(self.env,
                                                    'de_DE.UTF8'))

            self.env.config.set('trac', 'default_language', 'de')
            os.environ['LANG'] = 'POSIX'  # unavailable locale in Trac
            self.assertIsNone(get_console_locale())
            self.assertEqual(de, get_console_locale(self.env))
            os.environ['LANG'] = '****'  # invalid locale
            self.assertIsNone(get_console_locale())
            self.assertEqual(de, get_console_locale(self.env))
            os.environ['LANG'] = 'en_US.utf-8'
            self.assertEqual(en_US, get_console_locale())
            self.assertEqual(en_US, get_console_locale(self.env))
            os.environ['LC_MESSAGES'] = 'de_DE.utf-8'
            self.assertEqual(de, get_console_locale())
            self.assertEqual(de, get_console_locale(self.env))
            os.environ['LC_ALL'] = 'en_US.utf-8'
            self.assertEqual(en_US, get_console_locale())
            self.assertEqual(en_US, get_console_locale(self.env))
            os.environ['LANGUAGE'] = 'de_DE:en_US:en'
            self.assertEqual(de, get_console_locale())
            self.assertEqual(de, get_console_locale(self.env))

        if not locales:  # compiled catalog is missing
            unset_locale_envs()
            self.assertIsNone(get_console_locale(None, 'de_DE.UTF8'))
            self.env.config.set('trac', 'default_language', 'de')
            self.assertIsNone(get_console_locale(self.env, None))
            self.assertIsNone(get_console_locale(self.env, 'C'))
            self.assertIsNone(get_console_locale(self.env,
                                                      'de_DE.UTF8'))
            os.environ['LANG'] = 'en_US.utf-8'
            os.environ['LC_MESSAGES'] = 'de_DE.utf-8'
            os.environ['LC_ALL'] = 'en_US.utf-8'
            os.environ['LANGUAGE'] = 'de_DE:en_US'
            self.assertEqual(en_US, get_console_locale())
            self.assertEqual(en_US, get_console_locale(self.env))

    def _test_get_console_locale_without_babel(self):
        os.environ['LANG'] = 'en_US.utf-8'
        os.environ['LC_MESSAGES'] = 'de_DE.utf-8'
        os.environ['LC_ALL'] = 'en_US.utf-8'
        os.environ['LANGUAGE'] = 'de_DE:en_US'
        self.assertIsNone(get_console_locale(None, 'en_US.UTF8'))
        self.env.config.set('trac', 'default_language', '')
        self.assertIsNone(get_console_locale(self.env, 'en_US.UTF8'))
        self.assertIsNone(get_console_locale(self.env))
        self.env.config.set('trac', 'default_language', 'en_US')
        self.assertIsNone(get_console_locale(self.env, 'en_US.UTF8'))
        self.assertIsNone(get_console_locale(self.env))

    if has_babel:
        test_get_console_locale = _test_get_console_locale_with_babel
    else:
        test_get_console_locale = _test_get_console_locale_without_babel


class TracAdminNoEnvTestCase(TracAdminTestCaseBase):

    def test_help(self):
        rv, output = self.execute('help')
        output = output.splitlines()
        self.assertEqual('', output[-3])
        self.assertEqual('help     Show documentation', output[-2])
        self.assertEqual('initenv  Create and initialize a new environment',
                         output[-1])

    def test_help_with_nocmd(self):
        rv, output = self.execute('help nocmd')
        output = output.splitlines()
        self.assertEqual(["No documentation found for 'nocmd'. Use 'help' to "
                          "see the list of commands."],
                          output)

    def test_run_help_with_arguments(self):
        rv, output = self.execute_run(['help'])
        self.assertIn('Usage: trac-admin </path/to/projenv>', output)
        rv, output = self.execute_run(['help', "foo'bar"])
        self.assertNotIn('No closing quotation', output)
        self.assertIn("No documentation found for 'foo'bar'", output)

    def test_run_cmd_with_env_path(self):
        rv, output = self.execute_run(['notfound-tracenv', 'help'])
        self.assertIn('Usage: trac-admin </path/to/projenv>', output)
        rv, output = self.execute_run(['notfound-tracenv', 'help', "foo'bar"])
        self.assertNotIn('No closing quotation', output)
        self.assertIn("No documentation found for 'foo'bar'", output)


class TracAdminHelpMacroTestCase(TracAdminTestCaseBase):

    unicode_help_command = None

    @classmethod
    def setUpClass(cls):
        class UnicodeHelpCommand(Component):
            implements(IAdminCommandProvider)

            unicode_help = u'Hélp text with unicöde charàcters'

            def get_admin_commands(self):
                yield ('unicode-help', '', self.unicode_help,
                       None, self._cmd)

            def _cmd(self):
                pass

        cls.unicode_help_command = UnicodeHelpCommand

    @classmethod
    def tearDownClass(cls):
        ComponentMeta.deregister(cls.unicode_help_command)

    def setUp(self):
        self.env = EnvironmentStub()

    def test_unicode_help(self):
        macro = TracAdminHelpMacro(self.env)
        help = unicode(macro.expand_macro(None, None, 'unicode-help'))
        self.assertIn(self.unicode_help_command.unicode_help, help)

    def test_invalid_command(self):
        macro = TracAdminHelpMacro(self.env)

        try:
            macro.expand_macro(None, None, 'copystatic')
        except MacroError as e:
            self.assertEqual('Unknown trac-admin command "copystatic"',
                             unicode(e))
        else:
            self.fail("MacroError not raised")


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TracadminTestCase))
    suite.addTest(unittest.makeSuite(TracAdminNoEnvTestCase))
    suite.addTest(unittest.makeSuite(TracAdminHelpMacroTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
