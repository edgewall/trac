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
        has no command arguments, it is hard to call the it incorrectly.  As
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
            err = 'Running (%s %s) failed: %s, %s.' % \
                  (tracadmin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == expected_results

    #
    #  help test
    #
    def test_help_ok(self):

        """
        Tests the 'help' command in trac-admin.  Since the 'help' command
        has no command arguments, it is hard to call the it incorrectly.  As
        a result, there is only this one test.
        """

        test_name = sys._getframe().f_code.co_name
        expected_results = self.expected_results[test_name] % trac.__version__
        cmd = 'help'
        trac_admin = 'trac-admin %s %s' % (self.env.path, cmd)
        np = NaivePopen(trac_admin, None, capturestderr=1)
        if np.errorlevel or np.err:
            err = 'Running (%s %s) failed: %s, %s.' % \
                  (tracadmin, np.errorlevel, np.err)
            raise Exception, err
        test_results = np.out
        assert test_results == expected_results


def suite():
    return unittest.makeSuite(TracadminTestCase, 'test')
