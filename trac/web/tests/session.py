from __future__ import with_statement

from Cookie import SimpleCookie as Cookie
import time
from datetime import datetime
import unittest

from trac.test import EnvironmentStub, Mock
from trac.web.session import DetachedSession, Session, PURGE_AGE, \
                             UPDATE_INTERVAL, SessionAdmin
from trac.core import TracError


def _prep_session_table(env, spread_visits=False):
    """ Populate the session table with known values.

    :return: a tuple of lists `(auth_list, anon_list, all_list)`
    :since 1.0: changed `db` input parameter to `env`
    """
    with env.db_transaction as db:
        db("DELETE FROM session")
        db("DELETE FROM session_attribute")
    last_visit_base = time.mktime(datetime(2010, 1, 1).timetuple())
    visit_delta = 86400 if spread_visits else 0
    auth_list, anon_list = [], []
    with env.db_transaction as db:
        for x in xrange(20):
            sid = 'name%02d' % x
            authenticated = int(x < 10)
            last_visit = last_visit_base + (visit_delta * x)
            val = 'val%02d' % x
            data = (sid, authenticated, last_visit, val, val)
            if authenticated:
                auth_list.append(data)
            else:
                anon_list.append(data)
            db("INSERT INTO session VALUES (%s, %s, %s)",
               (sid, authenticated, last_visit))
            db("INSERT INTO session_attribute VALUES (%s, %s, 'name', %s)",
               (sid, authenticated, val))
            db("INSERT INTO session_attribute VALUES (%s, %s, 'email', %s)",
               (sid, authenticated, val))
    all_list = auth_list + anon_list
    return (auth_list, anon_list, all_list)

def get_session_info(env, sid):
    """:since 1.0: changed `db` input parameter to `env`"""
    for row in env.db_query("""
            SELECT DISTINCT s.sid, n.value, e.value FROM session AS s
            LEFT JOIN session_attribute AS n ON (n.sid=s.sid AND n.name='name')
            LEFT JOIN session_attribute AS e ON (e.sid=s.sid AND e.name='email')
            WHERE s.sid=%s
            """, (sid,)):
        return row
    else:
        return (None, None, None)


class SessionTestCase(unittest.TestCase):
    """Unit tests for the persistent session support."""

    def setUp(self):
        self.env = EnvironmentStub()

    def tearDown(self):
        self.env.reset_db()

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
        self.assertEqual(0, self.env.db_query(
                "SELECT COUNT(*) FROM session")[0][0])

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
        with self.env.db_transaction as db:
            db("INSERT INTO session VALUES ('123456', 0, 0)")
            incookie = Cookie()
            incookie['trac_session'] = '123456'
            outcookie = Cookie()
            req = Mock(authname='john', base_path='/', incookie=incookie,
                       outcookie=outcookie)
            session = Session(self.env, req)
            self.assertEqual('john', session.sid)
            session.save()

        self.assertEqual([('john', 1)], self.env.db_query(
            "SELECT sid, authenticated FROM session"))

    def test_new_session_promotion(self):
        """
        Verifies that even without a preexisting anonymous session,
        an authenticated session will be created when the user logs in.
        (same test as above without the initial INSERT)
        """
        with self.env.db_transaction as db:
            incookie = Cookie()
            incookie['trac_session'] = '123456'
            outcookie = Cookie()
            req = Mock(authname='john', base_path='/', incookie=incookie,
                       outcookie=outcookie)
            session = Session(self.env, req)
            self.assertEqual('john', session.sid)
            session.save()

        self.assertEqual([('john', 1)], self.env.db_query(
                "SELECT sid, authenticated FROM session"))

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

        self.assertEqual('bar', self.env.db_query(
                "SELECT value FROM session_attribute WHERE sid='123456'")[0][0])

    def test_modify_anonymous_session_var(self):
        """
        Verify that modifying an existing variable updates the 'session' table
        accordingly for an anonymous session.
        """
        with self.env.db_transaction as db:
            db("INSERT INTO session VALUES ('123456', 0, 0)")
            db("""
                INSERT INTO session_attribute VALUES
                ('123456', 0, 'foo', 'bar')
                """)
            incookie = Cookie()
            incookie['trac_session'] = '123456'
            req = Mock(authname='anonymous', base_path='/', incookie=incookie,
                       outcookie=Cookie())
            session = Session(self.env, req)
            self.assertEqual('bar', session['foo'])
            session['foo'] = 'baz'
            session.save()

        self.assertEqual('baz', self.env.db_query(
                "SELECT value FROM session_attribute WHERE sid='123456'")[0][0])

    def test_delete_anonymous_session_var(self):
        """
        Verify that modifying a variable updates the 'session' table accordingly
        for an anonymous session.
        """
        with self.env.db_transaction as db:
            db("INSERT INTO session VALUES ('123456', 0, 0)")
            db("""
                INSERT INTO session_attribute VALUES
                ('123456', 0, 'foo', 'bar')
                """)
            incookie = Cookie()
            incookie['trac_session'] = '123456'
            req = Mock(authname='anonymous', base_path='/', incookie=incookie,
                       outcookie=Cookie())
            session = Session(self.env, req)
            self.assertEqual('bar', session['foo'])
            del session['foo']
            session.save()

        self.assertEqual(0, self.env.db_query("""
            SELECT COUNT(*) FROM session_attribute
            WHERE sid='123456' AND name='foo'
            """)[0][0])

    def test_purge_anonymous_session(self):
        """
        Verify that old sessions get purged.
        """
        with self.env.db_transaction as db:
            db("INSERT INTO session VALUES ('123456', 0, %s)", (0,))
            db("INSERT INTO session VALUES ('987654', 0, %s)",
               (int(time.time() - PURGE_AGE - 3600),))
            db("""
                INSERT INTO session_attribute
                VALUES ('987654', 0, 'foo', 'bar')
                """)

            # We need to modify a different session to trigger the purging
            incookie = Cookie()
            incookie['trac_session'] = '123456'
            req = Mock(authname='anonymous', base_path='/', incookie=incookie,
                       outcookie=Cookie())
            session = Session(self.env, req)
            session['foo'] = 'bar'
            session.save()

        self.assertEqual(0, self.env.db_query("""
            SELECT COUNT(*) FROM session WHERE sid='987654' AND authenticated=0
            """)[0][0])

    def test_delete_empty_session(self):
        """
        Verify that a session gets deleted when it doesn't have any data except
        for the 'last_visit' timestamp.
        """
        now = time.time()

        # Make sure the session has data so that it doesn't get dropped
        with self.env.db_transaction as db:
            db("INSERT INTO session VALUES ('123456', 0, %s)",
               (int(now - UPDATE_INTERVAL - 3600),))
            db("""
                INSERT INTO session_attribute
                VALUES ('123456', 0, 'foo', 'bar')
                """)

            incookie = Cookie()
            incookie['trac_session'] = '123456'
            req = Mock(authname='anonymous', base_path='/', incookie=incookie,
                       outcookie=Cookie())
            session = Session(self.env, req)
            del session['foo']
            session.save()

        self.assertEqual(0, self.env.db_query("""
            SELECT COUNT(*) FROM session WHERE sid='123456' AND authenticated=0
            """)[0][0])

    def test_change_anonymous_session(self):
        """
        Verify that changing from one anonymous session to an inexisting
        anonymous session creates the new session and doesn't carry over
        variables from the previous session.
        """

        with self.env.db_transaction as db:
            db("INSERT INTO session VALUES ('123456', 0, 0)")
            db("""
                INSERT INTO session_attribute
                VALUES ('123456', 0, 'foo', 'bar')
                """)

        incookie = Cookie()
        incookie['trac_session'] = '123456'
        req = Mock(authname='anonymous', base_path='/', incookie=incookie,
                   outcookie=Cookie())
        session = Session(self.env, req)
        self.assertEqual({'foo': 'bar'}, session)

        session.get_session('7890')
        session['baz'] = 'moo'
        session.save()
        self.assertEqual({'baz': 'moo'}, session)

        with self.env.db_query as db:
            self.assertEqual(1, db("""
                SELECT COUNT(*) FROM session
                WHERE sid='7890' AND authenticated=0
                """)[0][0])
            self.assertEqual([('baz', 'moo')], db("""
                SELECT name, value FROM session_attribute
                WHERE sid='7890' AND authenticated=0
                """))

    def test_add_authenticated_session_var(self):
        """
        Verify that new variables are inserted into the 'session' table in the
        database for an authenticated session.
        """
        req = Mock(authname='john', base_path='/', incookie=Cookie())
        session = Session(self.env, req)
        session['foo'] = 'bar'
        session.save()

        self.assertEqual('bar', self.env.db_query("""
            SELECT value FROM session_attribute WHERE sid='john' AND name='foo'
            """)[0][0])

    def test_modify_authenticated_session_var(self):
        """
        Verify that modifying an existing variable updates the 'session' table
        accordingly for an authenticated session.
        """
        with self.env.db_transaction as db:
            db("INSERT INTO session VALUES ('john', 1, 0)")
            db("INSERT INTO session_attribute VALUES ('john',1,'foo','bar')")

            req = Mock(authname='john', base_path='/', incookie=Cookie())
            session = Session(self.env, req)
            self.assertEqual('bar', session['foo'])
            session['foo'] = 'baz'
            session.save()

        self.assertEqual('baz', self.env.db_query("""
            SELECT value FROM session_attribute WHERE sid='john' AND name='foo'
            """)[0][0])

    def test_authenticated_session_independence_var(self):
        """
        Verify that an anonymous session with the same name as an authenticated
        session doesn't interfere with the latter.
        """
        with self.env.db_transaction as db:
            db("INSERT INTO session VALUES ('john', 1, 0)")
            db("INSERT INTO session_attribute VALUES ('john',1,'foo','bar')")

        self.assertEqual('bar', self.env.db_query("""
            SELECT value FROM session_attribute
            WHERE sid='john' AND authenticated=1 AND name='foo'
            """)[0][0])

        incookie = Cookie()
        incookie['trac_session'] = 'john'
        req = Mock(authname='anonymous', base_path='/', incookie=incookie,
                   outcookie=Cookie())
        session = Session(self.env, req)
        self.assert_('foo' not in session)
        session['foo'] = 'baz'
        session.save()

        rows = self.env.db_query("""
            SELECT value FROM session_attribute
            WHERE sid='john' AND authenticated=1 AND name='foo'
            """)
        self.assertEqual(1, len(rows))
        self.assertEqual('bar', rows[0][0])
        rows = self.env.db_query("""
            SELECT value FROM session_attribute
            WHERE sid='john' AND authenticated=0 AND name='foo'
            """)
        self.assertEqual(1, len(rows))
        self.assertEqual('baz', rows[0][0])

    def test_delete_authenticated_session_var(self):
        """
        Verify that deleting a variable updates the 'session' table accordingly
        for an authenticated session.
        """
        with self.env.db_transaction as db:
            db("INSERT INTO session VALUES ('john', 1, 0)")
            db("INSERT INTO session_attribute VALUES ('john', 1, 'foo', 'bar')")

            req = Mock(authname='john', base_path='/', incookie=Cookie())
            session = Session(self.env, req)
            self.assertEqual('bar', session['foo'])
            del session['foo']
            session.save()

        self.assertEqual(0, self.env.db_query("""
            SELECT COUNT(*) FROM session_attribute
            WHERE sid='john' AND name='foo'
            """)[0][0])

    def test_update_session(self):
        """
        Verify that accessing a session after one day updates the sessions
        'last_visit' variable so that the session doesn't get purged.
        """
        now = time.time()

        # Make sure the session has data so that it doesn't get dropped
        with self.env.db_transaction as db:
            db("INSERT INTO session VALUES ('123456', 0, 1)")
            db("""
                INSERT INTO session_attribute
                VALUES ('123456', 0, 'foo', 'bar')
                """)

            incookie = Cookie()
            incookie['trac_session'] = '123456'
            outcookie = Cookie()
            req = Mock(authname='anonymous', base_path='/', incookie=incookie,
                       outcookie=outcookie)
            session = Session(self.env, req)
            session['modified'] = True
            session.save() # updating does require modifications

            self.assertEqual(PURGE_AGE, outcookie['trac_session']['expires'])

        self.assertAlmostEqual(now, int(self.env.db_query("""
            SELECT last_visit FROM session
            WHERE sid='123456' AND authenticated=0
            """)[0][0]), -1)

    def test_modify_detached_session(self):
        """
        Verify that modifying a variable in a session not associated with a
        request updates the database accordingly.
        """
        with self.env.db_transaction as db:
            db("INSERT INTO session VALUES ('john', 1, 0)")
            db("INSERT INTO session_attribute VALUES ('john', 1, 'foo', 'bar')")

            session = DetachedSession(self.env, 'john')
            self.assertEqual('bar', session['foo'])
            session['foo'] = 'baz'
            session.save()

        self.assertEqual('baz', self.env.db_query("""
            SELECT value FROM session_attribute WHERE sid='john' AND name='foo'
            """)[0][0])

    def test_delete_detached_session_var(self):
        """
        Verify that removing a variable in a session not associated with a
        request deletes the variable from the database.
        """
        with self.env.db_transaction as db:
            db("INSERT INTO session VALUES ('john', 1, 0)")
            db("INSERT INTO session_attribute VALUES ('john', 1, 'foo', 'bar')")

            session = DetachedSession(self.env, 'john')
            self.assertEqual('bar', session['foo'])
            del session['foo']
            session.save()

        self.assertEqual(0, self.env.db_query("""
            SELECT COUNT(*) FROM session_attribute
            WHERE sid='john' AND name='foo'
            """)[0][0])

    def test_session_set(self):
        """Verify that setting a variable in a session to the default value
        removes it from the session.
        """
        with self.env.db_transaction as db:
            db("INSERT INTO session VALUES ('john', 1, 0)")
            db("INSERT INTO session_attribute VALUES ('john', 1, 'foo', 'bar')")

        session = DetachedSession(self.env, 'john')
        self.assertEqual('bar', session['foo'])

        # Setting the variable to the default value removes the variable
        with self.env.db_transaction as db:
            session.set('foo', 'default', 'default')
            session.save()
        self.assertEqual(0, self.env.db_query("""
            SELECT COUNT(*) FROM session_attribute
            WHERE sid='john' AND name='foo'
            """)[0][0])

        # Setting the variable to a value different from the default sets it
        with self.env.db_transaction as db:
            session.set('foo', 'something', 'default')
            session.save()
        self.assertEqual('something', self.env.db_query("""
            SELECT value FROM session_attribute
            WHERE sid='john' AND name='foo'
            """)[0][0])

    def test_session_admin_list(self):
        auth_list, anon_list, all_list = _prep_session_table(self.env)
        sess_admin = SessionAdmin(self.env)

        # Verify the empty case
        self.assertRaises(StopIteration, sess_admin._get_list([]).next)

        self.assertEqual([i for i in sess_admin._get_list(['authenticated'])],
                         auth_list)
        self.assertEqual([i for i in sess_admin._get_list(['anonymous'])],
                         anon_list)
        self.assertEqual([i for i in sess_admin._get_list(['*'])], all_list)
        self.assertEqual([i for i in sess_admin._get_list(['name00'])][0],
                         auth_list[0])
        self.assertEqual([i for i in sess_admin._get_list(['name10:0'])][0],
                         anon_list[0])
        self.assertEqual([i for i in sess_admin._get_list(['name00', 'name01',
                                                           'name02'])],
                         all_list[:3])

    def test_session_admin_add(self):
        auth_list, anon_list, all_list = _prep_session_table(self.env)
        sess_admin = SessionAdmin(self.env)
        self.assertRaises(Exception, sess_admin._do_add, 'name00')
        sess_admin._do_add('john')
        result = get_session_info(self.env, 'john')
        self.assertEqual(result, ('john', None, None))
        sess_admin._do_add('john1', 'John1')
        result = get_session_info(self.env, 'john1')
        self.assertEqual(result, ('john1', 'John1', None))
        sess_admin._do_add('john2', 'John2', 'john2@example.org')
        result = get_session_info(self.env, 'john2')
        self.assertEqual(result, ('john2', 'John2', 'john2@example.org'))

    def test_session_admin_set(self):
        auth_list, anon_list, all_list = _prep_session_table(self.env)
        sess_admin = SessionAdmin(self.env)
        self.assertRaises(TracError, sess_admin._do_set, 'name', 'nothere',
                          'foo')
        sess_admin._do_set('name', 'name00', 'john')
        result = get_session_info(self.env, 'name00')
        self.assertEqual(result, ('name00', 'john', 'val00'))
        sess_admin._do_set('email', 'name00', 'john@example.org')
        result = get_session_info(self.env, 'name00')
        self.assertEqual(result, ('name00', 'john', 'john@example.org'))

    def test_session_admin_delete(self):
        auth_list, anon_list, all_list = _prep_session_table(self.env)
        sess_admin = SessionAdmin(self.env)
        sess_admin._do_delete('name00')
        result = get_session_info(self.env, 'name00')
        self.assertEqual(result, (None, None, None))
        sess_admin._do_delete('nothere')
        result = get_session_info(self.env, 'nothere')
        self.assertEqual(result, (None, None, None))
        auth_list, anon_list, all_list = _prep_session_table(self.env)
        sess_admin._do_delete('anonymous')
        result = [i for i in sess_admin._get_list(['*'])]
        self.assertEqual(result, auth_list)

    def test_session_admin_purge(self):
        sess_admin = SessionAdmin(self.env)

        auth_list, anon_list, all_list = \
            _prep_session_table(self.env, spread_visits=True)
        sess_admin._do_purge('2010-01-02')
        result = [i for i in sess_admin._get_list(['*'])]
        self.assertEqual(result, auth_list + anon_list)
        result = get_session_info(self.env, anon_list[0][0])
        self.assertEqual(result, ('name10', 'val10', 'val10'))
        result = get_session_info(self.env, anon_list[1][0])
        self.assertEqual(result, ('name11', 'val11', 'val11'))

        auth_list, anon_list, all_list = \
            _prep_session_table(self.env, spread_visits=True)
        sess_admin._do_purge('2010-01-12')
        result = [i for i in sess_admin._get_list(['*'])]
        self.assertEqual(result, auth_list + anon_list[1:])
        rows = self.env.db_query("""
            SELECT name, value FROM session_attribute WHERE sid = %s
            """, (anon_list[0][0],))
        self.assertEqual([], rows)
        result = get_session_info(self.env, anon_list[1][0])
        self.assertEqual(result, ('name11', 'val11', 'val11'))


def suite():
    return unittest.makeSuite(SessionTestCase, 'test')


if __name__ == '__main__':
    unittest.main()
