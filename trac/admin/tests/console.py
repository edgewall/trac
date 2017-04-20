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
import difflib
import inspect
import os
import re
import sys
import tempfile
import unittest
from subprocess import PIPE, Popen
from StringIO import StringIO

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

from trac.admin.api import AdminCommandManager, IAdminCommandProvider, \
                           console_date_format, get_console_locale
from trac.admin.console import TracAdmin, TracAdminHelpMacro, _run
from trac.config import ConfigSection, Option
from trac.core import Component, ComponentMeta, implements
from trac.env import Environment
from trac.test import EnvironmentStub, rmtree
from trac.util import create_file
from trac.util.compat import close_fds
from trac.util.datefmt import format_date, get_date_format_hint, \
                              get_datetime_format_hint
from trac.util.translation import get_available_locales, has_babel
from trac.web.tests.session import _prep_session_table
from trac.wiki.formatter import MacroError

STRIP_TRAILING_SPACE = re.compile(r'( +)$', re.MULTILINE)


def load_expected_results(file, pattern):
    """Reads the file, named file, which contains test results separated by the
    regular expression pattern.

    The test results are returned as a dictionary.
    """
    expected = {}
    compiled_pattern = re.compile(pattern)
    with open(file, 'r') as f:
        for line in f:
            line = line.rstrip().decode('utf-8')
            match = compiled_pattern.search(line)
            if match:
                test = match.groups()[0]
                expected[test] = ''
            else:
                expected[test] += line + '\n'
    return expected


def _execute(func, strip_trailing_space=True, input=None):
    _in = sys.stdin
    _err = sys.stderr
    _out = sys.stdout
    try:
        if input:
            sys.stdin = StringIO(input.encode('utf-8'))
            sys.stdin.encoding = 'utf-8' # fake input encoding
        sys.stderr = sys.stdout = out = StringIO()
        out.encoding = 'utf-8' # fake output encoding
        retval = func()
        value = out.getvalue()
        if isinstance(value, str): # reverse what print_listing did
            value = value.decode('utf-8')
        if strip_trailing_space:
            return retval, STRIP_TRAILING_SPACE.sub('', value)
        else:
            return retval, value
    finally:
        sys.stdin = _in
        sys.stderr = _err
        sys.stdout = _out


def execute_cmd(tracadmin, cmd, strip_trailing_space=True, input=None):
    def func():
        try:
            return tracadmin.onecmd(cmd)
        except SystemExit:
            return None
    return _execute(func, strip_trailing_space, input)


def execute_run(args):
    def func():
        try:
            return _run(args)
        except SystemExit:
            return None
    return _execute(func)


class TracAdminTestCaseBase(unittest.TestCase):

    expected_results_file = os.path.join(os.path.dirname(__file__),
                                         'console-tests.txt')

    expected_results = load_expected_results(expected_results_file,
                                             '===== (test_[^ ]+) =====')

    def _execute(self, cmd, strip_trailing_space=True, input=None):
        return execute_cmd(self._admin, cmd,
                           strip_trailing_space=strip_trailing_space,
                           input=input)

    def assertExpectedResult(self, output, args=None):
        test_name = inspect.stack()[1][3]
        expected_result = self.expected_results[test_name]
        if args is not None:
            expected_result %= args
        self.assertEqual(expected_result, output)

    def assertEqual(self, expected_results, output, msg=None):
        """:deprecated: since 1.0.2, use `assertExpectedResult` instead."""
        if not (isinstance(expected_results, basestring) and
                isinstance(output, basestring)):
            return unittest.TestCase.assertEqual(self, expected_results,
                                                 output, msg)
        def diff():
            # Create a useful delta between the output and the expected output
            output_lines = ['%s\n' % x for x in output.split('\n')]
            expected_lines = ['%s\n' % x for x in expected_results.split('\n')]
            return ''.join(difflib.unified_diff(expected_lines, output_lines,
                                                'expected', 'actual'))

        if '[...]' in expected_results:
            m = re.match('.*'.join(map(re.escape,
                                       expected_results.split('[...]'))) +
                         '\Z',
                         output, re.DOTALL)
            unittest.TestCase.assertTrue(self, m,
                                         "%r != %r\n%s" % (expected_results,
                                                           output, diff()))
        else:
            unittest.TestCase.assertEqual(self, expected_results, output,
                                          "%r != %r\n%s" % (expected_results,
                                                            output, diff()))


class TracadminTestCase(TracAdminTestCaseBase):
    """
    Tests the output of trac-admin and is meant to be used with
    .../trac/tests.py.
    """

    def setUp(self):
        self.env = EnvironmentStub(default_data=True, enable=('trac.*',),
                                   disable=('trac.tests.*',))
        self._admin = TracAdmin()
        self._admin.env_set('', self.env)
        self.environ = os.environ.copy()

        # Set test date to 11th Jan 2004
        self._test_date = '2004-01-11'

    def tearDown(self):
        self.env = None
        for name in set(os.environ) - set(self.environ):
            del os.environ[name]
        os.environ.update(self.environ)

    @property
    def _datetime_format_hint(self):
        return get_datetime_format_hint(get_console_locale(self.env))

    def _get_command_help(self, *args):
        docs = AdminCommandManager(self.env).get_command_help(list(args))
        self.assertEqual(1, len(docs))
        return docs[0][2]

    def _complete_command(self, *args):
        return AdminCommandManager(self.env).complete_command(list(args))

    def test_python_with_optimizations_returns_error(self):
        """Error is returned when a command is executed in interpreter
        with optimizations enabled.
        """
        proc = Popen((sys.executable, '-O', '-m', 'trac.admin.console',
                      'help'), stdin=PIPE, stdout=PIPE, stderr=PIPE,
                     close_fds=close_fds)
        stdout, stderr = proc.communicate(input='')
        for f in (proc.stdin, proc.stdout, proc.stderr):
            f.close()
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
        rv, output = self._execute('help')
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
            self.assertEqual(None, get_console_locale(None, None))
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
            self.assertEqual(None, get_console_locale())
            self.assertEqual(de, get_console_locale(self.env))
            os.environ['LANG'] = '****'  # invalid locale
            self.assertEqual(None, get_console_locale())
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
            self.assertEqual(None, get_console_locale(None, 'de_DE.UTF8'))
            self.env.config.set('trac', 'default_language', 'de')
            self.assertEqual(None, get_console_locale(self.env, None))
            self.assertEqual(None, get_console_locale(self.env, 'C'))
            self.assertEqual(None, get_console_locale(self.env,
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
        self.assertEqual(None, get_console_locale(None, 'en_US.UTF8'))
        self.env.config.set('trac', 'default_language', '')
        self.assertEqual(None, get_console_locale(self.env, 'en_US.UTF8'))
        self.assertEqual(None, get_console_locale(self.env))
        self.env.config.set('trac', 'default_language', 'en_US')
        self.assertEqual(None, get_console_locale(self.env, 'en_US.UTF8'))
        self.assertEqual(None, get_console_locale(self.env))

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
        rv, output = self._execute('attachment list wiki:WikiStart')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_attachment_add_nonexistent_resource(self):
        """Tests the 'attachment add' command in trac-admin, on a non-existent
        resource."""
        rv, output = self._execute('attachment add wiki:NonExistentPage "%s"'
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
        rv, output = self._execute('config get project name')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_config_set(self):
        """
        Tests the 'config set' command in trac-admin.  This particular
        test sets the project name using an option value containing a space.
        """
        rv, output = self._execute('config set project name "Test project"')
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
        rv, output = self._execute('config remove project name')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)
        self.assertEqual('My Project', self.env.config.get('project', 'name'))

    # Permission tests

    def test_permission_list_ok(self):
        """
        Tests the 'permission list' command in trac-admin.  Since this command
        has no command arguments, it is hard to call it incorrectly.  As
        a result, there is only this one test.
        """
        rv, output = self._execute('permission list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_permission_add_one_action_ok(self):
        """
        Tests the 'permission add' command in trac-admin.  This particular
        test passes valid arguments to add one permission and checks for
        success.
        """
        self._execute('permission add test_user WIKI_VIEW')
        rv, output = self._execute('permission list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_permission_add_multiple_actions_ok(self):
        """
        Tests the 'permission add' command in trac-admin.  This particular
        test passes valid arguments to add multiple permissions and checks for
        success.
        """
        self._execute('permission add test_user LOG_VIEW FILE_VIEW')
        rv, output = self._execute('permission list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_permission_add_already_exists(self):
        """
        Tests the 'permission add' command in trac-admin.  This particular
        test passes a permission that already exists and checks for the
        message. Other permissions passed are added.
        """
        rv, output = self._execute('permission add anonymous WIKI_CREATE '
                                   'WIKI_VIEW WIKI_MODIFY')
        self.assertEqual(0, rv, output)
        rv, output2 = self._execute('permission list')
        self.assertEqual(0, rv, output2)
        self.assertExpectedResult(output + output2)

    def test_permission_add_differs_from_action_by_casing(self):
        """
        Tests the 'permission add' command in trac-admin.  This particular
        test passes a permission that differs from an action by casing and
        checks for the message.
        """
        rv, output = self._execute('permission add anonymous Trac_Admin')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_permission_add_unknown_action(self):
        """
        Tests the 'permission add' command in trac-admin.  This particular
        test tries granting NOT_A_PERM to a user. NOT_A_PERM does not exist
        in the system."""
        rv, output = self._execute('permission add joe NOT_A_PERM')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_permission_remove_one_action_ok(self):
        """
        Tests the 'permission remove' command in trac-admin.  This particular
        test passes valid arguments to remove one permission and checks for
        success.
        """
        self._execute('permission remove anonymous TICKET_MODIFY')
        rv, output = self._execute('permission list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_permission_remove_multiple_actions_ok(self):
        """
        Tests the 'permission remove' command in trac-admin.  This particular
        test passes valid arguments to remove multiple permission and checks
        for success.
        """
        self._execute('permission remove anonymous WIKI_CREATE WIKI_MODIFY')
        rv, output = self._execute('permission list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_permission_remove_all_actions_for_user(self):
        """
        Tests the 'permission remove' command in trac-admin.  This particular
        test removes all permissions for anonymous.
        """
        self._execute('permission remove anonymous *')
        rv, output = self._execute('permission list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_permission_remove_action_for_all_users(self):
        """
        Tests the 'permission remove' command in trac-admin.  This particular
        test removes the TICKET_CREATE permission from all users.
        """
        self._execute('permission add anonymous TICKET_CREATE')
        self._execute('permission remove * TICKET_CREATE')
        rv, output = self._execute('permission list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_permission_remove_unknown_user(self):
        """
        Tests the 'permission remove' command in trac-admin.  This particular
        test tries removing a permission from an unknown user.
        """
        rv, output = self._execute('permission remove joe TICKET_VIEW')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_permission_remove_action_not_granted(self):
        """
        Tests the 'permission remove' command in trac-admin.  This particular
        test tries removing TICKET_CREATE from user anonymous, who doesn't
        have that permission.
        """
        rv, output = self._execute('permission remove anonymous TICKET_CREATE')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_permission_remove_action_granted_through_meta_permission(self):
        """
        Tests the 'permission remove' command in trac-admin.  This particular
        test tries removing WIKI_VIEW from a user. WIKI_VIEW has been granted
        through user anonymous."""
        self._execute('permission add joe TICKET_VIEW')
        rv, output = self._execute('permission remove joe WIKI_VIEW')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_permission_remove_unknown_action(self):
        """
        Tests the 'permission remove' command in trac-admin.  This particular
        test tries removing NOT_A_PERM from a user. NOT_A_PERM does not exist
        in the system."""
        rv, output = self._execute('permission remove joe NOT_A_PERM')
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
        rv, output = self._execute('permission remove joe NOT_A_PERM')
        self.assertEqual(0, rv, output)
        rv, output = self._execute('permission list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_permission_export_ok(self):
        """
        Tests the 'permission export' command in trac-admin.  This particular
        test exports the default permissions to stdout.
        """
        rv, output = self._execute('permission export')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_permission_import_ok(self):
        """
        Tests the 'permission import' command in trac-admin.  This particular
        test exports additional permissions, removes them and imports them back.
        """
        user = u'test_user\u0250'
        self._execute('permission add ' + user + ' WIKI_VIEW')
        self._execute('permission add ' + user + ' TICKET_VIEW')
        rv, output = self._execute('permission export')
        self._execute('permission remove ' + user + ' *')
        rv, output = self._execute('permission import', input=output)
        self.assertEqual(0, rv, output)
        self.assertEqual('', output)
        rv, output = self._execute('permission list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    # Component tests

    def test_component_list_ok(self):
        """
        Tests the 'component list' command in trac-admin.  Since this command
        has no command arguments, it is hard to call it incorrectly.  As
        a result, there is only this one test.
        """
        rv, output = self._execute('component list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_component_add_ok(self):
        """
        Tests the 'component add' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        self._execute('component add new_component')
        rv, output = self._execute('component list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_component_add_optional_owner_ok(self):
        """
        Tests the 'component add' command in trac-admin with the optional
        'owner' argument.  This particular test passes valid arguments and
        checks for success.
        """
        self._execute('component add new_component new_user')
        rv, output = self._execute('component list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_component_add_complete_optional_owner_restrict_owner_false(self):
        """Tests completion of the 'component add <component>' command with
        [ticket] restrict_owner = false.
        """
        self._execute('config set ticket restrict_owner false')
        self._execute('session add user1')
        self._execute('session add user3')
        self._execute('permission add user1 TICKET_MODIFY')
        self._execute('permission add user2 TICKET_VIEW')
        self._execute('permission add user3 TICKET_MODIFY')
        output = self._complete_command('component', 'add',
                                        'new_component', '')
        self.assertEqual([], output)

    def test_component_add_complete_optional_owner_restrict_owner_true(self):
        """Tests completion of the 'component add <component>' command with
        [ticket] restrict_owner = true.
        """
        self._execute('config set ticket restrict_owner true')
        self._execute('session add user1')
        self._execute('session add user3')
        self._execute('permission add user1 TICKET_MODIFY')
        self._execute('permission add user2 TICKET_VIEW')
        self._execute('permission add user3 TICKET_MODIFY')
        output = self._complete_command('component', 'add',
                                        'new_component', '')
        self.assertEqual(['user1', 'user3'], output)

    def test_component_add_error_already_exists(self):
        """
        Tests the 'component add' command in trac-admin.  This particular
        test passes a component name that already exists and checks for an
        error message.
        """
        rv, output = self._execute('component add component1 new_user')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_component_rename_ok(self):
        """
        Tests the 'component rename' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        self._execute('component rename component1 changed_name')
        rv, output = self._execute('component list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_component_rename_error_bad_component(self):
        """
        Tests the 'component rename' command in trac-admin.  This particular
        test tries to rename a component that does not exist.
        """
        rv, output = self._execute('component rename bad_component changed_name')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_component_rename_error_bad_new_name(self):
        """
        Tests the 'component rename' command in trac-admin.  This particular
        test tries to rename a component to a name that already exists.
        """
        rv, output = self._execute('component rename component1 component2')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_component_chown_ok(self):
        """
        Tests the 'component chown' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        self._execute('component chown component2 changed_owner')
        rv, output = self._execute('component list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_component_chown_complete_component(self):
        """Tests completion of the 'component chown' command.
        """
        output = self._complete_command('component', 'chown', '')
        self.assertEqual(['component1', 'component2'], output)

    def test_component_chown_complete_owner_restrict_owner_false(self):
        """Tests completion of the 'component chown <component>' command with
        [ticket] restrict_owner = false.
        """
        self._execute('config set ticket restrict_owner false')
        self._execute('session add user1')
        self._execute('session add user3')
        self._execute('permission add user1 TICKET_MODIFY')
        self._execute('permission add user2 TICKET_VIEW')
        self._execute('permission add user3 TICKET_MODIFY')
        output = self._complete_command('component', 'chown', 'component1', '')
        self.assertEqual([], output)

    def test_component_chown_complete_owner_restrict_owner_true(self):
        """Tests completion of the 'component chown <component>' command with
        [ticket] restrict_owner = true.
        """
        self._execute('config set ticket restrict_owner true')
        self._execute('session add user1')
        self._execute('session add user3')
        self._execute('permission add user1 TICKET_MODIFY')
        self._execute('permission add user2 TICKET_VIEW')
        self._execute('permission add user3 TICKET_MODIFY')
        output = self._complete_command('component', 'chown', 'component1', '')
        self.assertEqual(['user1', 'user3'], output)

    def test_component_chown_error_bad_component(self):
        """
        Tests the 'component chown' command in trac-admin.  This particular
        test tries to change the owner of a component that does not
        exist.
        """
        rv, output = self._execute('component chown bad_component changed_owner')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_component_remove_ok(self):
        """
        Tests the 'component remove' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """
        self._execute('component remove component1')
        rv, output = self._execute('component list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_component_remove_error_bad_component(self):
        """
        Tests the 'component remove' command in trac-admin.  This particular
        test tries to remove a component that does not exist.
        """
        rv, output = self._execute('component remove bad_component')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    # Ticket-type tests

    def test_ticket_type_list_ok(self):
        """
        Tests the 'ticket_type list' command in trac-admin.  Since this command
        has no command arguments, it is hard to call it incorrectly.  As
        a result, there is only this one test.
        """
        rv, output = self._execute('ticket_type list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_ticket_type_add_ok(self):
        """
        Tests the 'ticket_type add' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """
        self._execute('ticket_type add new_type')
        rv, output = self._execute('ticket_type list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_ticket_type_add_error_already_exists(self):
        """
        Tests the 'ticket_type add' command in trac-admin.  This particular
        test passes a ticket type that already exists and checks for an error
        message.
        """
        rv, output = self._execute('ticket_type add defect')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_ticket_type_change_ok(self):
        """
        Tests the 'ticket_type change' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        self._execute('ticket_type change defect bug')
        rv, output = self._execute('ticket_type list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_ticket_type_change_error_bad_type(self):
        """
        Tests the 'ticket_type change' command in trac-admin.  This particular
        test tries to change a priority that does not exist.
        """
        rv, output = self._execute('ticket_type change bad_type changed_type')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_ticket_type_change_error_bad_new_name(self):
        """
        Tests the 'ticket_type change' command in trac-admin.  This particular
        test tries to change a ticket type to another type that already exists.
        """
        rv, output = self._execute('ticket_type change defect task')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_ticket_type_remove_ok(self):
        """
        Tests the 'ticket_type remove' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """
        self._execute('ticket_type remove task')
        rv, output = self._execute('ticket_type list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_ticket_type_remove_error_bad_type(self):
        """
        Tests the 'ticket_type remove' command in trac-admin.  This particular
        test tries to remove a ticket type that does not exist.
        """
        rv, output = self._execute('ticket_type remove bad_type')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_ticket_type_order_down_ok(self):
        """
        Tests the 'ticket_type order' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """
        self._execute('ticket_type order defect down')
        rv, output = self._execute('ticket_type list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_ticket_type_order_up_ok(self):
        """
        Tests the 'ticket_type order' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """
        self._execute('ticket_type order enhancement up')
        rv, output = self._execute('ticket_type list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_ticket_type_order_error_bad_type(self):
        """
        Tests the 'priority order' command in trac-admin.  This particular
        test tries to reorder a priority that does not exist.
        """
        rv, output = self._execute('ticket_type order bad_type up')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    # Priority tests

    def test_priority_list_ok(self):
        """
        Tests the 'priority list' command in trac-admin.  Since this command
        has no command arguments, it is hard to call it incorrectly.  As
        a result, there is only this one test.
        """
        rv, output = self._execute('priority list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_priority_add_ok(self):
        """
        Tests the 'priority add' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """
        self._execute('priority add new_priority')
        rv, output = self._execute('priority list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_priority_add_many_ok(self):
        """
        Tests adding more than 10 priority values.  This makes sure that
        ordering is preserved when adding more than 10 values.
        """
        for i in xrange(11):
            self._execute('priority add p%s' % i)
        rv, output = self._execute('priority list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_priority_add_error_already_exists(self):
        """
        Tests the 'priority add' command in trac-admin.  This particular
        test passes a priority name that already exists and checks for an
        error message.
        """
        rv, output = self._execute('priority add blocker')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_priority_change_ok(self):
        """
        Tests the 'priority change' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        self._execute('priority change major normal')
        rv, output = self._execute('priority list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_priority_change_error_bad_priority(self):
        """
        Tests the 'priority change' command in trac-admin.  This particular
        test tries to change a priority that does not exist.
        """
        rv, output = self._execute('priority change bad_priority changed_name')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_priority_change_error_bad_new_name(self):
        """
        Tests the 'priority change' command in trac-admin.  This particular
        test tries to change a priority to a name that already exists.
        """
        rv, output = self._execute('priority change major minor')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_priority_remove_ok(self):
        """
        Tests the 'priority remove' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """
        self._execute('priority remove major')
        rv, output = self._execute('priority list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_priority_remove_error_bad_priority(self):
        """
        Tests the 'priority remove' command in trac-admin.  This particular
        test tries to remove a priority that does not exist.
        """
        rv, output = self._execute('priority remove bad_priority')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_priority_order_down_ok(self):
        """
        Tests the 'priority order' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """
        self._execute('priority order blocker down')
        rv, output = self._execute('priority list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_priority_order_up_ok(self):
        """
        Tests the 'priority order' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """
        self._execute('priority order critical up')
        rv, output = self._execute('priority list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_priority_order_error_bad_priority(self):
        """
        Tests the 'priority order' command in trac-admin.  This particular
        test tries to reorder a priority that does not exist.
        """
        rv, output = self._execute('priority remove bad_priority')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    # Severity tests

    def test_severity_list_ok(self):
        """
        Tests the 'severity list' command in trac-admin.  Since this command
        has no command arguments, it is hard to call it incorrectly.  As
        a result, there is only this one test.
        """
        rv, output = self._execute('severity list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_severity_add_ok(self):
        """
        Tests the 'severity add' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """
        self._execute('severity add new_severity')
        rv, output = self._execute('severity list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_severity_add_error_already_exists(self):
        """
        Tests the 'severity add' command in trac-admin.  This particular
        test passes a severity name that already exists and checks for an
        error message.
        """
        self._execute('severity add blocker')
        rv, output = self._execute('severity add blocker')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_severity_change_ok(self):
        """
        Tests the 'severity add' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        self._execute('severity add critical')
        self._execute('severity change critical "end-of-the-world"')
        rv, output = self._execute('severity list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_severity_change_error_bad_severity(self):
        """
        Tests the 'severity change' command in trac-admin.  This particular
        test tries to change a severity that does not exist.
        """
        rv, output = self._execute('severity change bad_severity changed_name')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_severity_change_error_bad_new_name(self):
        """
        Tests the 'severity change' command in trac-admin.  This particular
        test tries to change a severity to a name that already exists.
        """
        self._execute('severity add major')
        self._execute('severity add critical')
        rv, output = self._execute('severity change critical major')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_severity_remove_ok(self):
        """
        Tests the 'severity add' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """
        self._execute('severity remove trivial')
        rv, output = self._execute('severity list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_severity_remove_error_bad_severity(self):
        """
        Tests the 'severity remove' command in trac-admin.  This particular
        test tries to remove a severity that does not exist.
        """
        rv, output = self._execute('severity remove bad_severity')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_severity_order_down_ok(self):
        """
        Tests the 'severity order' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """
        self._execute('severity add foo')
        self._execute('severity add bar')
        self._execute('severity order foo down')
        rv, output = self._execute('severity list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_severity_order_up_ok(self):
        """
        Tests the 'severity order' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """
        self._execute('severity add foo')
        self._execute('severity add bar')
        self._execute('severity order bar up')
        rv, output = self._execute('severity list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_severity_order_error_bad_severity(self):
        """
        Tests the 'severity order' command in trac-admin.  This particular
        test tries to reorder a priority that does not exist.
        """
        rv, output = self._execute('severity remove bad_severity')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    # Version tests

    def test_version_list_ok(self):
        """
        Tests the 'version list' command in trac-admin.  Since this command
        has no command arguments, it is hard to call it incorrectly.  As
        a result, there is only this one test.
        """
        rv, output = self._execute('version list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_version_add_ok(self):
        """
        Tests the 'version add' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        self._execute('version add 9.9 "%s"' % self._test_date)
        rv, output = self._execute('version list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_version_add_error_already_exists(self):
        """
        Tests the 'version add' command in trac-admin.  This particular
        test passes a version name that already exists and checks for an
        error message.
        """
        rv, output = self._execute('version add 1.0 "%s"' % self._test_date)
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_version_rename_ok(self):
        """
        Tests the 'version rename' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        self._execute('version rename 1.0 9.9')
        rv, output = self._execute('version list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_version_rename_error_bad_version(self):
        """
        Tests the 'version rename' command in trac-admin.  This particular
        test tries to rename a version that does not exist.
        """
        rv, output = self._execute('version rename bad_version changed_name')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_version_time_ok(self):
        """
        Tests the 'version time' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        self._execute('version time 2.0 "%s"' % self._test_date)
        rv, output = self._execute('version list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_version_time_unset_ok(self):
        """
        Tests the 'version time' command in trac-admin.  This particular
        test passes valid arguments for unsetting the date.
        """
        self._execute('version time 2.0 "%s"' % self._test_date)
        self._execute('version time 2.0 ""')
        rv, output = self._execute('version list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_version_time_error_bad_version(self):
        """
        Tests the 'version time' command in trac-admin.  This particular
        test tries to change the time on a version that does not exist.
        """
        rv, output = self._execute('version time bad_version "%s"'
                                   % self._test_date)
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_version_remove_ok(self):
        """
        Tests the 'version remove' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """
        self._execute('version remove 1.0')
        rv, output = self._execute('version list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_version_remove_error_bad_version(self):
        """
        Tests the 'version remove' command in trac-admin.  This particular
        test tries to remove a version that does not exist.
        """
        rv, output = self._execute('version remove bad_version')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    # Milestone tests

    def test_milestone_list_ok(self):
        """
        Tests the 'milestone list' command in trac-admin.  Since this command
        has no command arguments, it is hard to call it incorrectly.  As
        a result, there is only this one test.
        """
        rv, output = self._execute('milestone list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_milestone_add_ok(self):
        """
        Tests the 'milestone add' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        self._execute('milestone add new_milestone "%s"' % self._test_date)
        rv, output = self._execute('milestone list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_milestone_add_utf8_ok(self):
        """
        Tests the 'milestone add' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        self._execute(u'milestone add \xa9tat_final "%s"'  #\xc2\xa9
                      % self._test_date)
        rv, output = self._execute('milestone list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_milestone_add_error_already_exists(self):
        """
        Tests the 'milestone add' command in trac-admin.  This particular
        test passes a milestone name that already exists and checks for an
        error message.
        """
        rv, output = self._execute('milestone add milestone1 "%s"'
                                   % self._test_date)
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_milestone_add_invalid_date(self):
        rv, output = self._execute('milestone add new_milestone <add>')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output, {
            'hint': self._datetime_format_hint,
            'isohint': get_datetime_format_hint('iso8601')
        })

    def test_milestone_rename_ok(self):
        """
        Tests the 'milestone rename' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        self._execute('milestone rename milestone1 changed_milestone')
        rv, output = self._execute('milestone list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_milestone_rename_error_bad_milestone(self):
        """
        Tests the 'milestone rename' command in trac-admin.  This particular
        test tries to rename a milestone that does not exist.
        """
        rv, output = self._execute('milestone rename bad_milestone changed_name')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_milestone_due_ok(self):
        """
        Tests the 'milestone due' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        self._execute('milestone due milestone2 "%s"' % self._test_date)
        rv, output = self._execute('milestone list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_milestone_due_unset_ok(self):
        """
        Tests the 'milestone due' command in trac-admin.  This particular
        test passes valid arguments for unsetting the due date.
        """
        self._execute('milestone due milestone2 "%s"' % self._test_date)
        self._execute('milestone due milestone2 ""')
        rv, output = self._execute('milestone list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_milestone_due_error_bad_milestone(self):
        """
        Tests the 'milestone due' command in trac-admin.  This particular
        test tries to change the due date on a milestone that does not exist.
        """
        rv, output = self._execute('milestone due bad_milestone "%s"'
                                   % self._test_date)
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_milestone_due_invalid_date(self):
        rv, output = self._execute('milestone due milestone1 <due>')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output, {
            'hint': self._datetime_format_hint,
            'isohint': get_datetime_format_hint('iso8601')
        })

    def test_milestone_completed_ok(self):
        """
        Tests the 'milestone completed' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        self._execute('milestone completed milestone2 "%s"' % self._test_date)
        rv, output = self._execute('milestone list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_milestone_completed_error_bad_milestone(self):
        """
        Tests the 'milestone completed' command in trac-admin.  This particular
        test tries to change the completed date on a milestone that does not
        exist.
        """
        rv, output = self._execute('milestone completed bad_milestone "%s"'
                                   % self._test_date)
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_milestone_completed_invalid_date(self):
        rv, output = self._execute('milestone completed milestone1 <com>')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output, {
            'hint': self._datetime_format_hint,
            'isohint': get_datetime_format_hint('iso8601')
        })

    def test_milestone_remove_ok(self):
        """
        Tests the 'milestone remove' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """
        self._execute('milestone remove milestone3')
        rv, output = self._execute('milestone list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_milestone_remove_error_bad_milestone(self):
        """
        Tests the 'milestone remove' command in trac-admin.  This particular
        test tries to remove a milestone that does not exist.
        """
        rv, output = self._execute('milestone remove bad_milestone')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_backslash_use_ok(self):
        if self._admin.interactive:
            self._execute('version add \\')
        else:
            self._execute(r"version add '\'")
        rv, output = self._execute('version list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_session_list_no_sessions(self):
        rv, output = self._execute('session list authenticated')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_session_list_authenticated(self):
        _prep_session_table(self.env)
        rv, output = self._execute('session list authenticated')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_session_list_anonymous(self):
        _prep_session_table(self.env)
        rv, output = self._execute('session list anonymous')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_session_list_all(self):
        _prep_session_table(self.env)
        if self._admin.interactive:
            rv, output = self._execute("session list *")
        else:
            rv, output = self._execute("session list '*'")
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_session_list_authenticated_sid(self):
        _prep_session_table(self.env)
        rv, output = self._execute('session list name00')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_session_list_anonymous_sid(self):
        _prep_session_table(self.env)
        rv, output = self._execute('session list name10:0')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_session_list_missing_sid(self):
        _prep_session_table(self.env)
        rv, output = self._execute('session list thisdoesntexist')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_session_add_missing_sid(self):
        rv, output = self._execute('session add')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_session_add_duplicate_sid(self):
        _prep_session_table(self.env)
        rv, output = self._execute('session add name00')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_session_add_sid_all(self):
        rv, output = self._execute('session add john John john@example.org')
        self.assertEqual(0, rv, output)
        rv, output = self._execute('session list john')
        self.assertExpectedResult(output, {
            'today': format_date(None, console_date_format)
        })

    def test_session_add_sid(self):
        rv, output = self._execute('session add john')
        self.assertEqual(0, rv, output)
        rv, output = self._execute('session list john')
        self.assertExpectedResult(output, {
            'today': format_date(None, console_date_format)
        })

    def test_session_add_sid_name(self):
        rv, output = self._execute('session add john John')
        self.assertEqual(0, rv, output)
        rv, output = self._execute('session list john')
        self.assertExpectedResult(output,  {
            'today': format_date(None, console_date_format)
        })

    def test_session_set_attr_name(self):
        _prep_session_table(self.env)
        rv, output = self._execute('session set name name00 JOHN')
        self.assertEqual(0, rv, output)
        rv, output = self._execute('session list name00')
        self.assertExpectedResult(output)

    def test_session_set_attr_email(self):
        _prep_session_table(self.env)
        rv, output = self._execute('session set email name00 JOHN@EXAMPLE.ORG')
        self.assertEqual(0, rv, output)
        rv, output = self._execute('session list name00')
        self.assertExpectedResult(output)

    def test_session_set_attr_default_handler(self):
        _prep_session_table(self.env)
        rv, output = \
            self._execute('session set default_handler name00 SearchModule')
        self.assertEqual(0, rv, output)
        rv, output = self._execute('session list name00')
        self.assertExpectedResult(output)

    def test_session_set_attr_default_handler_invalid(self):
        _prep_session_table(self.env)
        rv, output = \
            self._execute('session set default_handler name00 InvalidModule')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_session_set_attr_missing_attr(self):
        rv, output = self._execute('session set')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_session_set_attr_missing_value(self):
        rv, output = self._execute('session set name john')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_session_set_attr_missing_sid(self):
        rv, output = self._execute('session set name')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_session_set_attr_nonexistent_sid(self):
        rv, output = self._execute('session set name john foo')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_session_delete_sid(self):
        _prep_session_table(self.env)
        rv, output = self._execute('session delete name00')
        self.assertEqual(0, rv, output)
        rv, output = self._execute('session list nam00')
        self.assertExpectedResult(output)

    def test_session_delete_missing_params(self):
        rv, output = self._execute('session delete')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_session_delete_anonymous(self):
        _prep_session_table(self.env)
        rv, output = self._execute('session delete anonymous')
        self.assertEqual(0, rv, output)
        rv, output = self._execute('session list *')
        self.assertExpectedResult(output)

    def test_session_delete_multiple_sids(self):
        _prep_session_table(self.env)
        rv, output = self._execute('session delete name00 name01 name02 '
                                   'name03')
        self.assertEqual(0, rv, output)
        rv, output = self._execute('session list *')
        self.assertExpectedResult(output)

    def test_session_purge_age(self):
        _prep_session_table(self.env, spread_visits=True)
        rv, output = self._execute('session purge 20100112')
        self.assertEqual(0, rv, output)
        rv, output = self._execute('session list *')
        self.assertExpectedResult(output)

    def test_session_purge_invalid_date(self):
        rv, output = self._execute('session purge <purge>')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output, {
            'hint': self._datetime_format_hint,
            'isohint': get_datetime_format_hint('iso8601')
        })

    def test_help_milestone_due(self):
        doc = self._get_command_help('milestone', 'due')
        self.assertIn(self._datetime_format_hint, doc)
        self.assertIn(u'"YYYY-MM-DDThh:mm:ss±hh:mm"', doc)

    def test_help_milestone_completed(self):
        doc = self._get_command_help('milestone', 'completed')
        self.assertIn(self._datetime_format_hint, doc)
        self.assertIn(u'"YYYY-MM-DDThh:mm:ss±hh:mm"', doc)

    def test_help_version_time(self):
        doc = self._get_command_help('version', 'time')
        self.assertIn(self._datetime_format_hint, doc)
        self.assertIn(u'"YYYY-MM-DDThh:mm:ss±hh:mm"', doc)

    def test_help_session_purge(self):
        doc = self._get_command_help('session', 'purge')
        self.assertIn(u'"YYYY-MM-DDThh:mm:ss±hh:mm"', doc)

    def test_changeset_add_no_repository_revision(self):
        rv, output = self._execute('changeset added')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_changeset_add_no_revision(self):
        rv, output = self._execute('changeset added repos')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_changeset_modify_no_repository_revision(self):
        rv, output = self._execute('changeset modified')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_changeset_modify_no_revision(self):
        rv, output = self._execute('changeset modified repos')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_changeset_add_invalid_repository(self):
        rv, output = self._execute('changeset added repos 123')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_changeset_modify_invalid_repository(self):
        rv, output = self._execute('changeset modified repos 123')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)


class TracadminNoEnvTestCase(unittest.TestCase):

    def setUp(self):
        self._admin = TracAdmin()

    def tearDown(self):
        self._admin = None

    def _execute(self, cmd, strip_trailing_space=True, input=None):
        return execute_cmd(self._admin, cmd,
                           strip_trailing_space=strip_trailing_space,
                           input=input)

    def test_help(self):
        rv, output = self._execute('help')
        output = output.splitlines()
        self.assertEqual('', output[-3])
        self.assertEqual('help     Show documentation', output[-2])
        self.assertEqual('initenv  Create and initialize a new environment',
                         output[-1])

    def test_help_with_nocmd(self):
        rv, output = self._execute('help nocmd')
        output = output.splitlines()
        self.assertEqual(["No documentation found for 'nocmd'. Use 'help' to "
                          "see the list of commands."],
                          output)

    def test_run_help_with_arguments(self):
        rv, output = execute_run(['help'])
        self.assertIn('Usage: trac-admin </path/to/projenv>', output)
        rv, output = execute_run(['help', "foo'bar"])
        self.assertNotIn('No closing quotation', output)
        self.assertIn("No documentation found for 'foo'bar'", output)

    def test_run_cmd_with_env_path(self):
        rv, output = execute_run(['notfound-tracenv', 'help'])
        self.assertIn('Usage: trac-admin </path/to/projenv>', output)
        rv, output = execute_run(['notfound-tracenv', 'help', "foo'bar"])
        self.assertNotIn('No closing quotation', output)
        self.assertIn("No documentation found for 'foo'bar'", output)


class TracAdminHelpMacroTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(enable=['%s.UnicodeHelpCommand' %
                                           self.__module__])

    def tearDown(self):
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
        self.assertTrue(unicode_help in help)

    def test_invalid_command(self):
        macro = TracAdminHelpMacro(self.env)

        try:
            macro.expand_macro(None, None, 'copystatic')
            self.fail("MacroError not raised")
        except MacroError as e:
            self.assertEqual('Unknown trac-admin command "copystatic"',
                             unicode(e))


class TracAdminComponentTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True, enable=('trac.*',),
                                   disable=('trac.tests.*',))
        self._admin = TracAdmin()
        self._admin.env_set('', self.env)
        self._orig = {
            'ComponentMeta._components': ComponentMeta._components,
            'ComponentMeta._registry': ComponentMeta._registry,
            'ConfigSection.registry': ConfigSection.registry,
            'Option.registry': Option.registry,
        }
        ComponentMeta._components = list(ComponentMeta._components)
        ComponentMeta._registry = dict((interface, list(classes))
                                       for interface, classes
                                       in ComponentMeta._registry.iteritems())
        ConfigSection.registry = {}
        Option.registry = {}

        class CompA(Component):
            from trac.config import Option
            opt1 = Option('compa', 'opt1', 1)
            opt2 = Option('compa', 'opt2', 2)

    def tearDown(self):
        self.env = None
        self._admin = None
        ComponentMeta._components = self._orig['ComponentMeta._components']
        ComponentMeta._registry = self._orig['ComponentMeta._registry']
        ConfigSection.registry = self._orig['ConfigSection.registry']
        Option.registry = self._orig['Option.registry']

    def _execute(self, cmd, strip_trailing_space=True, input=None):
        return execute_cmd(self._admin, cmd,
                           strip_trailing_space=strip_trailing_space,
                           input=input)

    def test_config_component_enable(self):
        self.env.config.save()
        initial_file = copy.deepcopy(self.env.config.parser)

        rv, output = self._execute('config set components '
                                   'trac.admin.tests.console.* enabled')

        self.assertEqual(0, rv, output)
        self.assertFalse(initial_file.has_section('compa'))
        self.assertIn('compa', self.env.config)
        self.assertIn('1', self.env.config.parser.get('compa', 'opt1'))
        self.assertIn('2', self.env.config.parser.get('compa', 'opt2'))


class TracAdminInitenvTestCase(TracAdminTestCaseBase):

    def setUp(self):
        self.parent_dir = tempfile.mkdtemp()
        self.env_path = os.path.join(self.parent_dir, 'trac')
        self._admin = TracAdmin(self.env_path)

    def tearDown(self):
        if os.path.isfile(os.path.join(self.env_path, 'VERSION')):
            self._admin.env.shutdown()
        rmtree(self.parent_dir)

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
        rv, output = self._execute('initenv project1 sqlite:db/sqlite.db '
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
        rv, output = self._execute('initenv project1 sqlite:db/sqlite.db '
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
        rv, output = self._execute('initenv project1 sqlite:db/sqlite.db '
                                   '--config=%s' % config_file)

        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output, {
            'env_path': self.env_path,
            'config_file': config_file,
        })


class TracAdminDeployTestCase(TracAdminTestCaseBase):
    """Tests for the trac-admin deploy command."""

    def setUp(self):
        self.env = Environment(path=tempfile.mkdtemp(), create=True)
        self._admin = TracAdmin(self.env.path)
        self._admin.env_set('', self.env)

    def tearDown(self):
        self.env.shutdown()  # really closes the db connections
        rmtree(self.env.path)

    def test_deploy(self):
        """Deploy into valid target directory."""
        target = os.path.join(self.env.path, 'www')
        htdocs_dir = os.path.join(target, 'htdocs')

        rv, output = self._execute('deploy %s' % target)

        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)
        self.assertTrue(os.path.exists(os.path.join(target, 'cgi-bin')))
        self.assertTrue(os.path.exists(htdocs_dir))
        self.assertTrue(os.path.exists(os.path.join(htdocs_dir, 'common')))
        self.assertTrue(os.path.exists(os.path.join(htdocs_dir, 'site')))

    def test_deploy_to_invalid_target_raises_error(self):
        """Running deploy with target directory equal to or below the source
        directory raises AdminCommandError.
        """
        rv, output = self._execute('deploy %s' % self.env.htdocs_dir)

        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)


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
    suite.addTest(unittest.makeSuite(TracAdminDeployTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
