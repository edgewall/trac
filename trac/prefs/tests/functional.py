#!/usr/bin/python
from trac.tests.functional import *


#TODO: split this into multiple smaller testcases
class TestPreferences(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Set preferences for admin user"""
        prefs_url = self._tester.url + "/prefs"
        tc.follow('Preferences')
        tc.url(prefs_url)
        tc.notfind('Your preferences have been saved.')
        tc.formvalue('userprefs', 'name', ' System Administrator ')
        tc.formvalue('userprefs', 'email', ' admin@example.com ')
        tc.submit()
        tc.find('Your preferences have been saved.')
        tc.follow('Date & Time')
        tc.url(prefs_url + '/datetime')
        tc.formvalue('userprefs', 'tz', 'GMT -10:00')
        tc.submit()
        tc.find('Your preferences have been saved.')
        tc.follow('General')
        tc.url(prefs_url)
        tc.notfind('Your preferences have been saved.')
        tc.find('value="System Administrator"')
        tc.find(r'value="admin@example\.com"')
        tc.follow('Date & Time')
        tc.url(prefs_url + '/datetime')
        tc.find('GMT -10:00')


class RegressionTestRev5785(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of the fix in r5785"""
        prefs_url = self._tester.url + "/prefs"
        tc.follow('Preferences')
        tc.url(prefs_url)
        tc.follow('Logout')
        tc.notfind(internal_error) # See [5785]
        tc.follow('Login')


class RegressionTestTicket5765(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/5765
        Unable to turn off 'Enable access keys' in Preferences
        """
        self._tester.go_to_front()
        tc.follow('Preferences')
        tc.follow('Keyboard Shortcuts')
        tc.formvalue('userprefs', 'accesskeys', True)
        tc.submit()
        tc.find('name="accesskeys".*checked="checked"')
        tc.formvalue('userprefs', 'accesskeys', False)
        tc.submit()
        tc.notfind('name="accesskeys".*checked="checked"')


def functionalSuite(suite=None):
    if not suite:
        import trac.tests.functional.testcases
        suite = trac.tests.functional.testcases.functionalSuite()
    suite.addTest(TestPreferences())
    suite.addTest(RegressionTestRev5785())
    suite.addTest(RegressionTestTicket5765())
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='functionalSuite')
