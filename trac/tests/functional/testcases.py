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
import re
import time
import unittest

from trac.tests.functional import FunctionalTwillTestCaseSetup, \
                                  internal_error, tc
from trac.util import create_file


class TestAttachmentNonexistentParent(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """TracError should be raised when navigating to the attachment
        page for a nonexistent resource."""
        self._tester.go_to_wiki('NonexistentPage')
        tc.find("The page NonexistentPage does not exist. "
                "You can create it here.")
        tc.find(r"\bCreate this page\b")

        tc.go(self._tester.url + '/attachment/wiki/NonexistentPage')
        tc.find('<h1>Trac Error</h1>\s+<p class="message">'
                'Parent resource NonexistentPage doesn\'t exist</p>')


class TestErrorPage(FunctionalTwillTestCaseSetup):
    """Validate the error page.
    Defects reported to trac-hacks should use the Component defined in the
    plugin's URL (#11434).
    """
    def runTest(self):
        env = self._testenv.get_trac_environment()
        env.config.set('components', 'RaiseExceptionPlugin.*', 'enabled')
        env.config.save()
        create_file(os.path.join(env.plugins_dir, 'RaiseExceptionPlugin.py'),
"""\
from trac.core import Component, implements
from trac.web.api import IRequestHandler

url = None

class RaiseExceptionPlugin(Component):
    implements(IRequestHandler)

    def match_request(self, req):
        if req.path_info.startswith('/raise-exception'):
            return True

    def process_request(self, req):
        if req.args.get('report') == 'tho':
            global url
            url = 'http://trac-hacks.org/wiki/HelloWorldMacro'
        raise Exception

""")
        self._testenv.restart()

        try:
            tc.go(self._tester.url + '/raise-exception')
            tc.find(internal_error)
            tc.find('<form class="newticket" method="get" '
                    'action="https://trac.edgewall.org/newticket">')

            tc.go(self._tester.url + '/raise-exception?report=tho')
            tc.find(internal_error)
            tc.find('<form class="newticket" method="get" '
                    'action="http://trac-hacks.org/newticket">')
            tc.find('<input type="hidden" name="component" '
                    'value="HelloWorldMacro" />')
        finally:
            env.config.set('components', 'RaiseExceptionPlugin.*', 'disabled')


class RegressionTestRev6017(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of the plugin reload fix in r6017"""
        # Setup the DeleteTicket plugin
        env = self._testenv.get_trac_environment()
        plugin = open(os.path.join(self._testenv.trac_src,
                                   'sample-plugins', 'workflow',
                                   'DeleteTicket.py')).read()
        plugin_path = os.path.join(env.plugins_dir, 'DeleteTicket.py')
        open(plugin_path, 'w').write(plugin)
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
            for ext in ('py', 'pyc', 'pyo'):
                filename = os.path.join(env.plugins_dir,
                                        'DeleteTicket.%s' % ext)
                if os.path.exists(filename):
                    os.unlink(filename)


class RegressionTestTicket3833a(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/3833 a"""
        env = self._testenv.get_trac_environment()
        # Assume the logging is already set to debug.
        traclogfile = open(os.path.join(env.log_dir, 'trac.log'))
        # Seek to the end of file so we only look at new log output
        traclogfile.seek(0, 2)

        # Verify that logging is on initially
        env.log.debug("RegressionTestTicket3833 debug1")
        debug1 = traclogfile.read()
        self.assertNotEqual(debug1.find("RegressionTestTicket3833 debug1"), -1,
                            'Logging off when it should have been on.\n%r'
                            % debug1)


class RegressionTestTicket3833b(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/3833 b"""
        # Turn logging off, try to log something, and verify that it does
        # not show up.
        env = self._testenv.get_trac_environment()
        traclogfile = open(os.path.join(env.log_dir, 'trac.log'))
        # Seek to the end of file so we only look at new log output
        traclogfile.seek(0, 2)

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


class RegressionTestTicket3833c(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/3833 c"""
        # Turn logging back on, try to log something, and verify that it
        # does show up.
        env = self._testenv.get_trac_environment()
        traclogfile = open(os.path.join(env.log_dir, 'trac.log'))
        # Seek to the end of file so we only look at new log output
        traclogfile.seek(0, 2)

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
        # first do a logout, otherwise we might end up logged in as
        # admin again, as this is the first thing the tester does.
        # ... but even before that we need to make sure we're coming
        # from a valid URL, which is not the case if we're just coming
        # from the above test! ('/wiki/\xE9t\xE9')
        self._tester.go_to_front()
        self._tester.logout()
        try:
            # also test a regular ascii user name
            self._testenv.adduser(u'user')
            self._tester.login(u'user')
            self._tester.go_to_front()
            self._tester.logout()
            # now test utf-8 user name
            self._testenv.adduser(u'joé')
            self._tester.login(u'joé')
            self._tester.go_to_front()
            # when failed to retrieve session, FakeSession() and FakePerm()
            # are used and the req.perm has no permissions.
            tc.notfind(internal_error)
            tc.notfind("You don't have the required permissions")
            self._tester.logout()
            # finally restore expected 'admin' login
            self._tester.login('admin')
        finally:
            self._testenv.deluser(u'joé')


class RegressionTestTicket11434(FunctionalTwillTestCaseSetup):
    """Test for regression of http://trac.edgewall.org/ticket/11434
    Defects reported to trac-hacks should use the Component defined in the
    plugin's URL.
    """
    def runTest(self):
        env = self._testenv.get_trac_environment()
        env.config.set('components', 'RaiseExceptionPlugin.*', 'enabled')
        env.config.save()
        create_file(os.path.join(env.plugins_dir, 'RaiseExceptionPlugin.py'),
"""\
from trac.core import Component, implements
from trac.web.api import IRequestHandler

url = 'http://trac-hacks.org/wiki/HelloWorldMacro'

class RaiseExceptionPlugin(Component):
    implements(IRequestHandler)

    def match_request(self, req):
        if req.path_info == '/raise-exception':
            return True

    def process_request(self, req):
        raise Exception

""")

        try:
            tc.go(self._tester.url + '/raise-exception')
            tc.find(internal_error)
            tc.find('<form class="newticket" method="get" '
                    'action="http://trac-hacks.org/newticket">')
            tc.find('<input type="hidden" name="component" '
                    'value="HelloWorldMacro" />')
        finally:
            env.config.set('components', 'RaiseExceptionPlugin.*', 'disabled')


class RegressionTestTicket11503a(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/11503 a"""
        base = self._tester.url

        tc.go(base + '/notf%C5%91und/')
        tc.notfind(internal_error)
        tc.url(re.escape(base + '/notf%C5%91und') + r'\Z')

        tc.go(base + '/notf%C5%91und/?type=def%C3%A9ct')
        tc.notfind(internal_error)
        tc.url(re.escape(base + '/notf%C5%91und?type=def%C3%A9ct') + r'\Z')

        tc.go(base + '/notf%C5%91und/%252F/?type=%252F')
        tc.notfind(internal_error)
        tc.url(re.escape(base + '/notf%C5%91und/%252F?type=%252F') + r'\Z')


class RegressionTestTicket11503b(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/11503 b"""
        env = self._testenv.get_trac_environment()
        try:
            env.config.set('mainnav', 'wiki.href',
                           u'/wiki/SändBõx?action=history&blah=%252F')
            env.config.save()
            # reloads the environment
            env = self._testenv.get_trac_environment()

            self._tester.go_to_front()
            tc.notfind(internal_error)
            tc.find(' href="/wiki/S%C3%A4ndB%C3%B5x\?'
                    'action=history&amp;blah=%252F"')
        finally:
            env.config.remove('mainnav', 'wiki.href')
            env.config.save()



def functionalSuite(suite=None):
    if not suite:
        import trac.tests.functional
        suite = trac.tests.functional.functionalSuite()
    suite.addTest(TestAttachmentNonexistentParent())
    suite.addTest(TestErrorPage())
    suite.addTest(RegressionTestRev6017())
    suite.addTest(RegressionTestTicket3833a())
    suite.addTest(RegressionTestTicket3833b())
    suite.addTest(RegressionTestTicket3833c())
    suite.addTest(RegressionTestTicket5572())
    suite.addTest(RegressionTestTicket7209())
    suite.addTest(RegressionTestTicket9880())
    suite.addTest(RegressionTestTicket3663())
    suite.addTest(RegressionTestTicket6318())
    suite.addTest(RegressionTestTicket11434())
    suite.addTest(RegressionTestTicket11503a())
    suite.addTest(RegressionTestTicket11503b())
    return suite


suite = functionalSuite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
