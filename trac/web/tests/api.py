# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2013 Edgewall Software
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
import shutil
import sys
import tempfile
import unittest
from StringIO import StringIO

import trac.tests.compat
from trac import perm
from trac.core import TracError
from trac.test import EnvironmentStub, Mock, MockPerm, locale_en
from trac.util import create_file
from trac.util.datefmt import utc
from trac.util.text import shorten_line
from trac.web.api import Request, RequestDone, parse_arg_list
from tracopt.perm.authz_policy import AuthzPolicy


class RequestHandlerPermissionsTestCaseBase(unittest.TestCase):

    authz_policy = None

    def setUp(self, module_class):
        self.path = tempfile.mkdtemp(prefix='trac-')
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
        self.env.reset_db()
        shutil.rmtree(self.path)

    def create_request(self, authname='anonymous', **kwargs):
        kw = {'perm': perm.PermissionCache(self.env, authname), 'args': {},
              'href': self.env.href, 'abs_href': self.env.abs_href,
              'tz': utc, 'locale': None, 'lc_time': locale_en,
              'chrome': {'notices': [], 'warnings': []},
              'method': None, 'get_header': lambda v: None}
        kw.update(kwargs)
        return Mock(**kw)

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
    environ = {'wsgi.url_scheme': scheme, 'wsgi.input': StringIO(''),
               'REQUEST_METHOD': method, 'SERVER_NAME': server_name,
               'SERVER_PORT': server_port, 'SCRIPT_NAME': script_name}
    environ.update(kwargs)
    return environ


def _make_req(environ, start_response, args={}, arg_list=(), authname='admin',
              form_token='A' * 40, chrome={'links': {}, 'scripts': []},
              perm=MockPerm(), session={}, tz=utc, locale=None, **kwargs):
    req = Request(environ, start_response)
    req.args = args
    req.arg_list = arg_list
    req.authname = authname
    req.form_token = form_token
    req.chrome = chrome
    req.perm = perm
    req.session = session
    req.tz = tz
    req.locale = locale
    for name, value in kwargs.iteritems():
        setattr(req, name, value)
    return req


class RequestTestCase(unittest.TestCase):

    def _make_environ(self, *args, **kwargs):
        return _make_environ(*args, **kwargs)

    def test_base_url(self):
        environ = self._make_environ()
        req = Request(environ, None)
        self.assertEqual('http://example.org/trac', req.base_url)

    def test_base_url_host(self):
        environ = self._make_environ(server_port=8080, HTTP_HOST='example.com')
        req = Request(environ, None)
        self.assertEqual('http://example.com/trac', req.base_url)

    def test_base_url_nondefaultport(self):
        environ = self._make_environ(server_port=8080)
        req = Request(environ, None)
        self.assertEqual('http://example.org:8080/trac', req.base_url)

    def test_base_url_https(self):
        environ = self._make_environ(scheme='https', server_port=443)
        req = Request(environ, None)
        self.assertEqual('https://example.org/trac', req.base_url)

    def test_base_url_https_host(self):
        environ = self._make_environ(scheme='https', server_port=443,
                                     HTTP_HOST='example.com')
        req = Request(environ, None)
        self.assertEqual('https://example.com/trac', req.base_url)

    def test_base_url_https_nondefaultport(self):
        environ = self._make_environ(scheme='https', server_port=8443)
        req = Request(environ, None)
        self.assertEqual('https://example.org:8443/trac', req.base_url)

    def test_base_url_proxy(self):
        environ = self._make_environ(HTTP_HOST='localhost',
                                     HTTP_X_FORWARDED_HOST='example.com')
        req = Request(environ, None)
        self.assertEqual('http://localhost/trac', req.base_url)

    def test_languages(self):
        environ = self._make_environ()
        environ['HTTP_ACCEPT_LANGUAGE'] = 'en-us,en;q=0.5'
        req = Request(environ, None)
        self.assertEqual(['en-us', 'en'], req.languages)

    def test_redirect(self):
        status_sent = []
        headers_sent = {}
        def start_response(status, headers):
            status_sent.append(status)
            headers_sent.update(dict(headers))
        environ = self._make_environ(method='HEAD')
        req = Request(environ, start_response)
        req.session = Mock(save=lambda: None)
        self.assertRaises(RequestDone, req.redirect, '/trac/test')
        self.assertEqual('302 Found', status_sent[0])
        self.assertEqual('http://example.org/trac/test',
                         headers_sent['Location'])

    def test_redirect_absolute(self):
        status_sent = []
        headers_sent = {}
        def start_response(status, headers):
            status_sent.append(status)
            headers_sent.update(dict(headers))
        environ = self._make_environ(method='HEAD')
        req = Request(environ, start_response,)
        req.session = Mock(save=lambda: None)
        self.assertRaises(RequestDone, req.redirect,
                          'http://example.com/trac/test')
        self.assertEqual('302 Found', status_sent[0])
        self.assertEqual('http://example.com/trac/test',
                         headers_sent['Location'])

    def test_write_unicode(self):
        buf = StringIO()
        def write(data):
            buf.write(data)
        def start_response(status, headers):
            return write
        environ = self._make_environ(method='HEAD')

        req = Request(environ, start_response)
        req.send_header('Content-Type', 'text/plain;charset=utf-8')
        req.send_header('Content-Length', 0)
        # anyway we're not supposed to send unicode, so we get a ValueError
        self.assertRaises(ValueError, req.write, u'Föö')

    def test_invalid_cookies(self):
        environ = self._make_environ(HTTP_COOKIE='bad:key=value;')
        req = Request(environ, None)
        self.assertEqual('', str(req.incookie))

    def test_multiple_cookies(self):
        environ = self._make_environ(HTTP_COOKIE='key=value1; key=value2;')
        req = Request(environ, None)
        self.assertEqual('Set-Cookie: key=value1',
                         str(req.incookie).rstrip(';'))

    def test_read(self):
        environ = self._make_environ(**{'wsgi.input': StringIO('test input')})
        req = Request(environ, None)
        self.assertEqual('test input', req.read())

    def test_read_size(self):
        environ = self._make_environ(**{'wsgi.input': StringIO('test input')})
        req = Request(environ, None)
        self.assertEqual('test', req.read(size=4))

    def test_qs_on_post(self):
        """Make sure req.args parsing is consistent even after the backwards
        incompatible change introduced in Python 2.6.
        """
        environ = self._make_environ(method='GET',
                                     **{'QUERY_STRING': 'action=foo'})
        req = Request(environ, None)
        self.assertEqual('foo', req.args['action'])
        environ = self._make_environ(method='POST',
                                     **{'wsgi.input': StringIO('action=bar'),
                                        'CONTENT_LENGTH': '10',
                                        'CONTENT_TYPE': 'application/x-www-form-urlencoded',
                                        'QUERY_STRING': 'action=foo'})
        req = Request(environ, None)
        self.assertEqual('bar', req.args['action'])


class SendErrorTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()

    def tearDown(self):
        self.env.reset_db()

    def test_trac_error(self):
        content = self._send_error(error_klass=TracError)
        self.assertIn('<p class="message">Oops!</p>', content)
        self.assertNotIn('<strong>Trac detected an internal error:</strong>',
                         content)
        self.assertNotIn('There was an internal error in Trac.', content)

    def test_internal_error_for_non_admin(self):
        content = self._send_error(perm={})
        self.assertIn('There was an internal error in Trac.', content)
        self.assertIn('<p>To that end, you could', content)
        self.assertNotIn('This is probably a local installation issue.',
                         content)
        self.assertNotIn('<h2>Found a bug in Trac?</h2>', content)

    def test_internal_error_with_admin_trac_for_non_admin(self):
        content = self._send_error(perm={},
                                   admin_trac_url='http://example.org/admin')
        self.assertIn('There was an internal error in Trac.', content)
        self.assertIn('<p>To that end, you could', content)
        self.assertIn(' action="http://example.org/admin/newticket#"', content)
        self.assertNotIn('This is probably a local installation issue.',
                         content)
        self.assertNotIn('<h2>Found a bug in Trac?</h2>', content)

    def test_internal_error_without_admin_trac_for_non_admin(self):
        content = self._send_error(perm={}, admin_trac_url='')
        self.assertIn('There was an internal error in Trac.', content)
        self.assertNotIn('<p>To that end, you could', content)
        self.assertNotIn('This is probably a local installation issue.',
                         content)
        self.assertNotIn('<h2>Found a bug in Trac?</h2>', content)

    def test_internal_error_for_admin(self):
        content = self._send_error()
        self.assertNotIn('There was an internal error in Trac.', content)
        self.assertIn('This is probably a local installation issue.', content)
        self.assertNotIn('a ticket at the admin Trac to report', content)
        self.assertIn('<h2>Found a bug in Trac?</h2>', content)
        self.assertIn('<p>Otherwise, please', content)
        self.assertIn(' action="http://example.org/tracker/newticket"',
                      content)

    def test_internal_error_with_admin_trac_for_admin(self):
        content = self._send_error(admin_trac_url='http://example.org/admin')
        self.assertNotIn('There was an internal error in Trac.', content)
        self.assertIn('This is probably a local installation issue.', content)
        self.assertIn('a ticket at the admin Trac to report', content)
        self.assertIn(' action="http://example.org/admin/newticket#"', content)
        self.assertIn('<h2>Found a bug in Trac?</h2>', content)
        self.assertIn('<p>Otherwise, please', content)
        self.assertIn(' action="http://example.org/tracker/newticket"',
                      content)

    def test_internal_error_without_admin_trac_for_admin(self):
        content = self._send_error(admin_trac_url='')
        self.assertNotIn('There was an internal error in Trac.', content)
        self.assertIn('This is probably a local installation issue.', content)
        self.assertNotIn('a ticket at the admin Trac to report', content)
        self.assertIn('<h2>Found a bug in Trac?</h2>', content)
        self.assertIn('<p>Otherwise, please', content)
        self.assertIn(' action="http://example.org/tracker/newticket"',
                      content)

    def _send_error(self, admin_trac_url='.', perm=None,
                    error_klass=ValueError):
        self.env.config.set('project', 'admin_trac_url', admin_trac_url)
        self.assertEquals(admin_trac_url, self.env.project_admin_trac_url)

        content = StringIO()
        result = {'status': None, 'headers': []}
        def write(data):
            content.write(data)
        def start_response(status, headers, exc_info=None):
            result['status'] = status
            result['headers'].extend(headers)
            return write
        environ = _make_environ()
        req = _make_req(environ, start_response)
        try:
            raise error_klass('Oops!')
        except:
            exc_info = sys.exc_info()
        data = {'title': 'Internal Error',
                'type': ('internal', 'TracError')[error_klass is TracError],
                'message': 'Oops!', 'traceback': None, 'frames': [],
                'shorten_line': shorten_line,
                'plugins': [], 'faulty_plugins': [],
                'tracker': 'http://example.org/tracker', 'tracker_args': {},
                'description': '', 'description_en': '',
                'get_systeminfo': lambda: ()}
        if perm is not None:
            data['perm'] = perm

        self.assertRaises(RequestDone, req.send_error, exc_info, env=self.env,
                          data=data)
        content = content.getvalue().decode('utf-8')
        self.assertIn('<!DOCTYPE ', content)
        self.assertEquals('500', result['status'].split()[0])
        self.assertIn(('Content-Type', 'text/html;charset=utf-8'),
                      result['headers'])
        return content


class ParseArgListTestCase(unittest.TestCase):

    def test_qs_str(self):
        args = parse_arg_list('k%C3%A9y=resum%C3%A9&r%C3%A9sum%C3%A9')
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


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(RequestTestCase))
    suite.addTest(unittest.makeSuite(SendErrorTestCase))
    suite.addTest(unittest.makeSuite(ParseArgListTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
