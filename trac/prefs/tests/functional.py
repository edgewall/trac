#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2008-2013 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

from trac.tests.functional import *


#TODO: split this into multiple smaller testcases
class TestPreferences(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Set preferences for admin user"""
        self._tester.go_to_preferences()
        tc.notfind('Your preferences have been saved.')
        tc.formvalue('userprefs', 'name', ' System Administrator ')
        tc.formvalue('userprefs', 'email', ' admin@example.com ')
        tc.submit()
        tc.find('Your preferences have been saved.')
        self._tester.go_to_preferences("Date & Time")
        tc.formvalue('userprefs', 'tz', 'GMT -10:00')
        tc.submit()
        tc.find('Your preferences have been saved.')
        self._tester.go_to_preferences()
        tc.notfind('Your preferences have been saved.')
        tc.find('value="System Administrator"')
        tc.find(r'value="admin@example\.com"')
        self._tester.go_to_preferences("Date & Time")
        tc.find('GMT -10:00')


class RegressionTestRev5785(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of the fix in r5785"""
        self._tester.go_to_preferences()
        tc.follow('Logout')
        tc.notfind(internal_error) # See [5785]
        tc.follow('Login')


class RegressionTestTicket5765(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/5765
        Unable to turn off 'Enable access keys' in Preferences
        """
        self._tester.go_to_preferences("Keyboard Shortcuts")
        tc.formvalue('userprefs', 'accesskeys', True)
        tc.submit()
        tc.find('name="accesskeys".*checked="checked"')
        tc.formvalue('userprefs', 'accesskeys', False)
        tc.submit()
        tc.notfind('name="accesskeys".*checked="checked"')


def functionalSuite(suite=None):
    if not suite:
        import trac.tests.functional
        suite = trac.tests.functional.functionalSuite()
    suite.addTest(TestPreferences())
    suite.addTest(RegressionTestRev5785())
    suite.addTest(RegressionTestTicket5765())
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='functionalSuite')
