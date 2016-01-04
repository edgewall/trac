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

from __future__ import with_statement

import os
import unittest

import trac.tests.compat
from trac.config import ConfigurationError
from trac.db.api import DatabaseManager, _parse_db_str, get_column_names, \
                        with_transaction
from trac.db_default import schema as default_schema
from trac.db.schema import Column, Table
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
    from trac.core import ComponentManager
    return Mock(ComponentManager, components={DatabaseManager:
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

    def test_empty_string(self):
        self.assertRaises(ConfigurationError, _parse_db_str, '')

    def test_invalid_port(self):
        self.assertRaises(ConfigurationError, _parse_db_str,
                          'postgres://localhost:42:42')

    def test_invalid_schema(self):
        self.assertRaises(ConfigurationError, _parse_db_str,
                          'sqlitedb/trac.db')

    def test_no_path(self):
        self.assertRaises(ConfigurationError, _parse_db_str,
                          'sqlite:')

    def test_invalid_query_string(self):
        self.assertRaises(ConfigurationError, _parse_db_str,
                          'postgres://localhost/schema?name')


class StringsTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()

    def tearDown(self):
        self.env.reset_db()

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

    def test_quoted_id_with_percent(self):
        db = self.env.get_read_db()
        name = """%?`%s"%'%%"""

        def test(db, logging=False):
            cursor = db.cursor()
            if logging:
                cursor.log = self.env.log

            cursor.execute('SELECT 1 AS ' + db.quote(name))
            self.assertEqual(name, get_column_names(cursor)[0])
            cursor.execute('SELECT %s AS ' + db.quote(name), (42,))
            self.assertEqual(name, get_column_names(cursor)[0])
            cursor.executemany("UPDATE system SET value=%s WHERE "
                               "1=(SELECT 0 AS " + db.quote(name) + ")",
                               [])
            cursor.executemany("UPDATE system SET value=%s WHERE "
                               "1=(SELECT 0 AS " + db.quote(name) + ")",
                               [('42',), ('43',)])

        test(db)
        test(db, logging=True)

    def test_prefix_match_case_sensitive(self):
        @self.env.with_transaction()
        def do_insert(db):
            cursor = db.cursor()
            cursor.executemany("INSERT INTO system (name,value) VALUES (%s,1)",
                               [('blahblah',), ('BlahBlah',), ('BLAHBLAH',),
                                (u'BlähBlah',), (u'BlahBläh',)])

        db = self.env.get_read_db()
        cursor = db.cursor()
        cursor.execute("SELECT name FROM system WHERE name %s" %
                       db.prefix_match(),
                       (db.prefix_match_value('Blah'),))
        names = sorted(name for name, in cursor)
        self.assertEqual('BlahBlah', names[0])
        self.assertEqual(u'BlahBläh', names[1])
        self.assertEqual(2, len(names))

    def test_prefix_match_metachars(self):
        def do_query(prefix):
            db = self.env.get_read_db()
            cursor = db.cursor()
            cursor.execute("SELECT name FROM system WHERE name %s "
                           "ORDER BY name" % db.prefix_match(),
                           (db.prefix_match_value(prefix),))
            return [name for name, in cursor]

        @self.env.with_transaction()
        def do_insert(db):
            values = ['foo*bar', 'foo*bar!', 'foo?bar', 'foo?bar!',
                      'foo[bar', 'foo[bar!', 'foo]bar', 'foo]bar!',
                      'foo%bar', 'foo%bar!', 'foo_bar', 'foo_bar!',
                      'foo/bar', 'foo/bar!', 'fo*ob?ar[fo]ob%ar_fo/obar']
            cursor = db.cursor()
            cursor.executemany("INSERT INTO system (name,value) VALUES (%s,1)",
                               [(value,) for value in values])

        self.assertEqual(['foo*bar', 'foo*bar!'], do_query('foo*'))
        self.assertEqual(['foo?bar', 'foo?bar!'], do_query('foo?'))
        self.assertEqual(['foo[bar', 'foo[bar!'], do_query('foo['))
        self.assertEqual(['foo]bar', 'foo]bar!'], do_query('foo]'))
        self.assertEqual(['foo%bar', 'foo%bar!'], do_query('foo%'))
        self.assertEqual(['foo_bar', 'foo_bar!'], do_query('foo_'))
        self.assertEqual(['foo/bar', 'foo/bar!'], do_query('foo/'))
        self.assertEqual(['fo*ob?ar[fo]ob%ar_fo/obar'], do_query('fo*'))
        self.assertEqual(['fo*ob?ar[fo]ob%ar_fo/obar'],
                         do_query('fo*ob?ar[fo]ob%ar_fo/obar'))


class ConnectionTestCase(unittest.TestCase):
    def setUp(self):
        self.env = EnvironmentStub()
        self.schema = [
            Table('HOURS', key='ID')[
                Column('ID', auto_increment=True),
                Column('AUTHOR')],
            Table('blog', key='bid')[
                Column('bid', auto_increment=True),
                Column('author')
            ]
        ]
        self.env.global_databasemanager.drop_tables(self.schema)
        self.env.global_databasemanager.create_tables(self.schema)

    def tearDown(self):
        self.env.global_databasemanager.drop_tables(self.schema)
        self.env.reset_db()

    def test_get_last_id(self):
        q = "INSERT INTO report (author) VALUES ('anonymous')"
        with self.env.db_transaction as db:
            cursor = db.cursor()
            cursor.execute(q)
            # Row ID correct before...
            id1 = db.get_last_id(cursor, 'report')
            db.commit()
            cursor.execute(q)
            # ... and after commit()
            db.commit()
            id2 = db.get_last_id(cursor, 'report')

        self.assertNotEqual(0, id1)
        self.assertEqual(id1 + 1, id2)

    def test_update_sequence_default_column(self):
        with self.env.db_transaction as db:
            db("INSERT INTO report (id, author) VALUES (42, 'anonymous')")
            cursor = db.cursor()
            db.update_sequence(cursor, 'report', 'id')

        self.env.db_transaction(
            "INSERT INTO report (author) VALUES ('next-id')")

        self.assertEqual(43, self.env.db_query(
                "SELECT id FROM report WHERE author='next-id'")[0][0])

    def test_update_sequence_nondefault_column(self):
        with self.env.db_transaction as db:
            cursor = db.cursor()
            cursor.execute(
                "INSERT INTO blog (bid, author) VALUES (42, 'anonymous')")
            db.update_sequence(cursor, 'blog', 'bid')

        self.env.db_transaction(
            "INSERT INTO blog (author) VALUES ('next-id')")

        self.assertEqual(43, self.env.db_query(
            "SELECT bid FROM blog WHERE author='next-id'")[0][0])

    def test_identifiers_need_quoting(self):
        """Test for regression described in comment:4:ticket:11512."""
        with self.env.db_transaction as db:
            db("INSERT INTO %s (%s, %s) VALUES (42, 'anonymous')"
               % (db.quote('HOURS'), db.quote('ID'), db.quote('AUTHOR')))
            cursor = db.cursor()
            db.update_sequence(cursor, 'HOURS', 'ID')

        with self.env.db_transaction as db:
            cursor = db.cursor()
            cursor.execute(
                "INSERT INTO %s (%s) VALUES ('next-id')"
                % (db.quote('HOURS'), db.quote('AUTHOR')))
            last_id = db.get_last_id(cursor, 'HOURS', 'ID')

        self.assertEqual(43, last_id)

    def test_table_names(self):
        schema = default_schema + self.schema
        with self.env.db_query as db:
            db_tables = db.get_table_names()
            self.assertEqual(len(schema), len(db_tables))
            # Some DB (e.g. MariaDB) normalize the table names to lower case
            db_tables = [t.lower() for t in db_tables]
            for table in schema:
                self.assertIn(table.name.lower(), db_tables)

    def test_get_column_names(self):
        schema = default_schema + self.schema
        with self.env.db_transaction as db:
            for table in schema:
                db_columns = db.get_column_names(table.name)
                self.assertEqual(len(table.columns), len(db_columns))
                for column in table.columns:
                    self.assertIn(column.name, db_columns)


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(ParseConnectionStringTestCase))
    suite.addTest(unittest.makeSuite(StringsTestCase))
    suite.addTest(unittest.makeSuite(ConnectionTestCase))
    suite.addTest(unittest.makeSuite(WithTransactionTest))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
