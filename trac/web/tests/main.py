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
import re
import sys
import tempfile
import unittest
from subprocess import PIPE, Popen


import trac.tests.compat
from trac.config import ConfigurationError
from trac.core import Component, ComponentManager, TracError, implements
from trac.db.api import DatabaseManager
from trac.perm import PermissionError
from trac.resource import ResourceNotFound
from trac.test import EnvironmentStub, MockRequest
from trac.util import create_file
from trac.util.compat import close_fds
from trac.web.api import (HTTPForbidden, HTTPInternalError, HTTPNotFound,
    IRequestFilter, IRequestHandler, RequestDone)
from trac.web.auth import IAuthenticator
from trac.web.main import FakeSession, RequestDispatcher, Session, \
                          get_environments


class TestStubRequestHandler(Component):

    implements(IRequestHandler)

    filename = 'test_stub.html'

    template = """\
<!DOCTYPE html
    PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"
    "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html xmlns="http://www.w3.org/1999/xhtml"
      xmlns:py="http://genshi.edgewall.org/">
  <body>
    <h1>${greeting}</h1>
  </body>
</html>
"""

    def match_request(self, req):
        return req.path_info == '/test-stub'

    def process_request(self, req):
        return self.filename, {'greeting': 'Hello World'}, None


class AuthenticateTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(disable=['trac.web.auth.LoginModule'])
        self.request_dispatcher = RequestDispatcher(self.env)
        self.req = MockRequest(self.env)
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
        self.request_dispatcher.set_default_callbacks(req)

        self.assertEqual(1, len(self.request_dispatcher.authenticators))
        self.assertIsInstance(self.request_dispatcher.authenticators[0],
                              Authenticator)
        self.assertRaises(RequestDone, self.request_dispatcher.dispatch, req)
        self.assertEqual(1, authenticated[0])


class DispatchRequestTestCase(unittest.TestCase):

    def test_python_with_optimizations_raises_environment_error(self):
        """EnvironmentError exception is raised when dispatching request
        with optimizations enabled.
        """
        proc = Popen((sys.executable, '-O', '-c',
                      'from trac.web.main import dispatch_request; '
                      'dispatch_request({}, None)'), stdin=PIPE,
                     stdout=PIPE, stderr=PIPE, close_fds=close_fds)

        stdout, stderr = proc.communicate()
        for f in (proc.stdin, proc.stdout, proc.stderr):
            f.close()
        self.assertEqual(1, proc.returncode)
        self.assertIn("EnvironmentError: Python with optimizations is not "
                      "supported.", stderr)


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
        except HTTPInternalError as e:
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
        except HTTPForbidden as e:
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
        except HTTPNotFound as e:
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
        except HTTPInternalError as e:
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
        except HTTPInternalError as e:
            self.assertEqual("500 Not Implemented Error (Raised in "
                             "process_request)", unicode(e))
        else:
            self.fail("HTTPInternalError not raised")


class PostProcessRequestTestCase(unittest.TestCase):
    """Test cases for handling of the optional `method` argument in
    RequestDispatcher._post_process_request."""

    def setUp(self):
        self.env = EnvironmentStub()
        self.req = MockRequest(self.env)
        self.request_dispatcher = RequestDispatcher(self.env)
        self.compmgr = ComponentManager()
        self.env.clear_component_registry()

    def tearDown(self):
        self.env.restore_component_registry()

    def test_no_request_filters_request_handler_returns_method_false(self):
        """IRequestHandler doesn't return `method` and no IRequestFilters
        are registered. The `method` is set to `None`.
        """
        args = ('template.html', {}, 'text/html')
        resp = self.request_dispatcher._post_process_request(self.req, *args)
        self.assertEqual(0, len(self.request_dispatcher.filters))
        self.assertEqual(4, len(resp))
        self.assertEqual(args + (None,), resp)

    def test_no_request_filters_request_handler_returns_method_true(self):
        """IRequestHandler returns `method` and no IRequestFilters
        are registered. The `method` is forwarded.
        """
        args = ('template.html', {}, 'text/html', 'xhtml')
        resp = self.request_dispatcher._post_process_request(self.req, *args)
        self.assertEqual(0, len(self.request_dispatcher.filters))
        self.assertEqual(4, len(resp))
        self.assertEqual(args, resp)

    def test_4arg_post_process_request_request_handler_returns_method_false(self):
        """IRequestHandler doesn't return `method` and IRequestFilter doesn't
        accept `method` as an argument. The `method` is set to `None`.
        """
        class RequestFilter(Component):
            implements(IRequestFilter)
            def pre_process_request(self, req, handler):
                return handler
            def post_process_request(self, req, template, data, content_type):
                return template, data, content_type
        args = ('template.html', {}, 'text/html')
        resp = self.request_dispatcher._post_process_request(self.req, *args)
        self.assertEqual(1, len(self.request_dispatcher.filters))
        self.assertEqual(4, len(resp))
        self.assertEqual(args + (None,), resp)

    def test_4arg_post_process_request_request_handler_returns_method_true(self):
        """IRequestHandler returns `method` and IRequestFilter doesn't accept
        the argument. The `method` argument is forwarded over IRequestFilter
        implementations that don't accept the argument.
        """
        class RequestFilter(Component):
            implements(IRequestFilter)
            def pre_process_request(self, req, handler):
                return handler
            def post_process_request(self, req, template, data, content_type):
                return template, data, content_type
        args = ('template.html', {}, 'text/html', 'xhtml')
        resp = self.request_dispatcher._post_process_request(self.req, *args)
        self.assertEqual(1, len(self.request_dispatcher.filters))
        self.assertEqual(4, len(resp))
        self.assertEqual(args, resp)

    def test_5arg_post_process_request_request_handler_returns_method_false(self):
        """IRequestHandler doesn't return `method` and IRequestFilter accepts
        `method` as an argument. The `method` is set to `None`.
        """
        class RequestFilter(Component):
            implements(IRequestFilter)
            def pre_process_request(self, req, handler):
                return handler
            def post_process_request(self, req, template, data,
                                     content_type, method=None):
                return template, data, content_type, method
        args = ('template.html', {}, 'text/html')
        resp = self.request_dispatcher._post_process_request(self.req, *args)
        self.assertEqual(1, len(self.request_dispatcher.filters))
        self.assertEqual(4, len(resp))
        self.assertEqual(args[:3] + (None,), resp)

    def test_5arg_post_process_request_request_handler_returns_method_true(self):
        """IRequestHandler returns `method` and IRequestFilter accepts
        the argument. The `method` argument is passed through IRequestFilter
        implementations.
        """
        class RequestFilter(Component):
            implements(IRequestFilter)
            def pre_process_request(self, req, handler):
                return handler
            def post_process_request(self, req, template, data,
                                     content_type, method=None):
                return template, data, content_type, method
        args = ('template.html', {}, 'text/html', 'xhtml')
        resp = self.request_dispatcher._post_process_request(self.req, *args)
        self.assertEqual(1, len(self.request_dispatcher.filters))
        self.assertEqual(4, len(resp))
        self.assertEqual(args, resp)

    def test_5arg_post_process_request_request_handler_adds_method(self):
        """IRequestFilter adds `method` not returned by IRequestHandler.
        """
        class RequestFilter(Component):
            implements(IRequestFilter)
            def pre_process_request(self, req, handler):
                return handler
            def post_process_request(self, req, template, data,
                                     content_type, method=None):
                return template, data, content_type, 'xml'
        args = ('template.html', {}, 'text/html')
        resp = self.request_dispatcher._post_process_request(self.req, *args)
        self.assertEqual(1, len(self.request_dispatcher.filters))
        self.assertEqual(4, len(resp))
        self.assertEqual(args[:3] + ('xml',), resp)

    def test_5arg_post_process_request_request_handler_modifies_method(self):
        """IRequestFilter modifies `method` returned by IRequestHandler.
        """
        class RequestFilter(Component):
            implements(IRequestFilter)
            def pre_process_request(self, req, handler):
                return handler
            def post_process_request(self, req, template, data,
                                     content_type, method=None):
                return template, data, content_type, 'xml'
        args = ('template.html', {}, 'text/html', 'xhtml')
        resp = self.request_dispatcher._post_process_request(self.req, *args)
        self.assertEqual(1, len(self.request_dispatcher.filters))
        self.assertEqual(4, len(resp))
        self.assertEqual(args[:3] + ('xml',), resp)

    def test_redirect_on_permission_error(self):
        """The post_process_request method can redirect during exception
        handling from an exception raised in process_request.
        """
        class RedirectOnPermissionErrorStub(Component):
            implements(IRequestHandler, IRequestFilter)

            def match_request(self, req):
                return re.match(r'/perm-error', req.path_info)

            def process_request(self, req):
                req.entered_process_request = True
                raise PermissionError("No permission to view")

            def pre_process_request(self, req, handler):
                return handler

            def post_process_request(self, req, template, data, content_type):
                if (template, data, content_type) == (None, None, None):
                    req.entered_post_process_request = True
                    req.redirect(req.href('/redirect-target'))
                return template, data, content_type

        dispatcher = RequestDispatcher(self.env)
        req = MockRequest(self.env, method='GET', path_info='/perm-error')
        req.entered_process_request = False
        req.entered_post_process_request = False

        try:
            dispatcher.dispatch(req)
        except RequestDone:
            pass
        else:
            self.fail("RequestDone not raised")

        self.assertTrue(req.entered_process_request)
        self.assertTrue(req.entered_post_process_request)


class RequestDispatcherTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(
            path=tempfile.mkdtemp(prefix='trac-tempenv-'))
        os.mkdir(self.env.templates_dir)
        filepath = os.path.join(self.env.templates_dir,
                                TestStubRequestHandler.filename)
        create_file(filepath, TestStubRequestHandler.template)

    def tearDown(self):
        self.env.reset_db_and_disk()

    def _insert_session(self):
        sid = '1234567890abcdef'
        name = 'First Last'
        email = 'first.last@example.com'
        self.env.insert_users([(sid, name, email, 0)])
        return sid, name, email

    def test_invalid_default_date_format_raises_exception(self):
        self.env.config.set('trac', 'default_date_format', u'ĭšo8601')

        self.assertEqual(u'ĭšo8601',
                         self.env.config.get('trac', 'default_date_format'))
        self.assertRaises(ConfigurationError, getattr,
                          RequestDispatcher(self.env), 'default_date_format')

    def test_get_session_returns_session(self):
        """Session is returned when database is reachable."""
        sid, name, email = self._insert_session()
        req = MockRequest(self.env, path_info='/test-stub',
                          cookie='trac_session=%s;' % sid)
        request_dispatcher = RequestDispatcher(self.env)
        request_dispatcher.set_default_callbacks(req)

        self.assertRaises(RequestDone, request_dispatcher.dispatch, req)

        self.assertIsInstance(req.session, Session)
        self.assertEqual(sid, req.session.sid)
        self.assertEqual(name, req.session['name'])
        self.assertEqual(email, req.session['email'])
        self.assertFalse(req.session.authenticated)
        self.assertEqual('200 Ok', req.status_sent[0])
        self.assertIn('<h1>Hello World</h1>', req.response_sent.getvalue())

    def test_get_session_returns_fake_session(self):
        """Fake session is returned when database is not reachable."""
        sid = self._insert_session()[0]
        request_dispatcher = RequestDispatcher(self.env)

        def get_session(req):
            """Simulates an unreachable database."""
            _get_connector = DatabaseManager.get_connector

            def get_connector(self):
                raise TracError("Database not reachable")

            DatabaseManager.get_connector = get_connector
            DatabaseManager(self.env).shutdown()
            session = request_dispatcher._get_session(req)
            DatabaseManager.get_connector = _get_connector
            return session

        req = MockRequest(self.env, path_info='/test-stub',
                          cookie='trac_session=%s;' % sid)
        req.callbacks['session'] = get_session

        self.assertRaises(RequestDone, request_dispatcher.dispatch, req)

        self.assertIsInstance(req.session, FakeSession)
        self.assertIsNone(req.session.sid)
        self.assertNotIn('name', req.session)
        self.assertNotIn('email', req.session)
        self.assertFalse(req.session.authenticated)
        self.assertEqual('200 Ok', req.status_sent[0])
        self.assertIn('<h1>Hello World</h1>', req.response_sent.getvalue())

    def test_invalid_session_id_returns_fake_session(self):
        """Fake session is returned when session id is invalid."""
        sid = 'a' * 23 + '$'  # last char invalid, sid must be alphanumeric.
        req = MockRequest(self.env, path_info='/test-stub',
                          cookie='trac_session=%s;' % sid)
        request_dispatcher = RequestDispatcher(self.env)
        request_dispatcher.set_default_callbacks(req)

        self.assertRaises(RequestDone, request_dispatcher.dispatch, req)

        self.assertIsInstance(req.session, FakeSession)
        self.assertIsNone(req.session.sid)
        self.assertEqual('200 Ok', req.status_sent[0])
        self.assertIn('<h1>Hello World</h1>', req.response_sent.getvalue())


class HdfdumpTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.req = MockRequest(self.env, args={'hdfdump': '1'})
        self.env.clear_component_registry()
        self.request_dispatcher = RequestDispatcher(self.env)
        perm = self.req.perm
        self.request_dispatcher._get_perm = lambda req: perm

    def tearDown(self):
        self.env.restore_component_registry()

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
        self.assertIn("{'name': 'value'}\n",
                      self.req.response_sent.getvalue())
        self.assertEqual('text/plain;charset=utf-8',
                         self.req.headers_sent['Content-Type'])


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(AuthenticateTestCase))
    suite.addTest(unittest.makeSuite(DispatchRequestTestCase))
    suite.addTest(unittest.makeSuite(EnvironmentsTestCase))
    suite.addTest(unittest.makeSuite(PreProcessRequestTestCase))
    suite.addTest(unittest.makeSuite(ProcessRequestTestCase))
    suite.addTest(unittest.makeSuite(PostProcessRequestTestCase))
    suite.addTest(unittest.makeSuite(RequestDispatcherTestCase))
    suite.addTest(unittest.makeSuite(HdfdumpTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
