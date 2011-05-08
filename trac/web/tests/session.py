from Cookie import SimpleCookie as Cookie
import time
from datetime import datetime
import unittest

from trac.test import EnvironmentStub, Mock
from trac.web.session import DetachedSession, Session, PURGE_AGE, \
                             UPDATE_INTERVAL, SessionAdmin
from trac.core import TracError


def _prep_session_table(db, spread_visits=False):
    """ Populate the session table with known values.

    Return a tuple of lists: (auth_list, anon_list, all_list)
    """
    cursor = db.cursor()
    cursor.execute("DELETE FROM session")
    cursor.execute("DELETE FROM session_attribute")
    last_visit_base = time.mktime(datetime(2010, 1, 1).timetuple())
    visit_delta = spread_visits and 86400 or 0
    auth_list, anon_list = [], []
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
        cursor.execute("INSERT INTO session VALUES (%s, %s, %s)",
                       (sid, authenticated, last_visit))
        cursor.execute("INSERT INTO session_attribute VALUES "
                       "(%s, %s, 'name', %s)",
                       (sid, authenticated, val))
        cursor.execute("INSERT INTO session_attribute VALUES "
                       "(%s, %s, 'email', %s)",
                       (sid, authenticated, val))
    all_list = auth_list + anon_list 
    db.commit()
    return (auth_list, anon_list, all_list)


def get_session_info(db, sid):
    cursor = db.cursor()
    cursor.execute("SELECT DISTINCT s.sid, n.value, e.value "
                   "  FROM session AS s "
                   " LEFT JOIN session_attribute AS n ON (n.sid=s.sid "
                   "  AND n.name = 'name') "
                   " LEFT JOIN session_attribute AS e ON (e.sid=s.sid "
                   "  AND e.name = 'email') "
                   "WHERE s.sid = %s", (sid,))
    rows = [r for r in cursor]
    if rows:
        return rows[0]
    else:
        return (None, None, None)


class SessionTestCase(unittest.TestCase):
    """Unit tests for the persistent session support."""

    def setUp(self):
        self.env = EnvironmentStub()
        self.db = self.env.get_db_cnx()

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
                       (int(time.time() - PURGE_AGE - 3600),))
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

    def test_change_anonymous_session(self):
        """
        Verify that changing from one anonymous session to an inexisting
        anonymous session creates the new session and doesn't carry over
        variables from the previous session.
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
        self.assertEqual({'foo': 'bar'}, session)
        
        session.get_session('7890')
        session['baz'] = 'moo'
        session.save()
        self.assertEqual({'baz': 'moo'}, session)

        cursor.execute("SELECT COUNT(*) FROM session WHERE sid='7890' AND "
                       "authenticated=0")
        self.assertEqual(1, cursor.fetchone()[0])
        cursor.execute("SELECT name, value FROM session_attribute "
                       "WHERE sid='7890' AND authenticated=0")
        self.assertEqual([('baz', 'moo')], cursor.fetchall())

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

    def test_authenticated_session_independence_var(self):
        """
        Verify that an anonymous session with the same name as an authenticated
        session doesn't interfere with the latter.
        """
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO session VALUES ('john', 1, 0)")
        cursor.execute("INSERT INTO session_attribute VALUES "
                       "('john', 1, 'foo', 'bar')")

        cursor.execute("SELECT value FROM session_attribute "
                       "WHERE sid='john' AND authenticated=1 AND name='foo'")
        self.assertEqual('bar', cursor.fetchone()[0])

        incookie = Cookie()
        incookie['trac_session'] = 'john'
        req = Mock(authname='anonymous', base_path='/', incookie=incookie,
                   outcookie=Cookie())
        session = Session(self.env, req)
        self.assert_('foo' not in session)
        session['foo'] = 'baz'
        session.save()

        cursor.execute("SELECT value FROM session_attribute "
                       "WHERE sid='john' AND authenticated=1 AND name='foo'")
        rows = cursor.fetchall()
        self.assertEqual(1, len(rows))
        self.assertEqual('bar', rows[0][0])
        cursor.execute("SELECT value FROM session_attribute "
                       "WHERE sid='john' AND authenticated=0 AND name='foo'")
        rows = cursor.fetchall()
        self.assertEqual(1, len(rows))
        self.assertEqual('baz', rows[0][0])

    def test_delete_authenticated_session_var(self):
        """
        Verify that deleting a variable updates the 'session' table accordingly
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
        session['modified'] = True
        session.save() # updating does require modifications

        self.assertEqual(PURGE_AGE, outcookie['trac_session']['expires'])

        cursor.execute("SELECT last_visit FROM session WHERE sid='123456' AND "
                       "authenticated=0")
        self.assertAlmostEqual(now, int(cursor.fetchone()[0]), -1)

    def test_modify_detached_session(self):
        """
        Verify that modifying a variable in a session not associated with a
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

    def test_session_admin_list(self):
        auth_list, anon_list, all_list = _prep_session_table(self.db)
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
        auth_list, anon_list, all_list = _prep_session_table(self.db)
        sess_admin = SessionAdmin(self.env)
        self.assertRaises(Exception, sess_admin._do_add, 'name00')
        sess_admin._do_add('john')
        result = get_session_info(self.db, 'john')
        self.assertEqual(result, ('john', None, None))
        sess_admin._do_add('john1', 'John1')
        result = get_session_info(self.db, 'john1')
        self.assertEqual(result, ('john1', 'John1', None))
        sess_admin._do_add('john2', 'John2', 'john2@example.org')
        result = get_session_info(self.db, 'john2')
        self.assertEqual(result, ('john2', 'John2', 'john2@example.org'))

    def test_session_admin_set(self):
        auth_list, anon_list, all_list = _prep_session_table(self.db)
        sess_admin = SessionAdmin(self.env)
        self.assertRaises(TracError, sess_admin._do_set, 'name', 'nothere',
                          'foo')
        sess_admin._do_set('name', 'name00', 'john')
        result = get_session_info(self.db, 'name00')
        self.assertEqual(result, ('name00', 'john', 'val00'))
        sess_admin._do_set('email', 'name00', 'john@example.org')
        result = get_session_info(self.db, 'name00')
        self.assertEqual(result, ('name00', 'john', 'john@example.org'))

    def test_session_admin_delete(self):
        auth_list, anon_list, all_list = _prep_session_table(self.db)
        sess_admin = SessionAdmin(self.env)
        sess_admin._do_delete('name00')
        result = get_session_info(self.db, 'name00')
        self.assertEqual(result, (None, None, None))
        sess_admin._do_delete('nothere')
        result = get_session_info(self.db, 'nothere')
        self.assertEqual(result, (None, None, None))
        auth_list, anon_list, all_list = _prep_session_table(self.db)
        sess_admin._do_delete('anonymous')
        result = [i for i in sess_admin._get_list(['*'])]
        self.assertEqual(result, auth_list)

    def test_session_admin_purge(self):
        sess_admin = SessionAdmin(self.env)

        auth_list, anon_list, all_list = \
            _prep_session_table(self.db, spread_visits=True)
        sess_admin._do_purge('2010-01-02')
        result = [i for i in sess_admin._get_list(['*'])]
        self.assertEqual(result, auth_list + anon_list)
        result = get_session_info(self.db, anon_list[0][0])
        self.assertEqual(result, ('name10', 'val10', 'val10'))
        result = get_session_info(self.db, anon_list[1][0])
        self.assertEqual(result, ('name11', 'val11', 'val11'))

        auth_list, anon_list, all_list = \
            _prep_session_table(self.db, spread_visits=True)
        sess_admin._do_purge('2010-01-12')
        result = [i for i in sess_admin._get_list(['*'])]
        self.assertEqual(result, auth_list + anon_list[1:])
        cursor = self.db.cursor()
        cursor.execute("""
            SELECT name, value FROM session_attribute WHERE sid = %s
            """, (anon_list[0][0],))
        self.assertEqual([], list(cursor))
        result = get_session_info(self.db, anon_list[1][0])
        self.assertEqual(result, ('name11', 'val11', 'val11'))


def suite():
    return unittest.makeSuite(SessionTestCase, 'test')


if __name__ == '__main__':
    unittest.main()
