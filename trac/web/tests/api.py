# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2019 Edgewall Software
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
import textwrap
import unittest

from trac import perm
from trac.core import TracError
from trac.test import EnvironmentStub, MockPerm, mkdtemp, rmtree
from trac.util import create_file
from trac.util.datefmt import utc
from trac.util.html import tag
from trac.web.api import HTTPBadRequest, HTTPInternalServerError, Request, \
                         RequestDone, parse_arg_list
from trac.web.main import FakeSession
from tracopt.perm.authz_policy import AuthzPolicy


class RequestHandlerPermissionsTestCaseBase(unittest.TestCase):

    authz_policy = None

    def setUp(self, module_class):
        self.path = mkdtemp()
        if self.authz_policy is not None:
            self.authz_file = os.path.join(self.path, 'authz_policy.conf')
            create_file(self.authz_file, self.authz_policy)
            self.env = EnvironmentStub(enable=['trac.*', AuthzPolicy],
                                       path=self.path)
            self.env.config.set('authz_policy', 'authz_file', self.authz_file)
            self.env.config.set('trac', 'permission_policies',
                                'AuthzPolicy, DefaultPermissionPolicy')
        else:
            self.env = EnvironmentStub(path=self.path)
        self.req_handler = module_class(self.env)

    def tearDown(self):
        self.env.reset_db_and_disk()

    def get_navigation_items(self, req):
        return self.req_handler.get_navigation_items(req)

    def grant_perm(self, username, *actions):
        permsys = perm.PermissionSystem(self.env)
        for action in actions:
            permsys.grant_permission(username, action)

    def process_request(self, req):
        self.assertTrue(self.req_handler.match_request(req))
        return self.req_handler.process_request(req)


def _make_environ(scheme='http', server_name='example.org',
                  server_port=80, method='GET', script_name='/trac',
                  **kwargs):
    environ = {'wsgi.url_scheme': scheme, 'wsgi.input': io.BytesIO(),
               'REQUEST_METHOD': method, 'SERVER_NAME': server_name,
               'SERVER_PORT': server_port, 'SCRIPT_NAME': script_name}
    environ.update(kwargs)
    return environ


def _make_req(environ, authname='admin', chrome=None, form_token='A' * 40,
              locale=None, perm=MockPerm(), tz=utc, use_xsendfile=False,
              xsendfile_header='X-Sendfile'):
    if chrome is None:
        chrome = {
            'links': {},
            'scripts': [],
            'theme': 'theme.html',
            'logo': '',
            'nav': ''
        }

    class RequestWithSentAttrs(Request):
        """Subclass of `Request` with "sent" attributes."""

        def __init__(self, environ):
            self.status_sent = []
            self.headers_sent = {}
            self._response_sent = io.BytesIO()

            def write(data):
                self._response_sent.write(data)

            def start_response(status, headers, exc_info=None):
                self.status_sent.append(status)
                self.headers_sent.update(dict(headers))
                return write

            super(RequestWithSentAttrs, self).__init__(environ, start_response)

        @property
        def response_sent(self):
            return self._response_sent.getvalue()

    req = RequestWithSentAttrs(environ)
    # Setup default callbacks.
    req.authname = authname
    req.chrome = chrome
    req.form_token = form_token
    req.locale = locale
    req.perm = perm
    req.session = FakeSession()
    req.tz = tz
    req.use_xsendfile = use_xsendfile
    req.xsendfile_header = xsendfile_header
    return req


class RequestTestCase(unittest.TestCase):

    def test_repr_with_path(self):
        environ = _make_environ(PATH_INFO='/path')
        req = Request(environ, None)
        self.assertEqual(repr(req), """<Request "GET '/path'">""")

    def test_repr_with_path_and_query_string(self):
        environ = _make_environ(QUERY_STRING='A=B', PATH_INFO='/path')
        req = Request(environ, None)
        self.assertEqual(repr(req), """<Request "GET '/path?A=B'">""")

    def test_get(self):
        qs = 'arg1=0&arg2=1&arg1=abc&arg3=def&arg3=1'
        environ = _make_environ(method='GET', QUERY_STRING=qs)
        req = Request(environ, None)

        self.assertEqual('0', req.args.get('arg1'))
        self.assertEqual('def', req.args.get('arg3'))

    def test_getfirst(self):
        qs = 'arg1=0&arg2=1&arg1=abc&arg3=def&arg3=1'
        environ = _make_environ(method='GET', QUERY_STRING=qs)
        req = Request(environ, None)

        self.assertEqual('0', req.args.getfirst('arg1'))
        self.assertEqual('def', req.args.getfirst('arg3'))

    def test_get_list(self):
        qs = 'arg1=0&arg2=1&arg1=abc&arg3=def&arg3=1'
        environ = _make_environ(method='GET', QUERY_STRING=qs)
        req = Request(environ, None)

        self.assertEqual(['0', 'abc'], req.args.getlist('arg1'))
        self.assertEqual(['def', '1'], req.args.getlist('arg3'))

    def test_as_bool(self):
        qs = 'arg1=0&arg2=1&arg3=yes&arg4=a&arg5=1&arg5=0'
        environ = _make_environ(method='GET', QUERY_STRING=qs)
        req = Request(environ, None)

        self.assertIsNone(req.args.as_bool('arg0'))
        self.assertTrue(req.args.as_bool('arg0', True))
        self.assertFalse(req.args.as_bool('arg1'))
        self.assertFalse(req.args.as_bool('arg1', True))
        self.assertTrue(req.args.as_bool('arg2'))
        self.assertTrue(req.args.as_bool('arg3'))
        self.assertFalse(req.args.as_bool('arg4'))
        self.assertTrue(req.args.as_bool('arg4', True))
        self.assertTrue(req.args.as_bool('arg5'))

    def test_as_int(self):
        qs = 'arg1=1&arg2=a&arg3=3&arg3=4'
        environ = _make_environ(method='GET', QUERY_STRING=qs)
        req = Request(environ, None)

        self.assertIsNone(req.args.as_int('arg0'))
        self.assertEqual(2, req.args.as_int('arg0', 2))
        self.assertEqual(1, req.args.as_int('arg1'))
        self.assertEqual(1, req.args.as_int('arg1', 2))
        self.assertEqual(2, req.args.as_int('arg1', min=2))
        self.assertEqual(2, req.args.as_int('arg1', None, 2))
        self.assertEqual(0, req.args.as_int('arg1', max=0))
        self.assertEqual(0, req.args.as_int('arg1', None, max=0))
        self.assertEqual(0, req.args.as_int('arg1', None, -1, 0))
        self.assertIsNone(req.args.as_int('arg2'))
        self.assertEqual(2, req.args.as_int('arg2', 2))
        self.assertEqual(3, req.args.as_int('arg3'))

    def test_getbool(self):
        qs = 'arg1=0&arg2=1&arg3=yes&arg4=a&arg5=1&arg5=0'
        environ = _make_environ(method='GET', QUERY_STRING=qs)
        req = Request(environ, None)

        self.assertIsNone(req.args.getbool('arg0'))
        self.assertTrue(req.args.getbool('arg0', True))
        self.assertFalse(req.args.getbool('arg1'))
        self.assertFalse(req.args.getbool('arg1', True))
        self.assertTrue(req.args.getbool('arg2'))
        self.assertTrue(req.args.getbool('arg3'))
        with self.assertRaises(HTTPBadRequest):
            req.args.getbool('arg4')
        with self.assertRaises(HTTPBadRequest):
            req.args.getbool('arg4', True)
        with self.assertRaises(HTTPBadRequest):
            req.args.getbool('arg5')
        with self.assertRaises(HTTPBadRequest):
            req.args.getbool('arg5', True)

    def test_getint(self):
        qs = 'arg1=1&arg2=a&arg3=3&arg3=4'
        environ = _make_environ(method='GET', QUERY_STRING=qs)
        req = Request(environ, None)

        self.assertIsNone(req.args.getint('arg0'))
        self.assertEqual(2, req.args.getint('arg0', 2))
        self.assertEqual(1, req.args.getint('arg1'))
        self.assertEqual(1, req.args.getint('arg1', 2))
        self.assertEqual(2, req.args.getint('arg1', min=2))
        self.assertEqual(2, req.args.getint('arg1', None, 2))
        self.assertEqual(0, req.args.getint('arg1', max=0))
        self.assertEqual(0, req.args.getint('arg1', None, max=0))
        self.assertEqual(0, req.args.getint('arg1', None, -1, 0))
        with self.assertRaises(HTTPBadRequest):
            req.args.getbool('arg2')
        with self.assertRaises(HTTPBadRequest):
            req.args.getbool('arg2', 2)
        with self.assertRaises(HTTPBadRequest):
            req.args.getbool('arg3')
        with self.assertRaises(HTTPBadRequest):
            req.args.getbool('arg3', 2)

    def test_getfile(self):
        file_content = 'The file content.'
        file_name = 'thefile.txt'
        form_data = """\
--%(boundary)s\r\n\
Content-Disposition: form-data; name="attachment"; filename="%(file_name)s"\r\n\
Content-Type: text/plain\r\n\
\r\n\
%(file_content)s\r\n\
--%(boundary)s\r\n\
Content-Disposition: form-data; name="action"\r\n\
\r\n\
new\r\n\
--%(boundary)s--\r\n\
"""
        boundary = '_BOUNDARY_'
        content_type = b'multipart/form-data; boundary="%s"' % boundary
        form_data %= {
            'boundary': boundary,
            'file_content': file_content,
            'file_name': file_name,
        }
        environ = _make_environ(method='POST', **{
            'wsgi.input': io.BytesIO(form_data),
            'CONTENT_LENGTH': str(len(form_data)),
            'CONTENT_TYPE': content_type
        })
        req = Request(environ, None)

        file_ = req.args.getfile('attachment')

        self.assertEqual(file_name, file_[0])
        self.assertEqual(file_content, file_[1].getvalue())
        self.assertEqual(len(file_content), file_[2])

    def test_getfilelist(self):
        file_content = 'The file0 content.', 'The file1 content.'
        file_name = 'file0.txt', 'file1.txt'
        form_data = """\
--%(boundary)s\r\n\
Content-Disposition: form-data; name="attachment"; filename="%(file0_name)s"\r\n\
Content-Type: text/plain\r\n\
\r\n\
%(file0_content)s\r\n\
--%(boundary)s\r\n\
Content-Disposition: form-data; name="attachment"; filename="%(file1_name)s"\r\n\
Content-Type: text/plain\r\n\
\r\n\
%(file1_content)s\r\n\
--%(boundary)s\r\n\
Content-Disposition: form-data; name="action"\r\n\
\r\n\
new\r\n\
--%(boundary)s--\r\n\
"""
        boundary = '_BOUNDARY_'
        content_type = b'multipart/form-data; boundary="%s"' % boundary
        form_data %= {
            'boundary': boundary,
            'file0_content': file_content[0],
            'file0_name': file_name[0],
            'file1_content': file_content[1],
            'file1_name': file_name[1],
        }
        environ = _make_environ(method='POST', **{
            'wsgi.input': io.BytesIO(form_data),
            'CONTENT_LENGTH': str(len(form_data)),
            'CONTENT_TYPE': content_type
        })
        req = Request(environ, None)

        file_ = req.args.getfilelist('attachment')

        self.assertEqual(2, len(file_))
        self.assertEqual(file_name[0], file_[0][0])
        self.assertEqual(file_content[0], file_[0][1].getvalue())
        self.assertEqual(file_name[1], file_[1][0])
        self.assertEqual(file_content[1], file_[1][1].getvalue())
        self.assertEqual(len(file_content[1]), file_[1][2])

    def test_require(self):
        qs = 'arg1=1'
        environ = _make_environ(method='GET', QUERY_STRING=qs)
        req = Request(environ, None)

        with self.assertRaises(HTTPBadRequest):
            req.args.require('arg0')
        self.assertIsNone(req.args.require('arg1'))

    def test_is_xhr_true(self):
        environ = _make_environ(HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        req = Request(environ, None)
        self.assertTrue(req.is_xhr)

    def test_is_xhr_false(self):
        environ = _make_environ()
        req = Request(environ, None)
        self.assertFalse(req.is_xhr)

    def test_is_authenticated_as_none(self):
        environ = _make_environ()
        req = Request(environ, None)
        req.authname = None
        self.assertFalse(req.is_authenticated)

    def test_is_authenticated_as_anonymous(self):
        environ = _make_environ()
        req = Request(environ, None)
        req.authname = 'anonymous'
        self.assertFalse(req.is_authenticated)

    def test_is_authenticated_as_valid_user(self):
        environ = _make_environ()
        req = Request(environ, None)
        req.authname = 'user'
        self.assertTrue(req.is_authenticated)

    def test_base_url(self):
        environ = _make_environ()
        req = Request(environ, None)
        self.assertEqual('http://example.org/trac', req.base_url)

    def test_base_url_host(self):
        environ = _make_environ(server_port=8080, HTTP_HOST='example.com')
        req = Request(environ, None)
        self.assertEqual('http://example.com/trac', req.base_url)

    def test_base_url_nondefaultport(self):
        environ = _make_environ(server_port=8080)
        req = Request(environ, None)
        self.assertEqual('http://example.org:8080/trac', req.base_url)

    def test_base_url_https(self):
        environ = _make_environ(scheme='https', server_port=443)
        req = Request(environ, None)
        self.assertEqual('https://example.org/trac', req.base_url)

    def test_base_url_https_host(self):
        environ = _make_environ(scheme='https', server_port=443,
                                HTTP_HOST='example.com')
        req = Request(environ, None)
        self.assertEqual('https://example.com/trac', req.base_url)

    def test_base_url_https_nondefaultport(self):
        environ = _make_environ(scheme='https', server_port=8443)
        req = Request(environ, None)
        self.assertEqual('https://example.org:8443/trac', req.base_url)

    def test_base_url_proxy(self):
        environ = _make_environ(HTTP_HOST='localhost',
                                HTTP_X_FORWARDED_HOST='example.com')
        req = Request(environ, None)
        self.assertEqual('http://localhost/trac', req.base_url)

    def test_languages(self):
        environ = _make_environ(HTTP_ACCEPT_LANGUAGE='en-us,en;q=0.5')
        req = Request(environ, None)
        self.assertEqual(['en-us', 'en'], req.languages)

    def test_redirect(self):
        req = _make_req(_make_environ(method='HEAD'))
        with self.assertRaises(RequestDone):
            req.redirect('/trac/test')
        self.assertEqual('302 Found', req.status_sent[0])
        self.assertEqual('http://example.org/trac/test',
                         req.headers_sent['Location'])

    def test_redirect_absolute(self):
        req = _make_req(_make_environ(method='HEAD'))
        with self.assertRaises(RequestDone):
            req.redirect('http://example.com/trac/test')
        self.assertEqual('302 Found', req.status_sent[0])
        self.assertEqual('http://example.com/trac/test',
                         req.headers_sent['Location'])

    def test_redirect_with_post_and_hash_for_msie(self):
        url = 'http://example.com/trac/ticket/1#comment:2'
        msie303 = 'http://example.com/trac/ticket/1#__msie303:comment:2'

        def location(ua):
            environ = _make_environ(method='POST', HTTP_USER_AGENT=ua)
            req = _make_req(environ)
            with self.assertRaises(RequestDone):
                req.redirect(url)
            self.assertEqual('303 See Other', req.status_sent[0])
            return req.headers_sent['Location']

        # IE 11 strict mode
        self.assertEqual(url, location(
            'Mozilla/5.0 (Windows NT 6.1; Trident/7.0; rv:11.0) like Gecko'))
        # IE 11 compatibility view mode
        self.assertEqual(url, location(
            'Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.1; Trident/7.0)'))
        # IE 10 strict mode
        self.assertEqual(url, location(
            'Mozilla/5.0 (compatible; MSIE 10.0; Windows NT 6.1; Trident/6.0)'
            ))
        # IE 10 compatibility view mode
        self.assertEqual(url, location(
            'Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.1; Trident/6.0)'))
        # IE 9 strict mode
        self.assertEqual(msie303, location(
            'Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; Trident/5.0)'))
        # IE 9 compatibility view mode
        self.assertEqual(msie303, location(
            'Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 6.1; Trident/5.0)'))
        # IE 8 strict mode
        self.assertEqual(msie303, location(
            'Mozilla/4.0 (compatible; MSIE 8.0; Windows NT 5.1; Trident/4.0)'))
        # IE 8 compatibility view mode
        self.assertEqual(msie303, location(
            'Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 5.1; Trident/4.0)'))
        # IE 7
        self.assertEqual(msie303, location(
            'Mozilla/4.0 (compatible; MSIE 7.0; Windows NT 5.1)'))
        # IE 6
        self.assertEqual(msie303, location(
            'Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1; SV1)'))

    def test_write_iterable(self):
        req = _make_req(_make_environ(method='GET'))
        req.send_header('Content-Type', 'text/plain;charset=utf-8')
        req.write(('Foo', 'bar', 'baz'))
        self.assertEqual('Foobarbaz', req.response_sent)

    def test_write_unicode(self):
        req = _make_req(_make_environ(method='HEAD'))
        req.send_header('Content-Type', 'text/plain;charset=utf-8')
        req.send_header('Content-Length', 0)
        # anyway we're not supposed to send unicode, so we get a ValueError
        with self.assertRaises(ValueError):
            req.write(u'Föö')
        with self.assertRaises(ValueError):
            req.write(('F', u'öo'))

    def test_send_iterable(self):
        def iterable():
            yield 'line1,'
            yield ''
            yield 'line2,'
            yield 'line3\n'

        req = _make_req(_make_environ(method='GET'))
        with self.assertRaises(RequestDone):
            req.send(iterable())
        self.assertEqual('200 Ok', req.status_sent[0])
        self.assertEqual('must-revalidate', req.headers_sent['Cache-Control'])
        self.assertEqual('Fri, 01 Jan 1999 00:00:00 GMT',
                         req.headers_sent['Expires'])
        self.assertEqual('text/html;charset=utf-8',
                         req.headers_sent['Content-Type'])
        self.assertEqual('line1,line2,line3\n', req.response_sent)

    def test_invalid_cookies(self):
        environ = _make_environ(HTTP_COOKIE='bad:key=value;')
        req = Request(environ, None)
        self.assertEqual('', str(req.incookie))

    def test_multiple_cookies(self):
        environ = _make_environ(HTTP_COOKIE='key=value1; key=value2;')
        req = Request(environ, None)
        self.assertEqual('Set-Cookie: key=value1',
                         str(req.incookie).rstrip(';'))

    def test_read(self):
        environ = _make_environ(**{
            'wsgi.input': io.BytesIO(b'test input')
        })
        req = Request(environ, None)
        self.assertEqual('test input', req.read())

    def test_read_size(self):
        environ = _make_environ(**{
            'wsgi.input': io.BytesIO(b'test input')
        })
        req = Request(environ, None)
        self.assertEqual('test', req.read(size=4))

    def _test_qs_with_null_bytes(self, environ):
        req = Request(environ, None)
        try:
            req.args['action']
        except HTTPBadRequest as e:
            self.assertEqual("400 Bad Request (Invalid request arguments.)",
                             unicode(e))
        else:
            self.fail("HTTPBadRequest not raised.")

    def test_qs_with_null_bytes_for_name(self):
        environ = _make_environ(method='GET', QUERY_STRING='acti\x00n=fOO')
        self._test_qs_with_null_bytes(environ)

    def test_qs_with_null_bytes_for_value(self):
        environ = _make_environ(method='GET', QUERY_STRING='action=f\x00O')
        self._test_qs_with_null_bytes(environ)

    def test_post_with_unnamed_value(self):
        boundary = '_BOUNDARY_'
        form_data = textwrap.dedent(b"""\
            --%(boundary)s\r\n\
            Content-Disposition: form-data; name="foo"\r\n\
            \r\n\
            named value\r\n\
            --%(boundary)s\r\n\
            Content-Disposition: form-data; name=""\r\n\
            \r\n\
            name is empty\r\n\
            --%(boundary)s\r\n\
            Content-Disposition: form-data\r\n\
            \r\n\
            unnamed value\r\n\
            --%(boundary)s--\r\n\
            """)
        form_data %= {'boundary': boundary}
        content_type = 'multipart/form-data; boundary="%s"' % boundary
        environ = _make_environ(method='POST', **{
            'wsgi.input': io.BytesIO(form_data),
            'CONTENT_LENGTH': str(len(form_data)),
            'CONTENT_TYPE': content_type
        })
        req = Request(environ, None)

        self.assertEqual('named value', req.args['foo'])
        self.assertEqual([('foo', 'named value'), ('', 'name is empty'),
                          (None, 'unnamed value')], req.arg_list)

    def _test_post_with_null_bytes(self, form_data):
        boundary = '_BOUNDARY_'
        content_type = b'multipart/form-data; boundary="%s"' % boundary
        form_data %= {'boundary': boundary}

        environ = _make_environ(method='POST', **{
            'wsgi.input': io.BytesIO(form_data),
            'CONTENT_LENGTH': str(len(form_data)),
            'CONTENT_TYPE': content_type
        })
        req = Request(environ, None)

        try:
            req.args['action']
        except HTTPBadRequest as e:
            self.assertEqual("400 Bad Request (Invalid request arguments.)",
                             unicode(e))
        else:
            self.fail("HTTPBadRequest not raised.")

    def test_post_with_null_bytes_for_filename(self):
        form_data = textwrap.dedent("""\
            --%(boundary)s\r\n\
            Content-Disposition: form-data; name="attachment"; \
            filename="thefi\x00le.txt"\r\n\
            Content-Type: text/plain\r\n\
            \r\n\
            The file content.\r\n\
            --%(boundary)s\r\n\
            Content-Disposition: form-data; name="action"\r\n\
            \r\n\
            new\r\n\
            --%(boundary)s--\r\n\
            """)
        self._test_post_with_null_bytes(form_data)

    def test_post_with_null_bytes_for_name(self):
        form_data = textwrap.dedent("""\
            --%(boundary)s\r\n\
            Content-Disposition: form-data; name="acti\x00n"\r\n\
            \r\n\
            new\r\n\
            --%(boundary)s--\r\n\
            """)

        self._test_post_with_null_bytes(form_data)

    def test_post_with_null_bytes_for_value(self):
        form_data = textwrap.dedent("""\
            --%(boundary)s\r\n\
            Content-Disposition: form-data; name="action"\r\n\
            \r\n\
            ne\x00w\r\n\
            --%(boundary)s--\r\n\
            """)
        self._test_post_with_null_bytes(form_data)

    def test_qs_on_post(self):
        """Make sure req.args parsing is consistent even after the backwards
        incompatible change introduced in Python 2.6.
        """
        environ = _make_environ(method='GET', QUERY_STRING='action=foo')
        req = Request(environ, None)
        self.assertEqual('foo', req.args['action'])
        environ = _make_environ(method='POST', **{
            'wsgi.input': io.BytesIO(b'action=bar'),
            'CONTENT_LENGTH': '10',
            'CONTENT_TYPE': 'application/x-www-form-urlencoded',
            'QUERY_STRING': 'action=foo'
        })
        req = Request(environ, None)
        self.assertEqual('bar', req.args['action'])

    def test_qs_invalid_value_bytes(self):
        environ = _make_environ(QUERY_STRING='name=%FF')
        req = Request(environ, None)
        with self.assertRaises(HTTPBadRequest):
            req.arg_list()

    def test_qs_invalid_name_bytes(self):
        environ = _make_environ(QUERY_STRING='%FF=value')
        req = Request(environ, None)
        with self.assertRaises(HTTPBadRequest):
            req.arg_list()

    def test_post_text_html_disables_xss(self):
        """POST request with content-type text/html disables XSS
        protection (#12926).
        """
        content_type = 'text/html'
        content = "The content"
        environ = _make_environ(method='POST',
                                **{'wsgi.input': io.BytesIO(content),
                                   'CONTENT_LENGTH': str(len(content)),
                                   'CONTENT_TYPE': content_type})
        req = _make_req(environ)
        with self.assertRaises(RequestDone):
            req.send(content, content_type)
        self.assertIn('0', req.headers_sent['X-XSS-Protection'])

    def test_is_valid_header(self):
        # Reserved headers not allowed.
        for name in ('Content-Type', 'Content-Length', 'Location',
                     'ETag', 'Pragma', 'Cache-Control', 'Expires'):
            self.assertFalse(Request.is_valid_header(name))
            self.assertFalse(Request.is_valid_header(name.lower()))
        # Control code not allowed in header value.
        self.assertFalse(Request.is_valid_header('X-Custom-1', '\x00custom1'))
        self.assertFalse(Request.is_valid_header('X-Custom-1', 'cust\x0aom1'))
        self.assertFalse(Request.is_valid_header('X-Custom-1', 'custom1\x7f'))
        # Only a subset of special characters allowed in header name.
        self.assertFalse(Request.is_valid_header('X-Custom-(2)', 'custom2'))
        self.assertFalse(Request.is_valid_header('X-Custom-:2:', 'custom2'))
        self.assertTrue(Request.is_valid_header('Aa0-!#$%&\'*+.^_`|~',
                                                'custom2'))


class RequestSendFileTestCase(unittest.TestCase):

    def setUp(self):
        self.dir = mkdtemp()
        self.filename = os.path.join(self.dir, 'test.txt')
        self.data = 'contents\n'
        create_file(self.filename, self.data, 'wb')
        self.req = None

    def tearDown(self):
        if self.req and self.req._response:
            self.req._response.close()
        rmtree(self.dir)

    def _create_req(self, use_xsendfile=False, xsendfile_header='X-Sendfile'):
        self.req = req = _make_req(_make_environ(), use_xsendfile=use_xsendfile,
                                   xsendfile_header=xsendfile_header)
        return req

    def test_send_file(self):
        req = self._create_req()
        with self.assertRaises(RequestDone):
            req.send_file(self.filename, 'text/plain')
        self.assertEqual('200 Ok', req.status_sent[0])
        self.assertEqual('text/plain', req.headers_sent['Content-Type'])
        self.assertEqual(str(len(self.data)),
                         req.headers_sent['Content-Length'])
        self.assertNotIn('X-Sendfile', req.headers_sent)
        self.assertEqual(self.data, ''.join(req._response))
        self.assertEqual('', req.response_sent)

    def test_send_file_with_xsendfile(self):
        req = self._create_req(use_xsendfile=True)
        with self.assertRaises(RequestDone):
            req.send_file(self.filename, 'text/plain')
        self.assertEqual('200 Ok', req.status_sent[0])
        self.assertEqual('text/plain', req.headers_sent['Content-Type'])
        self.assertEqual(self.filename, req.headers_sent['X-Sendfile'])
        self.assertIsNone(req._response)
        self.assertEqual('', req.response_sent)

    def test_send_file_with_xsendfile_header(self):
        req = self._create_req(use_xsendfile=True,
                               xsendfile_header='X-Accel-Redirect')
        with self.assertRaises(RequestDone):
            req.send_file(self.filename, 'text/plain')
        self.assertEqual('200 Ok', req.status_sent[0])
        self.assertEqual('text/plain', req.headers_sent['Content-Type'])
        self.assertEqual(self.filename, req.headers_sent['X-Accel-Redirect'])
        self.assertNotIn('X-Sendfile', req.headers_sent)
        self.assertIsNone(req._response)
        self.assertEqual('', req.response_sent)

    def test_send_file_with_xsendfile_and_empty_header(self):
        req = self._create_req(use_xsendfile=True, xsendfile_header='')
        with self.assertRaises(RequestDone):
            req.send_file(self.filename, 'text/plain')
        self.assertEqual('200 Ok', req.status_sent[0])
        self.assertEqual('text/plain', req.headers_sent['Content-Type'])
        self.assertEqual(str(len(self.data)),
                         req.headers_sent['Content-Length'])
        self.assertNotIn('X-Sendfile', req.headers_sent)
        self.assertEqual(self.data, ''.join(req._response))
        self.assertEqual('', req.response_sent)


class ParseArgListTestCase(unittest.TestCase):

    def test_qs_str(self):
        args = parse_arg_list('k%C3%A9y=resum%C3%A9&r%C3%A9sum%C3%A9')
        self.assertTrue(unicode, type(args[0][0]))
        self.assertTrue(unicode, type(args[0][1]))
        self.assertEqual(u'kéy', args[0][0])
        self.assertEqual(u'resumé', args[0][1])
        self.assertTrue(unicode, type(args[1][0]))
        self.assertEqual(u'résumé', args[1][0])

    def test_qs_str_with_prefix(self):
        """The leading `?` should be stripped from the query string."""
        args = parse_arg_list('?k%C3%A9y=resum%C3%A9&r%C3%A9sum%C3%A9')
        self.assertTrue(unicode, type(args[0][0]))
        self.assertTrue(unicode, type(args[0][1]))
        self.assertEqual(u'kéy', args[0][0])
        self.assertEqual(u'resumé', args[0][1])
        self.assertTrue(unicode, type(args[1][0]))
        self.assertEqual(u'résumé', args[1][0])

    def test_qs_unicode(self):
        args = parse_arg_list(u'ké%3Dy=re%26su=mé&résu%26mé')
        self.assertTrue(unicode, type(args[0][0]))
        self.assertTrue(unicode, type(args[0][1]))
        self.assertEqual(u'ké=y', args[0][0])
        self.assertEqual(u're&su=mé', args[0][1])
        self.assertTrue(unicode, type(args[1][0]))
        self.assertEqual(u'résu&mé', args[1][0])


class HTTPExceptionTestCase(unittest.TestCase):

    def test_tracerror_with_string_as_argument(self):
        e1 = TracError('the message')
        e2 = HTTPInternalServerError(e1)
        self.assertEqual('500 Trac Error (the message)', unicode(e2))

    def test_tracerror_with_fragment_as_argument(self):
        e1 = TracError(tag(tag.b('the message')))
        e2 = HTTPInternalServerError(e1)
        self.assertEqual('500 Trac Error (<b>the message</b>)', unicode(e2))

    def test_exception_with_string_as_argument(self):
        e1 = Exception('the message')
        e2 = HTTPInternalServerError(e1)
        self.assertEqual('500 Internal Server Error (the message)',
                         unicode(e2))

    def test_exception_with_fragment_as_argument(self):
        e1 = Exception(tag(tag.b('the message')))
        e2 = HTTPInternalServerError(e1)
        self.assertEqual('500 Internal Server Error (<b>the message</b>)',
                         unicode(e2))

    def test_fragment_with_unicode_as_argument(self):
        e = HTTPInternalServerError(tag.b(u'thé méssägé'))
        self.assertEqual(u'500 Internal Server Error (<b>thé méssägé</b>)',
                         unicode(e))


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(RequestTestCase))
    suite.addTest(unittest.makeSuite(RequestSendFileTestCase))
    suite.addTest(unittest.makeSuite(ParseArgListTestCase))
    suite.addTest(unittest.makeSuite(HTTPExceptionTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
