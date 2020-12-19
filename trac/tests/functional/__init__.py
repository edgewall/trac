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

import atexit
import os
import subprocess
import unittest
from pkg_resources import parse_version

try:
    from svn import core
except ImportError:
    has_svn = False
else:
    has_svn = True

# Handle missing twill so we can print a useful 'SKIP'
# message.  We import subprocess first to allow customizing it on Windows
# to select pywin32 in favor of _subprocess for low-level calls.  If Twill
# is allowed to load first, its (unmodified) copy will always be loaded.

import trac
from trac.test import TestSetup, TestCaseSetup
from trac.tests.functional.better_twill import b, tc, selenium
from trac.util import create_file, read_file


internal_error = 'Trac detected an internal error:'

trac_source_tree = os.path.normpath(os.path.join(trac.__file__, '..', '..'))

if selenium:
    from trac.tests.functional.testenv import FunctionalTestEnvironment
    from trac.tests.functional.svntestenv import SvnFunctionalTestEnvironment

    from trac.tests.functional.tester import FunctionalTester

    from selenium.common.exceptions import WebDriverException

    class FunctionalTestSuite(TestSetup):
        """TestSuite that provides a test fixture containing a
        FunctionalTestEnvironment and a FunctionalTester.
        """

        if has_svn:
            env_class = SvnFunctionalTestEnvironment
        else:
            env_class = FunctionalTestEnvironment

        tester_class = FunctionalTester

        def __init__(self):
            minimum = '3.0.0'
            if parse_version(selenium.__version__) < parse_version(minimum):
                raise ImportError('Selenium %s is required. Found version %s.'
                                  % (minimum, selenium.__version__))
            super(FunctionalTestSuite, self).__init__()

        def setUp(self, port=None):
            """If no port is specified, use a semi-random port and subdirectory
            'testenv'; but if a port is specified, use that port and
            subdirectory 'testenv<portnum>'.
            """
            if port is None:
                try:
                    port = int(os.getenv('TRAC_TEST_PORT'))
                except (TypeError, ValueError):
                    pass

            env_path = os.getenv('TRAC_TEST_ENV_PATH')
            if not env_path:
                env_name = 'testenv%s' % (port or '')
                env_path = os.path.join(trac_source_tree, env_name)
            else:
                env_path += str(port or '')

            if port is None:
                port = get_ephemeral_port()
            server_port = get_ephemeral_port()

            baseurl = "http://127.0.0.1:%s" % port
            self._testenv = self.env_class(env_path, server_port, baseurl)
            self._testenv.set_config('project', 'name', 'Functional Tests')
            self._testenv.set_config('trac', 'base_url', baseurl)
            create_file(
                os.path.join(env_path, 'trac', 'htdocs',
                             'your_project_logo.png'),
                read_file(os.path.join(trac_source_tree, 'trac', 'htdocs',
                                       'trac_logo_mini.png'), 'rb'),
                'wb')

            # functional-testing.log gets the twill output
            self.functional_test_log = \
                os.path.join(env_path, 'functional-testing.log')

            tc.init(port, server_port)
            self._testenv.start()
            try:
                self._tester = self.tester_class(baseurl)
            except:
                self._testenv.stop()
                tc.close()
                raise
            self.fixture = (self._testenv, self._tester)

            atexit.register(self.tearDown)

        def tearDown(self):
            atexit.unregister(self.tearDown)
            self._testenv.close()
            tc.close()


    class FunctionalTestCaseSetup(TestCaseSetup):
        """Convenience class to expand the fixture into the _testenv and
        _tester attributes."""
        def setUp(self):
            self._testenv, self._tester = self.fixture


    class FunctionalTestCaseSetup(FunctionalTestCaseSetup):
        failureException = WebDriverException

else:
    # We're going to have to skip the functional tests
    class FunctionalTestSuite(TestSetup):
        def __init__(self):
            raise ImportError("Selenium not installed")

    class FunctionalTestCaseSetup(object):
        pass

    class FunctionalTestCaseSetup(object):
        pass

# Compatibility code: Remove in 1.7.1
FunctionalTwillTestCaseSetup = FunctionalTestCaseSetup


def get_ephemeral_port():
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('127.0.0.1', 0))
        s.listen(1)
        return s.getsockname()[1]


# Twill's find command accepts regexes; some convenient but complex regexes
# & regex factories are provided here (only one so far):
def regex_owned_by(username):
    return '(Owned by:(<[^>]*>|\\n| )*%s)' % username


def functionalSuite():
    suite = FunctionalTestSuite()
    return suite


def test_suite():
    try:
        suite = functionalSuite()
    except ImportError as e:
        print("SKIP: functional tests (%s)" % e)
        # No tests to run, provide an empty suite.
        suite = unittest.TestSuite()
    else:
        import trac.tests.functional.testcases
        trac.tests.functional.testcases.functionalSuite(suite)
        import trac.versioncontrol.tests
        trac.versioncontrol.tests.functionalSuite(suite)
        import trac.ticket.tests
        trac.ticket.tests.functionalSuite(suite)
        import trac.mimeview.tests
        trac.mimeview.tests.functionalSuite(suite)
        import trac.prefs.tests
        trac.prefs.tests.functionalSuite(suite)
        import trac.wiki.tests
        trac.wiki.tests.functionalSuite(suite)
        import trac.timeline.tests
        trac.timeline.tests.functionalSuite(suite)
        import trac.admin.tests
        trac.admin.tests.functionalSuite(suite)
        import trac.search.tests
        trac.search.tests.functionalSuite(suite)
        # The db tests should be last since the backup test occurs there.
        import trac.db.tests
        trac.db.tests.functionalSuite(suite)
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
