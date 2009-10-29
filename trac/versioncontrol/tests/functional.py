#!/usr/bin/python
from trac.tests.functional import *


class TestEmptySvnRepo(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Check empty repository"""
        browser_url = self._tester.url + '/browser'
        tc.go(browser_url)
        tc.url(browser_url)
        # This tests the current behavior; I'm not sure it's the best
        # behavior.
        tc.follow('Last Change')
        tc.find('Error: No such changeset')
        tc.back()
        tc.follow('Revision Log')
        tc.notfind('Error: Nonexistent path')


class TestRepoCreation(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Create a directory tree in the repository"""
        # This should probably use the svn bindings...
        directories = []
        for component in ('component1', 'component2'):
            directories.append(component)
            for subdir in ('branches', 'tags', 'trunk'):
                directories.append('/'.join([component, subdir]))
        commit_message = 'Create component trees.'
        self._testenv.svn_mkdir(directories, commit_message)

        browser_url = self._tester.url + '/browser'
        tc.go(browser_url)
        tc.url(browser_url)
        tc.find('component1')
        tc.find('component2')
        tc.follow('Last Change')
        tc.url(self._tester.url + '/changeset/1/')
        tc.find(commit_message)
        for directory in directories:
            tc.find(directory)
        tc.back()
        tc.follow('Revision Log')
        # (Note that our commit log message is short enough to avoid
        # truncation.)
        tc.find(commit_message)
        tc.follow('Timeline')
        # (Note that our commit log message is short enough to avoid
        # truncation.)
        tc.find(commit_message)
        tc.formvalue('prefs', 'ticket', False)
        tc.formvalue('prefs', 'milestone', False)
        tc.formvalue('prefs', 'wiki', False)
        tc.submit()
        tc.find('by.*admin')
        # (Note that our commit log message is short enough to avoid
        # truncation.)
        tc.find(commit_message)


class TestRepoBrowse(FunctionalTwillTestCaseSetup):
    # TODO: move this out to a subversion-specific testing module
    def runTest(self):
        """Add a file to the repository and verify it is in the browser"""
        # Add a file to Subversion
        tempfilename = random_word()
        fulltempfilename = 'component1/trunk/' + tempfilename
        revision = self._testenv.svn_add(fulltempfilename, random_page())

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
        tc.find('Add %s' % fulltempfilename)
        tc.find('1 added')
        tc.follow('Timeline')
        tc.find('Add %s' % fulltempfilename)


class TestNewFileLog(FunctionalTwillTestCaseSetup):
    # TODO: move this out to a subversion-specific testing module
    def runTest(self):
        """Verify browser log for a new file"""
        tempfilename = random_word()
        fulltempfilename = 'component1/trunk/' + tempfilename
        revision = self._testenv.svn_add(fulltempfilename, '')
        tc.go(self._tester.url + '/log/' + fulltempfilename)
        tc.find('@%d' % revision)
        tc.find('Add %s' % fulltempfilename)


class RegressionTestTicket5819(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/5819
        Events with identical dates are reversed in timeline
        """
        # Multiple events very close together
        files = ['a', 'b', 'c', 'd']
        for filename in files:
            # We do a mkdir because it's easy.
            self._testenv.svn_mkdir(['component1/trunk/' + filename],
                     'Create component1/%s' % filename)
        self._tester.go_to_timeline()
        # They are supposed to show up in d, c, b, a order.
        components = '.*'.join(['Create component1/%s' % f for f in
                                      reversed(files)])
        tc.find(components, 's')


class RegressionTestRev5877(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of the source browser fix in r5877"""
        tc.go(self._tester.url + '/browser?range_min_secs=1')
        tc.notfind(internal_error)


def functionalSuite(suite=None):
    if not suite:
        import trac.tests.functional.testcases
        suite = trac.tests.functional.testcases.functionalSuite()
    if has_svn:
        suite.addTest(TestEmptySvnRepo())
        suite.addTest(TestRepoCreation())
        suite.addTest(TestRepoBrowse())
        suite.addTest(TestNewFileLog())
        if sys.version_info[:2] < (2, 4):
            print "SKIP: RegressionTestTicket5819 (python 2.3 issue)"
        else:
            suite.addTest(RegressionTestTicket5819())
        suite.addTest(RegressionTestRev5877())
    else:
        print "SKIP: versioncontrol/tests/functional.py (no svn bindings)"

    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='functionalSuite')
