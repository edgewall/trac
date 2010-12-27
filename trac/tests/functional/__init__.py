#!/usr/bin/python
"""functional_tests

While unittests work well for testing facets of an implementation, they fail to
provide assurances that the user-visible functions work in practice.  Here, we
complement the unittests with functional tests that drive the system as a user
would to verify user visible functionality.  These functional tests are run as
part of the unittests.

So, we use Twill to verify Trac's functionality as served by tracd (and in the
future, other frontends).

Unlike most unittests, we setup a single fixture against which we run all the
testcases.  This is for two reasons: Primarily, that provides us with a more
complex set of data to test against and thus more room for triggering bugs.
Secondarily, the cost of setting up a new Trac environment and Subversion
repository is significant, so recreating the fixture for each test would be
very costly.

There are two primary objects involved in the testing, the
FunctionalTestEnvironment and the FunctionalTester.

FunctionalTestEnvironment represents the Trac environment, the Subversion
repository, and the server.  The server will be run on a random local port in
the range 8000-8999.  A subdirectory named 'tracenv' will be created containing
the Trac environment, Subversion repository, and the user authentication
information.  An 'admin' user is created and given TRAC_ADMIN privs early in
the testing.  There are other users added as well.  All accounts are setup with
a password equalling the username.  The test environment is left behind after
the testing has completed to assist in debugging.

FunctionalTester provides code reuse for the testcases to allow a higher-level
description of the more complicated bugs.  For example, creating a new ticket
is the first step in regression testing many things, so FunctionalTester
provides a create_ticket() method.  That method is written as if it were itself
a testcase for creating a ticket, so there is a testcase that simply calls that
method, and other testcases that use it as a higher-level step don't have to
worry about basic issues such as if the ticket was successfully created.

Requirements:
 - Twill (http://twill.idyll.org/)
 - lxml for XHTML validation (optional)
"""

import os
import signal
import sys
import time
import shutil
import stat
import unittest
import exceptions

import trac
from trac.tests.functional.compat import close_fds, rmtree

# Handle missing twill so we can print a useful 'SKIP'
# message.  We import subprocess first to allow customizing it on Windows
# to select pywin32 in favor of _subprocess for low-level calls.  If Twill
# is allowed to load first, its (unmodified) copy will always be loaded.
import subprocess

from better_twill import twill, b, tc, ConnectError

try:
    # This is the first indicator of whether the subversion bindings are
    # correctly installed.
    from svn import core
    has_svn = True
except ImportError:
    has_svn = False

from datetime import datetime, timedelta

from trac.tests.contentgen import random_sentence, random_page, random_word, \
    random_unique_camel
from trac.test import TestSetup, TestCaseSetup

internal_error = 'Trac detected an internal error:'

trac_source_tree = os.path.normpath(os.path.join(trac.__file__, '..', '..'))

# testing.log gets any unused output from subprocesses
logfile = open(os.path.join(trac_source_tree, 'testing.log'), 'w')

if twill:
    # functional-testing.log gets the twill output
    twill.set_output(open(os.path.join(trac_source_tree,
                                       'functional-testing.log'), 'w'))

    from trac.tests.functional.testenv import FunctionalTestEnvironment
    from trac.tests.functional.svntestenv import SvnFunctionalTestEnvironment

    from trac.tests.functional.tester import FunctionalTester


    class FunctionalTestSuite(TestSetup):
        """TestSuite that provides a test fixture containing a
        FunctionalTestEnvironment and a FunctionalTester.
        """

        if has_svn:
            env_class = SvnFunctionalTestEnvironment
        else:
            env_class = FunctionalTestEnvironment

        def setUp(self, port=None):
            """If no port is specified, use a semi-random port and subdirectory
            'testenv'; but if a port is specified, use that port and
            subdirectory 'testenv<portnum>'.
            """
            if port == None:
                port = 8000 + os.getpid() % 1000
                dirname = "testenv"
            else:
                dirname = "testenv%s" % port
            dirname = os.path.join(trac_source_tree, dirname)

            baseurl = "http://127.0.0.1:%s" % port
            self._testenv = self.env_class(dirname, port, baseurl)
            self._testenv.start()
            self._tester = FunctionalTester(baseurl)
            self.fixture = (self._testenv, self._tester)

        def tearDown(self):
            self._testenv.stop()


    class FunctionalTestCaseSetup(TestCaseSetup):
        """Convenience class to expand the fixture into the _testenv and
        _tester attributes."""
        def setUp(self):
            self._testenv, self._tester = self.fixture


    class FunctionalTwillTestCaseSetup(FunctionalTestCaseSetup):
        failureException = twill.errors.TwillAssertionError
else:
    # We're going to have to skip the functional tests
    class FunctionalTwillTestCaseSetup:
        pass
    class FunctionalTestCaseSetup:
        pass


# Twill's find command accepts regexes; some convenient but complex regexes
# & regex factories are provided here (only one so far):
def regex_owned_by(username):
    return '(Owned by:(<[^>]*>|\\n| )*%s)' % username


def suite():
    if twill:
        from trac.tests.functional.testcases import suite
        suite = suite()
    else:
        diagnostic = "SKIP: functional tests"
        if not twill:
            diagnostic += " (no twill installed)"
        print diagnostic
        # No tests to run, provide an empty suite.
        suite = unittest.TestSuite()
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
