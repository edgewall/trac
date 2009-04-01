#!/usr/bin/python
from trac.tests.functional import *


class TestBasicSettings(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Check basic settings."""
        self._tester.go_to_admin()
        tc.formvalue('modbasic', 'url', 'https://my.example.com/something')
        tc.submit()
        tc.find('https://my.example.com/something')


class TestLoggingSettings(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Check logging settings."""
        # For now, we just check that it shows up.
        self._tester.go_to_admin()
        tc.follow('Logging')
        tc.find('trac.log')


class TestCreatePermissionGroup(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Create a permissions group"""
        self._tester.go_to_admin()
        tc.follow('Permissions')
        tc.find('Manage Permissions')
        tc.formvalue('addperm', 'gp_subject', 'somegroup')
        tc.formvalue('addperm', 'action', 'REPORT_CREATE')
        tc.submit()
        tc.find('somegroup')


class TestPluginSettings(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Check plugin settings."""
        self._tester.go_to_admin()
        tc.follow('Plugins')
        tc.find('Manage Plugins')
        tc.find('Install Plugin')



def functionalSuite(suite=None):
    if not suite:
        import trac.tests.functional.testcases
        suite = trac.tests.functional.testcases.functionalSuite()
    suite.addTest(TestBasicSettings())
    suite.addTest(TestLoggingSettings())
    suite.addTest(TestCreatePermissionGroup())
    suite.addTest(TestPluginSettings())
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='functionalSuite')
