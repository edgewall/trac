# -*- coding: utf-8 -*-

from __future__ import with_statement

import os
import unittest

from trac.db.api import DatabaseManager, _parse_db_str, get_column_names, \
                        with_transaction
from trac.test import EnvironmentStub, Mock
from trac.util.concurrency import ThreadLocal


class Connection(object):

    committed = False
    rolledback = False

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolledback = True


class Error(Exception):
    pass


def make_env(get_cnx):
    return Mock(components={DatabaseManager:
             Mock(get_connection=get_cnx,
                  _transaction_local=ThreadLocal(wdb=None, rdb=None))})


class WithTransactionTest(unittest.TestCase):

    def test_successful_transaction(self):
        db = Connection()
        env = make_env(lambda: db)
        @with_transaction(env)
        def do_transaction(db):
            self.assertTrue(not db.committed and not db.rolledback)
        self.assertTrue(db.committed and not db.rolledback)

    def test_failed_transaction(self):
        db = Connection()
        env = make_env(lambda: db)
        try:
            @with_transaction(env)
            def do_transaction(db):
                self.assertTrue(not db.committed and not db.rolledback)
                raise Error()
            self.fail()
        except Error:
            pass
        self.assertTrue(not db.committed and db.rolledback)

    def test_implicit_nesting_success(self):
        env = make_env(Connection)
        dbs = [None, None]
        @with_transaction(env)
        def level0(db):
            dbs[0] = db
            @with_transaction(env)
            def level1(db):
                dbs[1] = db
                self.assertTrue(not db.committed and not db.rolledback)
            self.assertTrue(not db.committed and not db.rolledback)
        self.assertTrue(dbs[0] is not None)
        self.assertTrue(dbs[0] is dbs[1])
        self.assertTrue(dbs[0].committed and not dbs[0].rolledback)

    def test_implicit_nesting_failure(self):
        env = make_env(Connection)
        dbs = [None, None]
        try:
            @with_transaction(env)
            def level0(db):
                dbs[0] = db
                try:
                    @with_transaction(env)
                    def level1(db):
                        dbs[1] = db
                        self.assertTrue(not db.committed and not db.rolledback)
                        raise Error()
                    self.fail()
                except Error:
                    self.assertTrue(not db.committed and not db.rolledback)
                    raise
            self.fail()
        except Error:
            pass
        self.assertTrue(dbs[0] is not None)
        self.assertTrue(dbs[0] is dbs[1])
        self.assertTrue(not dbs[0].committed and dbs[0].rolledback)

    def test_explicit_success(self):
        db = Connection()
        env = make_env(lambda: None)
        @with_transaction(env, db)
        def do_transaction(idb):
            self.assertTrue(idb is db)
            self.assertTrue(not db.committed and not db.rolledback)
        self.assertTrue(not db.committed and not db.rolledback)

    def test_explicit_failure(self):
        db = Connection()
        env = make_env(lambda: None)
        try:
            @with_transaction(env, db)
            def do_transaction(idb):
                self.assertTrue(idb is db)
                self.assertTrue(not db.committed and not db.rolledback)
                raise Error()
            self.fail()
        except Error:
            pass
        self.assertTrue(not db.committed and not db.rolledback)

    def test_implicit_in_explicit_success(self):
        db = Connection()
        env = make_env(lambda: db)
        dbs = [None, None]
        @with_transaction(env, db)
        def level0(db):
            dbs[0] = db
            @with_transaction(env)
            def level1(db):
                dbs[1] = db
                self.assertTrue(not db.committed and not db.rolledback)
            self.assertTrue(not db.committed and not db.rolledback)
        self.assertTrue(dbs[0] is not None)
        self.assertTrue(dbs[0] is dbs[1])
        self.assertTrue(not dbs[0].committed and not dbs[0].rolledback)

    def test_implicit_in_explicit_failure(self):
        db = Connection()
        env = make_env(lambda: db)
        dbs = [None, None]
        try:
            @with_transaction(env, db)
            def level0(db):
                dbs[0] = db
                @with_transaction(env)
                def level1(db):
                    dbs[1] = db
                    self.assertTrue(not db.committed and not db.rolledback)
                    raise Error()
                self.fail()
            self.fail()
        except Error:
            pass
        self.assertTrue(dbs[0] is not None)
        self.assertTrue(dbs[0] is dbs[1])
        self.assertTrue(not dbs[0].committed and not dbs[0].rolledback)

    def test_explicit_in_implicit_success(self):
        db = Connection()
        env = make_env(lambda: db)
        dbs = [None, None]
        @with_transaction(env)
        def level0(db):
            dbs[0] = db
            @with_transaction(env, db)
            def level1(db):
                dbs[1] = db
                self.assertTrue(not db.committed and not db.rolledback)
            self.assertTrue(not db.committed and not db.rolledback)
        self.assertTrue(dbs[0] is not None)
        self.assertTrue(dbs[0] is dbs[1])
        self.assertTrue(dbs[0].committed and not dbs[0].rolledback)

    def test_explicit_in_implicit_failure(self):
        db = Connection()
        env = make_env(lambda: db)
        dbs = [None, None]
        try:
            @with_transaction(env)
            def level0(db):
                dbs[0] = db
                @with_transaction(env, db)
                def level1(db):
                    dbs[1] = db
                    self.assertTrue(not db.committed and not db.rolledback)
                    raise Error()
                self.fail()
            self.fail()
        except Error:
            pass
        self.assertTrue(dbs[0] is not None)
        self.assertTrue(dbs[0] is dbs[1])
        self.assertTrue(not dbs[0].committed and dbs[0].rolledback)

    def test_invalid_nesting(self):
        env = make_env(Connection)
        try:
            @with_transaction(env)
            def level0(db):
                @with_transaction(env, Connection())
                def level1(db):
                    raise Error()
                raise Error()
            raise Error()
        except AssertionError:
            pass



class ParseConnectionStringTestCase(unittest.TestCase):

    def test_sqlite_relative(self):
        # Default syntax for specifying DB path relative to the environment
        # directory
        self.assertEqual(('sqlite', {'path': 'db/trac.db'}),
                         _parse_db_str('sqlite:db/trac.db'))

    def test_sqlite_absolute(self):
        # Standard syntax
        self.assertEqual(('sqlite', {'path': '/var/db/trac.db'}),
                         _parse_db_str('sqlite:///var/db/trac.db'))
        # Legacy syntax
        self.assertEqual(('sqlite', {'path': '/var/db/trac.db'}),
                         _parse_db_str('sqlite:/var/db/trac.db'))

    def test_sqlite_with_timeout_param(self):
        # In-memory database
        self.assertEqual(('sqlite', {'path': 'db/trac.db',
                                     'params': {'timeout': '10000'}}),
                         _parse_db_str('sqlite:db/trac.db?timeout=10000'))

    def test_sqlite_windows_path(self):
        # In-memory database
        os_name = os.name
        try:
            os.name = 'nt'
            self.assertEqual(('sqlite', {'path': 'C:/project/db/trac.db'}),
                             _parse_db_str('sqlite:C|/project/db/trac.db'))
        finally:
            os.name = os_name

    def test_postgres_simple(self):
        self.assertEqual(('postgres', {'host': 'localhost', 'path': '/trac'}),
                         _parse_db_str('postgres://localhost/trac'))

    def test_postgres_with_port(self):
        self.assertEqual(('postgres', {'host': 'localhost', 'port': 9431,
                                       'path': '/trac'}),
                         _parse_db_str('postgres://localhost:9431/trac'))

    def test_postgres_with_creds(self):
        self.assertEqual(('postgres', {'user': 'john', 'password': 'letmein',
                                       'host': 'localhost', 'port': 9431,
                                       'path': '/trac'}),
                 _parse_db_str('postgres://john:letmein@localhost:9431/trac'))

    def test_postgres_with_quoted_password(self):
        self.assertEqual(('postgres', {'user': 'john', 'password': ':@/',
                                       'host': 'localhost', 'path': '/trac'}),
                     _parse_db_str('postgres://john:%3a%40%2f@localhost/trac'))

    def test_mysql_simple(self):
        self.assertEqual(('mysql', {'host': 'localhost', 'path': '/trac'}),
                     _parse_db_str('mysql://localhost/trac'))

    def test_mysql_with_creds(self):
        self.assertEqual(('mysql', {'user': 'john', 'password': 'letmein',
                                    'host': 'localhost', 'port': 3306,
                                    'path': '/trac'}),
                     _parse_db_str('mysql://john:letmein@localhost:3306/trac'))


class StringsTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()

    def test_insert_unicode(self):
        self.env.db_transaction(
                "INSERT INTO system (name,value) VALUES (%s,%s)",
                ('test-unicode', u'ünicöde'))
        self.assertEqual([(u'ünicöde',)], self.env.db_query(
            "SELECT value FROM system WHERE name='test-unicode'"))

    def test_insert_empty(self):
        from trac.util.text import empty
        self.env.db_transaction(
                "INSERT INTO system (name,value) VALUES (%s,%s)",
                ('test-empty', empty))
        self.assertEqual([(u'',)], self.env.db_query(
            "SELECT value FROM system WHERE name='test-empty'"))

    def test_insert_markup(self):
        from genshi.core import Markup
        self.env.db_transaction(
                "INSERT INTO system (name,value) VALUES (%s,%s)",
                ('test-markup', Markup(u'<em>märkup</em>')))
        self.assertEqual([(u'<em>märkup</em>',)], self.env.db_query(
            "SELECT value FROM system WHERE name='test-markup'"))

    def test_quote(self):
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute('SELECT 1 AS %s' % \
                       db.quote(r'alpha\`\"\'\\beta``gamma""delta'))
        self.assertEqual(r'alpha\`\"\'\\beta``gamma""delta',
                         get_column_names(cursor)[0])


class ConnectionTestCase(unittest.TestCase):
    def setUp(self):
        self.env = EnvironmentStub()

    def tearDown(self):
        self.env.reset_db()

    def test_get_last_id(self):
        id1 = id2 = None
        q = "INSERT INTO report (author) VALUES ('anonymous')"
        with self.env.db_transaction as db:
            cursor = db.cursor()
            cursor.execute(q)
            # Row ID correct before...
            id1 = db.get_last_id(cursor, 'report')
            self.assertNotEqual(0, id1)
            db.commit()
            cursor.execute(q)
            # ... and after commit()
            db.commit()
            id2 = db.get_last_id(cursor, 'report')
            self.assertEqual(id1 + 1, id2)

    def test_update_sequence(self):
        self.env.db_transaction(
            "INSERT INTO report (id, author) VALUES (42, 'anonymous')")
        with self.env.db_transaction as db:
            cursor = db.cursor()
            db.update_sequence(cursor, 'report', 'id')
        self.env.db_transaction(
            "INSERT INTO report (author) VALUES ('next-id')")
        self.assertEqual(43, self.env.db_query(
                "SELECT id FROM report WHERE author='next-id'")[0][0])


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(ParseConnectionStringTestCase, 'test'))
    suite.addTest(unittest.makeSuite(StringsTestCase, 'test'))
    suite.addTest(unittest.makeSuite(ConnectionTestCase, 'test'))
    suite.addTest(unittest.makeSuite(WithTransactionTest, 'test'))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
