#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2008-2013 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import os
from trac.tests.functional import *


class RegressionTestRev6017(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of the plugin reload fix in r6017"""
        # Setup the DeleteTicket plugin
        plugin = open(os.path.join(self._testenv.command_cwd,
                                   'sample-plugins', 'workflow',
                                   'DeleteTicket.py')).read()
        open(os.path.join(self._testenv.tracdir, 'plugins',
                          'DeleteTicket.py'), 'w').write(plugin)
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
                            'Logging off when it should have been on.\n%r'
                            % debug1)


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
                         'Logging still on when it should have been off.\n%r'
                         % debug2)


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
        self.assertTrue(success, message)


class RegressionTestTicket5572(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/5572"""
        # TODO: this ticket (implemented in r6011) adds a new feature to
        # make the progress bar more configurable.  We need to test this
        # new configurability.


class RegressionTestTicket7209(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/7209"""
        ticketid = self._tester.create_ticket()
        self._tester.create_ticket()
        self._tester.add_comment(ticketid)
        self._tester.attach_file_to_ticket(ticketid, filename='hello.txt',
                                           description='Preserved Descr')
        self._tester.go_to_ticket(ticketid)
        tc.find('Preserved Descr')
        # Now replace the existing attachment, and the description should come
        # through.
        self._tester.attach_file_to_ticket(ticketid, filename='hello.txt',
                                           description='', replace=True)
        self._tester.go_to_ticket(ticketid)
        tc.find('Preserved Descr')

        self._tester.attach_file_to_ticket(ticketid, filename='blah.txt',
                                           description='Second Attachment')
        self._tester.go_to_ticket(ticketid)
        tc.find('Second Attachment')

        # This one should get a new description when it's replaced
        # (Second->Other)
        self._tester.attach_file_to_ticket(ticketid, filename='blah.txt',
                                           description='Other Attachment',
                                           replace=True)
        self._tester.go_to_ticket(ticketid)
        tc.find('Other Attachment')
        tc.notfind('Second Attachment')


class RegressionTestTicket9880(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/9880

        Upload of a file which the browsers associates a Content-Type
        of multipart/related (e.g. an .mht file) should succeed.
        """
        ticketid = self._tester.create_ticket()
        self._tester.create_ticket()
        self._tester.attach_file_to_ticket(ticketid, filename='hello.mht',
                                           content_type='multipart/related',
                                           data="""
Well, the actual content of the file doesn't matter, the problem is
related to the "multipart/..." content_type associated to the file.
See also http://bugs.python.org/issue15564.
""")


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


class RegressionTestTicket6318(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Regression test for non-ascii usernames (#6318)
        """
        # Add users at start of test to avoid intermittent failures on
        # platforms with low resolution time stamps, for which the file
        # modification time may not have changed between successive calls to
        # `adduser`, resulting in a stale cache.
        # http://trac.edgewall.org/ticket/11176#comment:13
        self._testenv.adduser(u'user')
        self._testenv.adduser(u'joé')
        # first do a logout, otherwise we might end up logged in as
        # admin again, as this is the first thing the tester does.
        # ... but even before that we need to make sure we're coming
        # from a valid URL, which is not the case if we're just coming
        # from the above test! ('/wiki/\xE9t\xE9')
        self._tester.go_to_front()
        self._tester.logout()
        try:
            # also test a regular ascii user name
            self._tester.login(u'user')
            self._tester.logout()
            # now test utf-8 user name
            self._tester.login(u'joé')
            self._tester.logout()
            # finally restore expected 'admin' login
            self._tester.login('admin')
        finally:
            self._testenv.deluser(u'joé')


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
    suite.addTest(RegressionTestTicket9880())
    suite.addTest(ErrorPageValidation())
    suite.addTest(RegressionTestTicket3663())
    suite.addTest(RegressionTestTicket6318())

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
