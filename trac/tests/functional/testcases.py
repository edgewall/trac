#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2008-2020 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

import os
import re
import socket
import unittest

from trac.tests.functional import FunctionalTestCaseSetup, \
                                  internal_error, tc
from trac.util import create_file


class TestAttachmentNonexistentParent(FunctionalTestCaseSetup):
    def runTest(self):
        """TracError should be raised when navigating to the attachment
        page for a nonexistent resource."""
        self._tester.go_to_wiki('NonexistentPage')
        tc.find(r"The page[ \n]+<strong>NonexistentPage</strong>[ \n]+"
                r"does not exist. You can create it here.")
        tc.find(r"\bCreate this page\b")

        tc.go(self._tester.url + '/attachment/wiki/NonexistentPage')
        tc.find(r'<h1>Trac Error</h1>\s+<p class="message">'
                r"Parent resource NonexistentPage doesn&#39;t exist</p>")


class TestAboutPage(FunctionalTestCaseSetup):
    def runTest(self):
        """Validate the About page."""
        tc.follow(r"\bAbout Trac\b")
        tc.find(r"<h1>About Trac</h1>")
        tc.find(r"<h2>System Information</h2>")
        tc.find(r"<h2>Configuration</h2>")


class TestErrorPage(FunctionalTestCaseSetup):
    """Validate the error page.
    Defects reported to trac-hacks should use the Component defined in the
    plugin's URL (#11434).
    """
    def runTest(self):
        env = self._testenv.get_trac_environment()
        create_file(os.path.join(env.plugins_dir, 'RaiseExceptionPlugin.py'),
"""\
from trac.core import Component, TracError, implements
from trac.web.api import IRequestHandler
from trac.util.html import html

url = None

class RaiseExceptionPlugin(Component):
    implements(IRequestHandler)

    def match_request(self, req):
        if req.path_info.startswith('/raise-exception'):
            return True

    def process_request(self, req):
        if req.args.get('type') == 'tracerror':
            if req.args.get('div'):
                raise TracError(html.div("The message in a div",
                                class_='message'))
            elif req.args.get('p'):
                raise TracError(html.p("The message in a p",
                                class_='message'))
            elif req.args.get('i'):
                raise TracError(html("The message with ",
                                     html.span("inline span"),
                                     " element"))
            else:
                raise TracError("The plaintext message")
        else:
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

            tc.go(self._tester.url + '/raise-exception?type=tracerror&div=true')
            tc.notfind(internal_error)
            tc.find('<h1>Trac Error</h1>[ \t\n]+'
                    '<div class="message">The message in a div</div>')

            tc.go(self._tester.url + '/raise-exception?type=tracerror&p=true')
            tc.notfind(internal_error)
            tc.find('<h1>Trac Error</h1>[ \t\n]+'
                    '<p class="message">The message in a p</p>')

            tc.go(self._tester.url + '/raise-exception?type=tracerror&i=true')
            tc.notfind(internal_error)
            tc.find('<h1>Trac Error</h1>[ \t\n]+'
                    '<p class="message">The message with '
                    '<span>inline span</span> element</p>')

            tc.go(self._tester.url + '/raise-exception?type=tracerror')
            tc.find('<h1>Trac Error</h1>[ \t\n]+'
                    '<p class="message">The plaintext message</p>')
        finally:
            env.config.set('components', 'RaiseExceptionPlugin.*', 'disabled')


class RegressionTestTicket3833(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/3833"""
        env = self._testenv.get_trac_environment()
        trac_log = os.path.join(env.log_dir, 'trac.log')

        def read_log_file(offset):
            with open(trac_log, 'rb') as fd:
                fd.seek(offset)
                return str(fd.read(), 'utf-8')

        # Verify that file logging is enabled as info level.
        log_size = os.path.getsize(trac_log)
        env.log.info("RegressionTestTicket3833 info1")
        info1 = "RegressionTestTicket3833 info1"
        log_content = read_log_file(log_size)
        self.assertEqual('INFO', env.config.get('logging', 'log_level'))
        self.assertIn(info1, log_content),

        # Verify that info level is not logged at warning level.
        env.config.set('logging', 'log_level', 'WARNING')
        env.config.save()
        env = self._testenv.get_trac_environment()
        log_size = os.path.getsize(trac_log)
        info2 = "RegressionTestTicket3833 info2"
        warn2 = "RegressionTestTicket3833 warn2"
        env.log.info(info2)
        env.log.warning(warn2)
        log_content = read_log_file(log_size)
        self.assertEqual('WARNING', env.config.get('logging', 'log_level'))
        self.assertNotIn(info2, log_content)
        self.assertIn(warn2, log_content)

        # Revert to info level logging.
        env.config.set('logging', 'log_level', 'INFO')
        env.config.save()
        env = self._testenv.get_trac_environment()
        log_size = os.path.getsize(trac_log)
        info3 = "RegressionTestTicket3833 info3"
        warn3 = "RegressionTestTicket3833 warn3"
        env.log.info(info3)
        env.log.warning(warn3)
        log_content = read_log_file(log_size)
        self.assertEqual('INFO', env.config.get('logging', 'log_level'))
        self.assertIn(info3, log_content)
        self.assertIn(warn3, log_content)


class RegressionTestTicket5572(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/5572"""
        # TODO: this ticket (implemented in r6011) adds a new feature to
        # make the progress bar more configurable.  We need to test this
        # new configurability.


class RegressionTestTicket7209(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/7209"""
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


class RegressionTestTicket9880(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/9880

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


class RegressionTestTicket3663(FunctionalTestCaseSetup):
    def runTest(self):
        """Regression test for non-UTF-8 PATH_INFO (#3663)

        Verify that URLs not encoded with UTF-8 are reported as invalid.
        """
        def fetch(uri):
            # http.client module disallows non-ascii characters in request
            # line. Instead, use directly socket module.
            cookie = '; '.join('%s=%s' % (c['name'], c['value'])
                               for c in tc.get_cookies()).encode('utf-8')
            req = (b'GET %s HTTP/1.0\r\n'
                   b'Host: %s:%d\r\n'
                   b'Cookie: %s\r\n'
                   b'Connection: close\r\n'
                   b'\r\n' % (uri, b'127.0.0.1', self._testenv.port, cookie))
            resp = []
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect(('127.0.0.1', self._testenv.port))
                s.send(req)
                while True:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    resp.append(chunk)
            resp = b''.join(resp)
            if not resp:
                raise RuntimeError('No response')
            match = re.match(b'HTTP\/[0-9]\.[0-9] +([0-9]{3}) +.*\r\n', resp)
            if not match:
                raise RuntimeError('No status line: %r' % resp)
            status = int(match.group(1))
            pos = resp.find(b'\r\n\r\n', len(match.group(0)))
            if pos == -1:
                raise RuntimeError('Missing CRLFCRLF in response: %r' % resp)
            body = resp[pos:]
            return status, body

        # invalid PATH_INFO
        status, body = fetch('/wiki/été'.encode('latin1'))
        self.assertEqual(404, status)
        self.assertIn(b'Invalid URL encoding', body)
        # invalid SCRIPT_NAME
        status, body = fetch('/été'.encode('latin1'))
        self.assertEqual(404, status)
        self.assertIn(b'Invalid URL encoding', body)


class RegressionTestTicket6318(FunctionalTestCaseSetup):
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
            self._tester.login('user')
            self._tester.go_to_front()
            self._tester.logout()
            # now test utf-8 user name
            self._testenv.adduser('joé')
            self._tester.login('joé')
            self._tester.go_to_front()
            # when failed to retrieve session, FakeSession() and FakePerm()
            # are used and the req.perm has no permissions.
            tc.notfind(internal_error)
            tc.notfind("You don't have the required permissions")
            self._tester.logout()
            # finally restore expected 'admin' login
            self._tester.login('admin')
        finally:
            self._testenv.deluser('joé')


class RegressionTestTicket11434(FunctionalTestCaseSetup):
    """Test for regression of https://trac.edgewall.org/ticket/11434
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


class RegressionTestTicket11503a(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/11503 a"""
        base = self._tester.url

        tc.go(base + '/notf%C5%91und/')
        tc.notfind(internal_error)
        tc.url(base + '/notf%C5%91und', regexp=False)

        tc.go(base + '/notf%C5%91und/?type=def%C3%A9ct')
        tc.notfind(internal_error)
        tc.url(base + '/notf%C5%91und?type=def%C3%A9ct', regexp=False)

        tc.go(base + '/notf%C5%91und/%252F/?type=%252F')
        tc.notfind(internal_error)
        tc.url(base + '/notf%C5%91und/%252F?type=%252F', regexp=False)


class RegressionTestTicket11503b(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/11503 b"""
        env = self._testenv.get_trac_environment()
        try:
            env.config.set('mainnav', 'wiki.href',
                           '/wiki/SändBõx?action=history&blah=%252F')
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
    suite.addTest(TestAboutPage())
    suite.addTest(TestErrorPage())
    suite.addTest(RegressionTestTicket3833())
    suite.addTest(RegressionTestTicket5572())
    suite.addTest(RegressionTestTicket7209())
    suite.addTest(RegressionTestTicket9880())
    suite.addTest(RegressionTestTicket3663())
    suite.addTest(RegressionTestTicket6318())
    suite.addTest(RegressionTestTicket11434())
    suite.addTest(RegressionTestTicket11503a())
    suite.addTest(RegressionTestTicket11503b())
    return suite


test_suite = functionalSuite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
