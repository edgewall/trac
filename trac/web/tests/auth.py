# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2023 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

import base64
import os
import tempfile

try:
    import crypt
except ImportError:
    crypt = None

try:
    import passlib
except ImportError:
    passlib = None
    has_method_sha256 = crypt and crypt.METHOD_SHA256 in crypt.methods
    has_method_sha512 = crypt and crypt.METHOD_SHA512 in crypt.methods
else:
    has_method_sha256 = True
    has_method_sha512 = True

has_method_bcrypt = crypt and hasattr(crypt, 'METHOD_BLOWFISH') and \
                    crypt.METHOD_BLOWFISH in crypt.methods
if not has_method_bcrypt and passlib:
    try:
        import bcrypt
    except ImportError:
        pass
    else:
        has_method_bcrypt = True

from trac.core import TracError
from trac.util.compat import verify_hash
from trac.util.text import unicode_to_base64
from trac.test import EnvironmentStub, MockRequest, makeSuite, rmtree
from trac.web.auth import BasicAuthentication, DigestAuthentication, LoginModule

from http.cookies import SimpleCookie as Cookie
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
        Test that login is successful when the usernames differ in case, but case
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
        with open(self.filename, 'w', encoding='utf-8') as fd:
            fd.write("user1:trac:f21b2f8c5abd6baaeb3ffc28dce30e7c:U One #cmt\n")
            fd.write("user2:trac:97a40f5b8d13962839f664534aa573ef:U Two \n")

        auth = DigestAuthentication(self.filename, 'trac')
        self.assertIn('user1', auth.hash)
        self.assertIn('f21b2f8c5abd6baaeb3ffc28dce30e7c', auth.hash['user1'])
        self.assertIn('user2', auth.hash)
        self.assertIn('97a40f5b8d13962839f664534aa573ef', auth.hash['user2'])


@unittest.skipUnless(verify_hash, 'verify_hash is unavailable')
class BasicAuthenticationTestCase(unittest.TestCase):

    _HASH_CRYPT= 'PgjnZnmDQ8S7w'
    _HASH_MD5 = '$apr1$PjxHNVvY$41a7qPozEZ1b47OomFoos/'
    _HASH_SHA = '{SHA}2PRZAyDhNDqRW2OUFwZQqPNdaSY='
    _HASH_BCRYPT = ('$2b$05$b6vmJqKFbMa9k0EYTbPn4OmniMo2cHULRX3C4FxbI2iijv1.qB'
                    't.e')
    _HASH_SHA256 = ('$5$GoITETngL2iA/Mkl$zOQuOlD10PvoELd9wQaV5YLWNun.iAm.pS8cK'
                    'XlUjO.')
    _HASH_SHA512 = ('$6$K0aa86U7nBj4rbxv$BI70lxTsmw9aN6OrUOrSb4h/CjZ0t5rCQMUY1'
                    'ag0UMQZceHkb8tgqn9X6WxjcXEpKfzE.sOeDz6qIeBQMUdXG/')
    _HASH_COLON = '$apr1$YMlTTmM3$01fy1fQDi4sc48d/FaohC/'
    _HASH_UNKNOWN = '$unknown$hash'

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.filename = os.path.join(self.dir, 'htpasswd.txt')

    def tearDown(self):
        rmtree(self.dir)

    def _write_default_htpasswd(self):
        with open(self.filename, 'w', encoding='utf-8') as fd:
            fd.write('crypt:{}\n'.format(self._HASH_CRYPT))
            fd.write('md5:{}\n'.format(self._HASH_MD5))
            fd.write('sha:{}\n'.format(self._HASH_SHA))
            fd.write('bcrypt:{}\n'.format(self._HASH_BCRYPT))
            fd.write('sha256:{}\n'.format(self._HASH_SHA256))
            fd.write('sha512:{}\n'.format(self._HASH_SHA512))
            fd.write('colon:{}\n'.format(self._HASH_COLON))
            fd.write('unknown:{}\n'.format(self._HASH_UNKNOWN))

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

    def test_colon_in_password(self):
        self._write_default_htpasswd()
        auth = BasicAuthentication(self.filename, 'realm')
        def do_auth(username, password):
            value = 'Basic ' + unicode_to_base64('%s:%s' %
                                                 (username, password))
            environ = {'HTTP_AUTHORIZATION': value}
            def start_response(status, headers):
                return lambda body: None
            return auth.do_auth(environ, start_response)
        self.assertEqual('colon', do_auth('colon', 'blah:blah'))
        self.assertIsNone(do_auth('colon', 'blah:blah:'))
        self.assertIsNone(do_auth('colon', 'blah:blah:blah'))

    @unittest.skipUnless(has_method_bcrypt, 'bcrypt unavailable')
    def test_bcrypt(self):
        self._write_default_htpasswd()
        auth = BasicAuthentication(self.filename, 'realm')
        self.assertTrue(auth.test('bcrypt', 'bcrypt'))
        self.assertFalse(auth.test('bcrypt', 'other'))

    @unittest.skipUnless(has_method_sha256, 'sha256 hash unavailable')
    def test_sha256(self):
        self._write_default_htpasswd()
        auth = BasicAuthentication(self.filename, 'realm')
        self.assertTrue(auth.test('sha256', 'sha256'))
        self.assertFalse(auth.test('sha256', 'other'))

    @unittest.skipUnless(has_method_sha512, 'sha512 hash unavailable')
    def test_sha512(self):
        self._write_default_htpasswd()
        auth = BasicAuthentication(self.filename, 'realm')
        self.assertTrue(auth.test('sha512', 'sha512'))
        self.assertFalse(auth.test('sha512', 'other'))

    def test_unknown(self):
        self._write_default_htpasswd()
        auth = BasicAuthentication(self.filename, 'realm')
        self.assertFalse(auth.test('unknown', 'unknown'))

    def test_extra_entries_ignored(self):
        """Extra entries and comments are ignored."""
        with open(self.filename, 'w', encoding='utf-8') as fd:
            fd.write('crypt:{}:User One #comment\n'.format(self._HASH_CRYPT))
            fd.write('md5:{}:User Two \n'.format(self._HASH_MD5))
            fd.write('sha:{}:User Three #\n'.format(self._HASH_SHA))
            fd.write('bcrypt:{}:User Four\n'.format(self._HASH_BCRYPT))
            fd.write('sha256:{}:User Five\n'.format(self._HASH_SHA256))
            fd.write('sha512:{}:User Six\n'.format(self._HASH_SHA512))
            fd.write('unknown:{}:User Unknown ?\n'.format(self._HASH_UNKNOWN))

        auth = BasicAuthentication(self.filename, 'realm')
        self.assertTrue(auth.test('crypt', 'crypt'))
        self.assertFalse(auth.test('crypt', 'other'))
        self.assertTrue(auth.test('md5', 'md5'))
        self.assertFalse(auth.test('md5', 'other'))
        self.assertTrue(auth.test('sha', 'sha'))
        self.assertFalse(auth.test('sha', 'other'))
        if has_method_bcrypt:
            self.assertTrue(auth.test('bcrypt', 'bcrypt'))
            self.assertFalse(auth.test('bcrypt', 'other'))
        if has_method_sha256:
            self.assertTrue(auth.test('sha256', 'sha256'))
            self.assertFalse(auth.test('sha256', 'other'))
        if has_method_sha512:
            self.assertTrue(auth.test('sha512', 'sha512'))
            self.assertFalse(auth.test('sha512', 'other'))
        self.assertFalse(auth.test('unknown', 'unknown'))


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(makeSuite(LoginModuleTestCase))
    suite.addTest(makeSuite(DigestAuthenticationTestCase))
    suite.addTest(makeSuite(BasicAuthenticationTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
