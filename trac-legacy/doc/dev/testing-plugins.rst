Writing Tests for Plugins
=========================

Testing a VCS backend
---------------------

You'll need to make several subclasses to get this working in the
current test infrastructure.  But first, we start with some imports.
These are pretty much required for all plugin tests::

    from trac.tests.functional import (FunctionalTestSuite,
                                       FunctionalTestCaseSetup,
                                       FunctionalTwillTestCaseSetup, tc)
    from trac.tests.functional import testenv

Now subclass
:class:`~trac.tests.functional.testenv.FunctionalTestEnvironment`.
This allows you to override methods that you need to set up your repo
instead of the default Subversion one::

    class GitFunctionalTestEnvironment(testenv.FunctionalTestEnvironment):
        repotype = 'git'

        def create_repo(self):
            os.mkdir(self.repodir)
            self.call_in_repo(["git", "init"])
            self.call_in_repo(["git", "config", "user.name", "Test User"])
            self.call_in_repo(["git", "config", "user.email", "test@example.com"])

        def get_enabled_components(self):
            return ['tracext.git.*']

        def get_repourl(self):
            return self.repodir + '/.git'
        repourl = property(get_repourl)


Now you need a bit of glue that sets up a test suite specifically for
your plugin's repo type.  Any testcases within this test suite will
use the same environment.  No other changes are generally necessary on
the test suite::

    class GitFunctionalTestSuite(FunctionalTestSuite):
        env_class = GitFunctionalTestEnvironment

Your test cases can call functions on either the :ref:`tester
<functional-tester>` or :ref:`twill commands <using-twill>` to do
their job.  Here's one that just verifies we were able to sync the
repo without issue::

    class EmptyRepoTestCase(FunctionalTwillTestCaseSetup):
        def runTest(self):
            self._tester.go_to_timeline()
            tc.notfind('Unsupported version control system')

Lastly, there's some boilerplate needed for the end of your test file,
so it can be run from the command line::

    def suite():
        # Here you need to create an instance of your subclass
        suite = GitFunctionalTestSuite()
        suite.addTest(EmptyRepoTestCase())
        # ...
        suite.addTest(AnotherRepoTestCase())
        return suite

    if __name__ == '__main__':
        unittest.main(defaultTest='suite')

