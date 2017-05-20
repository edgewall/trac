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
import tempfile

import trac.tests.compat
from trac.core import TracError
from trac.util.compat import crypt
from trac.test import EnvironmentStub, MockRequest, rmtree
from trac.web.auth import BasicAuthentication, DigestAuthentication, LoginModule

from Cookie import SimpleCookie as Cookie
import unittest


class LoginModuleTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.module = LoginModule(self.env)

    def tearDown(self):
        self.env.reset_db()

    def test_anonymous_access(self):
        req = MockRequest(self.env, remote_user=None)
        self.assertIsNone(self.module.authenticate(req))

    def test_unknown_cookie_access(self):
        incookie = Cookie()
        incookie['trac_auth'] = '123'
        req = MockRequest(self.env, remote_user=None)
        self.assertIsNone(self.module.authenticate(req))

    def test_known_cookie_access(self):
        self.env.db_transaction("""
            INSERT INTO auth_cookie (cookie, name, ipnr)
            VALUES ('123', 'john', '127.0.0.1')""")
        req = MockRequest(self.env, remote_user=None)
        req.incookie['trac_auth'] = '123'
        self.assertEqual('john', self.module.authenticate(req))
        self.assertNotIn('auth_cookie', req.outcookie)

    def test_known_cookie_ip_check_enabled(self):
        self.env.config.set('trac', 'check_auth_ip', 'yes')
        self.env.db_transaction("""
            INSERT INTO auth_cookie (cookie, name, ipnr)
            VALUES ('123', 'john', '127.0.0.1')""")
        req = MockRequest(self.env, remote_addr='192.168.0.100',
                          remote_user=None)
        req.incookie['trac_auth'] = '123'
        self.assertIsNone(self.module.authenticate(req))
        self.assertIn('trac_auth', req.outcookie)

    def test_known_cookie_ip_check_disabled(self):
        self.env.config.set('trac', 'check_auth_ip', 'no')
        self.env.db_transaction("""
            INSERT INTO auth_cookie (cookie, name, ipnr)
            VALUES ('123', 'john', '127.0.0.1')""")
        req = MockRequest(self.env, remote_addr='192.168.0.100',
                          remote_user=None)
        req.incookie['trac_auth'] = '123'
        self.assertEqual('john', self.module.authenticate(req))
        self.assertNotIn('auth_cookie', req.outcookie)

    def test_login(self):
        # remote_user must be upper case to test that by default, case is
        # preserved.
        req = MockRequest(self.env, authname='john')
        self.module._do_login(req)

        self.assertIn('trac_auth', req.outcookie, '"trac_auth" Cookie not set')
        auth_cookie = req.outcookie['trac_auth'].value

        self.assertEqual([('john', '127.0.0.1')], self.env.db_query(
            "SELECT name, ipnr FROM auth_cookie WHERE cookie=%s",
            (auth_cookie,)))

    def test_login_ignore_case(self):
        """
        Test that login is succesful when the usernames differ in case, but case
        is ignored.
        """
        self.env.config.set('trac', 'ignore_auth_case', 'yes')

        req = MockRequest(self.env, remote_user='John')

        self.module._do_login(req)

        self.assertIn('trac_auth', req.outcookie, '"trac_auth" Cookie not set')
        auth_cookie = req.outcookie['trac_auth'].value
        self.assertEqual([('john', '127.0.0.1')], self.env.db_query(
            "SELECT name, ipnr FROM auth_cookie WHERE cookie=%s",
            (auth_cookie,)))

    def test_login_no_username(self):
        req = MockRequest(self.env, remote_user=None)
        self.assertRaises(TracError, self.module._do_login, req)

    def test_already_logged_in_same_user(self):
        self.env.db_transaction("""
            INSERT INTO auth_cookie (cookie, name, ipnr)
            VALUES ('123', 'john', '127.0.0.1')""")
        req = MockRequest(self.env, authname='john')
        self.module._do_login(req)  # this shouldn't raise an error

    def test_already_logged_in_different_user(self):
        self.env.db_transaction("""
            INSERT INTO auth_cookie (cookie, name, ipnr)
            VALUES ('123', 'john', '127.0.0.1')""")
        req = MockRequest(self.env, authname='john', remote_user='tom')
        self.assertRaises(TracError, self.module._do_login, req)

    def test_logout(self):
        self.env.db_transaction("""
            INSERT INTO auth_cookie (cookie, name, ipnr)
            VALUES ('123', 'john', '127.0.0.1')""")
        req = MockRequest(self.env, authname='john', method='POST')
        self.module._do_logout(req)
        self.assertIn('trac_auth', req.outcookie)
        self.assertFalse(self.env.db_query(
            "SELECT name, ipnr FROM auth_cookie WHERE name='john'"))

    def test_logout_not_logged_in(self):
        req = MockRequest(self.env, method='POST')
        self.module._do_logout(req)  # this shouldn't raise an error

    def test_logout_protect(self):
        self.env.db_transaction("""
            INSERT INTO auth_cookie (cookie, name, ipnr)
            VALUES ('123', 'john', '127.0.0.1')""")
        req = MockRequest(self.env, authname='john')
        self.module._do_logout(req)
        self.assertNotIn('trac_auth', req.outcookie)
        self.assertEqual(
            [('john', '127.0.0.1')],
            self.env.db_query("SELECT name, ipnr FROM auth_cookie "
                              "WHERE cookie='123'"))


class DigestAuthenticationTestCase(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.filename = os.path.join(self.dir, 'htdigest.txt')

    def tearDown(self):
        rmtree(self.dir)

    def test_extra_entries_ignored(self):
        """Extra entries and comments are ignored."""
        with open(self.filename, 'w') as fd:
            fd.write("user1:trac:f21b2f8c5abd6baaeb3ffc28dce30e7c:U One #cmt\n")
            fd.write("user2:trac:97a40f5b8d13962839f664534aa573ef:U Two \n")

        auth = DigestAuthentication(self.filename, 'trac')
        self.assertIn('user1', auth.hash)
        self.assertIn('f21b2f8c5abd6baaeb3ffc28dce30e7c', auth.hash['user1'])
        self.assertIn('user2', auth.hash)
        self.assertIn('97a40f5b8d13962839f664534aa573ef', auth.hash['user2'])


class BasicAuthenticationTestCase(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.filename = os.path.join(self.dir, 'htpasswd.txt')

    def tearDown(self):
        rmtree(self.dir)

    def _write_default_htpasswd(self):
        with open(self.filename, 'w') as fd:
            fd.write("crypt:PgjnZnmDQ8S7w\n")
            fd.write("md5:$apr1$PjxHNVvY$41a7qPozEZ1b47OomFoos/\n")
            fd.write("sha:{SHA}2PRZAyDhNDqRW2OUFwZQqPNdaSY=\n")

    def test_crypt(self):
        self._write_default_htpasswd()
        auth = BasicAuthentication(self.filename, 'realm')
        self.assertTrue(auth.test('crypt', 'crypt'))
        self.assertFalse(auth.test('crypt', 'other'))

    def test_md5(self):
        self._write_default_htpasswd()
        auth = BasicAuthentication(self.filename, 'realm')
        self.assertTrue(auth.test('md5', 'md5'))
        self.assertFalse(auth.test('md5', 'other'))

    def test_sha(self):
        self._write_default_htpasswd()
        auth = BasicAuthentication(self.filename, 'realm')
        self.assertTrue(auth.test('sha', 'sha'))
        self.assertFalse(auth.test('sha', 'other'))

    def test_extra_entries_ignored(self):
        """Extra entries and comments are ignored."""
        with open(self.filename, 'w') as fd:
            fd.write("crypt:PgjnZnmDQ8S7w:User One #comment\n")
            fd.write("md5:$apr1$PjxHNVvY$41a7qPozEZ1b47OomFoos/:User Two \n")
            fd.write("sha:{SHA}2PRZAyDhNDqRW2OUFwZQqPNdaSY=:User Three #\n")

        auth = BasicAuthentication(self.filename, 'realm')
        self.assertTrue(auth.test('crypt', 'crypt'))
        self.assertFalse(auth.test('crypt', 'other'))
        self.assertTrue(auth.test('md5', 'md5'))
        self.assertFalse(auth.test('md5', 'other'))
        self.assertTrue(auth.test('sha', 'sha'))
        self.assertFalse(auth.test('sha', 'other'))


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(LoginModuleTestCase))
    suite.addTest(unittest.makeSuite(DigestAuthenticationTestCase))
    if crypt:
        suite.addTest(unittest.makeSuite(BasicAuthenticationTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
