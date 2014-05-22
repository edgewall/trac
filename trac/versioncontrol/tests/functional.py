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
        tempfilename = random_word() + '_new.txt'
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


class RegressionTestTicket11194(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/11194
        TracError should be raised when repository with name already exists
        """
        self._tester.go_to_admin()
        tc.follow("\\bRepositories\\b")
        tc.url(self._tester.url + '/admin/versioncontrol/repository')

        word = random_word()
        names = ['%s_%d' % (word, n) for n in xrange(3)]
        tc.formvalue('trac-addrepos', 'name', names[0])
        tc.formvalue('trac-addrepos', 'dir', '/var/svn/%s' % names[0])
        tc.submit()
        tc.notfind(internal_error)

        tc.formvalue('trac-addrepos', 'name', names[1])
        tc.formvalue('trac-addrepos', 'dir', '/var/svn/%s' % names[1])
        tc.submit()
        tc.notfind(internal_error)

        tc.follow('\\b' + names[1] + '\\b')
        tc.url(self._tester.url + '/admin/versioncontrol/repository/' + names[1])
        tc.formvalue('trac-modrepos', 'name', names[2])
        tc.submit('save')
        tc.notfind(internal_error)
        tc.url(self._tester.url + '/admin/versioncontrol/repository')

        tc.follow('\\b' + names[2] + '\\b')
        tc.url(self._tester.url + '/admin/versioncontrol/repository/' + names[2])
        tc.formvalue('trac-modrepos', 'name', names[0])
        tc.submit('save')
        tc.find('The repository "%s" already exists.' % names[0])
        tc.notfind(internal_error)


class RegressionTestTicket11346(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/11346
        fix for log: link with revision ranges included oldest wrongly
        showing HEAD revision
        """
        # create new 3 revisions
        self._testenv.svn_mkdir(['ticket11346'], '')
        for i in (1, 2):
            rev = self._testenv.svn_add('ticket11346/file%d.txt' % i, '')
        tc.go(self._tester.url + '/log?revs=1-2')
        tc.find('@1')
        tc.find('@2')
        tc.notfind('@3')
        tc.notfind('@%d' % rev)


class RegressionTestTicket11618(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/11618
        fix for malformed `readonly="True"` attribute in repository admin.
        """
        env = self._testenv.get_trac_environment()
        env.config.set('repositories', 't11618.dir',
                       self._testenv.repo_path_for_initenv())
        env.config.save()
        self._testenv.restart()
        try:
            self._tester.go_to_admin()
            tc.follow(r'\bRepositories\b')
            tc.url(self._tester.url + '/admin/versioncontrol/repository')
            tc.follow(r'\bt11618\b')
            tc.url(self._tester.url + '/admin/versioncontrol/repository/t11618')
            tc.notfind(' readonly="True"')
            tc.find(' readonly="readonly"')
        finally:
            env.config.remove('repositories', 't11618.dir')
            env.config.save()
            self._testenv.restart()


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
        suite.addTest(RegressionTestTicket11194())
        suite.addTest(RegressionTestTicket11346())
        suite.addTest(RegressionTestTicket11618())
        suite.addTest(RegressionTestRev5877())
    else:
        print "SKIP: versioncontrol/tests/functional.py (no svn bindings)"

    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='functionalSuite')
