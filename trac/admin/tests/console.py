# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2013 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.
#
# Author: Tim Moloney <t.moloney@verizon.net>

import copy
import os
import shutil
import sys
import unittest
from subprocess import PIPE

# IAdminCommandProvider implementations
import trac.admin.api
import trac.attachment
import trac.perm
import trac.ticket.admin
import trac.versioncontrol.admin
import trac.versioncontrol.api
import trac.versioncontrol.web_ui
import trac.wiki.admin

# IPermissionRequestor implementations (for 'permission' related tests)
import trac.about
import trac.admin.web_ui
import trac.config
import trac.ticket.api
import trac.ticket.batch
import trac.ticket.report
import trac.ticket.roadmap
import trac.ticket.web_ui
import trac.search.web_ui
import trac.timeline.web_ui
import trac.wiki.web_ui

from trac.admin.api import IAdminCommandProvider, console_date_format, \
                           get_console_locale
from trac.admin.console import TracAdmin, TracAdminHelpMacro
from trac.admin.test import TracAdminTestCaseBase
from trac.config import ConfigSection, Option
from trac.core import Component, ComponentMeta, implements
from trac.env import Environment
from trac.test import EnvironmentStub, mkdtemp
from trac.util import create_file
from trac.util.compat import Popen, close_fds
from trac.util.datefmt import format_date, get_date_format_hint, \
                              get_datetime_format_hint
from trac.util.translation import get_available_locales, has_babel
from trac.web.tests.session import _prep_session_table
from trac.wiki.formatter import MacroError


class TracadminTestCase(TracAdminTestCaseBase):
    """
    Tests the output of trac-admin and is meant to be used with
    .../trac/tests.py.
    """

    def setUp(self):
        self.env = EnvironmentStub(default_data=True, enable=('trac.*',),
                                   disable=('trac.tests.*',))
        self.admin = TracAdmin()
        self.admin.env_set('', self.env)

    def tearDown(self):
        self.env = None

    @property
    def datetime_format_hint(self):
        return get_datetime_format_hint(get_console_locale(self.env))

    def test_python_with_optimizations_returns_error(self):
        """Error is returned when a command is executed in interpreter
        with optimizations enabled.
        """
        with Popen((sys.executable, '-O', '-m', 'trac.admin.console', 'help'),
                   stdin=PIPE, stdout=PIPE, stderr=PIPE,
                   close_fds=close_fds) as proc:
            stdout, stderr = proc.communicate(input='')
        self.assertEqual(2, proc.returncode)
        self.assertEqual("Python with optimizations is not supported.",
                         stderr.strip())

    # Help test

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

    # Locale test

    def _test_get_console_locale_with_babel(self):
        from babel.core import Locale, UnknownLocaleError
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

    # Attachment tests

    def test_attachment_list_empty(self):
        """
        Tests the 'attachment list' command in trac-admin, on a wiki page that
        doesn't have any attachments.
        """
        # FIXME: Additional tests should be written for the other 'attachment'
        #        commands. This requires being able to control the current
        #        time, which in turn would require centralizing the time
        #        provider, for example in the environment object.
        rv, output = self.execute('attachment list wiki:WikiStart')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_attachment_add_nonexistent_resource(self):
        """Tests the 'attachment add' command in trac-admin, on a non-existent
        resource."""
        rv, output = self.execute('attachment add wiki:NonExistentPage "%s"'
                                  % __file__)
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    # Config tests

    def test_config_get(self):
        """
        Tests the 'config get' command in trac-admin.  This particular
        test gets the project name from the config.
        """
        self.env.config.set('project', 'name', 'Test project')
        rv, output = self.execute('config get project name')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_config_set(self):
        """
        Tests the 'config set' command in trac-admin.  This particular
        test sets the project name using an option value containing a space.
        """
        rv, output = self.execute('config set project name "Test project"')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)
        self.assertEqual('Test project',
                         self.env.config.get('project', 'name'))

    def test_config_remove(self):
        """
        Tests the 'config remove' command in trac-admin.  This particular
        test removes the project name from the config, therefore reverting
        the option to the default value.
        """
        self.env.config.set('project', 'name', 'Test project')
        rv, output = self.execute('config remove project name')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)
        self.assertEqual('My Project', self.env.config.get('project', 'name'))

    # Permission tests

    def test_permission_list_ok(self):
        """Tests the 'permission list' command in trac-admin."""
        rv, output = self.execute('permission list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_permission_list_includes_undefined_actions(self):
        """Undefined actions are included in the User Action table,
        but not in the Available Actions list.
        """
        self.env.disable_component(trac.search.web_ui.SearchModule)
        rv, output = self.execute('permission list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_permission_add_one_action_ok(self):
        """
        Tests the 'permission add' command in trac-admin.  This particular
        test passes valid arguments to add one permission and checks for
        success.
        """
        self.execute('permission add test_user WIKI_VIEW')
        rv, output = self.execute('permission list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_permission_add_multiple_actions_ok(self):
        """
        Tests the 'permission add' command in trac-admin.  This particular
        test passes valid arguments to add multiple permissions and checks for
        success.
        """
        self.execute('permission add test_user LOG_VIEW FILE_VIEW')
        rv, output = self.execute('permission list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_permission_add_already_exists(self):
        """
        Tests the 'permission add' command in trac-admin.  This particular
        test passes a permission that already exists and checks for the
        message. Other permissions passed are added.
        """
        rv, output = self.execute('permission add anonymous WIKI_CREATE '
                                   'WIKI_VIEW WIKI_MODIFY')
        self.assertEqual(0, rv, output)
        rv, output2 = self.execute('permission list')
        self.assertEqual(0, rv, output2)
        self.assertExpectedResult(output + output2)

    def test_permission_add_subject_already_in_group(self):
        """
        Tests the 'permission add' command in trac-admin.  This particular
        test passes a group that the subject is already a member of and
        checks for the message. Other permissions passed are added.
        """
        rv, output1 = self.execute('permission add user1 group2')
        self.assertEqual(0, rv, output1)
        rv, output2 = self.execute('permission add user1 group1 group2 '
                                    'group3')
        self.assertEqual(0, rv, output2)
        rv, output3 = self.execute('permission list')
        self.assertEqual(0, rv, output3)
        self.assertExpectedResult(output2 + output3)

    def test_permission_add_differs_from_action_by_casing(self):
        """
        Tests the 'permission add' command in trac-admin.  This particular
        test passes a permission that differs from an action by casing and
        checks for the message. None of the permissions in the list are
        granted.
        """
        rv, output = self.execute('permission add joe WIKI_CREATE '
                                   'Trac_Admin WIKI_MODIFY')
        self.assertEqual(2, rv, output)
        rv, output2 = self.execute('permission list')
        self.assertEqual(0, rv, output2)
        self.assertExpectedResult(output + output2)

    def test_permission_add_unknown_action(self):
        """
        Tests the 'permission add' command in trac-admin.  This particular
        test tries granting NOT_A_PERM to a user. NOT_A_PERM does not exist
        in the system. None of the permissions in the list are granted.
        """
        rv, output = self.execute('permission add joe WIKI_CREATE '
                                   'NOT_A_PERM WIKI_MODIFY')
        self.assertEqual(2, rv, output)
        rv, output2 = self.execute('permission list')
        self.assertEqual(0, rv, output2)
        self.assertExpectedResult(output + output2)

    def test_permission_remove_one_action_ok(self):
        """
        Tests the 'permission remove' command in trac-admin.  This particular
        test passes valid arguments to remove one permission and checks for
        success.
        """
        self.execute('permission remove anonymous TICKET_MODIFY')
        rv, output = self.execute('permission list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_permission_remove_multiple_actions_ok(self):
        """
        Tests the 'permission remove' command in trac-admin.  This particular
        test passes valid arguments to remove multiple permission and checks
        for success.
        """
        self.execute('permission remove anonymous WIKI_CREATE WIKI_MODIFY')
        rv, output = self.execute('permission list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_permission_remove_all_actions_for_user(self):
        """
        Tests the 'permission remove' command in trac-admin.  This particular
        test removes all permissions for anonymous.
        """
        self.execute('permission remove anonymous *')
        rv, output = self.execute('permission list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_permission_remove_action_for_all_users(self):
        """
        Tests the 'permission remove' command in trac-admin.  This particular
        test removes the TICKET_CREATE permission from all users.
        """
        self.execute('permission add anonymous TICKET_CREATE')
        self.execute('permission remove * TICKET_CREATE')
        rv, output = self.execute('permission list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_permission_remove_unknown_user(self):
        """
        Tests the 'permission remove' command in trac-admin.  This particular
        test tries removing a permission from an unknown user.
        """
        rv, output = self.execute('permission remove joe TICKET_VIEW')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_permission_remove_action_not_granted(self):
        """
        Tests the 'permission remove' command in trac-admin.  This particular
        test tries removing TICKET_CREATE from user anonymous, who doesn't
        have that permission.
        """
        rv, output = self.execute('permission remove anonymous TICKET_CREATE')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_permission_remove_action_granted_through_meta_permission(self):
        """
        Tests the 'permission remove' command in trac-admin.  This particular
        test tries removing WIKI_VIEW from a user. WIKI_VIEW has been granted
        through user anonymous."""
        self.execute('permission add joe TICKET_VIEW')
        rv, output = self.execute('permission remove joe WIKI_VIEW')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_permission_remove_unknown_action(self):
        """
        Tests the 'permission remove' command in trac-admin.  This particular
        test tries removing NOT_A_PERM from a user. NOT_A_PERM does not exist
        in the system."""
        rv, output = self.execute('permission remove joe NOT_A_PERM')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_permission_remove_unknown_action_granted(self):
        """
        Tests the 'permission remove' command in trac-admin.  This particular
        test tries removing NOT_A_PERM from a user. NOT_A_PERM does not exist
        in the system, but the user possesses the permission."""
        self.env.db_transaction("""
            INSERT INTO permission VALUES (%s, %s)
        """, ('joe', 'NOT_A_PERM'))
        rv, output = self.execute('permission remove joe NOT_A_PERM')
        self.assertEqual(0, rv, output)
        rv, output = self.execute('permission list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_permission_export_ok(self):
        """
        Tests the 'permission export' command in trac-admin.  This particular
        test exports the default permissions to stdout.
        """
        rv, output = self.execute('permission export')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_permission_import_ok(self):
        """
        Tests the 'permission import' command in trac-admin.  This particular
        test exports additional permissions, removes them and imports them back.
        """
        user = u'test_user\u0250'
        self.execute('permission add ' + user + ' WIKI_VIEW')
        self.execute('permission add ' + user + ' TICKET_VIEW')
        rv, output = self.execute('permission export')
        self.execute('permission remove ' + user + ' *')
        rv, output = self.execute('permission import', input=output)
        self.assertEqual(0, rv, output)
        self.assertEqual('', output)
        rv, output = self.execute('permission list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_backslash_use_ok(self):
        if self.admin.interactive:
            self.execute('version add \\')
        else:
            self.execute(r"version add '\'")
        rv, output = self.execute('version list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_session_list_no_sessions(self):
        rv, output = self.execute('session list authenticated')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_session_list_authenticated(self):
        _prep_session_table(self.env)
        rv, output = self.execute('session list authenticated')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_session_list_anonymous(self):
        _prep_session_table(self.env)
        rv, output = self.execute('session list anonymous')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_session_list_all(self):
        _prep_session_table(self.env)
        if self.admin.interactive:
            rv, output = self.execute("session list *")
        else:
            rv, output = self.execute("session list '*'")
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_session_list_authenticated_sid(self):
        _prep_session_table(self.env)
        rv, output = self.execute('session list name00')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_session_list_anonymous_sid(self):
        _prep_session_table(self.env)
        rv, output = self.execute('session list name10:0')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_session_list_missing_sid(self):
        _prep_session_table(self.env)
        rv, output = self.execute('session list thisdoesntexist')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_session_add_missing_sid(self):
        rv, output = self.execute('session add')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_session_add_duplicate_sid(self):
        _prep_session_table(self.env)
        rv, output = self.execute('session add name00')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_session_add_sid_all(self):
        rv, output = self.execute('session add john John john@example.org')
        self.assertEqual(0, rv, output)
        rv, output = self.execute('session list john')
        self.assertExpectedResult(output, {
            'today': format_date(None, console_date_format)
        })

    def test_session_add_sid(self):
        rv, output = self.execute('session add john')
        self.assertEqual(0, rv, output)
        rv, output = self.execute('session list john')
        self.assertExpectedResult(output, {
            'today': format_date(None, console_date_format)
        })

    def test_session_add_sid_name(self):
        rv, output = self.execute('session add john John')
        self.assertEqual(0, rv, output)
        rv, output = self.execute('session list john')
        self.assertExpectedResult(output,  {
            'today': format_date(None, console_date_format)
        })

    def test_session_set_attr_name(self):
        _prep_session_table(self.env)
        rv, output = self.execute('session set name name00 JOHN')
        self.assertEqual(0, rv, output)
        rv, output = self.execute('session list name00')
        self.assertExpectedResult(output)

    def test_session_set_attr_email(self):
        _prep_session_table(self.env)
        rv, output = self.execute('session set email name00 JOHN@EXAMPLE.ORG')
        self.assertEqual(0, rv, output)
        rv, output = self.execute('session list name00')
        self.assertExpectedResult(output)

    def test_session_set_attr_default_handler(self):
        _prep_session_table(self.env)
        rv, output = \
            self.execute('session set default_handler name00 SearchModule')
        self.assertEqual(0, rv, output)
        rv, output = self.execute('session list name00')
        self.assertExpectedResult(output)

    def test_session_set_attr_default_handler_invalid(self):
        _prep_session_table(self.env)
        rv, output = \
            self.execute('session set default_handler name00 InvalidModule')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_session_set_attr_missing_attr(self):
        rv, output = self.execute('session set')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_session_set_attr_missing_value(self):
        rv, output = self.execute('session set name john')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_session_set_attr_missing_sid(self):
        rv, output = self.execute('session set name')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_session_set_attr_nonexistent_sid(self):
        rv, output = self.execute('session set name john foo')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_session_delete_sid(self):
        _prep_session_table(self.env)
        rv, output = self.execute('session delete name00')
        self.assertEqual(0, rv, output)
        rv, output = self.execute('session list nam00')
        self.assertExpectedResult(output)

    def test_session_delete_missing_params(self):
        rv, output = self.execute('session delete')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_session_delete_anonymous(self):
        _prep_session_table(self.env)
        rv, output = self.execute('session delete anonymous')
        self.assertEqual(0, rv, output)
        rv, output = self.execute('session list *')
        self.assertExpectedResult(output)

    def test_session_delete_multiple_sids(self):
        _prep_session_table(self.env)
        rv, output = self.execute('session delete name00 name01 name02 '
                                   'name03')
        self.assertEqual(0, rv, output)
        rv, output = self.execute('session list *')
        self.assertExpectedResult(output)

    def test_session_purge_age(self):
        _prep_session_table(self.env, spread_visits=True)
        rv, output = self.execute('session purge 20100112')
        self.assertEqual(0, rv, output)
        rv, output = self.execute('session list *')
        self.assertExpectedResult(output)

    def test_session_purge_invalid_date(self):
        rv, output = self.execute('session purge <purge>')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output, {
            'hint': self.datetime_format_hint,
            'isohint': get_datetime_format_hint('iso8601')
        })

    def test_help_session_purge(self):
        doc = self.get_command_help('session', 'purge')
        self.assertIn(u'"YYYY-MM-DDThh:mm:ss±hh:mm"', doc)


class TracadminNoEnvTestCase(TracAdminTestCaseBase):

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

    def setUp(self):
        self.env = EnvironmentStub(enable=['%s.UnicodeHelpCommand' %
                                           self.__module__])
        self.env.clear_component_registry()

    def tearDown(self):
        self.env.restore_component_registry()
        self.env.reset_db()

    def test_unicode_help(self):
        unicode_help = u'Hélp text with unicöde charàcters'

        class UnicodeHelpCommand(Component):
            implements(IAdminCommandProvider)
            def get_admin_commands(self):
                yield ('unicode-help', '', unicode_help,
                       None, self._cmd)
            def _cmd(self):
                pass

        macro = TracAdminHelpMacro(self.env)
        help = unicode(macro.expand_macro(None, None, 'unicode-help'))
        self.assertIn(unicode_help, help)

    def test_invalid_command(self):
        macro = TracAdminHelpMacro(self.env)

        try:
            macro.expand_macro(None, None, 'copystatic')
            self.fail("MacroError not raised")
        except MacroError as e:
            self.assertEqual('Unknown trac-admin command "copystatic"',
                             unicode(e))


class TracAdminComponentTestCase(TracAdminTestCaseBase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True, enable=('trac.*',),
                                   disable=('trac.tests.*',))
        self.admin = TracAdmin()
        self.admin.env_set('', self.env)
        self._orig = {
            'ComponentMeta._components': ComponentMeta._components,
            'ComponentMeta._registry': ComponentMeta._registry,
            'ConfigSection.registry': ConfigSection.registry,
            'Option.registry': Option.registry,
        }
        ComponentMeta._components = list(ComponentMeta._components)
        ComponentMeta._registry = {interface: list(classes)
                                   for interface, classes
                                   in ComponentMeta._registry.iteritems()}
        ConfigSection.registry = {}
        Option.registry = {}

        class CompA(Component):
            from trac.config import Option
            opt1 = Option('compa', 'opt1', 1)
            opt2 = Option('compa', 'opt2', 2)

    def tearDown(self):
        self.env = None
        self.admin = None
        ComponentMeta._components = self._orig['ComponentMeta._components']
        ComponentMeta._registry = self._orig['ComponentMeta._registry']
        ConfigSection.registry = self._orig['ConfigSection.registry']
        Option.registry = self._orig['Option.registry']

    def test_config_component_enable(self):
        self.env.config.save()
        initial_file = copy.deepcopy(self.env.config.parser)

        rv, output = self.execute('config set components '
                                   'trac.admin.tests.console.* enabled')

        self.assertEqual(0, rv, output)
        self.assertFalse(initial_file.has_section('compa'))
        self.assertIn('compa', self.env.config)
        self.assertIn('1', self.env.config.parser.get('compa', 'opt1'))
        self.assertIn('2', self.env.config.parser.get('compa', 'opt2'))


class TracAdminInitenvTestCase(TracAdminTestCaseBase):

    def setUp(self):
        self.parent_dir = mkdtemp()
        self.env_path = os.path.join(self.parent_dir, 'trac')
        self.admin = TracAdmin(self.env_path)

    def tearDown(self):
        if os.path.isfile(os.path.join(self.env_path, 'VERSION')):
            self.admin.env.shutdown()
        shutil.rmtree(self.parent_dir)

    def test_config_argument(self):
        """Options contained in file specified by the --config argument
        are written to trac.ini.
        """
        config_file = os.path.join(self.parent_dir, 'config.ini')
        create_file(config_file, """\
[the-plugin]
option_a = 1
option_b = 2
[components]
the_plugin.* = enabled
[project]
name = project2
        """)
        rv, output = self.execute('initenv project1 sqlite:db/sqlite.db '
                                   '--config=%s' % config_file)
        env = Environment(self.env_path)
        cfile = env.config.parser

        self.assertEqual(0, rv, output)
        self.assertEqual('1', cfile.get('the-plugin', 'option_a'))
        self.assertEqual('2', cfile.get('the-plugin', 'option_b'))
        self.assertEqual('enabled', cfile.get('components', 'the_plugin.*'))
        self.assertEqual('project1', cfile.get('project', 'name'))
        self.assertEqual('sqlite:db/sqlite.db', cfile.get('trac', 'database'))
        for (section, name), option in \
                Option.get_registry(env.compmgr).iteritems():
            if (section, name) not in \
                    (('trac', 'database'), ('project', 'name')):
                self.assertEqual(option.default, cfile.get(section, name))

    def test_config_argument_has_invalid_path(self):
        """Exception is raised when --config argument is an invalid path."""
        config_file = os.path.join(self.parent_dir, 'config.ini')
        rv, output = self.execute('initenv project1 sqlite:db/sqlite.db '
                                   '--config=%s' % config_file)

        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output, {
            'env_path': self.env_path,
            'config_file': config_file,
        })

    def test_config_argument_has_invalid_value(self):
        """Exception is raised when --config argument specifies a malformed
        configuration file.
        """
        config_file = os.path.join(self.parent_dir, 'config.ini')
        create_file(config_file, """\
[the-plugin]
option_a = 1
[components
the_plugin.* = enabled
        """)
        rv, output = self.execute('initenv project1 sqlite:db/sqlite.db '
                                   '--config=%s' % config_file)

        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output, {
            'env_path': self.env_path,
            'config_file': config_file,
        })


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TracadminTestCase))
    suite.addTest(unittest.makeSuite(TracadminNoEnvTestCase))
    suite.addTest(unittest.makeSuite(TracAdminHelpMacroTestCase))
    if __name__ == 'trac.admin.tests.console':
        suite.addTest(unittest.makeSuite(TracAdminComponentTestCase))
    else:
        print("SKIP: trac.admin.tests.console.TracAdminComponentTestCase "
              "(__name__ is not trac.admin.tests.console)")
    suite.addTest(unittest.makeSuite(TracAdminInitenvTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
