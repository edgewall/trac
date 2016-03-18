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

from trac.config import ConfigurationError
from trac.core import Component, ComponentManager, TracError, implements
from trac.test import EnvironmentStub, Mock, MockPerm
from trac.util import create_file
from trac.web.api import IRequestFilter, IRequestHandler, Request, RequestDone
from trac.web.auth import IAuthenticator
from trac.web.main import RequestDispatcher, get_environments


def _make_environ(scheme='http', server_name='example.org',
                  server_port=80, method='GET', script_name='/trac',
                  **kwargs):
    environ = {'wsgi.url_scheme': scheme, 'wsgi.input': None,
               'REQUEST_METHOD': method, 'SERVER_NAME': server_name,
               'SERVER_PORT': server_port, 'SCRIPT_NAME': script_name}
    environ.update(kwargs)
    return environ


def _make_req(environ, start_response, **kwargs):
    req = Request(environ, start_response)
    for name, value in kwargs.iteritems():
        setattr(req, name, value)
    return req


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
        def start_response(status, headers, exc_info=None):
            return lambda data: None

        self.env.config.set('trac', 'default_handler',
                            'AuthenticateRequestHandler')
        authenticated = [0]
        req = _make_req(_make_environ(), start_response)
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


class PostProcessRequestTestCase(unittest.TestCase):
    """Test cases for handling of the optional `method` argument in
    RequestDispatcher._post_process_request."""

    def setUp(self):
        self.env = EnvironmentStub()
        self.req = Mock()
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
            def pre_process_request(self, handler):
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
            def pre_process_request(self, handler):
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
            def pre_process_request(self, handler):
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
            def pre_process_request(self, handler):
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
            def pre_process_request(self, handler):
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
            def pre_process_request(self, handler):
                return handler
            def post_process_request(self, req, template, data,
                                     content_type, method=None):
                return template, data, content_type, 'xml'
        args = ('template.html', {}, 'text/html', 'xhtml')
        resp = self.request_dispatcher._post_process_request(self.req, *args)
        self.assertEqual(1, len(self.request_dispatcher.filters))
        self.assertEqual(4, len(resp))
        self.assertEqual(args[:3] + ('xml',), resp)


class RequestDispatcherTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()

    def test_invalid_default_date_format_raises_exception(self):
        self.env.config.set('trac', 'default_date_format', u'ĭšo8601')

        self.assertEqual(u'ĭšo8601',
                         self.env.config.get('trac', 'default_date_format'))
        self.assertRaises(ConfigurationError, getattr,
                          RequestDispatcher(self.env), 'default_date_format')


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
    suite.addTest(unittest.makeSuite(PostProcessRequestTestCase))
    suite.addTest(unittest.makeSuite(RequestDispatcherTestCase))
    suite.addTest(unittest.makeSuite(HdfdumpTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
