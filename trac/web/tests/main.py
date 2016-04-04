# -*- coding: utf-8 -*-
#
# Copyright (C) 2010-2013 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import os.path
import tempfile
import unittest

from trac.core import Component, TracError, implements
from trac.perm import PermissionError
from trac.resource import ResourceNotFound
from trac.test import EnvironmentStub, Mock, MockPerm, MockRequest
from trac.util import create_file
from trac.web.api import (HTTPForbidden, HTTPInternalError, HTTPNotFound,
    IRequestFilter, IRequestHandler, RequestDone)
from trac.web.auth import IAuthenticator
from trac.web.main import RequestDispatcher, get_environments


class AuthenticateTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(disable=['trac.web.auth.LoginModule'])
        self.request_dispatcher = RequestDispatcher(self.env)
        self.req = Mock(chrome={'warnings': []})
        self.env.clear_component_registry()

    def tearDown(self):
        self.env.restore_component_registry()

    def test_authenticate_returns_first_successful(self):
        class SuccessfulAuthenticator1(Component):
            implements(IAuthenticator)
            def authenticate(self, req):
                return 'user1'
        class SuccessfulAuthenticator2(Component):
            implements(IAuthenticator)
            def authenticate(self, req):
                return 'user2'
        self.assertEqual(2, len(self.request_dispatcher.authenticators))
        self.assertIsInstance(self.request_dispatcher.authenticators[0],
                              SuccessfulAuthenticator1)
        self.assertIsInstance(self.request_dispatcher.authenticators[1],
                              SuccessfulAuthenticator2)
        self.assertEqual('user1',
                         self.request_dispatcher.authenticate(self.req))

    def test_authenticate_skips_unsuccessful(self):
        class UnsuccessfulAuthenticator(Component):
            implements(IAuthenticator)
            def authenticate(self, req):
                return None
        class SuccessfulAuthenticator(Component):
            implements(IAuthenticator)
            def authenticate(self, req):
                return 'user'
        self.assertEqual(2, len(self.request_dispatcher.authenticators))
        self.assertIsInstance(self.request_dispatcher.authenticators[0],
                              UnsuccessfulAuthenticator)
        self.assertIsInstance(self.request_dispatcher.authenticators[1],
                              SuccessfulAuthenticator)
        self.assertEqual('user',
                         self.request_dispatcher.authenticate(self.req))

    def test_authenticate_raises(self):
        class RaisingAuthenticator(Component):
            implements(IAuthenticator)
            def authenticate(self, req):
                raise TracError("Bad attempt")
        class SuccessfulAuthenticator(Component):
            implements(IAuthenticator)
            def authenticate(self, req):
                return 'user'
        self.assertEqual(2, len(self.request_dispatcher.authenticators))
        self.assertIsInstance(self.request_dispatcher.authenticators[0],
                              RaisingAuthenticator)
        self.assertIsInstance(self.request_dispatcher.authenticators[1],
                              SuccessfulAuthenticator)
        self.assertEqual('anonymous',
                         self.request_dispatcher.authenticate(self.req))
        self.assertEqual(1, len(self.req.chrome['warnings']))

    def test_authenticate_once(self):
        class Authenticator(Component):
            implements(IAuthenticator)
            def authenticate(self, req):
                authenticated[0] += 1
                return 'admin'
        class AuthenticateRequestHandler(Component):
            implements(IRequestHandler)
            def match_request(self, req):
                return bool(req.perm)
            def process_request(self, req):
                req.authname
                req.send('')

        self.env.config.set('trac', 'default_handler',
                            'AuthenticateRequestHandler')
        authenticated = [0]
        req = MockRequest(self.env)

        self.assertEqual(1, len(self.request_dispatcher.authenticators))
        self.assertIsInstance(self.request_dispatcher.authenticators[0],
                              Authenticator)
        self.assertRaises(RequestDone, self.request_dispatcher.dispatch, req)
        self.assertEqual(1, authenticated[0])


class EnvironmentsTestCase(unittest.TestCase):

    dirs = ('mydir1', 'mydir2', '.hidden_dir')
    files = ('myfile1', 'myfile2', '.dot_file')

    def setUp(self):
        self.parent_dir = tempfile.mkdtemp(prefix='trac-')
        self.tracignore = os.path.join(self.parent_dir, '.tracignore')
        for dname in self.dirs:
            os.mkdir(os.path.join(self.parent_dir, dname))
        for fname in self.files:
            create_file(os.path.join(self.parent_dir, fname))
        self.environ = {
           'trac.env_paths': [],
           'trac.env_parent_dir': self.parent_dir,
        }

    def tearDown(self):
        for fname in self.files:
            os.unlink(os.path.join(self.parent_dir, fname))
        for dname in self.dirs:
            os.rmdir(os.path.join(self.parent_dir, dname))
        if os.path.exists(self.tracignore):
            os.unlink(self.tracignore)
        os.rmdir(self.parent_dir)

    def env_paths(self, projects):
        return dict((project, os.path.normpath(os.path.join(self.parent_dir,
                                                            project)))
                    for project in projects)

    def test_default_tracignore(self):
        self.assertEqual(self.env_paths(['mydir1', 'mydir2']),
                         get_environments(self.environ))

    def test_empty_tracignore(self):
        create_file(self.tracignore)
        self.assertEqual(self.env_paths(['mydir1', 'mydir2', '.hidden_dir']),
                         get_environments(self.environ))

    def test_qmark_pattern_tracignore(self):
        create_file(self.tracignore, 'mydir?')
        self.assertEqual(self.env_paths(['.hidden_dir']),
                         get_environments(self.environ))

    def test_star_pattern_tracignore(self):
        create_file(self.tracignore, 'my*\n.hidden_dir')
        self.assertEqual({}, get_environments(self.environ))

    def test_combined_tracignore(self):
        create_file(self.tracignore, 'my*i?1\n\n#mydir2')
        self.assertEqual(self.env_paths(['mydir2', '.hidden_dir']),
                         get_environments(self.environ))


class PreProcessRequestTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.env.config.set('trac', 'default_handler', 'DefaultHandler')
        self.env.clear_component_registry()
        class DefaultHandler(Component):
            implements(IRequestHandler)
            def match_request(self, req):
                return True
            def process_request(self, req):
                pass

    def tearDown(self):
        self.env.restore_component_registry()

    def test_trac_error_raises_http_internal_error(self):
        """TracError in pre_process_request is trapped and an
        HTTPInternalError is raised.
        """
        class RequestFilter(Component):
            implements(IRequestFilter)
            def pre_process_request(self, req, handler):
                raise TracError("Raised in pre_process_request")
            def post_process_request(self, req, template, data, content_type):
                return template, data, content_type
        req = MockRequest(self.env)

        try:
            RequestDispatcher(self.env).dispatch(req)
        except HTTPInternalError, e:
            self.assertEqual("500 Trac Error (Raised in pre_process_request)",
                             unicode(e))
        else:
            self.fail("HTTPInternalError not raised")


class ProcessRequestTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.env.config.set('trac', 'default_handler', 'DefaultHandler')
        self.env.clear_component_registry()
        class DefaultHandler(Component):
            implements(IRequestHandler)
            def match_request(self, req):
                return True
            def process_request(self, req):
                raise req.exc_class("Raised in process_request")

    def tearDown(self):
        self.env.restore_component_registry()

    def test_permission_error_raises_http_forbidden(self):
        """TracError in process_request is trapped and an HTTPForbidden
        error is raised.
        """
        req = MockRequest(self.env)
        req.exc_class = PermissionError

        try:
            RequestDispatcher(self.env).dispatch(req)
        except HTTPForbidden, e:
            self.assertEqual(
                "403 Forbidden (Raised in process_request "
                "privileges are required to perform this operation. You "
                "don't have the required permissions.)", unicode(e))
        else:
            self.fail("HTTPForbidden not raised")

    def test_resource_not_found_raises_http_not_found(self):
        """ResourceNotFound error in process_request is trapped and an
        HTTPNotFound error is raised.
        """
        req = MockRequest(self.env)
        req.exc_class = ResourceNotFound

        try:
            RequestDispatcher(self.env).dispatch(req)
        except HTTPNotFound, e:
            self.assertEqual("404 Trac Error (Raised in process_request)",
                             unicode(e))
        else:
            self.fail("HTTPNotFound not raised")

    def test_trac_error_raises_http_internal_error(self):
        """TracError in process_request is trapped and an
        HTTPInternalError is raised.
        """
        req = MockRequest(self.env)
        req.exc_class = TracError

        try:
            RequestDispatcher(self.env).dispatch(req)
        except HTTPInternalError, e:
            self.assertEqual("500 Trac Error (Raised in process_request)",
                             unicode(e))
        else:
            self.fail("HTTPInternalError not raised")

    def test_not_implemented_error_raises_http_internal_server_error(self):
        """NotImplementedError in process_request is trapped and an
        HTTPInternalError is raised.
        """
        req = MockRequest(self.env)
        req.exc_class = NotImplementedError

        try:
            RequestDispatcher(self.env).dispatch(req)
        except HTTPInternalError, e:
            self.assertEqual("500 Not Implemented Error (Raised in "
                             "process_request)", unicode(e))
        else:
            self.fail("HTTPInternalError not raised")


class HdfdumpTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.request_dispatcher = RequestDispatcher(self.env)
        self.req = Mock(chrome={'warnings': []}, method='GET', perm=MockPerm(),
                        args={'hdfdump': '1'}, session={}, callbacks={},
                        send=self._req_send)
        self.content = None
        self.content_type = None
        self.env.clear_component_registry()

    def tearDown(self):
        self.env.restore_component_registry()

    def _req_send(self, content, content_type='text/html'):
        self.content = content
        self.content_type = content_type
        raise RequestDone()

    def test_hdfdump(self):
        class HdfdumpRequestHandler(Component):
            implements(IRequestHandler)
            def match_request(self, req):
                return True
            def process_request(self, req):
                data = {'name': 'value'}
                return 'error.html', data, None

        self.env.config.set('trac', 'default_handler', 'HdfdumpRequestHandler')
        self.assertRaises(RequestDone, self.request_dispatcher.dispatch,
                          self.req)
        self.assertEqual("{'name': 'value'}\n", self.content)
        self.assertEqual('text/plain', self.content_type)


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(AuthenticateTestCase))
    suite.addTest(unittest.makeSuite(EnvironmentsTestCase))
    suite.addTest(unittest.makeSuite(PreProcessRequestTestCase))
    suite.addTest(unittest.makeSuite(ProcessRequestTestCase))
    suite.addTest(unittest.makeSuite(HdfdumpTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
