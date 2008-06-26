#!/usr/bin/python
from trac.tests.functional import *
from trac.util.datefmt import format_date, utc


class TestRepoBrowse(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Add a file to the repository and verify it is in the browser"""
        # Add a file to Subversion
        tempfilename = random_word()
        revision = self._tester.svn_add('/component1/trunk', tempfilename,
                                        random_page())

        # Verify that it appears in the browser view:
        browser_url = self._tester.url + '/browser'
        tc.go(browser_url)
        tc.url(browser_url)
        tc.find('component1')
        tc.follow('component1')
        tc.follow('trunk')
        tc.follow(tempfilename)
        self._tester.quickjump('[%s]' % revision)
        tc.find('Changeset %s' % revision)
        tc.find('admin')
        tc.find('Add %s' % tempfilename)
        tc.find('1 added')
        tc.follow('Timeline')
        tc.find('Add %s' % tempfilename)


class TestNewFileLog(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Verify browser log for a new file"""
        tempfilename = random_word()
        revision = self._tester.svn_add('/component1/trunk', tempfilename, '')
        tc.go(self._tester.url + '/log/component1/trunk/' + tempfilename)
        tc.find('@%d' % revision)
        tc.find('Add %s' % tempfilename)


class RegressionTestRev5877(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of the source browser fix in r5877"""
        tc.go(self._tester.url + '/browser?range_min_secs=1')
        tc.notfind(internal_error)


def functionalSuite(suite=None):
    if not suite:
        import trac.tests.functional.testcases
        suite = trac.tests.functional.testcases.functionalSuite()
    suite.addTest(TestRepoBrowse())
    suite.addTest(TestNewFileLog())
    suite.addTest(RegressionTestRev5877())

    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='functionalSuite')
