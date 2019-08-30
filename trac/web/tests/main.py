# -*- coding: utf-8 -*-
#
# Copyright (C) 2010-2019 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

import io
import os.path
import re
import textwrap
import unittest

import trac.env
from trac.config import ConfigurationError
from trac.core import Component, TracError, implements
from trac.db.api import DatabaseManager
from trac.perm import PermissionError, PermissionSystem
from trac.resource import ResourceNotFound
from trac.test import EnvironmentStub, MockRequest, mkdtemp
from trac.util import create_file
from trac.web.api import (HTTPForbidden, HTTPInternalServerError,
    HTTPNotFound, IRequestFilter, IRequestHandler, RequestDone)
from trac.web.auth import IAuthenticator
from trac.web.main import FakeSession, RequestDispatcher, Session, \
                          dispatch_request, get_environments


class TestStubRequestHandler(Component):

    implements(IRequestHandler)

    filename = 'test_stub.html'

    template = textwrap.dedent("""\
        <!DOCTYPE html>
        <html>
          <body>
            <h1>${greeting}</h1>
          </body>
        </html>
        """)

    def match_request(self, req):
        return req.path_info == '/test-stub'

    def process_request(self, req):
        return self.filename, {'greeting': 'Hello World'}


class AuthenticateTestCase(unittest.TestCase):

    authenticators = {}
    request_handlers = []

    @classmethod
    def setUpClass(cls):
        class UnsuccessfulAuthenticator(Component):
            implements(IAuthenticator)
            def authenticate(self, req):
                return None

        class RaisingAuthenticator(Component):
            implements(IAuthenticator)
            def authenticate(self, req):
                raise TracError("Bad attempt")

        class SuccessfulAuthenticator1(Component):
            implements(IAuthenticator)
            def authenticate(self, req):
                return 'user1'

        class SuccessfulAuthenticator2(Component):
            implements(IAuthenticator)
            def authenticate(self, req):
                return 'user2'

        class AuthenticateRequestHandler(Component):
            implements(IRequestHandler)
            def __init__(self):
                self.calls = 0
            def match_request(self, req):
                return bool(req.perm)
            def process_request(self, req):
                self.calls += 1
                req.authname
                req.send('')

        cls.authenticators['success1'] = SuccessfulAuthenticator1
        cls.authenticators['success2'] = SuccessfulAuthenticator2
        cls.authenticators['unsuccess'] = UnsuccessfulAuthenticator
        cls.authenticators['raising'] = RaisingAuthenticator
        cls.request_handlers = [AuthenticateRequestHandler]

    @classmethod
    def tearDownClass(cls):
        from trac.core import ComponentMeta
        for component in cls.authenticators.values() + cls.request_handlers:
            ComponentMeta.deregister(component)

    def setUp(self):
        self.env = EnvironmentStub(enable=('trac.web.main.*',))
        self.req = MockRequest(self.env)
        self.request_dispatcher = RequestDispatcher(self.env)

    def test_authenticate_returns_first_successful(self):
        self.env.enable_component(self.authenticators['success1'])
        self.env.enable_component(self.authenticators['success2'])
        self.assertEqual(2, len(self.request_dispatcher.authenticators))
        self.assertIsInstance(self.request_dispatcher.authenticators[0],
                              self.authenticators['success1'])
        self.assertIsInstance(self.request_dispatcher.authenticators[1],
                              self.authenticators['success2'])
        self.assertEqual('user1',
                         self.request_dispatcher.authenticate(self.req))

    def test_authenticate_skips_unsuccessful(self):
        self.env.enable_component(self.authenticators['unsuccess'])
        self.env.enable_component(self.authenticators['success1'])
        self.assertEqual(2, len(self.request_dispatcher.authenticators))
        self.assertIsInstance(self.request_dispatcher.authenticators[0],
                              self.authenticators['unsuccess'])
        self.assertIsInstance(self.request_dispatcher.authenticators[1],
                              self.authenticators['success1'])
        self.assertEqual('user1',
                         self.request_dispatcher.authenticate(self.req))

    def test_authenticate_raises(self):
        self.env.enable_component(self.authenticators['raising'])
        self.env.enable_component(self.authenticators['success1'])
        self.assertEqual(2, len(self.request_dispatcher.authenticators))
        self.assertIsInstance(self.request_dispatcher.authenticators[0],
                              self.authenticators['raising'])
        self.assertIsInstance(self.request_dispatcher.authenticators[1],
                              self.authenticators['success1'])
        self.assertEqual('anonymous',
                         self.request_dispatcher.authenticate(self.req))
        self.assertEqual(1, len(self.req.chrome['warnings']))
        expected = "Can't authenticate using RaisingAuthenticator: "
        for level, message in self.env.log_messages:
            if expected in message.split('\n'):
                self.assertEqual('ERROR', level)
                break
        else:
            self.fail("Expected log message not found: \"%s\"" % expected)

    def test_authenticate_once(self):
        self.env.enable_component(self.authenticators['success1'])
        self.env.enable_component(self.request_handlers[0])
        self.env.config.set('trac', 'default_handler',
                            'AuthenticateRequestHandler')
        self.request_dispatcher.set_default_callbacks(self.req)

        with self.assertRaises(RequestDone):
            self.request_dispatcher.dispatch(self.req)

        self.assertEqual(1, len(self.request_dispatcher.authenticators))
        self.assertEqual(1, len(self.request_dispatcher.handlers))
        self.assertEqual(1, self.request_dispatcher.handlers[0].calls)


class EnvironmentsTestCase(unittest.TestCase):

    dirs = ('mydir1', 'mydir2', '.hidden_dir')
    files = ('myfile1', 'myfile2', '.dot_file')

    def setUp(self):
        self.parent_dir = mkdtemp()
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
        return {project: os.path.normpath(os.path.join(self.parent_dir,
                                                       project))
                for project in projects}

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

    components = []

    @classmethod
    def setUpClass(cls):

        class DefaultHandler(Component):
            implements(IRequestHandler)
            def match_request(self, req):
                return True
            def process_request(self, req):
                pass

        class RequestFilter(Component):
            implements(IRequestFilter)
            def pre_process_request(self, req, handler):
                raise TracError("Raised in pre_process_request")
            def post_process_request(self, req, template, data, metadata):
                return template, data, metadata

        cls.components = [DefaultHandler, RequestFilter]

    @classmethod
    def tearDownClass(cls):
        from trac.core import ComponentMeta
        for component in cls.components:
            ComponentMeta.deregister(component)

    def setUp(self):
        self.env = EnvironmentStub(enable=['trac.web.*'] +
                                          self.components)
        self.env.config.set('trac', 'default_handler', 'DefaultHandler')

    def test_trac_error_raises_http_internal_server_error(self):
        """TracError in pre_process_request is trapped and an
        HTTPInternalServerError is raised.
        """
        req = MockRequest(self.env)

        try:
            RequestDispatcher(self.env).dispatch(req)
        except HTTPInternalServerError as e:
            self.assertEqual("500 Trac Error (Raised in pre_process_request)",
                             unicode(e))
        else:
            self.fail("HTTPInternalServerError not raised")


class ProcessRequestTestCase(unittest.TestCase):

    request_handlers = []

    @classmethod
    def setUpClass(cls):

        class DefaultHandler(Component):
            implements(IRequestHandler)
            def match_request(self, req):
                return True
            def process_request(self, req):
                raise req.exc_class("Raised in process_request")

        cls.request_handlers = [DefaultHandler]

    @classmethod
    def tearDownClass(cls):
        from trac.core import ComponentMeta
        for component in cls.request_handlers:
            ComponentMeta.deregister(component)

    def setUp(self):
        self.env = EnvironmentStub(enable=['trac.web.*'] +
                                          self.request_handlers)
        self.env.config.set('trac', 'default_handler', 'DefaultHandler')

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

    def test_trac_error_raises_http_internal_server_error(self):
        """TracError in process_request is trapped and an
        HTTPInternalServerError is raised.
        """
        req = MockRequest(self.env)
        req.exc_class = TracError

        try:
            RequestDispatcher(self.env).dispatch(req)
        except HTTPInternalServerError as e:
            self.assertEqual("500 Trac Error (Raised in process_request)",
                             unicode(e))
        else:
            self.fail("HTTPInternalServerError not raised")

    def test_not_implemented_error_raises_http_internal_server_error(self):
        """NotImplementedError in process_request is trapped and an
        HTTPInternalServerError is raised.
        """
        req = MockRequest(self.env)
        req.exc_class = NotImplementedError

        try:
            RequestDispatcher(self.env).dispatch(req)
        except HTTPInternalServerError as e:
            self.assertEqual("500 Not Implemented Error (Raised in "
                             "process_request)", unicode(e))
        else:
            self.fail("HTTPInternalServerError not raised")


class PostProcessRequestTestCase(unittest.TestCase):
    """Test cases for handling of the optional `method` argument in
    RequestDispatcher._post_process_request."""

    request_filter = {}

    @classmethod
    def setUpClass(cls):
        class RequestFilter4Arg(Component):
            implements(IRequestFilter)
            def pre_process_request(self, req, handler):
                return handler
            def post_process_request(self, req, template, data, metadata):
                return template, data, metadata

        class RequestFilter5Arg(Component):
            implements(IRequestFilter)
            def pre_process_request(self, req, handler):
                return handler
            def post_process_request(self, req, template, data, metadata,
                                     method=None):
                return template, data, metadata, method

        class RequestFilter5ArgXml(Component):
            implements(IRequestFilter)
            def pre_process_request(self, req, handler):
                return handler
            def post_process_request(self, req, template, data,
                                     metadata, method=None):
                return template, data, metadata, 'xml'

        class RequestFilterRedirectOnPermError(Component):
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

        cls.request_filter['4Arg'] = RequestFilter4Arg
        cls.request_filter['5Arg'] = RequestFilter5Arg
        cls.request_filter['5ArgXml'] = RequestFilter5ArgXml
        cls.request_filter['RedirectOnPermError'] = \
            RequestFilterRedirectOnPermError

    @classmethod
    def tearDownClass(cls):
        from trac.core import ComponentMeta
        for component in cls.request_filter.values():
            ComponentMeta.deregister(component)

    def setUp(self):
        self.env = EnvironmentStub(enable=('trac.web.main.*',))
        self.req = MockRequest(self.env)

    def test_no_request_filters_request_handler_returns_method_false(self):
        """IRequestHandler doesn't return `method` and no IRequestFilters
        are registered. The `method` is set to `None`.
        """
        args = ('template.html', {}, 'text/html')
        request_dispatcher = RequestDispatcher(self.env)
        resp = request_dispatcher._post_process_request(self.req, *args)
        self.assertEqual(0, len(request_dispatcher.filters))
        self.assertEqual(4, len(resp))
        self.assertEqual(args + (None,), resp)
        # TODO (1.5.1) remove old API (genshi style)
        args = ('template.html', {}, {'content_type': 'text/html'})
        request_dispatcher = RequestDispatcher(self.env)
        resp = request_dispatcher._post_process_request(self.req, *args)
        self.assertEqual(0, len(request_dispatcher.filters))
        self.assertEqual(4, len(resp))
        self.assertEqual(args + (None,), resp)

    def test_no_request_filters_request_handler_returns_method_true(self):
        """IRequestHandler returns `method` and no IRequestFilters
        are registered. The `method` is forwarded.
        """
        args = ('template.html', {}, 'text/html', 'xhtml')
        request_dispatcher = RequestDispatcher(self.env)
        resp = request_dispatcher._post_process_request(self.req, *args)
        self.assertEqual(0, len(request_dispatcher.filters))
        self.assertEqual(4, len(resp))
        self.assertEqual(args, resp)
        # TODO (1.5.1) remove old API (genshi style)
        args = ('template.html', {}, {'content_type': 'text/html'}, 'xhtml')
        resp = request_dispatcher._post_process_request(self.req, *args)
        self.assertEqual(0, len(request_dispatcher.filters))
        self.assertEqual(4, len(resp))
        self.assertEqual(args, resp)

    def test_4arg_post_process_request_request_handler_returns_method_false(self):
        """IRequestHandler doesn't return `method` and IRequestFilter doesn't
        accept `method` as an argument. The `method` is set to `None`.
        """
        self.env.enable_component(self.request_filter['4Arg'])
        request_dispatcher = RequestDispatcher(self.env)
        args = ('template.html', {}, 'text/html')
        resp = request_dispatcher._post_process_request(self.req, *args)
        self.assertEqual(1, len(request_dispatcher.filters))
        self.assertEqual(4, len(resp))
        self.assertEqual(args + (None,), resp)
        # TODO (1.5.1) remove old API (genshi style)
        args = ('template.html', {}, {'content_type': 'text/html'})
        resp = request_dispatcher._post_process_request(self.req, *args)
        self.assertEqual(1, len(request_dispatcher.filters))
        self.assertEqual(4, len(resp))
        self.assertEqual(args + (None,), resp)

    def test_4arg_post_process_request_request_handler_returns_method_true(self):
        """IRequestHandler returns `method` and IRequestFilter doesn't accept
        the argument. The `method` argument is forwarded over IRequestFilter
        implementations that don't accept the argument.
        """
        self.env.enable_component(self.request_filter['4Arg'])
        request_dispatcher = RequestDispatcher(self.env)
        args = ('template.html', {}, 'text/html', 'xhtml')
        resp = request_dispatcher._post_process_request(self.req, *args)
        self.assertEqual(1, len(request_dispatcher.filters))
        self.assertEqual(4, len(resp))
        self.assertEqual(args, resp)
        # TODO (1.5.1) remove old API (genshi style)
        args = ('template.html', {}, {'content_type': 'text/html'}, 'xhtml')
        resp = request_dispatcher._post_process_request(self.req, *args)
        self.assertEqual(1, len(request_dispatcher.filters))
        self.assertEqual(4, len(resp))
        self.assertEqual(args, resp)

    def test_5arg_post_process_request_request_handler_returns_method_false(self):
        """IRequestHandler doesn't return `method` and IRequestFilter accepts
        `method` as an argument. The `method` is set to `None`.
        """
        self.env.enable_component(self.request_filter['5Arg'])
        request_dispatcher = RequestDispatcher(self.env)
        args = ('template.html', {}, 'text/html')
        resp = request_dispatcher._post_process_request(self.req, *args)
        self.assertEqual(1, len(request_dispatcher.filters))
        self.assertEqual(4, len(resp))
        self.assertEqual(args[:3] + (None,), resp)

    def test_5arg_post_process_request_request_handler_returns_method_true(self):
        """IRequestHandler returns `method` and IRequestFilter accepts
        the argument. The `method` argument is passed through IRequestFilter
        implementations.
        """
        self.env.enable_component(self.request_filter['5Arg'])
        request_dispatcher = RequestDispatcher(self.env)
        args = ('template.html', {}, 'text/html', 'xhtml')
        resp = request_dispatcher._post_process_request(self.req, *args)
        self.assertEqual(1, len(request_dispatcher.filters))
        self.assertEqual(4, len(resp))
        self.assertEqual(args, resp)
        # TODO (1.5.1) remove old API (genshi style)
        args = ('template.html', {}, {'content_type': 'text/html'}, 'xhtml')
        resp = request_dispatcher._post_process_request(self.req, *args)
        self.assertEqual(1, len(request_dispatcher.filters))
        self.assertEqual(4, len(resp))
        self.assertEqual(args, resp)

    def test_5arg_post_process_request_request_handler_adds_method(self):
        """IRequestFilter adds `method` not returned by IRequestHandler.
        """
        self.env.enable_component(self.request_filter['5ArgXml'])
        args = ('template.html', {}, 'text/html')
        request_dispatcher = RequestDispatcher(self.env)
        resp = request_dispatcher._post_process_request(self.req, *args)
        self.assertEqual(1, len(request_dispatcher.filters))
        self.assertEqual(4, len(resp))
        self.assertEqual(args[:3] + ('xml',), resp)
        # TODO (1.5.1) remove old API (genshi style)
        args = ('template.html', {}, {'content_type': 'text/html'})
        resp = request_dispatcher._post_process_request(self.req, *args)
        self.assertEqual(1, len(request_dispatcher.filters))
        self.assertEqual(4, len(resp))
        self.assertEqual(args[:3] + ('xml',), resp)

    def test_5arg_post_process_request_request_handler_modifies_method(self):
        """IRequestFilter modifies `method` returned by IRequestHandler.
        """
        self.env.enable_component(self.request_filter['5ArgXml'])
        args = ('template.html', {}, 'text/html', 'xhtml')
        request_dispatcher = RequestDispatcher(self.env)
        resp = request_dispatcher._post_process_request(self.req, *args)
        self.assertEqual(1, len(request_dispatcher.filters))
        self.assertEqual(4, len(resp))
        self.assertEqual(args[:3] + ('xml',), resp)
        # TODO (1.5.1) remove old API (genshi style)
        args = ('template.html', {}, {'content_type': 'text/html'}, 'xhtml')
        resp = request_dispatcher._post_process_request(self.req, *args)
        self.assertEqual(1, len(request_dispatcher.filters))
        self.assertEqual(4, len(resp))
        self.assertEqual(args[:3] + ('xml',), resp)

    def test_redirect_on_permission_error(self):
        """The post_process_request method can redirect during exception
        handling from an exception raised in process_request.
        """
        self.env.enable_component(self.request_filter['RedirectOnPermError'])
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
        self.env = EnvironmentStub(path=mkdtemp())
        os.mkdir(self.env.templates_dir)
        filepath = os.path.join(self.env.templates_dir,
                                TestStubRequestHandler.filename)
        create_file(filepath, TestStubRequestHandler.template)
        self.filename = os.path.join(self.env.path, 'test.txt')
        self.data = 'contents\n'
        create_file(self.filename, self.data, 'wb')

    def tearDown(self):
        self.env.reset_db_and_disk()

    def _insert_session(self):
        sid = '1234567890abcdef'
        name = 'First Last'
        email = 'first.last@example.com'
        self.env.insert_users([(sid, name, email, 0)])
        return sid, name, email

    def _content(self):
        yield 'line1,'
        yield 'line2,'
        yield 'line3\n'

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

        self.assertIn(('DEBUG', "Chosen handler is <Component trac.web.tests"
                                ".main.TestStubRequestHandler>"),
                       self.env.log_messages)
        self.assertIn(('ERROR', "can't retrieve session: TracError: Database "
                                "not reachable"), self.env.log_messages)
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

        with self.assertRaises(RequestDone):
            request_dispatcher.dispatch(req)

        self.assertIn(('DEBUG', "Chosen handler is <Component trac.web.tests"
                                ".main.TestStubRequestHandler>"),
                      self.env.log_messages)
        self.assertIn(('WARNING', "can't retrieve session: "
                                  "Session ID must be alphanumeric."),
                      self.env.log_messages)
        self.assertIsInstance(req.session, FakeSession)
        self.assertIsNone(req.session.sid)
        self.assertEqual('200 Ok', req.status_sent[0])
        self.assertIn('<h1>Hello World</h1>', req.response_sent.getvalue())

    def test_set_valid_xsendfile_header(self):
        """Send file using xsendfile header."""
        self.env.config.set('trac', 'use_xsendfile', True)
        self.env.config.set('trac', 'xsendfile_header', 'X-Accel-Redirect')

        req = MockRequest(self.env)
        request_dispatcher = RequestDispatcher(self.env)
        request_dispatcher.set_default_callbacks(req)

        # File is sent using xsendfile.
        self.assertRaises(RequestDone, req.send_file, self.filename)
        self.assertEqual(['200 Ok'], req.status_sent)
        self.assertEqual('text/plain', req.headers_sent['Content-Type'])
        self.assertEqual(self.filename, req.headers_sent['X-Accel-Redirect'])
        self.assertNotIn('X-Sendfile', req.headers_sent)
        self.assertIsNone(req._response)
        self.assertEqual('', req.response_sent.getvalue())

    def _test_file_not_sent_using_xsendfile_header(self, xsendfile_header):
        req = MockRequest(self.env)
        request_dispatcher = RequestDispatcher(self.env)
        request_dispatcher.set_default_callbacks(req)

        # File is not sent using xsendfile.
        self.assertRaises(RequestDone, req.send_file, self.filename)
        self.assertEqual(['200 Ok'], req.status_sent)
        self.assertEqual('text/plain', req.headers_sent['Content-Type'])
        self.assertNotIn(xsendfile_header, req.headers_sent)
        self.assertEqual('_FileWrapper', type(req._response).__name__)
        self.assertEqual('', req.response_sent.getvalue())

    def test_set_invalid_xsendfile_header(self):
        """Not sent by xsendfile header because header is invalid."""
        xsendfile_header = '(X-SendFile)'
        self.env.config.set('trac', 'use_xsendfile', True)
        self.env.config.set('trac', 'xsendfile_header', xsendfile_header)

        self._test_file_not_sent_using_xsendfile_header(xsendfile_header)

    def test_xsendfile_is_disabled(self):
        """Not sent by xsendfile header because xsendfile is disabled."""
        xsendfile_header = 'X-SendFile'
        self.env.config.set('trac', 'use_xsendfile', False)
        self.env.config.set('trac', 'xsendfile_header', xsendfile_header)

        self._test_file_not_sent_using_xsendfile_header(xsendfile_header)

    def _test_configurable_headers(self, method):
        # Reserved headers not allowed.
        content_type = 'not-allowed'
        self.env.config.set('http-headers', 'Content-Type', content_type)
        # Control code not allowed.
        custom1 = '\x00custom1'
        self.env.config.set('http-headers', 'X-Custom-1', custom1)
        # Many special characters allowed in header name.
        custom2 = 'Custom2-!#$%&\'*+.^_`|~'
        self.env.config.set('http-headers', custom2, 'custom2')
        # Some special characters not allowed in header name.
        self.env.config.set('http-headers', 'X-Custom-(3)', 'custom3')

        req = MockRequest(self.env, method='POST')
        request_dispatcher = RequestDispatcher(self.env)
        request_dispatcher.set_default_callbacks(req)
        self.assertRaises(RequestDone, method, req)

        self.assertNotEqual('not-allowed', req.headers_sent.get('Content-Type'))
        self.assertNotIn('x-custom-1', req.headers_sent)
        self.assertIn(custom2.lower(), req.headers_sent)
        self.assertNotIn('x-custom-(3)', req.headers_sent)
        self.assertIn(('WARNING', "[http-headers] invalid headers are ignored: "
                                  "u'content-type': u'not-allowed', "
                                  "u'x-custom-1': u'\\x00custom1', "
                                  "u'x-custom-(3)': u'custom3'"),
                      self.env.log_messages)

    def test_send_configurable_headers(self):
        def send(req):
            req.send(self._content())

        self._test_configurable_headers(send)

    def test_send_error_configurable_headers(self):
        def send_error(req):
            req.send_error(None, self._content())

        self._test_configurable_headers(send_error)

    def test_send_configurable_headers_no_override(self):
        """Headers in request not overridden by configurable headers."""
        self.env.config.set('http-headers', 'X-XSS-Protection', '1; mode=block')
        request_dispatcher = RequestDispatcher(self.env)
        req1 = MockRequest(self.env)
        request_dispatcher.set_default_callbacks(req1)

        self.assertRaises(RequestDone, req1.send, self._content())

        self.assertNotIn('X-XSS-protection', req1.headers_sent)
        self.assertIn('x-xss-protection', req1.headers_sent)
        self.assertEqual('1; mode=block', req1.headers_sent['x-xss-protection'])

        req2 = MockRequest(self.env, method='POST')
        request_dispatcher.set_default_callbacks(req2)

        self.assertRaises(RequestDone, req2.send, self._content())

        self.assertNotIn('x-xss-protection', req2.headers_sent)
        self.assertIn('X-XSS-Protection', req2.headers_sent)
        self.assertEqual('0', req2.headers_sent['X-XSS-Protection'])


class HdfdumpTestCase(unittest.TestCase):

    components = []

    @classmethod
    def setUpClass(cls):
        class HdfdumpRequestHandler(Component):
            implements(IRequestHandler)
            def match_request(self, req):
                return True
            def process_request(self, req):
                data = {'name': 'value'}
                return 'error.html', data

        cls.components = [HdfdumpRequestHandler]

    @classmethod
    def tearDownClass(cls):
        from trac.core import ComponentMeta
        for component in cls.components:
            ComponentMeta.deregister(component)

    def setUp(self):
        self.env = EnvironmentStub(enable=['trac.web.*'])
        self.req = MockRequest(self.env, args={'hdfdump': '1'})
        self.request_dispatcher = RequestDispatcher(self.env)

    def test_hdfdump(self):
        self.env.config.set('trac', 'default_handler', 'HdfdumpRequestHandler')
        self.assertRaises(RequestDone, self.request_dispatcher.dispatch,
                          self.req)
        self.assertIn("{'name': 'value'}",
                      self.req.response_sent.getvalue())
        self.assertEqual('text/plain;charset=utf-8',
                         self.req.headers_sent['Content-Type'])


class SendErrorTestCase(unittest.TestCase):

    use_chunked_encoding = False

    components = None
    env_path = None

    @classmethod
    def setUpClass(cls):
        class RaiseExceptionHandler(Component):
            implements(IRequestHandler)

            def match_request(self, req):
                if req.path_info.startswith('/raise-exception'):
                    return True

            def process_request(self, req):
                if req.args.get('type') == 'tracerror':
                    raise TracError("The TracError message")
                else:
                    raise Exception("The Exception message")

        cls.components = [RaiseExceptionHandler]
        cls.env_path = mkdtemp()
        env = trac.env.Environment(path=cls.env_path, create=True)
        PermissionSystem(env).grant_permission('admin', 'TRAC_ADMIN')
        env.shutdown()

    @classmethod
    def tearDownClass(cls):
        from trac.core import ComponentMeta
        for component in cls.components:
            ComponentMeta.deregister(component)
        if cls.env_path in trac.env.env_cache:
            trac.env.env_cache[cls.env_path].shutdown()
            del trac.env.env_cache[cls.env_path]
        EnvironmentStub(path=cls.env_path, destroying=True).reset_db_and_disk()

    def _make_environ(self, scheme='http', server_name='example.org',
                      server_port=80, method='GET', script_name='/',
                      env_path=None, **kwargs):
        environ = {'wsgi.url_scheme': scheme, 'wsgi.input': io.BytesIO(),
                   'REQUEST_METHOD': method, 'SERVER_NAME': server_name,
                   'SERVER_PORT': server_port, 'SCRIPT_NAME': script_name,
                   'trac.env_path': env_path or self.env_path,
                   'wsgi.run_once': False}
        environ.update(kwargs)
        return environ

    def _make_start_response(self):
        self.status_sent = []
        self.headers_sent = {}
        self.response_sent = io.BytesIO()

        def start_response(status, headers, exc_info=None):
            self.status_sent.append(status)
            self.headers_sent.update(dict(headers))
            return self.response_sent.write

        return start_response

    def _set_config(self, admin_trac_url):
        env = trac.env.open_environment(self.env_path, use_cache=True)
        env.config.set('trac', 'use_chunked_encoding',
                       self.use_chunked_encoding)
        env.config.set('project', 'admin_trac_url', admin_trac_url)
        env.config.save()

    def assert_internal_error(self, content):
        self.assertEqual('500 Internal Server Error', self.status_sent[0])
        self.assertEqual('text/html;charset=utf-8',
                         self.headers_sent['Content-Type'])
        self.assertIn('<h1>Oops\xe2\x80\xa6</h1>', content)

    def test_trac_error(self):
        self._set_config(admin_trac_url='.')
        environ = self._make_environ(PATH_INFO='/raise-exception',
                                     QUERY_STRING='type=tracerror')
        dispatch_request(environ, self._make_start_response())

        content = self.response_sent.getvalue()
        self.assertEqual('500 Internal Server Error', self.status_sent[0])
        self.assertEqual('text/html;charset=utf-8',
                         self.headers_sent['Content-Type'])
        self.assertIn('<h1>Trac Error</h1>', content)
        self.assertIn('<p class="message">The TracError message</p>', content)
        self.assertNotIn('<strong>Trac detected an internal error:</strong>',
                         content)
        self.assertNotIn('There was an internal error in Trac.', content)

    def test_internal_error_for_non_admin(self):
        self._set_config(admin_trac_url='.')
        environ = self._make_environ(PATH_INFO='/raise-exception')

        dispatch_request(environ, self._make_start_response())
        content = self.response_sent.getvalue()

        self.assert_internal_error(content)
        self.assertIn('There was an internal error in Trac.', content)
        self.assertIn('<p>\nTo that end, you could', content)
        self.assertNotIn('This is probably a local installation issue.',
                         content)
        self.assertNotIn('<h2>Found a bug in Trac?</h2>', content)

    def test_internal_error_with_admin_trac_url_for_non_admin(self):
        self._set_config(admin_trac_url='http://example.org/admin')
        environ = self._make_environ(PATH_INFO='/raise-exception')

        dispatch_request(environ, self._make_start_response())
        content = self.response_sent.getvalue()

        self.assert_internal_error(content)
        self.assertIn('There was an internal error in Trac.', content)
        self.assertIn('<p>\nTo that end, you could', content)
        self.assertIn(' action="http://example.org/admin/newticket#"', content)
        self.assertNotIn('This is probably a local installation issue.',
                         content)
        self.assertNotIn('<h2>Found a bug in Trac?</h2>', content)

    def test_internal_error_without_admin_trac_url_for_non_admin(self):
        self._set_config(admin_trac_url='')
        environ = self._make_environ(PATH_INFO='/raise-exception')

        dispatch_request(environ, self._make_start_response())
        content = self.response_sent.getvalue()

        self.assert_internal_error(content)
        self.assertIn('There was an internal error in Trac.', content)
        self.assertNotIn('<p>\nTo that end, you could', content)
        self.assertNotIn('This is probably a local installation issue.',
                         content)
        self.assertNotIn('<h2>Found a bug in Trac?</h2>', content)

    def test_internal_error_for_admin(self):
        self._set_config(admin_trac_url='.')
        environ = self._make_environ(PATH_INFO='/raise-exception',
                                     REMOTE_USER='admin')

        dispatch_request(environ, self._make_start_response())
        content = self.response_sent.getvalue()

        self.assert_internal_error(content)
        self.assertNotIn('There was an internal error in Trac.', content)
        self.assertIn('This is probably a local installation issue.', content)
        self.assertNotIn('a ticket at the admin Trac to report', content)
        self.assertIn('<h2>Found a bug in Trac?</h2>', content)
        self.assertIn('<p>\nOtherwise, please', content)
        self.assertIn(' action="https://trac.edgewall.org/newticket"',
                      content)

    def test_internal_error_with_admin_trac_url_for_admin(self):
        self._set_config(admin_trac_url='http://example.org/admin')
        environ = self._make_environ(PATH_INFO='/raise-exception',
                                     REMOTE_USER='admin')

        dispatch_request(environ, self._make_start_response())
        content = self.response_sent.getvalue()

        self.assert_internal_error(content)
        self.assertNotIn('There was an internal error in Trac.', content)
        self.assertIn('This is probably a local installation issue.', content)
        self.assertIn('a ticket at the admin Trac to report', content)
        self.assertIn(' action="http://example.org/admin/newticket#"', content)
        self.assertIn('<h2>Found a bug in Trac?</h2>', content)
        self.assertIn('<p>\nOtherwise, please', content)
        self.assertIn(' action="https://trac.edgewall.org/newticket"',
                      content)

    def test_internal_error_without_admin_trac_url_for_admin(self):
        self._set_config(admin_trac_url='')
        environ = self._make_environ(PATH_INFO='/raise-exception',
                                     REMOTE_USER='admin')

        dispatch_request(environ, self._make_start_response())
        content = self.response_sent.getvalue()

        self.assert_internal_error(content)
        self.assertNotIn('There was an internal error in Trac.', content)
        self.assertIn('This is probably a local installation issue.', content)
        self.assertNotIn('a ticket at the admin Trac to report', content)
        self.assertIn('<h2>Found a bug in Trac?</h2>', content)
        self.assertIn('<p>\nOtherwise, please', content)
        self.assertIn(' action="https://trac.edgewall.org/newticket"',
                      content)

    def test_environment_not_found(self):
        """User error reported when environment is not found."""
        env_path = self.env_path + '$'  # Arbitrarily modified path
        environ = self._make_environ(PATH_INFO='/', env_path=env_path)

        dispatch_request(environ, self._make_start_response())
        content = self.response_sent.getvalue()

        self.assertEqual(
            "Trac Error\n\nTracError: No Trac environment found at %s\n"
            "IOError: [Errno 2] No such file or directory: '%s'"
            % (env_path, os.path.join(env_path, 'VERSION')), content)


class SendErrorUseChunkedEncodingTestCase(SendErrorTestCase):

    use_chunked_encoding = True


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(AuthenticateTestCase))
    suite.addTest(unittest.makeSuite(EnvironmentsTestCase))
    suite.addTest(unittest.makeSuite(PreProcessRequestTestCase))
    suite.addTest(unittest.makeSuite(ProcessRequestTestCase))
    suite.addTest(unittest.makeSuite(PostProcessRequestTestCase))
    suite.addTest(unittest.makeSuite(RequestDispatcherTestCase))
    suite.addTest(unittest.makeSuite(HdfdumpTestCase))
    suite.addTest(unittest.makeSuite(SendErrorTestCase))
    suite.addTest(unittest.makeSuite(SendErrorUseChunkedEncodingTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
