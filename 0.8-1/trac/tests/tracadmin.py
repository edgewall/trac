#!/usr/bin/env python

__author__ = 'Tim Moloney <t.moloney@verizon.net>'
__copyright__ = 'Copyright (c) 2004 Edgewall Software'
__license__ = """
 Copyright (C) 2003, 2004 Edgewall Software
 Copyright (C) 2004 Tim Moloney <t.moloney@verizon.net>

 Trac is free software; you can redistribute it and/or
 modify it under the terms of the GNU General Public License as
 published by the Free Software Foundation; either version 2 of
 the License, or (at your option) any later version.

 Trac is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU General Public License for more details.

 You should have received a copy of the GNU General Public License
 along with this program; if not, write to the Free Software
 Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA."""


import os
import re
import sys
import time
import unittest

import trac
from trac.db_default import data as default_data
from trac.util import NaivePopen
from environment import EnvironmentTestBase


def load_expected_results(file, pattern):

    """
    Reads the file, named file, which contains test results separated by
    the a regular expression, pattern.  The test results are returned as
    a dictionary.
    """

    expected = {}
    compiled_pattern = re.compile(pattern)
    data = open(file, 'r').read()
    for line in data.split('\n'):
        match = re.search(compiled_pattern, line)
        if match:
            test = match.groups()[0]
            expected[test] = ''
        else:
            expected[test] += line + '\n'
    expected[test] = expected[test][:-1]
    return expected


class TracadminTestCase(EnvironmentTestBase, unittest.TestCase):

    """
    Tests the output of trac-admin and is meant to be used with
    .../trac/tests.py.
    """

    def __init__(self, method_name):

        """
        Loads the expected test results in addition to the normal
        initialization done by unittest.TestCase.
        """

        unittest.TestCase.__init__(self, method_name)
        self.expected_results = \
            load_expected_results(os.path.join(os.path.split(__file__)[0],
                                               'tracadmin-tests.txt'),
                                  '===== (test_.*) =====')

    #
    #  about test
    #
    def test_about(self):

        """
        Tests the 'about' command in trac-admin.  Since the 'about' command
        has no command arguments, it is hard to call it incorrectly.  As
        a result, there is only this one test.
        """

        expected_results = """
Trac Admin Console %s
=================================================================
%s
%s
""" % (trac.__version__, trac.__license_long__, trac.__credits__)
        cmd = 'about'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == expected_results

    #
    #  help test
    #
    def test_help_ok(self):

        """
        Tests the 'help' command in trac-admin.  Since the 'help' command
        has no command arguments, it is hard to call it incorrectly.  As
        a result, there is only this one test.
        """

        test_name = sys._getframe().f_code.co_name
        expected_results = self.expected_results[test_name] % trac.__version__
        cmd = 'help'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == expected_results

    #
    #  permission tests
    #
    def test_permission_list_ok(self):

        """
        Tests the 'permission list' command in trac-admin.  Since this command
        has no command arguments, it is hard to call it incorrectly.  As
        a result, there is only this one test.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'permission list'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_permission_add_one_action_ok(self):

        """
        Tests the 'permission add' command in trac-admin.  This particular
        test passes valid arguments to add one permission and checks for
        success.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'permission add test_user WIKI_VIEW'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        cmd = 'permission list'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_permission_add_multiple_actions_ok(self):

        """
        Tests the 'permission add' command in trac-admin.  This particular
        test passes valid arguments to add multiple permissions and checks for
        success.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'permission add test_user LOG_VIEW FILE_VIEW'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        cmd = 'permission list'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_permission_remove_one_action_ok(self):

        """
        Tests the 'permission remove' command in trac-admin.  This particular
        test passes valid arguments to remove one permission and checks for
        success.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'permission remove anonymous TICKET_MODIFY'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        cmd = 'permission list'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_permission_remove_multiple_actions_ok(self):

        """
        Tests the 'permission remove' command in trac-admin.  This particular
        test passes valid arguments to remove multiple permission and checks
        for success.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'permission remove anonymous WIKI_CREATE WIKI_MODIFY'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        cmd = 'permission list'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    #
    #  component tests
    #
    def test_component_list_ok(self):

        """
        Tests the 'component list' command in trac-admin.  Since this command
        has no command arguments, it is hard to call it incorrectly.  As
        a result, there is only this one test.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'component list'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_component_add_ok(self):

        """
        Tests the 'component add' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'component add new_component new_user'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        cmd = 'component list'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_component_add_error_already_exists(self):

        """
        Tests the 'component add' command in trac-admin.  This particular
        test passes a component name that already exists and checks for an
        error message.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'component add component1 new_user'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_component_rename_ok(self):

        """
        Tests the 'component rename' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'component rename component1 changed_name'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        cmd = 'component list'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_component_rename_error_bad_component(self):

        """
        Tests the 'component rename' command in trac-admin.  This particular
        test tries to rename a component that does not exist.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'component rename bad_component changed_name'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_component_rename_error_bad_new_name(self):

        """
        Tests the 'component rename' command in trac-admin.  This particular
        test tries to rename a component to a name that already exists.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'component rename component1 component2'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_component_chown_ok(self):

        """
        Tests the 'component chown' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'component chown component2 changed_owner'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        cmd = 'component list'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_component_chown_error_bad_component(self):

        """
        Tests the 'component chown' command in trac-admin.  This particular
        test tries to change the owner of a component that does not
        exist.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'component chown bad_component changed_owner'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_component_remove_ok(self):

        """
        Tests the 'component remove' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'component remove component1'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        cmd = 'component list'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_component_remove_error_bad_component(self):

        """
        Tests the 'component remove' command in trac-admin.  This particular
        test tries to remove a component that does not exist.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'component remove bad_component'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    #
    #  priority tests
    #
    def test_priority_list_ok(self):

        """
        Tests the 'priority list' command in trac-admin.  Since this command
        has no command arguments, it is hard to call it incorrectly.  As
        a result, there is only this one test.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'priority list'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_priority_add_ok(self):

        """
        Tests the 'priority add' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'priority add new_priority'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        cmd = 'priority list'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_priority_add_error_already_exists(self):

        """
        Tests the 'priority add' command in trac-admin.  This particular
        test passes a priority name that already exists and checks for an
        error message.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'priority add highest'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_priority_change_ok(self):

        """
        Tests the 'priority change' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'priority change normal abby_normal'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        cmd = 'priority list'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_priority_change_error_bad_priority(self):

        """
        Tests the 'priority change' command in trac-admin.  This particular
        test tries to change a priority that does not exist.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'priority change bad_priority changed_name'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_priority_change_error_bad_new_name(self):

        """
        Tests the 'priority change' command in trac-admin.  This particular
        test tries to change a priority to a name that already exists.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'priority change highest high'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_priority_remove_ok(self):

        """
        Tests the 'priority remove' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'priority remove low'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        cmd = 'priority list'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_priority_remove_error_bad_priority(self):

        """
        Tests the 'priority remove' command in trac-admin.  This particular
        test tries to remove a priority that does not exist.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'priority remove bad_priority'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    #
    #  severity tests
    #
    def test_severity_list_ok(self):

        """
        Tests the 'severity list' command in trac-admin.  Since this command
        has no command arguments, it is hard to call it incorrectly.  As
        a result, there is only this one test.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'severity list'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_severity_add_ok(self):

        """
        Tests the 'severity add' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'severity add new_severity'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        cmd = 'severity list'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_severity_add_error_already_exists(self):

        """
        Tests the 'severity add' command in trac-admin.  This particular
        test passes a severity name that already exists and checks for an
        error message.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'severity add blocker'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name], test_results

    def test_severity_change_ok(self):

        """
        Tests the 'severity add' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'severity change critical end-of-the-world'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        cmd = 'severity list'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_severity_change_error_bad_severity(self):

        """
        Tests the 'severity change' command in trac-admin.  This particular
        test tries to change a severity that does not exist.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'severity change bad_severity changed_name'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_severity_change_error_bad_new_name(self):

        """
        Tests the 'severity change' command in trac-admin.  This particular
        test tries to change a severity to a name that already exists.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'severity change critical major'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_severity_remove_ok(self):

        """
        Tests the 'severity add' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'severity remove trivial'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        cmd = 'severity list'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_severity_remove_error_bad_severity(self):

        """
        Tests the 'severity remove' command in trac-admin.  This particular
        test tries to remove a severity that does not exist.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'severity remove bad_severity'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    #
    #  version tests
    #
    def test_version_list_ok(self):

        """
        Tests the 'version list' command in trac-admin.  Since this command
        has no command arguments, it is hard to call it incorrectly.  As
        a result, there is only this one test.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'version list'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_version_add_ok(self):

        """
        Tests the 'version add' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """

        test_name = sys._getframe().f_code.co_name
        new_years = time.strftime('%b %d, %Y', (2004, 1, 1, 0, 0, 0, 3, 1, -1))
        cmd = 'version add 9.9 "%s"' % new_years
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        cmd = 'version list'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_version_add_error_already_exists(self):

        """
        Tests the 'version add' command in trac-admin.  This particular
        test passes a version name that already exists and checks for an
        error message.
        """

        test_name = sys._getframe().f_code.co_name
        new_years = time.strftime('%b %d, %Y', (2004, 1, 1, 0, 0, 0, 3, 1, -1))
        cmd = 'version add 1.0 "%s"' % new_years
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_version_rename_ok(self):

        """
        Tests the 'version rename' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'version rename 1.0 9.9'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        cmd = 'version list'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_version_rename_error_bad_version(self):

        """
        Tests the 'version rename' command in trac-admin.  This particular
        test tries to rename a version that does not exist.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'version rename bad_version changed_name'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_version_time_ok(self):

        """
        Tests the 'version time' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """

        test_name = sys._getframe().f_code.co_name
        new_years = time.strftime('%b %d, %Y', (2004, 1, 1, 0, 0, 0, 3, 1, -1))
        cmd = 'version time 2.0 "%s"' % new_years
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        cmd = 'version list'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_version_time_error_bad_version(self):

        """
        Tests the 'version time' command in trac-admin.  This particular
        test tries to change the time on a version that does not exist.
        """

        test_name = sys._getframe().f_code.co_name
        new_years = time.strftime('%b %d, %Y', (2004, 1, 1, 0, 0, 0, 3, 1, -1))
        cmd = 'version time bad_version "%s"' % new_years
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_version_remove_ok(self):

        """
        Tests the 'version remove' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'version remove 1.0'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        cmd = 'version list'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_version_remove_error_bad_version(self):

        """
        Tests the 'version remove' command in trac-admin.  This particular
        test tries to remove a version that does not exist.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'version remove bad_version'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    #
    #  milestone tests
    #
    def test_milestone_list_ok(self):

        """
        Tests the 'milestone list' command in trac-admin.  Since this command
        has no command arguments, it is hard to call it incorrectly.  As
        a result, there is only this one test.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'milestone list'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_milestone_add_ok(self):

        """
        Tests the 'milestone add' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """

        test_name = sys._getframe().f_code.co_name
        new_years = time.strftime('%b %d, %Y', (2004, 1, 1, 0, 0, 0, 3, 1, -1))
        cmd = 'milestone add new_milestone "%s"' % new_years
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        cmd = 'milestone list'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_milestone_add_error_already_exists(self):

        """
        Tests the 'milestone add' command in trac-admin.  This particular
        test passes a milestone name that already exists and checks for an
        error message.
        """

        test_name = sys._getframe().f_code.co_name
        new_years = time.strftime('%b %d, %Y', (2004, 1, 1, 0, 0, 0, 3, 1, -1))
        cmd = 'milestone add milestone1 "%s"' % new_years
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_milestone_rename_ok(self):

        """
        Tests the 'milestone rename' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'milestone rename milestone1 changed_milestone'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        cmd = 'milestone list'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_milestone_rename_error_bad_milestone(self):

        """
        Tests the 'milestone rename' command in trac-admin.  This particular
        test tries to rename a milestone that does not exist.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'milestone rename bad_milestone changed_name'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_milestone_time_ok(self):

        """
        Tests the 'milestone time' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """

        test_name = sys._getframe().f_code.co_name
        new_years = time.strftime('%b %d, %Y', (2004, 1, 1, 0, 0, 0, 3, 1, -1))
        cmd = 'milestone time milestone2 "%s"' % new_years
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        cmd = 'milestone list'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_milestone_time_error_bad_milestone(self):

        """
        Tests the 'milestone time' command in trac-admin.  This particular
        test tries to change the time on a milestone that does not exist.
        """

        test_name = sys._getframe().f_code.co_name
        new_years = time.strftime('%b %d, %Y', (2004, 1, 1, 0, 0, 0, 3, 1, -1))
        cmd = 'milestone time bad_milestone "%s"' % new_years
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_milestone_remove_ok(self):

        """
        Tests the 'milestone remove' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'milestone remove milestone3'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        cmd = 'milestone list'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]

    def test_milestone_remove_error_bad_milestone(self):

        """
        Tests the 'milestone remove' command in trac-admin.  This particular
        test tries to remove a milestone that does not exist.
        """

        test_name = sys._getframe().f_code.co_name
        cmd = 'milestone remove bad_milestone'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s) failed: %s, %s.' % \
                  (trac_admin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == self.expected_results[test_name]


def suite():
    return unittest.makeSuite(TracadminTestCase, 'test')
