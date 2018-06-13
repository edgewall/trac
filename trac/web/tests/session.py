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

import time
from datetime import datetime
import unittest

from trac.admin.api import console_date_format, get_console_locale
from trac.admin.console import TracAdmin
from trac.admin.test import TracAdminTestCaseBase
from trac.core import Component, ComponentMeta, TracError, implements
from trac.test import EnvironmentStub, MockRequest
from trac.util.datefmt import format_date, get_datetime_format_hint, \
                              time_now, to_datetime
from trac.web.api import IRequestHandler
from trac.web.session import DetachedSession, PURGE_AGE, Session, \
                             SessionAdmin, SessionDict, UPDATE_INTERVAL


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
        for x in range(20):
            sid = 'name%02d' % x
            authenticated = int(x < 10)
            last_visit = last_visit_base + (visit_delta * x)
            val = 'val%02d' % x
            data = (sid, authenticated,
                    format_date(to_datetime(last_visit), console_date_format),
                    val, val, None)
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
    return auth_list, anon_list, all_list


def get_session_attrs(env, sid):
    rows = env.db_query("""
        SELECT a.sid, a.name, a.value
        FROM session AS s
        LEFT JOIN session_attribute AS a
            ON a.sid=s.sid AND a.authenticated=s.authenticated
        WHERE s.sid=%s
        """, (sid,))
    if rows:
        return {row[1]: row[2] for row in rows if row[0]}
    else:
        return None


def get_session_info(env, sid):
    """
    :since 1.0: changed `db` input parameter to `env`
    :since 1.1.2: returns `default_handler` as the fourth entry in the tuple.
    """
    attrs = get_session_attrs(env, sid)
    if attrs is None:
        return None, None, None, None
    else:
        return sid, attrs.get('name'), attrs.get('email'), \
               attrs.get('default_handler')


class SessionDictTestCase(unittest.TestCase):

    def test_initializer(self):
        """`SessionDict` initializer accepts same arguments as `dict`."""
        session = SessionDict(kwarg1=1, kwarg2='b')
        self.assertEqual(1, session['kwarg1'])
        self.assertEqual('b', session['kwarg2'])

        session = SessionDict([('kwarg1', 1), ('kwarg2', 'b')])
        self.assertEqual(1, session['kwarg1'])
        self.assertEqual('b', session['kwarg2'])


class SessionTestCase(unittest.TestCase):
    """Unit tests for the persistent session support."""

    request_handlers = []

    @classmethod
    def setUpClass(cls):
        class DefaultHandlerStub(Component):
            implements(IRequestHandler)

            def match_request(self, req):
                pass

            def process_request(req):
                pass

        cls.request_handlers = [DefaultHandlerStub]

    @classmethod
    def tearDownClass(cls):
        for component in cls.request_handlers:
            ComponentMeta.deregister(component)

    def setUp(self):
        self.env = EnvironmentStub()

    def tearDown(self):
        self.env.reset_db()

    def test_new_session(self):
        """
        Verify that a session cookie gets sent back to the client for a new
        session.
        """
        req = MockRequest(self.env, authname='anonymous')
        session = Session(self.env, req)
        self.assertEqual(session.sid, req.outcookie['trac_session'].value)
        self.assertEqual(0, self.env.db_query(
                "SELECT COUNT(*) FROM session")[0][0])

    def test_anonymous_session(self):
        """
        Verify that session variables are stored in the database.
        """
        req = MockRequest(self.env, authname='anonymous')
        req.incookie['trac_session'] = '123456'
        session = Session(self.env, req)
        self.assertEqual('123456', session.sid)
        self.assertNotIn('trac_session', req.outcookie)

    def _test_authenticated_session(self, username):
        """
        Verifies that a session cookie does not get used if the user is logged
        in, and that Trac expires the cookie.
        """
        req = MockRequest(self.env, authname=username)
        req.incookie['trac_session'] = '123456'
        session = Session(self.env, req)
        self.assertEqual(username, session.sid)
        session['foo'] = 'bar'
        session.save()
        self.assertEqual(0, req.outcookie['trac_session']['expires'])

    def test_authenticated_session(self):
        self._test_authenticated_session('john')
        self._test_authenticated_session('j.smith')
        self._test_authenticated_session(u'Jöhn')  # non-ascii username
        self._test_authenticated_session('john@EXAMPLE.LOCAL')  # LDAP username

    def _test_session_promotion(self, username):
        """
        Verifies that an existing anonymous session gets promoted to an
        authenticated session when the user logs in.
        """
        with self.env.db_transaction as db:
            db("INSERT INTO session VALUES ('123456', 0, 0)")
            req = MockRequest(self.env, authname=username)
            req.incookie['trac_session'] = '123456'
            session = Session(self.env, req)
            self.assertEqual(username, session.sid)
            session.save()

        self.assertEqual([(username, 1)],
            self.env.db_query("""SELECT sid, authenticated FROM session
                                 WHERE sid=%s""", (username,)))

    def test_session_promotion(self):
        self._test_session_promotion('john')
        self._test_session_promotion('j.smith')
        self._test_session_promotion(u'Jöhn')  # non-ascii username
        self._test_session_promotion('john@EXAMPLE.LOCAL')  # LDAP username

        sessions = self.env.db_query("SELECT sid, authenticated FROM session")
        self.assertEqual({('john', 1), ('j.smith', 1), (u'Jöhn', 1),
                          ('john@EXAMPLE.LOCAL', 1)},
                         set(sessions))

    def _test_new_session_promotion(self, username):
        """
        Verifies that even without a preexisting anonymous session,
        an authenticated session will be created when the user logs in.
        (same test as above without the initial INSERT)
        """
        with self.env.db_transaction:
            req = MockRequest(self.env, authname=username)
            req.incookie['trac_session'] = '123456'
            session = Session(self.env, req)
            self.assertEqual(username, session.sid)
            session.save()

        self.assertEqual([(username, 1)],
            self.env.db_query("""SELECT sid, authenticated FROM session
                                 WHERE sid=%s""", (username,)))

    def test_new_session_promotion(self):
        self._test_new_session_promotion('john')
        self._test_new_session_promotion('j.smith')
        self._test_new_session_promotion(u'Jöhn')  # non-ascii username
        self._test_new_session_promotion('john@EXAMPLE.LOCAL')  # LDAP username

        sessions = self.env.db_query("SELECT sid, authenticated FROM session")
        self.assertEqual({('john', 1), ('j.smith', 1), (u'Jöhn', 1),
                          ('john@EXAMPLE.LOCAL', 1)},
                         set(sessions))

    def test_as_int(self):
        with self.env.db_transaction as db:
            db("INSERT INTO session VALUES ('123456', 1, 0)")
            db.executemany("""
                INSERT INTO session_attribute VALUES (%s,%s,%s,%s)
                """, (('123456', 1, 'foo', 'bar'), ('123456', 1, 'baz', 3)))

        req = MockRequest(self.env, authname='123456')
        session = Session(self.env, req)

        self.assertEqual('bar', session.get('foo'))
        self.assertEqual(2, session.as_int('foo', 2))
        self.assertEqual(3, session.as_int('baz', 1))
        self.assertEqual(2, session.as_int('baz', 1, max=2))
        self.assertEqual(4, session.as_int('baz', 1, min=4))
        self.assertIsNone(session.as_int('bat'))

    def test_as_bool(self):
        with self.env.db_transaction as db:
            db("INSERT INTO session VALUES ('123456', 1, 0)")
            db.executemany("""
                INSERT INTO session_attribute VALUES (%s,%s,%s,%s)
                """, (('123456', 1, 'foo', 'bar'), ('123456', 1, 'baz', 1)))

        req = MockRequest(self.env, authname='123456')
        session = Session(self.env, req)

        self.assertEqual('bar', session.get('foo'))
        self.assertIsNone(session.as_bool('foo', None))
        self.assertTrue(session.as_int('baz'))
        self.assertTrue(session.as_int('baz', False))
        self.assertIsNone(session.as_bool('bat'))

    def test_add_anonymous_session_var(self):
        """
        Verify that new variables are inserted into the 'session' table in the
        database for an anonymous session.
        """
        req = MockRequest(self.env, authname='anonymous')
        req.incookie['trac_session'] = '123456'
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
            req = MockRequest(self.env, authname='anonymous')
            req.incookie['trac_session'] = '123456'
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
            req = MockRequest(self.env, authname='anonymous')
            req.incookie['trac_session'] = '123456'
            session = Session(self.env, req)
            self.assertEqual('bar', session['foo'])
            del session['foo']
            session.save()

        self.assertEqual(0, self.env.db_query("""
            SELECT COUNT(*) FROM session_attribute
            WHERE sid='123456' AND name='foo'
            """)[0][0])

    def _purge_anonymous_session(self):
        now = int(time_now())
        lifetime = 90 * 86400  # default lifetime
        with self.env.db_transaction as db:
            db.executemany("INSERT INTO session VALUES (%s, 0, %s)",
                           [('123456', 0),
                            ('987654', now - lifetime - 3600),
                            ('876543', now - lifetime + 3600),
                            ('765432', now - 3600)])
            db.executemany("""
                INSERT INTO session_attribute
                VALUES (%s, 0, 'foo', 'bar')
                """, [('987654',), ('876543',), ('765432',)])

        with self.env.db_transaction as db:
            # We need to modify a different session to trigger the purging
            req = MockRequest(self.env, authname='anonymous')
            req.incookie['trac_session'] = '123456'
            session = Session(self.env, req)
            session['foo'] = 'bar'
            session.save()

        return [row[0] for row in self.env.db_query("""
            SELECT sid FROM session WHERE authenticated=0 ORDER BY sid
            """)]

    def test_purge_anonymous_session(self):
        """
        Verify that old sessions get purged.
        """
        sids = self._purge_anonymous_session()
        self.assertEqual(['123456', '765432', '876543'], sids)

    def test_purge_anonymous_session_with_short_lifetime(self):
        self.env.config.set('trac', 'anonymous_session_lifetime', '1')
        sids = self._purge_anonymous_session()
        self.assertEqual(['123456', '765432'], sids)

    def test_purge_anonymous_session_disabled(self):
        self.env.config.set('trac', 'anonymous_session_lifetime', '0')
        sids = self._purge_anonymous_session()
        self.assertEqual(['123456', '765432', '876543', '987654'], sids)

    def test_delete_empty_session(self):
        """
        Verify that a session gets deleted when it doesn't have any data except
        for the 'last_visit' timestamp.
        """
        now = time_now()

        # Make sure the session has data so that it doesn't get dropped
        with self.env.db_transaction as db:
            db("INSERT INTO session VALUES ('123456', 0, %s)",
               (int(now - UPDATE_INTERVAL - 3600),))
            db("""
                INSERT INTO session_attribute
                VALUES ('123456', 0, 'foo', 'bar')
                """)

            req = MockRequest(self.env, authname='anonymous')
            req.incookie['trac_session'] = '123456'
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

        req = MockRequest(self.env, authname='anonymous')
        req.incookie['trac_session'] = '123456'
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
        req = MockRequest(self.env, authname='john')
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

            req = MockRequest(self.env, authname='john')
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

        req = MockRequest(self.env, authname='anonymous')
        req.incookie['trac_session'] = 'john'
        session = Session(self.env, req)
        self.assertNotIn('foo', session)
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

            req = MockRequest(self.env, authname='john')
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
        now = time_now()

        # Make sure the session has data so that it doesn't get dropped
        with self.env.db_transaction as db:
            db("INSERT INTO session VALUES ('123456', 0, 1)")
            db("""
                INSERT INTO session_attribute
                VALUES ('123456', 0, 'foo', 'bar')
                """)

            req = MockRequest(self.env, authname='anonymous')
            req.incookie['trac_session'] = '123456'
            session = Session(self.env, req)
            session['modified'] = True
            session.save() # updating does require modifications

            self.assertEqual(PURGE_AGE, req.outcookie['trac_session']['expires'])

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

    def test_create_new_session(self):
        """Setting attribute on a new session invalidates known_users cache."""
        sid = 'user'
        session = DetachedSession(self.env, sid)
        session.authenticated = True

        self.assertEqual([], list(self.env.get_known_users()))
        session.save()
        known_users = list(self.env.get_known_users())
        self.assertEqual(1, len(known_users))
        self.assertEqual(sid, known_users[0][0])
        self.assertIsNone(known_users[0][1])
        self.assertIsNone(known_users[0][2])

    def test_create_new_anonymous_session(self):
        """Setting attribute on a new anonymous session doesn't invalidate
        known_users cache."""
        sid = 'anonymous'
        session = DetachedSession(self.env, sid)
        session.authenticated = False

        self.assertEqual([], list(self.env.get_known_users()))
        # insert a session record without invalidating cache
        self.env.insert_users([('user', 'Name' 'user@example.com', 1)])
        session.save()
        self.assertEqual([], list(self.env.get_known_users()))

        self.env.invalidate_known_users_cache()
        self.assertEqual(1, len(list(self.env.get_known_users())))

    def test_session_set_email(self):
        """Setting session email invalidates known_users cache."""
        sid = 'user'
        email = 'user@domain.org'
        session = DetachedSession(self.env, sid)
        session['email'] = email

        self.assertEqual([], list(self.env.get_known_users()))
        session.save()
        known_users = list(self.env.get_known_users())
        self.assertEqual(1, len(known_users))
        self.assertEqual(sid, known_users[0][0])
        self.assertIsNone(known_users[0][1])
        self.assertEqual(email, known_users[0][2])

    def test_session_set_name(self):
        """Setting session name invalidates known_users cache."""
        sid = 'user'
        name = 'The User'
        session = DetachedSession(self.env, sid)
        session['name'] = name

        self.assertEqual([], list(self.env.get_known_users()))
        session.save()
        known_users = list(self.env.get_known_users())
        self.assertEqual(1, len(known_users))
        self.assertEqual(sid, known_users[0][0])
        self.assertEqual(name, known_users[0][1])
        self.assertIsNone(known_users[0][2])

    def test_session_admin_list(self):
        auth_list, anon_list, all_list = _prep_session_table(self.env)
        sess_admin = SessionAdmin(self.env)

        # Verify the empty case
        self.assertRaises(StopIteration, next, sess_admin._get_list([]))

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
        _prep_session_table(self.env)
        sess_admin = SessionAdmin(self.env)

        self.assertRaises(Exception, sess_admin._do_add, 'name00')

        sess_admin._do_add('john')
        self.assertEqual({}, get_session_attrs(self.env, 'john'))
        self.assertIn(('john', None, None),
                      list(self.env.get_known_users()))

        sess_admin._do_add('john1', 'John1')
        self.assertEqual({'name': 'John1'},
                         get_session_attrs(self.env, 'john1'))
        self.assertIn(('john1', 'John1', None),
                      list(self.env.get_known_users()))

        sess_admin._do_add('john2', 'John2', 'john2@example.org')
        self.assertEqual({'name': 'John2', 'email': 'john2@example.org'},
                         get_session_attrs(self.env, 'john2'))
        self.assertIn(('john2', 'John2', 'john2@example.org'),
                      list(self.env.get_known_users()))

        sess_admin._do_add('alice1', None, 'alice1@example.org')
        self.assertEqual({'email': 'alice1@example.org'},
                         get_session_attrs(self.env, 'alice1'))
        sess_admin._do_add('alice2', '', 'alice2@example.org')
        self.assertEqual({'email': 'alice2@example.org'},
                         get_session_attrs(self.env, 'alice2'))
        sess_admin._do_add('bob1', 'Bob 1', None)
        self.assertEqual({'name': 'Bob 1'},
                         get_session_attrs(self.env, 'bob1'))
        sess_admin._do_add('bob2', 'Bob 2', '')
        self.assertEqual({'name': 'Bob 2'},
                         get_session_attrs(self.env, 'bob2'))
        sess_admin._do_add('charlie1', '', '')
        self.assertEqual({}, get_session_attrs(self.env, 'charlie1'))
        sess_admin._do_add('charlie2', None, None)
        self.assertEqual({}, get_session_attrs(self.env, 'charlie2'))

    def test_session_admin_set(self):
        _prep_session_table(self.env)
        sess_admin = SessionAdmin(self.env)

        self.assertRaises(TracError, sess_admin._do_set, 'name', 'nothere',
                          'foo')

        self.env.get_known_users()  # Prep the cache
        self.assertIn(('name00', 'val00', 'val00'),
                      list(self.env.get_known_users()))
        sess_admin._do_set('name', 'name00', 'john')
        self.assertEqual({'name': 'john', 'email': 'val00'},
                         get_session_attrs(self.env, 'name00'))
        self.assertIn(('name00', 'john', 'val00'),
                      list(self.env.get_known_users()))

        sess_admin._do_set('email', 'name00', 'john@example.org')
        self.assertEqual({'name': 'john', 'email': 'john@example.org'},
                         get_session_attrs(self.env, 'name00'))
        self.assertIn(('name00', 'john', 'john@example.org'),
                      list(self.env.get_known_users()))
        sess_admin._do_set('default_handler', 'name00', 'DefaultHandlerStub')
        self.assertEqual({'name': 'john', 'email': 'john@example.org',
                          'default_handler': 'DefaultHandlerStub'},
                         get_session_attrs(self.env, 'name00'))

        sess_admin._do_set('name', 'name00', '')
        self.assertEqual({'email': 'john@example.org',
                          'default_handler': 'DefaultHandlerStub'},
                         get_session_attrs(self.env, 'name00'))
        sess_admin._do_set('email', 'name00', '')
        self.assertEqual({'default_handler': 'DefaultHandlerStub'},
                         get_session_attrs(self.env, 'name00'))
        sess_admin._do_set('default_handler', 'name00', '')
        self.assertEqual({}, get_session_attrs(self.env, 'name00'))

    def test_session_admin_delete(self):
        _prep_session_table(self.env)
        sess_admin = SessionAdmin(self.env)

        self.assertIn(('name00', 'val00', 'val00'),
                      list(self.env.get_known_users()))
        sess_admin._do_delete('name00')
        self.assertIsNone(get_session_attrs(self.env, 'name00'))
        self.assertNotIn(('name00', 'val00', 'val00'),
                         list(self.env.get_known_users()))

        sess_admin._do_delete('nothere')
        self.assertIsNone(get_session_attrs(self.env, 'nothere'))

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
        self.assertEqual({'name': 'val10', 'email': 'val10'},
                         get_session_attrs(self.env, anon_list[0][0]))
        self.assertEqual({'name': 'val11', 'email': 'val11'},
                         get_session_attrs(self.env, anon_list[1][0]))

        auth_list, anon_list, all_list = \
            _prep_session_table(self.env, spread_visits=True)
        sess_admin._do_purge('2010-01-12')
        result = [i for i in sess_admin._get_list(['*'])]
        self.assertEqual(result, auth_list + anon_list[1:])
        rows = self.env.db_query("""
            SELECT name, value FROM session_attribute WHERE sid = %s
            """, (anon_list[0][0],))
        self.assertEqual([], rows)
        self.assertIsNone(get_session_attrs(self.env, anon_list[0][0]))
        self.assertEqual({'name': 'val11', 'email': 'val11'},
                         get_session_attrs(self.env, anon_list[1][0]))

    def test_session_get_session_with_invalid_sid(self):
        req = MockRequest(self.env, authname='anonymous')
        session = Session(self.env, req)
        session.get_session('0123456789')
        self.assertEqual('0123456789', session.sid)
        session.get_session('abcxyz')
        self.assertEqual('abcxyz', session.sid)
        session.get_session('abc123xyz')
        self.assertEqual('abc123xyz', session.sid)
        self.assertRaises(TracError, session.get_session, 'abc 123 xyz')
        self.assertRaises(TracError, session.get_session, 'abc-123-xyz')
        self.assertRaises(TracError, session.get_session, 'abc<i>123</i>xyz')
        self.assertRaises(TracError, session.get_session, u'abc123xÿz')
        self.assertRaises(TracError, session.get_session,
                          u'abc¹₂³xyz')  # Unicode digits

    def test_session_change_id_with_invalid_sid(self):
        req = MockRequest(self.env, authname='anonymous', base_path='/')
        session = Session(self.env, req)
        session.change_sid('0123456789')
        self.assertEqual('0123456789', session.sid)
        session.change_sid('abcxyz')
        self.assertEqual('abcxyz', session.sid)
        session.change_sid('abc123xyz')
        self.assertEqual('abc123xyz', session.sid)
        self.assertRaises(TracError, session.change_sid, 'abc 123 xyz')
        self.assertRaises(TracError, session.change_sid, 'abc-123-xyz')
        self.assertRaises(TracError, session.change_sid, 'abc<i>123</i>xyz')
        self.assertRaises(TracError, session.change_sid, u'abc123xÿz')
        self.assertRaises(TracError, session.change_sid,
                          u'abc¹₂³xyz')  # Unicode digits


class TracAdminTestCase(TracAdminTestCaseBase):

    request_handlers = []

    @classmethod
    def setUpClass(cls):
        class DefaultHandlerStub(Component):
            implements(IRequestHandler)

            def match_request(self, req):
                pass

            def process_request(req):
                pass

        cls.request_handlers = [DefaultHandlerStub]

    @classmethod
    def tearDownClass(cls):
        for component in cls.request_handlers:
            ComponentMeta.deregister(component)

    def setUp(self):
        self.env = EnvironmentStub()
        self.admin = TracAdmin()
        self.admin.env_set('', self.env)

    def tearDown(self):
        self.env = None

    @property
    def datetime_format_hint(self):
        return get_datetime_format_hint(get_console_locale(self.env))

    def test_session_list_no_sessions(self):
        rv, output = self.execute('session list authenticated')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_session_list_authenticated(self):
        _prep_session_table(self.env)
        rv, output = self.execute('session list authenticated')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_session_list_anonymous(self):
        _prep_session_table(self.env)
        rv, output = self.execute('session list anonymous')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_session_list_all(self):
        _prep_session_table(self.env)
        if self.admin.interactive:
            rv, output = self.execute("session list *")
        else:
            rv, output = self.execute("session list '*'")
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_session_list_authenticated_sid(self):
        _prep_session_table(self.env)
        rv, output = self.execute('session list name00')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_session_list_anonymous_sid(self):
        _prep_session_table(self.env)
        rv, output = self.execute('session list name10:0')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_session_list_missing_sid(self):
        _prep_session_table(self.env)
        rv, output = self.execute('session list thisdoesntexist')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_session_add_missing_sid(self):
        rv, output = self.execute('session add')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_session_add_duplicate_sid(self):
        _prep_session_table(self.env)
        rv, output = self.execute('session add name00')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_session_add_sid_all(self):
        rv, output = self.execute('session add john John john@example.org')
        self.assertEqual(0, rv, output)
        rv, output = self.execute('session list john')
        self.assertExpectedResult(output, {
            'today': format_date(None, console_date_format)
        })

    def test_session_add_sid(self):
        rv, output = self.execute('session add john')
        self.assertEqual(0, rv, output)
        rv, output = self.execute('session list john')
        self.assertExpectedResult(output, {
            'today': format_date(None, console_date_format)
        })

    def test_session_add_sid_name(self):
        rv, output = self.execute('session add john John')
        self.assertEqual(0, rv, output)
        rv, output = self.execute('session list john')
        self.assertExpectedResult(output,  {
            'today': format_date(None, console_date_format)
        })

    def test_session_set_attr_name(self):
        _prep_session_table(self.env)
        rv, output = self.execute('session set name name00 JOHN')
        self.assertEqual(0, rv, output)
        rv, output = self.execute('session list name00')
        self.assertExpectedResult(output)

    def test_session_set_attr_email(self):
        _prep_session_table(self.env)
        rv, output = self.execute('session set email name00 JOHN@EXAMPLE.ORG')
        self.assertEqual(0, rv, output)
        rv, output = self.execute('session list name00')
        self.assertExpectedResult(output)

    def test_session_set_attr_default_handler(self):
        _prep_session_table(self.env)
        rv, output = self.execute('session set default_handler name00 '
                                  'DefaultHandlerStub')
        self.assertEqual(0, rv, output)
        rv, output = self.execute('session list name00')
        self.assertExpectedResult(output)

    def test_session_set_attr_default_handler_invalid(self):
        _prep_session_table(self.env)
        rv, output = \
            self.execute('session set default_handler name00 InvalidModule')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_session_set_attr_missing_attr(self):
        rv, output = self.execute('session set')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_session_set_attr_missing_value(self):
        rv, output = self.execute('session set name john')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_session_set_attr_missing_sid(self):
        rv, output = self.execute('session set name')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_session_set_attr_nonexistent_sid(self):
        rv, output = self.execute('session set name john foo')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_session_delete_sid(self):
        _prep_session_table(self.env)
        rv, output = self.execute('session delete name00')
        self.assertEqual(0, rv, output)
        rv, output = self.execute('session list nam00')
        self.assertExpectedResult(output)

    def test_session_delete_missing_params(self):
        rv, output = self.execute('session delete')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_session_delete_anonymous(self):
        _prep_session_table(self.env)
        rv, output = self.execute('session delete anonymous')
        self.assertEqual(0, rv, output)
        rv, output = self.execute('session list *')
        self.assertExpectedResult(output)

    def test_session_delete_multiple_sids(self):
        _prep_session_table(self.env)
        rv, output = self.execute('session delete name00 name01 name02 '
                                   'name03')
        self.assertEqual(0, rv, output)
        rv, output = self.execute('session list *')
        self.assertExpectedResult(output)

    def test_session_purge_age(self):
        _prep_session_table(self.env, spread_visits=True)
        rv, output = self.execute('session purge 20100112')
        self.assertEqual(0, rv, output)
        rv, output = self.execute('session list *')
        self.assertExpectedResult(output)

    def test_session_purge_invalid_date(self):
        rv, output = self.execute('session purge <purge>')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output, {
            'hint': self.datetime_format_hint,
            'isohint': get_datetime_format_hint('iso8601')
        })

    def test_help_session_purge(self):
        doc = self.get_command_help('session', 'purge')
        self.assertIn(u'"YYYY-MM-DDThh:mm:ss±hh:mm"', doc)


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(SessionDictTestCase))
    suite.addTest(unittest.makeSuite(SessionTestCase))
    suite.addTest(unittest.makeSuite(TracAdminTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
