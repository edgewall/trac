#!/usr/bin/python
import os
from subprocess import call
from tempfile import mkdtemp
from trac.tests.functional import *
from trac.util.datefmt import format_date, utc


class TestEmptyRepo(FunctionalTwillTestCaseSetup):
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
        self._tester.svn_mkdir(directories, commit_message)

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


class RegressionTestRev6017(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of the plugin reload fix in r6017"""
        # Setup the DeleteTicket plugin
        plugin = open(os.path.join(self._testenv.command_cwd, 'sample-plugins',
            'workflow', 'DeleteTicket.py')).read()
        open(os.path.join(self._testenv.tracdir, 'plugins', 'DeleteTicket.py'),
             'w').write(plugin)
        env = self._testenv.get_trac_environment()
        prevconfig = env.config.get('ticket', 'workflow')
        env.config.set('ticket', 'workflow',
                       prevconfig + ',DeleteTicketActionController')
        env.config.save()
        env = self._testenv.get_trac_environment() # reloads the environment

        loaded_components = env.compmgr.__metaclass__._components
        delete_plugins = [c for c in loaded_components
                          if 'DeleteTicketActionController' in c.__name__]
        try:
            self.assertEqual(len(delete_plugins), 1,
                             "Plugin loaded more than once.")

        finally:
            # Remove the DeleteTicket plugin
            env.config.set('ticket', 'workflow', prevconfig)
            env.config.save()
            self._testenv.restart()
            for ext in ('py', 'pyc', 'pyo'):
                filename = os.path.join(self._testenv.tracdir, 'plugins',
                                        'DeleteTicket.%s' % ext)
                if os.path.exists(filename):
                    os.unlink(filename)


class RegressionTestTicket3833a(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/3833 a"""
        # Assume the logging is already set to debug.
        traclogfile = open(os.path.join(self._testenv.tracdir, 'log',
                                        'trac.log'))
        # Seek to the end of file so we only look at new log output
        traclogfile.seek(0, 2)
        # Verify that logging is on initially
        env = self._testenv.get_trac_environment()

        env.log.debug("RegressionTestTicket3833 debug1")
        debug1 = traclogfile.read()
        self.assertNotEqual(debug1.find("RegressionTestTicket3833 debug1"), -1,
            'Logging off when it should have been on.\n%r' % debug1)

class RegressionTestTicket3833b(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/3833 b"""
        # Turn logging off, try to log something, and verify that it does
        # not show up.
        traclogfile = open(os.path.join(self._testenv.tracdir, 'log',
                                        'trac.log'))
        # Seek to the end of file so we only look at new log output
        traclogfile.seek(0, 2)
        env = self._testenv.get_trac_environment()

        env.config.set('logging', 'log_level', 'INFO')
        env.config.save()
        env = self._testenv.get_trac_environment()
        env.log.debug("RegressionTestTicket3833 debug2")
        env.log.info("RegressionTestTicket3833 info2")
        debug2 = traclogfile.read()
        self.assertNotEqual(debug2.find("RegressionTestTicket3833 info2"), -1,
                            'Logging at info failed.\n%r' % debug2)
        self.assertEqual(debug2.find("RegressionTestTicket3833 debug2"), -1,
            'Logging still on when it should have been off.\n%r' % debug2)

class RegressionTestTicket3833c(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/3833 c"""
        # Turn logging back on, try to log something, and verify that it
        # does show up.
        traclogfile = open(os.path.join(self._testenv.tracdir, 'log',
                                        'trac.log'))
        # Seek to the end of file so we only look at new log output
        traclogfile.seek(0, 2)
        env = self._testenv.get_trac_environment()

        env.config.set('logging', 'log_level', 'DEBUG')
        time.sleep(2)
        env.config.save()
        #time.sleep(2)
        env = self._testenv.get_trac_environment()
        #time.sleep(2)
        env.log.debug("RegressionTestTicket3833 debug3")
        env.log.info("RegressionTestTicket3833 info3")
        #time.sleep(2)
        debug3 = traclogfile.read()
        message = ''
        success = debug3.find("RegressionTestTicket3833 debug3") != -1
        if not success:
            # Ok, the testcase failed, but we really need logging enabled.
            self._testenv.restart()
            env.log.debug("RegressionTestTicket3833 fixup3")
            fixup3 = traclogfile.read()
            message = 'Logging still off when it should have been on.\n' \
                      '%r\n%r' % (debug3, fixup3)
        self.assert_(success, message)


class RegressionTestTicket5572(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/5572"""
        # TODO: this ticket (implemented in r6011) adds a new feature to
        # make the progress bar more configurable.  We need to test this
        # new configurability.


def functionalSuite():
    suite = FunctionalTestSuite()
    # These basic tests of the repository need to occur before other things so
    # that we have a repository to work with.
    suite.addTest(TestEmptyRepo())
    suite.addTest(TestRepoCreation())
    return suite


def suite():
    suite = functionalSuite()

    suite.addTest(RegressionTestRev6017())
    suite.addTest(RegressionTestTicket3833a())
    suite.addTest(RegressionTestTicket3833b())
    suite.addTest(RegressionTestTicket3833c())
    suite.addTest(RegressionTestTicket5572())

    import trac.versioncontrol.tests
    trac.versioncontrol.tests.functionalSuite(suite)
    import trac.ticket.tests
    trac.ticket.tests.functionalSuite(suite)
    import trac.prefs.tests
    trac.prefs.tests.functionalSuite(suite)
    import trac.wiki.tests
    trac.wiki.tests.functionalSuite(suite)
    import trac.timeline.tests
    trac.timeline.tests.functionalSuite(suite)

    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
