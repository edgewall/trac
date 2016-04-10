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

import os

import trac.tests.compat
from trac.core import TracError
from trac.test import EnvironmentStub, Mock
from trac.util.compat import crypt
from trac.web.auth import BasicAuthentication, LoginModule
from trac.web.href import Href

from Cookie import SimpleCookie as Cookie
import unittest


class LoginModuleTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.module = LoginModule(self.env)

    def tearDown(self):
        self.env.reset_db()

    def test_anonymous_access(self):
        req = Mock(incookie=Cookie(), href=Href('/trac.cgi'),
                   remote_addr='127.0.0.1', remote_user=None,
                   base_path='/trac.cgi')
        self.assertIsNone(self.module.authenticate(req))

    def test_unknown_cookie_access(self):
        incookie = Cookie()
        incookie['trac_auth'] = '123'
        req = Mock(cgi_location='/trac', href=Href('/trac.cgi'),
                   incookie=incookie, outcookie=Cookie(),
                   remote_addr='127.0.0.1', remote_user=None,
                   base_path='/trac.cgi')
        self.assertIsNone(self.module.authenticate(req))

    def test_known_cookie_access(self):
        self.env.db_transaction("""
            INSERT INTO auth_cookie (cookie, name, ipnr)
            VALUES ('123', 'john', '127.0.0.1')""")
        incookie = Cookie()
        incookie['trac_auth'] = '123'
        outcookie = Cookie()
        req = Mock(incookie=incookie, outcookie=outcookie,
                   href=Href('/trac.cgi'), base_path='/trac.cgi',
                   remote_addr='127.0.0.1', remote_user=None)
        self.assertEqual('john', self.module.authenticate(req))
        self.assertNotIn('auth_cookie', req.outcookie)

    def test_known_cookie_ip_check_enabled(self):
        self.env.config.set('trac', 'check_auth_ip', 'yes')
        self.env.db_transaction("""
            INSERT INTO auth_cookie (cookie, name, ipnr)
            VALUES ('123', 'john', '127.0.0.1')""")
        incookie = Cookie()
        incookie['trac_auth'] = '123'
        outcookie = Cookie()
        req = Mock(cgi_location='/trac', href=Href('/trac.cgi'),
                   incookie=incookie, outcookie=outcookie,
                   remote_addr='192.168.0.100', remote_user=None,
                   base_path='/trac.cgi')
        self.assertIsNone(self.module.authenticate(req))
        self.assertIn('trac_auth', req.outcookie)

    def test_known_cookie_ip_check_disabled(self):
        self.env.config.set('trac', 'check_auth_ip', 'no')
        self.env.db_transaction("""
            INSERT INTO auth_cookie (cookie, name, ipnr)
            VALUES ('123', 'john', '127.0.0.1')""")
        incookie = Cookie()
        incookie['trac_auth'] = '123'
        outcookie = Cookie()
        req = Mock(incookie=incookie, outcookie=outcookie,
                   href=Href('/trac.cgi'), base_path='/trac.cgi',
                   remote_addr='192.168.0.100', remote_user=None)
        self.assertEqual('john', self.module.authenticate(req))
        self.assertNotIn('auth_cookie', req.outcookie)

    def test_login(self):
        outcookie = Cookie()
        # remote_user must be upper case to test that by default, case is
        # preserved.
        req = Mock(cgi_location='/trac', href=Href('/trac.cgi'),
                   incookie=Cookie(), outcookie=outcookie,
                   remote_addr='127.0.0.1', remote_user='john',
                   authname='john', base_path='/trac.cgi')
        self.module._do_login(req)

        self.assertIn('trac_auth', outcookie, '"trac_auth" Cookie not set')
        auth_cookie = outcookie['trac_auth'].value

        self.assertEqual([('john', '127.0.0.1')], self.env.db_query(
            "SELECT name, ipnr FROM auth_cookie WHERE cookie=%s",
            (auth_cookie,)))

    def test_login_ignore_case(self):
        """
        Test that login is succesful when the usernames differ in case, but case
        is ignored.
        """
        self.env.config.set('trac', 'ignore_auth_case', 'yes')

        outcookie = Cookie()
        req = Mock(cgi_location='/trac', href=Href('/trac.cgi'),
                   incookie=Cookie(), outcookie=outcookie,
                   remote_addr='127.0.0.1', remote_user='John',
                   authname='anonymous', base_path='/trac.cgi')
        self.module._do_login(req)

        self.assertIn('trac_auth', outcookie, '"trac_auth" Cookie not set')
        auth_cookie = outcookie['trac_auth'].value
        self.assertEqual([('john', '127.0.0.1')], self.env.db_query(
            "SELECT name, ipnr FROM auth_cookie WHERE cookie=%s",
            (auth_cookie,)))

    def test_login_no_username(self):
        req = Mock(incookie=Cookie(), href=Href('/trac.cgi'),
                   remote_addr='127.0.0.1', remote_user=None,
                   base_path='/trac.cgi')
        self.assertRaises(TracError, self.module._do_login, req)

    def test_already_logged_in_same_user(self):
        self.env.db_transaction("""
            INSERT INTO auth_cookie (cookie, name, ipnr)
            VALUES ('123', 'john', '127.0.0.1')""")
        incookie = Cookie()
        incookie['trac_auth'] = '123'
        req = Mock(incookie=incookie, outcookie=Cookie(),
                   href=Href('/trac.cgi'), base_path='/trac.cgi',
                   remote_addr='127.0.0.1', remote_user='john', authname='john')
        self.module._do_login(req) # this shouldn't raise an error

    def test_already_logged_in_different_user(self):
        self.env.db_transaction("""
            INSERT INTO auth_cookie (cookie, name, ipnr)
            VALUES ('123', 'john', '127.0.0.1')""")
        incookie = Cookie()
        incookie['trac_auth'] = '123'
        req = Mock(incookie=incookie, authname='john',
                   href=Href('/trac.cgi'), base_path='/trac.cgi',
                   remote_addr='127.0.0.1', remote_user='tom')
        self.assertRaises(TracError, self.module._do_login, req)

    def test_logout(self):
        self.env.db_transaction("""
            INSERT INTO auth_cookie (cookie, name, ipnr)
            VALUES ('123', 'john', '127.0.0.1')""")
        incookie = Cookie()
        incookie['trac_auth'] = '123'
        outcookie = Cookie()
        req = Mock(cgi_location='/trac', href=Href('/trac.cgi'),
                   incookie=incookie, outcookie=outcookie,
                   remote_addr='127.0.0.1', remote_user=None,
                   authname='john', method='POST', base_path='/trac.cgi')
        self.module._do_logout(req)
        self.assertIn('trac_auth', outcookie)
        self.assertFalse(self.env.db_query(
            "SELECT name, ipnr FROM auth_cookie WHERE name='john'"))

    def test_logout_not_logged_in(self):
        req = Mock(cgi_location='/trac', href=Href('/trac.cgi'),
                   incookie=Cookie(), outcookie=Cookie(),
                   remote_addr='127.0.0.1', remote_user=None,
                   authname='anonymous', method='POST', base_path='/trac.cgi')
        self.module._do_logout(req) # this shouldn't raise an error

    def test_logout_protect(self):
        self.env.db_transaction("""
            INSERT INTO auth_cookie (cookie, name, ipnr)
            VALUES ('123', 'john', '127.0.0.1')""")
        incookie = Cookie()
        incookie['trac_auth'] = '123'
        outcookie = Cookie()
        req = Mock(cgi_location='/trac', href=Href('/trac.cgi'),
                   incookie=incookie, outcookie=outcookie,
                   remote_addr='127.0.0.1', remote_user=None,
                   authname='john', method='GET', base_path='/trac.cgi')
        self.module._do_logout(req)
        self.assertNotIn('trac_auth', outcookie)
        self.assertEqual(
            [('john', '127.0.0.1')],
            self.env.db_query("SELECT name, ipnr FROM auth_cookie "
                              "WHERE cookie='123'"))


class BasicAuthenticationTestCase(unittest.TestCase):
    def setUp(self):
        filename = os.path.join(os.path.split(__file__)[0], 'htpasswd.txt')
        self.auth = BasicAuthentication(filename, 'realm')

    def tearDown(self):
        self.auth = None

    def test_crypt(self):
        self.assertTrue(self.auth.test('crypt', 'crypt'))
        self.assertFalse(self.auth.test('crypt', 'other'))

    def test_md5(self):
        self.assertTrue(self.auth.test('md5', 'md5'))
        self.assertFalse(self.auth.test('md5', 'other'))

    def test_sha(self):
        self.assertTrue(self.auth.test('sha', 'sha'))
        self.assertFalse(self.auth.test('sha', 'other'))


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(LoginModuleTestCase))
    if crypt:
        suite.addTest(unittest.makeSuite(BasicAuthenticationTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
