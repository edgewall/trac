from trac.test import Mock
from trac.web.auth import Authenticator

from Cookie import SimpleCookie as Cookie
import unittest


class AuthTestCase(unittest.TestCase):

    def setUp(self):
        from trac.test import InMemoryDatabase
        self.db = InMemoryDatabase()

    def test_anonymous_access(self):
        req = Mock(incookie=Cookie(), remote_addr='127.0.0.1')
        auth = Authenticator(self.db, req)
        self.assertEqual('anonymous', auth.authname)

    def test_unknown_cookie_access(self):
        incookie = Cookie()
        incookie['trac_auth'] = '123'
        req = Mock(incookie=incookie, remote_addr='127.0.0.1')
        auth = Authenticator(self.db, req)
        self.assertEqual('anonymous', auth.authname)

    def test_known_cookie_access(self):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO auth_cookie (cookie, name, ipnr) "
                       "VALUES ('123', 'john', '127.0.0.1')")
        incookie = Cookie()
        incookie['trac_auth'] = '123'
        req = Mock(incookie=incookie, remote_addr='127.0.0.1')
        auth = Authenticator(self.db, req)
        self.assertEqual('john', auth.authname)

    def test_known_cookie_different_ipnr_access(self):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO auth_cookie (cookie, name, ipnr) "
                       "VALUES ('123', 'john', '127.0.0.1')")
        incookie = Cookie()
        incookie['trac_auth'] = '123'
        req = Mock(incookie=incookie, remote_addr='192.168.0.100')
        auth = Authenticator(self.db, req)
        self.assertEqual('anonymous', auth.authname)

    def test_login(self):
        outcookie = Cookie()
        req = Mock(cgi_location='/trac', incookie=Cookie(), outcookie=outcookie,
                   remote_addr='127.0.0.1', remote_user='john')
        auth = Authenticator(self.db, req)
        auth.login(req)

        assert outcookie.has_key('trac_auth'), '"trac_auth" Cookie not set'
        auth_cookie = outcookie['trac_auth'].value
        cursor = self.db.cursor()
        cursor.execute("SELECT name,ipnr FROM auth_cookie WHERE cookie=%s",
                       (auth_cookie))
        row = cursor.fetchone()
        self.assertEquals('john', row[0])
        self.assertEquals('127.0.0.1', row[1])

    def test_login_no_username(self):
        req = Mock(incookie=Cookie(), remote_addr='127.0.0.1', remote_user=None)
        auth = Authenticator(self.db, req)
        self.assertRaises(AssertionError, lambda: auth.login(req))

    def test_already_logged_in(self):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO auth_cookie (cookie, name, ipnr) "
                       "VALUES ('123', 'john', '127.0.0.1')")
        incookie = Cookie()
        incookie['trac_auth'] = '123'
        req = Mock(incookie=incookie, remote_addr='127.0.0.1', remote_user=None)
        auth = Authenticator(self.db, req)
        self.assertRaises(AssertionError, auth.login, req)


    def test_logout(self):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO auth_cookie (cookie, name, ipnr) "
                       "VALUES ('123', 'john', '127.0.0.1')")
        incookie = Cookie()
        incookie['trac_auth'] = '123'
        req = Mock(incookie=incookie, remote_addr='127.0.0.1')
        auth = Authenticator(self.db, req)
        auth.logout()
        cursor.execute("SELECT name,ipnr FROM auth_cookie WHERE name='john'")
        self.failIf(cursor.fetchone())

    def test_logout_not_logged_in(self):
        req = Mock(incookie=Cookie(), remote_addr='127.0.0.1', remote_user=None)
        auth = Authenticator(self.db, req)
        self.assertRaises(AssertionError, auth.logout)


def suite():
    return unittest.makeSuite(CGIRequestTestCase, 'test')

if __name__ == '__main__':
    unittest.main()
