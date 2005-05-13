from trac.log import logger_factory
from trac.test import Mock
from trac.util import TracError
from trac.web.href import Href
from trac.web.session import Session, PURGE_AGE, UPDATE_INTERVAL

from Cookie import SimpleCookie as Cookie
import time
import unittest


class SessionTestCase(unittest.TestCase):
    """
    Unit tests for the persistent session support.
    """

    def setUp(self):
        from trac.test import InMemoryDatabase
        self.db = InMemoryDatabase()
        self.env = Mock(href=Href('/'), log=logger_factory('test'))

    def test_newsession(self):
        """
        Verify that a session cookie gets sent back to the client for a new
        session.
        """
        cookie = Cookie()
        req = Mock(incookie=Cookie(), outcookie=cookie, authname='anonymous',
                   cgi_location='/')
        session = Session(self.env, self.db, req, newsession=1)
        self.assertEqual(session.sid, cookie['trac_session'].value)
        cursor = self.db.cursor()
        cursor.execute("SELECT COUNT(*) FROM session")
        self.assertEqual(0, cursor.fetchone()[0])

    def test_anonymous_session(self):
        """
        Verify that session variables are stored in the database.
        """
        incookie = Cookie()
        incookie['trac_session'] = '123456'
        outcookie = Cookie()
        req = Mock(authname='anonymous', cgi_location='/', incookie=incookie,
                   outcookie=outcookie)
        session = Session(self.env, self.db, req)
        self.assertEquals('123456', session.sid)
        self.failIf(outcookie.has_key('trac_session'))

    def test_authenticated_session(self):
        """
        Verifies that a session cookie does not get used if the user is logged
        in, and that Trac expires the cookie.
        """
        incookie = Cookie()
        incookie['trac_session'] = '123456'
        outcookie = Cookie()
        req = Mock(authname='john', cgi_location='/', incookie=incookie,
                   outcookie=outcookie)
        session = Session(self.env, self.db, req)
        self.assertEqual('john', session.sid)
        session['foo'] = 'bar'
        session.save()
        self.assertEquals(0, outcookie['trac_session']['expires'])

    def test_session_promotion(self):
        """
        Verifies that an existing anonymous session gets promoted to an
        authenticated session when the user logs in.
        """
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO session VALUES ('123456', 0, 'foo', 'bar')")

        incookie = Cookie()
        incookie['trac_session'] = '123456'
        outcookie = Cookie()
        req = Mock(authname='john', cgi_location='/', incookie=incookie,
                   outcookie=outcookie)
        session = Session(self.env, self.db, req)
        self.assertEqual('john', session.sid)
        session.save()

        cursor.execute("SELECT sid,authenticated FROM session")
        row = cursor.fetchone()
        self.assertEqual(('john', 1), row)
        self.assertEqual(None, cursor.fetchone())

    def test_add_anonymous_session_var(self):
        """
        Verify that new variables are inserted into the 'session' table in the
        database for an anonymous session.
        """
        incookie = Cookie()
        incookie['trac_session'] = '123456'
        req = Mock(authname='anonymous', cgi_location='/', incookie=incookie,
                   outcookie=Cookie())
        session = Session(self.env, self.db, req)
        session['foo'] = 'bar'
        session.save()
        cursor = self.db.cursor()
        cursor.execute("SELECT var_value FROM session WHERE sid='123456' AND "
                       "authenticated=0 AND var_name='foo'") 
        self.assertEqual('bar', cursor.fetchone()[0])

    def test_modify_anonymous_session_var(self):
        """
        Verify that modifying an existing variable updates the 'session' table
        accordingly for an anonymous session.
        """
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO session VALUES ('123456', 0, 'foo', 'bar')")

        incookie = Cookie()
        incookie['trac_session'] = '123456'
        req = Mock(authname='anonymous', cgi_location='/', incookie=incookie,
                   outcookie=Cookie())
        session = Session(self.env, self.db, req)
        self.assertEqual('bar', session['foo'])
        session['foo'] = 'baz'
        session.save()
        cursor.execute("SELECT var_value FROM session WHERE sid='123456' AND "
                       "authenticated=0 AND var_name='foo'") 
        self.assertEqual('baz', cursor.fetchone()[0])

    def test_delete_anonymous_session_var(self):
        """
        Verify that modifying a variable updates the 'session' table accordingly
        for an anonymous session.
        """
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO session VALUES ('123456', 0, 'foo', 'bar')")

        incookie = Cookie()
        incookie['trac_session'] = '123456'
        req = Mock(authname='anonymous', cgi_location='/', incookie=incookie,
                   outcookie=Cookie())
        session = Session(self.env, self.db, req)
        self.assertEqual('bar', session['foo'])
        del session['foo']
        session.save()
        cursor.execute("SELECT COUNT(*) FROM session WHERE sid='123456' AND "
                       "authenticated=0 AND var_name='foo'") 
        self.assertEqual(0, cursor.fetchone()[0])

    def test_purge_anonymous_session(self):
        """
        Verify that old sessions get purged.
        """
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO session "
                       "VALUES ('987654', 0, 'last_visit', %s)",
                       (time.time() - PURGE_AGE - 3600))
        
        # We need to modify a different session to trigger the purging
        incookie = Cookie()
        incookie['trac_session'] = '123456'
        req = Mock(authname='anonymous', cgi_location='/', incookie=incookie,
                   outcookie=Cookie())
        session = Session(self.env, self.db, req)
        session['foo'] = 'bar'
        session.save()

        cursor.execute("SELECT COUNT(*) FROM session WHERE sid='987654' AND "
                       "authenticated=0")
        self.assertEqual(0, cursor.fetchone()[0])

    def test_delete_empty_session(self):
        """
        Verify that a session gets deleted when it doesn't have any data except
        for the 'last_visit' timestamp.
        """
        now = time.time()

        # Make sure the session has data so that it doesn't get dropped
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO session "
                       "VALUES ('123456', 0, 'last_visit', %s)",
                       (int(now - UPDATE_INTERVAL - 3600)))

        incookie = Cookie()
        incookie['trac_session'] = '123456'
        req = Mock(authname='anonymous', cgi_location='/', incookie=incookie,
                   outcookie=Cookie())
        session = Session(self.env, self.db, req)
        session.save()

        cursor.execute("SELECT COUNT(*) FROM session WHERE sid='123456' AND "
                       "authenticated=0")
        self.assertEqual(0, cursor.fetchone()[0])

    def test_add_authenticated_session_var(self):
        """
        Verify that new variables are inserted into the 'session' table in the
        database for an authenticted session.
        """
        req = Mock(authname='john', cgi_location='/', incookie=Cookie())
        session = Session(self.env, self.db, req)
        session['foo'] = 'bar'
        session.save()
        cursor = self.db.cursor()
        cursor.execute("SELECT var_value FROM session WHERE sid='john' AND "
                       "authenticated=1 AND var_name='foo'") 
        self.assertEqual('bar', cursor.fetchone()[0])

    def test_modify_authenticated_session_var(self):
        """
        Verify that modifying an existing variable updates the 'session' table
        accordingly for an authenticated session.
        """
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO session VALUES ('john', 1, 'foo', 'bar')")

        req = Mock(authname='john', cgi_location='/', incookie=Cookie())
        session = Session(self.env, self.db, req)
        self.assertEqual('bar', session['foo'])
        session['foo'] = 'baz'
        session.save()
        cursor.execute("SELECT var_value FROM session WHERE sid='john' AND "
                       "authenticated=1 AND var_name='foo'") 
        self.assertEqual('baz', cursor.fetchone()[0])

    def test_delete_authenticated_session_var(self):
        """
        Verify that modifying a variable updates the 'session' table accordingly
        for an authenticated session.
        """
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO session VALUES ('john', 1, 'foo', 'bar')")

        req = Mock(authname='john', cgi_location='/', incookie=Cookie())
        session = Session(self.env, self.db, req)
        self.assertEqual('bar', session['foo'])
        del session['foo']
        session.save()
        cursor.execute("SELECT COUNT(*) FROM session WHERE sid='john' AND "
                       "authenticated=1 AND var_name='foo'") 
        self.assertEqual(0, cursor.fetchone()[0])

    def test_update_session(self):
        """
        Verify that accessing a session after one day updates the sessions 
        'last_visit' variable so that the session doesn't get purged.
        """
        now = time.time()

        # Make sure the session has data so that it doesn't get dropped
        cursor = self.db.cursor()
        cursor.executemany("INSERT INTO session VALUES ('123456', 0, %s, %s)",
                           [('last_visit', int(now - UPDATE_INTERVAL - 3600)),
                            ('foo', 'bar')])

        incookie = Cookie()
        incookie['trac_session'] = '123456'
        outcookie = Cookie()
        req = Mock(authname='anonymous', cgi_location='/', incookie=incookie,
                   outcookie=outcookie)
        session = Session(self.env, self.db, req)
        session.save() # updating should not require modifications

        self.assertEqual(PURGE_AGE, outcookie['trac_session']['expires'])

        cursor.execute("SELECT var_value FROM session WHERE sid='123456' AND "
                       "authenticated=0 AND var_name='last_visit'")
        self.assertAlmostEqual(now, int(cursor.fetchone()[0]), -1)


def suite():
    return unittest.makeSuite(SessionTestCase, 'test')

if __name__ == '__main__':
    unittest.main()
