# -*- encoding: utf-8 -*-
#!/usr/bin/python
import os
from trac.tests.functional import *


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


class RegressionTestTicket7209(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/7209"""
        summary = random_sentence(5)
        ticketid = self._tester.create_ticket(summary)
        self._tester.create_ticket()
        self._tester.add_comment(ticketid)
        self._tester.attach_file_to_ticket(ticketid, tempfilename='hello.txt',
                                           description='Preserved Descr')
        self._tester.go_to_ticket(ticketid)
        tc.find('Preserved Descr')
        # Now replace the existing attachment, and the description should come
        # through.
        self._tester.attach_file_to_ticket(ticketid, tempfilename='hello.txt',
                                           description='', replace=True)
        self._tester.go_to_ticket(ticketid)
        tc.find('Preserved Descr')

        self._tester.attach_file_to_ticket(ticketid, tempfilename='blah.txt',
                                           description='Second Attachment')
        self._tester.go_to_ticket(ticketid)
        tc.find('Second Attachment')

        # This one should get a new description when it's replaced
        # (Second->Other)
        self._tester.attach_file_to_ticket(ticketid, tempfilename='blah.txt',
                                           description='Other Attachment',
                                           replace=True)
        self._tester.go_to_ticket(ticketid)
        tc.find('Other Attachment')
        tc.notfind('Second Attachment')


class ErrorPageValidation(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Validate the error page"""
        url = self._tester.url + '/wiki/WikiStart'
        tc.go(url + '?version=bug')
        tc.url(url)
        tc.find(internal_error)


class RegressionTestTicket3663(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Regression test for non-UTF-8 PATH_INFO (#3663)
        
        Verify that URLs not encoded with UTF-8 are reported as invalid.
        """
        # invalid PATH_INFO
        self._tester.go_to_wiki(u'été'.encode('latin1'))
        tc.code(404)
        tc.find('Invalid URL encoding')
        # invalid SCRIPT_NAME
        tc.go(u'été'.encode('latin1'))
        tc.code(404)
        tc.find('Invalid URL encoding')


def functionalSuite():
    suite = FunctionalTestSuite()
    return suite


def suite():
    suite = functionalSuite()

    suite.addTest(RegressionTestRev6017())
    suite.addTest(RegressionTestTicket3833a())
    suite.addTest(RegressionTestTicket3833b())
    suite.addTest(RegressionTestTicket3833c())
    suite.addTest(RegressionTestTicket5572())
    suite.addTest(RegressionTestTicket7209())
    suite.addTest(ErrorPageValidation())
    suite.addTest(RegressionTestTicket3663())

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
    import trac.admin.tests
    trac.admin.tests.functionalSuite(suite)
    # The db tests should be last since the backup test occurs there.
    import trac.db.tests
    trac.db.tests.functionalSuite(suite)

    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
