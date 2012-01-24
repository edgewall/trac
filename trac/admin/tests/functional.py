#!/usr/bin/python
from trac.tests.functional import *
from trac.util.text import unicode_to_base64, unicode_from_base64

class TestBasicSettings(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Check basic settings."""
        self._tester.go_to_admin()
        tc.formvalue('modbasic', 'url', 'https://my.example.com/something')
        tc.submit()
        tc.find('https://my.example.com/something')


class TestLoggingNone(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Turn off logging."""
        # For now, we just check that it shows up.
        self._tester.go_to_admin()
        tc.follow('Logging')
        tc.find('trac.log')
        tc.formvalue('modlog', 'log_type', 'none')
        tc.submit()
        tc.find('selected="selected">None</option')


class TestLoggingToFile(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Turn logging back on."""
        # For now, we just check that it shows up.
        self._tester.go_to_admin()
        tc.follow('Logging')
        tc.find('trac.log')
        tc.formvalue('modlog', 'log_type', 'file')
        tc.formvalue('modlog', 'log_file', 'trac.log2')
        tc.formvalue('modlog', 'log_level', 'INFO')
        tc.submit()
        tc.find('selected="selected">File</option')
        tc.find('id="log_file".*value="trac.log2"')
        tc.find('selected="selected">INFO</option>')


class TestLoggingToFileNormal(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Setting logging back to normal."""
        # For now, we just check that it shows up.
        self._tester.go_to_admin()
        tc.follow('Logging')
        tc.find('trac.log')
        tc.formvalue('modlog', 'log_file', 'trac.log')
        tc.formvalue('modlog', 'log_level', 'DEBUG')
        tc.submit()
        tc.find('selected="selected">File</option')
        tc.find('id="log_file".*value="trac.log"')
        tc.find('selected="selected">DEBUG</option>')


class TestCreatePermissionGroup(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Create a permissions group"""
        self._tester.go_to_admin()
        tc.follow('Permissions')
        tc.find('Manage Permissions')
        tc.formvalue('addperm', 'gp_subject', 'somegroup')
        tc.formvalue('addperm', 'action', 'REPORT_CREATE')
        tc.submit()
        somegroup = unicode_to_base64('somegroup')
        REPORT_CREATE = unicode_to_base64('REPORT_CREATE')
        tc.find('%s:%s' % (somegroup, REPORT_CREATE))


class TestAddUserToGroup(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Add a user to a permissions group"""
        self._tester.go_to_admin()
        tc.follow('Permissions')
        tc.find('Manage Permissions')
        tc.formvalue('addsubj', 'sg_subject', 'authenticated')
        tc.formvalue('addsubj', 'sg_group', 'somegroup')
        tc.submit()
        authenticated = unicode_to_base64('authenticated')
        somegroup = unicode_to_base64('somegroup')
        tc.find('%s:%s' % (authenticated, somegroup))


class TestRemoveUserFromGroup(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Remove a user from a permissions group"""
        self._tester.go_to_admin()
        tc.follow('Permissions')
        tc.find('Manage Permissions')
        authenticated = unicode_to_base64('authenticated')
        somegroup = unicode_to_base64('somegroup')
        tc.find('%s:%s' % (authenticated, somegroup))
        tc.formvalue('revokeform', 'sel', '%s:%s' % (authenticated, somegroup))
        tc.submit()
        tc.notfind('%s:%s' % (authenticated, somegroup))


class TestRemovePermissionGroup(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Remove a permissions group"""
        self._tester.go_to_admin()
        tc.follow('Permissions')
        tc.find('Manage Permissions')
        somegroup = unicode_to_base64('somegroup')
        REPORT_CREATE = unicode_to_base64('REPORT_CREATE')
        tc.find('%s:%s' % (somegroup, REPORT_CREATE))
        tc.formvalue('revokeform', 'sel', '%s:%s' % (somegroup, REPORT_CREATE))
        tc.submit()
        tc.notfind('%s:%s' % (somegroup, REPORT_CREATE))
        tc.notfind(somegroup)


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
    suite.addTest(TestLoggingNone())
    suite.addTest(TestLoggingToFile())
    suite.addTest(TestLoggingToFileNormal())
    suite.addTest(TestCreatePermissionGroup())
    suite.addTest(TestAddUserToGroup())
    suite.addTest(TestRemoveUserFromGroup())
    suite.addTest(TestRemovePermissionGroup())
    suite.addTest(TestPluginSettings())
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='functionalSuite')
