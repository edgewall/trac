from Cookie import SimpleCookie as Cookie
import time
import unittest

from trac.core import TracError
from trac.log import logger_factory
from trac.test import EnvironmentStub, Mock
from trac.web.href import Href
from trac.web.session import DetachedSession, Session, PURGE_AGE, UPDATE_INTERVAL


class SessionTestCase(unittest.TestCase):
    """Unit tests for the persistent session support."""

    def setUp(self):
        self.env = EnvironmentStub()
        self.db = self.env.get_db_cnx()

    def test_new_session(self):
        """
        Verify that a session cookie gets sent back to the client for a new
        session.
        """
        cookie = Cookie()
        req = Mock(incookie=Cookie(), outcookie=cookie, authname='anonymous',
                   base_path='/')
        session = Session(self.env, req)
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
        req = Mock(authname='anonymous', base_path='/', incookie=incookie,
                   outcookie=outcookie)
        session = Session(self.env, req)
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
        req = Mock(authname='john', base_path='/', incookie=incookie,
                   outcookie=outcookie)
        session = Session(self.env, req)
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
        cursor.execute("INSERT INTO session VALUES ('123456', 0, 0)")
        incookie = Cookie()
        incookie['trac_session'] = '123456'
        outcookie = Cookie()
        req = Mock(authname='john', base_path='/', incookie=incookie,
                   outcookie=outcookie)
        session = Session(self.env, req)
        self.assertEqual('john', session.sid)
        session.save()

        cursor.execute("SELECT sid,authenticated FROM session")
        self.assertEqual(('john', 1), cursor.fetchone())
        self.assertEqual(None, cursor.fetchone())

    def test_new_session_promotion(self):
        """
        Verifies that even without a preexisting anonymous session,
        an authenticated session will be created when the user logs in.
        (same test as above without the initial INSERT)
        """
        cursor = self.db.cursor()
        incookie = Cookie()
        incookie['trac_session'] = '123456'
        outcookie = Cookie()
        req = Mock(authname='john', base_path='/', incookie=incookie,
                   outcookie=outcookie)
        session = Session(self.env, req)
        self.assertEqual('john', session.sid)
        session.save()

        cursor.execute("SELECT sid,authenticated FROM session")
        self.assertEqual(('john', 1), cursor.fetchone())
        self.assertEqual(None, cursor.fetchone())

    def test_add_anonymous_session_var(self):
        """
        Verify that new variables are inserted into the 'session' table in the
        database for an anonymous session.
        """
        incookie = Cookie()
        incookie['trac_session'] = '123456'
        req = Mock(authname='anonymous', base_path='/', incookie=incookie,
                   outcookie=Cookie())
        session = Session(self.env, req)
        session['foo'] = 'bar'
        session.save()
        cursor = self.db.cursor()
        cursor.execute("SELECT value FROM session_attribute WHERE sid='123456'")
        self.assertEqual('bar', cursor.fetchone()[0])

    def test_modify_anonymous_session_var(self):
        """
        Verify that modifying an existing variable updates the 'session' table
        accordingly for an anonymous session.
        """
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO session VALUES ('123456', 0, 0)")
        cursor.execute("INSERT INTO session_attribute VALUES "
                       "('123456', 0, 'foo', 'bar')")
        incookie = Cookie()
        incookie['trac_session'] = '123456'
        req = Mock(authname='anonymous', base_path='/', incookie=incookie,
                   outcookie=Cookie())
        session = Session(self.env, req)
        self.assertEqual('bar', session['foo'])
        session['foo'] = 'baz'
        session.save()
        cursor.execute("SELECT value FROM session_attribute WHERE sid='123456'")
        self.assertEqual('baz', cursor.fetchone()[0])

    def test_delete_anonymous_session_var(self):
        """
        Verify that modifying a variable updates the 'session' table accordingly
        for an anonymous session.
        """
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO session VALUES ('123456', 0, 0)")
        cursor.execute("INSERT INTO session_attribute VALUES "
                       "('123456', 0, 'foo', 'bar')")
        incookie = Cookie()
        incookie['trac_session'] = '123456'
        req = Mock(authname='anonymous', base_path='/', incookie=incookie,
                   outcookie=Cookie())
        session = Session(self.env, req)
        self.assertEqual('bar', session['foo'])
        del session['foo']
        session.save()
        cursor.execute("SELECT COUNT(*) FROM session_attribute "
                       "WHERE sid='123456' AND name='foo'") 
        self.assertEqual(0, cursor.fetchone()[0])

    def test_purge_anonymous_session(self):
        """
        Verify that old sessions get purged.
        """
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO session "
                       "VALUES ('123456', 0, %s)",
                       (0,))
        cursor.execute("INSERT INTO session "
                       "VALUES ('987654', 0, %s)",
                       (time.time() - PURGE_AGE - 3600,))
        cursor.execute("INSERT INTO session_attribute VALUES "
                       "('987654', 0, 'foo', 'bar')")
        
        # We need to modify a different session to trigger the purging
        incookie = Cookie()
        incookie['trac_session'] = '123456'
        req = Mock(authname='anonymous', base_path='/', incookie=incookie,
                   outcookie=Cookie())
        session = Session(self.env, req)
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
                       "VALUES ('123456', 0, %s)",
                       (int(now - UPDATE_INTERVAL - 3600),))
        cursor.execute("INSERT INTO session_attribute VALUES "
                       "('123456', 0, 'foo', 'bar')")

        incookie = Cookie()
        incookie['trac_session'] = '123456'
        req = Mock(authname='anonymous', base_path='/', incookie=incookie,
                   outcookie=Cookie())
        session = Session(self.env, req)
        del session['foo']
        session.save()

        cursor.execute("SELECT COUNT(*) FROM session WHERE sid='123456' AND "
                       "authenticated=0")
        self.assertEqual(0, cursor.fetchone()[0])

    def test_add_authenticated_session_var(self):
        """
        Verify that new variables are inserted into the 'session' table in the
        database for an authenticated session.
        """
        req = Mock(authname='john', base_path='/', incookie=Cookie())
        session = Session(self.env, req)
        session['foo'] = 'bar'
        session.save()
        cursor = self.db.cursor()
        cursor.execute("SELECT value FROM session_attribute WHERE sid='john'"
                       "AND name='foo'") 
        self.assertEqual('bar', cursor.fetchone()[0])

    def test_modify_authenticated_session_var(self):
        """
        Verify that modifying an existing variable updates the 'session' table
        accordingly for an authenticated session.
        """
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO session VALUES ('john', 1, 0)")
        cursor.execute("INSERT INTO session_attribute VALUES "
                       "('john', 1, 'foo', 'bar')")

        req = Mock(authname='john', base_path='/', incookie=Cookie())
        session = Session(self.env, req)
        self.assertEqual('bar', session['foo'])
        session['foo'] = 'baz'
        session.save()
        cursor.execute("SELECT value FROM session_attribute "
                       "WHERE sid='john' AND name='foo'") 
        self.assertEqual('baz', cursor.fetchone()[0])

    def test_delete_authenticated_session_var(self):
        """
        Verify that modifying a variable updates the 'session' table accordingly
        for an authenticated session.
        """
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO session VALUES ('john', 1, 0)")
        cursor.execute("INSERT INTO session_attribute VALUES "
                       "('john', 1, 'foo', 'bar')")

        req = Mock(authname='john', base_path='/', incookie=Cookie())
        session = Session(self.env, req)
        self.assertEqual('bar', session['foo'])
        del session['foo']
        session.save()
        cursor.execute("SELECT COUNT(*) FROM session_attribute "
                       "WHERE sid='john' AND name='foo'") 
        self.assertEqual(0, cursor.fetchone()[0])

    def test_update_session(self):
        """
        Verify that accessing a session after one day updates the sessions 
        'last_visit' variable so that the session doesn't get purged.
        """
        now = time.time()

        # Make sure the session has data so that it doesn't get dropped
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO session VALUES ('123456', 0, 1)")
        cursor.execute("INSERT INTO session_attribute VALUES "
                       "('123456', 0, 'foo', 'bar')")

        incookie = Cookie()
        incookie['trac_session'] = '123456'
        outcookie = Cookie()
        req = Mock(authname='anonymous', base_path='/', incookie=incookie,
                   outcookie=outcookie)
        session = Session(self.env, req)
        session.save() # updating should not require modifications

        self.assertEqual(PURGE_AGE, outcookie['trac_session']['expires'])

        cursor.execute("SELECT last_visit FROM session WHERE sid='123456' AND "
                       "authenticated=0")
        self.assertAlmostEqual(now, int(cursor.fetchone()[0]), -1)

    def test_modify_detached_session(self):
        """
        Verify that a modifying a variable in a session not associated with a
        request updates the database accordingly.
        """
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO session VALUES ('john', 1, 0)")
        cursor.execute("INSERT INTO session_attribute VALUES "
                       "('john', 1, 'foo', 'bar')")

        session = DetachedSession(self.env, 'john')
        self.assertEqual('bar', session['foo'])
        session['foo'] = 'baz'
        session.save()
        cursor.execute("SELECT value FROM session_attribute "
                       "WHERE sid='john' AND name='foo'")
        self.assertEqual('baz', cursor.fetchone()[0])

    def test_delete_detached_session_var(self):
        """
        Verify that removing a variable in a session not associated with a
        request deletes the variable from the database.
        """
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO session VALUES ('john', 1, 0)")
        cursor.execute("INSERT INTO session_attribute VALUES "
                       "('john', 1, 'foo', 'bar')")

        session = DetachedSession(self.env, 'john')
        self.assertEqual('bar', session['foo'])
        del session['foo']
        session.save()
        cursor.execute("SELECT COUNT(*) FROM session_attribute "
                       "WHERE sid='john' AND name='foo'")
        self.assertEqual(0, cursor.fetchone()[0])


def suite():
    return unittest.makeSuite(SessionTestCase, 'test')

if __name__ == '__main__':
    unittest.main()
