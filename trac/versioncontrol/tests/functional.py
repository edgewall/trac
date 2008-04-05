#!/usr/bin/python
import os
import re
from subprocess import call, Popen, PIPE
from tempfile import mkdtemp
from trac.tests.functional import *
from trac.util.datefmt import format_date, utc


class TestRepoBrowse(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Add a file to the repository and verify it is in the browser"""
        # Add a file to Subversion
        tempdir = mkdtemp()
        working_copy = os.path.join(tempdir, 'trunk')

        if call(['svn', 'co', self._tester.repo_url + '/component1/trunk',
                 working_copy], stdout=logfile, stderr=logfile,
                close_fds=close_fds):
            raise Exception('Checkout from %s failed.' % self._tester.repo_url)
        tempfilename = random_word()
        temppathname = os.path.join(working_copy, tempfilename)
        data = random_page()
        f = open(temppathname, 'w')
        f.write(data)
        f.close()
        if call(['svn', 'add', tempfilename], cwd=working_copy,
                stdout=logfile, stderr=logfile, close_fds=close_fds):
            raise Exception('Checkout failed.')
        commit = Popen(['svn', '--username=admin', 'commit', '-m',
                 'Add %s' % tempfilename, tempfilename],
                cwd=working_copy, stdout=PIPE, stderr=logfile,
                close_fds=close_fds)
        output = commit.stdout.read()
        if commit.wait():
            raise Exception('Commit failed.')
        try:
            revision = int(re.compile('Committed revision ([0-9]+)\\.',
                                      re.M).findall(output)[0])
        except Exception, e:
            args = e.args + (output, )
            raise Exception(*args)
        rmtree(tempdir) # Cleanup
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
    suite.addTest(RegressionTestRev5877())

    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='functionalSuite')
