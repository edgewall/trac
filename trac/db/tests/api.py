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

import os
import unittest

import trac.tests.compat
from trac.config import ConfigurationError
from trac.db.api import DatabaseManager, get_column_names, \
                        parse_connection_uri, with_transaction
from trac.db_default import (schema as default_schema,
                             db_version as default_db_version)
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
                         parse_connection_uri('sqlite:db/trac.db'))

    def test_sqlite_absolute(self):
        # Standard syntax
        self.assertEqual(('sqlite', {'path': '/var/db/trac.db'}),
                         parse_connection_uri('sqlite:///var/db/trac.db'))
        # Legacy syntax
        self.assertEqual(('sqlite', {'path': '/var/db/trac.db'}),
                         parse_connection_uri('sqlite:/var/db/trac.db'))

    def test_sqlite_with_timeout_param(self):
        # In-memory database
        self.assertEqual(('sqlite', {'path': 'db/trac.db',
                                     'params': {'timeout': '10000'}}),
                         parse_connection_uri('sqlite:db/trac.db?timeout=10000'))

    def test_sqlite_windows_path(self):
        # In-memory database
        os_name = os.name
        try:
            os.name = 'nt'
            self.assertEqual(('sqlite', {'path': 'C:/project/db/trac.db'}),
                             parse_connection_uri('sqlite:C|/project/db/trac.db'))
        finally:
            os.name = os_name

    def test_postgres_simple(self):
        self.assertEqual(('postgres', {'host': 'localhost', 'path': '/trac'}),
                         parse_connection_uri('postgres://localhost/trac'))

    def test_postgres_with_port(self):
        self.assertEqual(('postgres', {'host': 'localhost', 'port': 9431,
                                       'path': '/trac'}),
                         parse_connection_uri('postgres://localhost:9431/trac'))

    def test_postgres_with_creds(self):
        self.assertEqual(('postgres', {'user': 'john', 'password': 'letmein',
                                       'host': 'localhost', 'port': 9431,
                                       'path': '/trac'}),
                 parse_connection_uri('postgres://john:letmein@localhost:9431/trac'))

    def test_postgres_with_quoted_password(self):
        self.assertEqual(('postgres', {'user': 'john', 'password': ':@/',
                                       'host': 'localhost', 'path': '/trac'}),
                     parse_connection_uri('postgres://john:%3a%40%2f@localhost/trac'))

    def test_mysql_simple(self):
        self.assertEqual(('mysql', {'host': 'localhost', 'path': '/trac'}),
                     parse_connection_uri('mysql://localhost/trac'))

    def test_mysql_with_creds(self):
        self.assertEqual(('mysql', {'user': 'john', 'password': 'letmein',
                                    'host': 'localhost', 'port': 3306,
                                    'path': '/trac'}),
                     parse_connection_uri('mysql://john:letmein@localhost:3306/trac'))

    def test_empty_string(self):
        self.assertRaises(ConfigurationError, parse_connection_uri, '')

    def test_invalid_port(self):
        self.assertRaises(ConfigurationError, parse_connection_uri,
                          'postgres://localhost:42:42')

    def test_invalid_schema(self):
        self.assertRaises(ConfigurationError, parse_connection_uri,
                          'sqlitedb/trac.db')

    def test_no_path(self):
        self.assertRaises(ConfigurationError, parse_connection_uri,
                          'sqlite:')

    def test_invalid_query_string(self):
        self.assertRaises(ConfigurationError, parse_connection_uri,
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
        with self.env.db_query as db:
            cursor = db.cursor()
            cursor.execute('SELECT 1 AS %s' % \
                           db.quote(r'alpha\`\"\'\\beta``gamma""delta'))
            self.assertEqual(r'alpha\`\"\'\\beta``gamma""delta',
                             get_column_names(cursor)[0])

    def test_quoted_id_with_percent(self):
        name = """%?`%s"%'%%"""

        def test(logging=False):
            with self.env.db_query as db:
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

        test()
        test(True)

    def test_prefix_match_case_sensitive(self):
        with self.env.db_transaction as db:
            db.executemany("INSERT INTO system (name,value) VALUES (%s,1)",
                           [('blahblah',), ('BlahBlah',), ('BLAHBLAH',),
                            (u'BlähBlah',), (u'BlahBläh',)])

        with self.env.db_query as db:
            names = sorted(name for name, in db(
                "SELECT name FROM system WHERE name %s"
                % db.prefix_match(),
                (db.prefix_match_value('Blah'),)))
        self.assertEqual('BlahBlah', names[0])
        self.assertEqual(u'BlahBläh', names[1])
        self.assertEqual(2, len(names))

    def test_prefix_match_metachars(self):
        def do_query(prefix):
            with self.env.db_query as db:
                return [name for name, in db(
                    "SELECT name FROM system WHERE name %s "
                    "ORDER BY name" % db.prefix_match(),
                    (db.prefix_match_value(prefix),))]

        values = ['foo*bar', 'foo*bar!', 'foo?bar', 'foo?bar!',
                  'foo[bar', 'foo[bar!', 'foo]bar', 'foo]bar!',
                  'foo%bar', 'foo%bar!', 'foo_bar', 'foo_bar!',
                  'foo/bar', 'foo/bar!', 'fo*ob?ar[fo]ob%ar_fo/obar']
        with self.env.db_transaction as db:
            db.executemany("INSERT INTO system (name,value) VALUES (%s,1)",
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

    def test_get_table_names(self):
        schema = default_schema + self.schema
        with self.env.db_query as db:
            self.assertEqual(sorted(table.name for table in schema),
                             sorted(db.get_table_names()))

    def test_get_column_names(self):
        schema = default_schema + self.schema
        with self.env.db_transaction as db:
            for table in schema:
                db_columns = db.get_column_names(table.name)
                self.assertEqual(len(table.columns), len(db_columns))
                for column in table.columns:
                    self.assertIn(column.name, db_columns)


class DatabaseManagerTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        self.dbm = DatabaseManager(self.env)

    def tearDown(self):
        self.env.reset_db()

    def test_get_default_database_version(self):
        """Get database version for the default entry named
        `database_version`.
        """
        self.assertEqual(default_db_version, self.dbm.get_database_version())

    def test_get_table_names(self):
        """Get table names for the default database."""
        self.assertEqual(sorted(table.name for table in default_schema),
                         sorted(self.dbm.get_table_names()))

    def test_set_default_database_version(self):
        """Set database version for the default entry named
        `database_version`.
        """
        new_db_version = default_db_version + 1
        self.dbm.set_database_version(new_db_version)
        self.assertEqual(new_db_version, self.dbm.get_database_version())

        # Restore the previous version to avoid destroying the database
        # on teardown
        self.dbm.set_database_version(default_db_version)
        self.assertEqual(default_db_version, self.dbm.get_database_version())

    def test_set_get_plugin_database_version(self):
        """Get and set database version for an entry with an
        arbitrary name.
        """
        name = 'a_trac_plugin_version'
        db_ver = 1

        self.assertFalse(self.dbm.get_database_version(name))
        self.dbm.set_database_version(db_ver, name)
        self.assertEqual(db_ver, self.dbm.get_database_version(name))


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(ParseConnectionStringTestCase))
    suite.addTest(unittest.makeSuite(StringsTestCase))
    suite.addTest(unittest.makeSuite(ConnectionTestCase))
    suite.addTest(unittest.makeSuite(WithTransactionTest))
    suite.addTest(unittest.makeSuite(DatabaseManagerTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
