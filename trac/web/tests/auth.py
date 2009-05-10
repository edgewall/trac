from trac.core import TracError
from trac.test import EnvironmentStub, Mock
from trac.web.auth import LoginModule
from trac.web.href import Href

from Cookie import SimpleCookie as Cookie
import unittest


class LoginModuleTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.db = self.env.get_db_cnx()
        self.module = LoginModule(self.env)

    def tearDown(self):
        self.env.reset_db()

    def test_anonymous_access(self):
        req = Mock(incookie=Cookie(), href=Href('/trac.cgi'),
                   remote_addr='127.0.0.1', remote_user=None,
                   base_path='/trac.cgi')
        self.assertEqual(None, self.module.authenticate(req))

    def test_unknown_cookie_access(self):
        incookie = Cookie()
        incookie['trac_auth'] = '123'
        req = Mock(cgi_location='/trac', href=Href('/trac.cgi'),
                   incookie=incookie, outcookie=Cookie(),
                   remote_addr='127.0.0.1', remote_user=None,
                   base_path='/trac.cgi')
        self.assertEqual(None, self.module.authenticate(req))

    def test_known_cookie_access(self):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO auth_cookie (cookie, name, ipnr) "
                       "VALUES ('123', 'john', '127.0.0.1')")
        incookie = Cookie()
        incookie['trac_auth'] = '123'
        outcookie = Cookie()
        req = Mock(incookie=incookie, outcookie=outcookie,
                   href=Href('/trac.cgi'), base_path='/trac.cgi',
                   remote_addr='127.0.0.1', remote_user=None)
        self.assertEqual('john', self.module.authenticate(req))
        self.failIf('auth_cookie' in req.outcookie)

    def test_known_cookie_ip_check_enabled(self):
        self.env.config.set('trac', 'check_auth_ip', 'yes')
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO auth_cookie (cookie, name, ipnr) "
                       "VALUES ('123', 'john', '127.0.0.1')")
        incookie = Cookie()
        incookie['trac_auth'] = '123'
        outcookie = Cookie()
        req = Mock(cgi_location='/trac', href=Href('/trac.cgi'),
                   incookie=incookie, outcookie=outcookie,
                   remote_addr='192.168.0.100', remote_user=None,
                   base_path='/trac.cgi')
        self.assertEqual(None, self.module.authenticate(req))
        self.failIf('trac_auth' not in req.outcookie)

    def test_known_cookie_ip_check_disabled(self):
        self.env.config.set('trac', 'check_auth_ip', 'no')
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO auth_cookie (cookie, name, ipnr) "
                       "VALUES ('123', 'john', '127.0.0.1')")
        incookie = Cookie()
        incookie['trac_auth'] = '123'
        outcookie = Cookie()
        req = Mock(incookie=incookie, outcookie=outcookie,
                   href=Href('/trac.cgi'), base_path='/trac.cgi',
                   remote_addr='192.168.0.100', remote_user=None)
        self.assertEqual('john', self.module.authenticate(req))
        self.failIf('auth_cookie' in req.outcookie)

    def test_login(self):
        outcookie = Cookie()
        # remote_user must be upper case to test that by default, case is
        # preserved.
        req = Mock(cgi_location='/trac', href=Href('/trac.cgi'),
                   incookie=Cookie(), outcookie=outcookie, 
                   remote_addr='127.0.0.1', remote_user='john', 
                   authname='john', base_path='/trac.cgi')
        self.module._do_login(req)

        assert outcookie.has_key('trac_auth'), '"trac_auth" Cookie not set'
        auth_cookie = outcookie['trac_auth'].value
        cursor = self.db.cursor()
        cursor.execute("SELECT name,ipnr FROM auth_cookie WHERE cookie=%s",
                       (auth_cookie,))
        row = cursor.fetchone()
        self.assertEquals('john', row[0])
        self.assertEquals('127.0.0.1', row[1])
    
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

        assert outcookie.has_key('trac_auth'), '"trac_auth" Cookie not set'
        auth_cookie = outcookie['trac_auth'].value
        cursor = self.db.cursor()
        cursor.execute("SELECT name,ipnr FROM auth_cookie WHERE cookie=%s",
                       (auth_cookie,))
        row = cursor.fetchone()
        self.assertEquals('john', row[0])
        self.assertEquals('127.0.0.1', row[1])

    def test_login_no_username(self):
        req = Mock(incookie=Cookie(), href=Href('/trac.cgi'),
                   remote_addr='127.0.0.1', remote_user=None,
                   base_path='/trac.cgi')
        self.assertRaises(TracError, self.module._do_login, req)

    def test_already_logged_in_same_user(self):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO auth_cookie (cookie, name, ipnr) "
                       "VALUES ('123', 'john', '127.0.0.1')")
        incookie = Cookie()
        incookie['trac_auth'] = '123'
        req = Mock(incookie=incookie, outcookie=Cookie(),
                   href=Href('/trac.cgi'), base_path='/trac.cgi',
                   remote_addr='127.0.0.1', remote_user='john', authname='john')
        self.module._do_login(req) # this shouldn't raise an error

    def test_already_logged_in_different_user(self):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO auth_cookie (cookie, name, ipnr) "
                       "VALUES ('123', 'john', '127.0.0.1')")
        incookie = Cookie()
        incookie['trac_auth'] = '123'
        req = Mock(incookie=incookie, authname='john',
                   href=Href('/trac.cgi'), base_path='/trac.cgi',
                   remote_addr='127.0.0.1', remote_user='tom')
        self.assertRaises(AssertionError, self.module._do_login, req)

    def test_logout(self):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO auth_cookie (cookie, name, ipnr) "
                       "VALUES ('123', 'john', '127.0.0.1')")
        incookie = Cookie()
        incookie['trac_auth'] = '123'
        outcookie = Cookie()
        req = Mock(cgi_location='/trac', href=Href('/trac.cgi'),
                   incookie=incookie, outcookie=outcookie, 
                   remote_addr='127.0.0.1', remote_user=None, authname='john',
                   base_path='/trac.cgi')
        self.module._do_logout(req)
        self.failIf('trac_auth' not in outcookie)
        cursor.execute("SELECT name,ipnr FROM auth_cookie WHERE name='john'")
        self.failIf(cursor.fetchone())

    def test_logout_not_logged_in(self):
        req = Mock(cgi_location='/trac', href=Href('/trac.cgi'),
                   incookie=Cookie(), outcookie=Cookie(),
                   remote_addr='127.0.0.1', remote_user=None,
                   authname='anonymous', base_path='/trac.cgi')
        self.module._do_logout(req) # this shouldn't raise an error


def suite():
    return unittest.makeSuite(LoginModuleTestCase, 'test')

if __name__ == '__main__':
    unittest.main()
