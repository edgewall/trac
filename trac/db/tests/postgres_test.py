# -*- coding: utf-8 -*-
#
# Copyright (C) 2009-2013 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import re
import unittest

from trac.db.api import DatabaseManager
from trac.db.postgres_backend import PostgreSQLConnector, assemble_pg_dsn
from trac.db.schema import Table, Column, Index
from trac.test import EnvironmentStub, get_dburi


class PostgresTableCreationSQLTest(unittest.TestCase):
    def setUp(self):
        self.env = EnvironmentStub()

    def _unroll_generator(self, generator):
        items = []
        for item in generator:
            items.append(item)
        return items

    def _normalize_sql(self, sql_generator):
        normalized_commands = []
        whitespace_regex = re.compile(r'\s+')
        commands = self._unroll_generator(sql_generator)
        for command in commands:
            command = command.replace('\n', '')
            command = whitespace_regex.sub(' ', command)
            normalized_commands.append(command)
        return normalized_commands

    def test_quote_table_name(self):
        table = Table('foo"bar')
        table[Column('name'),]
        sql_generator = PostgreSQLConnector(self.env).to_sql(table)
        sql_commands = self._normalize_sql(sql_generator)
        self.assertEqual(1, len(sql_commands))
        self.assertEqual('CREATE TABLE "foo""bar" ( "name" text)',
                         sql_commands[0])

    def test_quote_column_names(self):
        table = Table('foo')
        table[Column('my"name'),]
        sql_generator = PostgreSQLConnector(self.env).to_sql(table)
        sql_commands = self._normalize_sql(sql_generator)
        self.assertEqual(1, len(sql_commands))
        self.assertEqual('CREATE TABLE "foo" ( "my""name" text)',
                         sql_commands[0])

    def test_quote_compound_primary_key_declaration(self):
        table = Table('foo"bar', key=['my name', 'your"name'])
        table[Column('my name'), Column('your"name'),]
        sql_generator = PostgreSQLConnector(self.env).to_sql(table)
        sql_commands = self._normalize_sql(sql_generator)
        self.assertEqual(1, len(sql_commands))
        expected_sql = 'CREATE TABLE "foo""bar" ( "my name" text, ' + \
                       '"your""name" text, CONSTRAINT "foo""bar_pk" ' +\
                       'PRIMARY KEY ("my name","your""name"))'
        self.assertEqual(expected_sql, sql_commands[0])

    def test_quote_index_declaration(self):
        table = Table('foo')
        table[Column('my"name'), Index(['my"name'])]
        sql_generator = PostgreSQLConnector(self.env).to_sql(table)
        sql_commands = self._normalize_sql(sql_generator)
        self.assertEqual(2, len(sql_commands))
        self.assertEqual('CREATE TABLE "foo" ( "my""name" text)',
                         sql_commands[0])
        index_sql = 'CREATE INDEX "foo_my""name_idx" ON "foo" ("my""name")'
        self.assertEqual(index_sql, sql_commands[1])

    def test_quote_index_declaration_for_multiple_indexes(self):
        table = Table('foo')
        table[Column('a'), Column('b"c'),
              Index(['a', 'b"c'])]
        sql_generator = PostgreSQLConnector(self.env).to_sql(table)
        sql_commands = self._normalize_sql(sql_generator)
        self.assertEqual(2, len(sql_commands))
        self.assertEqual('CREATE TABLE "foo" ( "a" text, "b""c" text)',
                         sql_commands[0])
        index_sql = 'CREATE INDEX "foo_a_b""c_idx" ON "foo" ("a","b""c")'
        self.assertEqual(index_sql, sql_commands[1])

    def test_assemble_dsn(self):
        values = [
            {'path': 't', 'user': 't'},
            {'path': 't', 'password': 't'},
            {'path': 't', 'host': 't'},
            {'path': 't', 'port': 't'},
            {'path': 't', 'password': 't', 'user': 't'},
            {'path': 't', 'host': 't', 'user': 't'},
            {'path': 't', 'user': 't', 'port': 't'},
            {'path': 't', 'host': 't', 'password': 't'},
            {'path': 't', 'password': 't', 'port': 't'},
            {'path': 't', 'host': 't', 'port': 't'},
            {'path': 't', 'host': 't', 'password': 't', 'user': 't'},
            {'path': 't', 'password': 't', 'user': 't', 'port': 't'},
            {'path': 't', 'host': 't', 'user': 't', 'port': 't'},
            {'path': 't', 'host': 't', 'password': 't', 'port': 't'},
        ]
        for orig in values:
            dsn = assemble_pg_dsn(**orig)
            for k, v in orig.iteritems():
                orig[k] = "'%s'" % v
                continue
            orig['dbname'] = "'t'"
            del orig['path']
            new_values = {'dbname': "'t'"}
            for key_value in dsn.split(' '):
                k, v = key_value.split('=')
                new_values[k] = v
                continue
            self.assertEqual(new_values, orig)
            continue

    def test_assemble_dsn_quoting(self):
        self.assertEqual(
            ["dbname='/trac'", "password='pass'", "user='user'"],
            sorted(assemble_pg_dsn('/trac', 'user', 'pass').split(' ')))
        self.assertEqual(
            ["dbname='/trac'", r"password='pa\'ss'", "user='user'"],
            sorted(assemble_pg_dsn('/trac', 'user', "pa'ss").split(' ')))
        self.assertEqual(
            ["dbname='/trac'", r"password='pa\\ss'", "user='user'"],
            sorted(assemble_pg_dsn('/trac', 'user', r'pa\ss').split(' ')))
        self.assertEqual(
            ["dbname='/trac'", r"password='pa\\\'ss'", "user='user'"],
            sorted(assemble_pg_dsn('/trac', 'user', r"pa\'ss").split(' ')))


class PostgresTableAlterationSQLTest(unittest.TestCase):
    def setUp(self):
        self.env = EnvironmentStub()

    def test_alter_column_types(self):
        connector = PostgreSQLConnector(self.env)
        sql = connector.alter_column_types('milestone',
                                           {'due': ('int', 'int64'),
                                            'completed': ('int', 'int64')})
        sql = list(sql)
        self.assertEqual([
            'ALTER TABLE "milestone" '
                'ALTER COLUMN "completed" TYPE bigint, '
                'ALTER COLUMN "due" TYPE bigint',
            ], sql)

    def test_alter_column_types_same(self):
        connector = PostgreSQLConnector(self.env)
        sql = connector.alter_column_types('milestone',
                                           {'due': ('int', 'int'),
                                            'completed': ('int', 'int64')})
        sql = list(sql)
        self.assertEqual([
            'ALTER TABLE "milestone" '
                'ALTER COLUMN "completed" TYPE bigint',
            ], sql)

    def test_alter_column_types_none(self):
        connector = PostgreSQLConnector(self.env)
        sql = connector.alter_column_types('milestone',
                                           {'due': ('int', 'int')})
        self.assertEqual([], list(sql))


class PostgresConnectionTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.schema = [
            Table('test_simple', key='id')[
                Column('id', auto_increment=True),
                Column('username'),
                Column('email'),
                Column('enabled', type='int'),
                Column('extra'),
                Index(['username'], unique=True),
                Index(['email'], unique=False),
            ],
            Table('test_composite', key=['id', 'name'])[
                Column('id', type='int'),
                Column('name'),
                Column('value'),
                Column('enabled', type='int'),
                Index(['name', 'value'], unique=False),
                Index(['enabled', 'name'], unique=True),
            ],
        ]
        self.dbm = DatabaseManager(self.env)
        self.dbm.drop_tables(self.schema)
        self.dbm.create_tables(self.schema)
        self.dbm.insert_into_tables([
            ('test_simple',
             ('username', 'email', 'enabled'),
             [('joe', 'joe@example.org', 1), (u'joé', 'joe@example.org', 0)]),
            ('test_composite',
             ('id', 'name', 'value', 'enabled'),
             [(1, 'foo', '42', 1),
              (1, 'bar', '42', 1),
              (2, 'foo', '43', 0),
              (2, 'bar', '43', 0)]),
        ])

    def tearDown(self):
        DatabaseManager(self.env).drop_tables(self.schema)
        self.env.reset_db()

    def _drop_column(self, table, column):
        with self.env.db_transaction as db:
            db.drop_column(table, column)

    def _get_indices(self, table):
        with self.env.db_query:
            tab_oid = self._query("""
                SELECT tab.oid FROM pg_class tab
                INNER JOIN pg_namespace ns ON
                    ns.oid = tab.relnamespace AND
                    ns.nspname = ANY (current_schemas(false))
                WHERE tab.relname=%s AND tab.relkind = 'r'
                """, table)[0][0]
            column_names = self._query("""
                SELECT attnum, attname FROM pg_attribute
                WHERE attrelid=%s AND attnum >= 0 AND NOT attisdropped
                """, tab_oid)
            column_names = dict((row[0], row[1]) for row in column_names)
            indices = self._query("""
                SELECT ind.relname, d.indisprimary, d.indisunique, d.indkey
                FROM pg_index d
                INNER JOIN pg_class ind ON
                    d.indexrelid = ind.oid AND ind.relkind = 'i'
                WHERE d.indrelid=%s
                """, tab_oid)
            results = {}
            for index, pk, unique, indkey in indices:
                columns = [column_names[int(i)] for i in indkey.split()]
                results[index] = {'pk': bool(pk), 'unique': bool(unique),
                                  'columns': columns}
        return results

    def _query(self, stmt, *args):
        return self.env.db_query(stmt, args)

    def test_remove_simple_keys(self):
        indices_0 = self._get_indices('test_simple')
        self.assertEqual(['test_simple_email_idx', 'test_simple_pkey',
                          'test_simple_username_idx'],
                         sorted(indices_0))
        self.assertEqual({'pk': False, 'unique': True,
                          'columns': ['username']},
                         indices_0['test_simple_username_idx'])
        self.assertEqual({'pk': True, 'unique': True, 'columns': ['id']},
                         indices_0['test_simple_pkey'])
        self.assertEqual({'pk': False, 'unique': False, 'columns': ['email']},
                         indices_0['test_simple_email_idx'])

        self._drop_column('test_simple', 'enabled')
        self.assertEqual(indices_0, self._get_indices('test_simple'))

        self._drop_column('test_simple', 'username')
        indices_1 = self._get_indices('test_simple')
        self.assertEqual(['test_simple_email_idx', 'test_simple_pkey'],
                         sorted(indices_1))

        self._drop_column('test_simple', 'email')
        indices_2 = self._get_indices('test_simple')
        self.assertEqual(['test_simple_pkey'], sorted(indices_2))

        self._drop_column('test_simple', 'id')
        indices_3 = self._get_indices('test_simple')
        self.assertEqual({}, indices_3)

    def test_remove_composite_keys(self):
        indices_0 = self._get_indices('test_composite')
        self.assertEqual(['test_composite_enabled_name_idx',
                          'test_composite_name_value_idx',
                          'test_composite_pk'],
                         sorted(indices_0))
        self.assertEqual({'pk': False, 'unique': False,
                          'columns': ['name', 'value']},
                         indices_0['test_composite_name_value_idx'])
        self.assertEqual({'pk': False, 'unique': True,
                          'columns': ['enabled', 'name']},
                         indices_0['test_composite_enabled_name_idx'])
        self.assertEqual({'pk': True, 'unique': True,
                          'columns': ['id', 'name']},
                         indices_0['test_composite_pk'])

        self._drop_column('test_composite', 'id')
        indices_1 = self._get_indices('test_composite')
        self.assertEqual(['test_composite_enabled_name_idx',
                          'test_composite_name_value_idx'],
                         sorted(indices_1))
        self.assertEqual(indices_0['test_composite_name_value_idx'],
                         indices_1['test_composite_name_value_idx'])
        self.assertEqual(indices_0['test_composite_enabled_name_idx'],
                         indices_1['test_composite_enabled_name_idx'])
        rows = self._query("""SELECT * FROM test_composite
                              ORDER BY name, value, enabled""")
        self.assertEqual([('bar', '42', 1), ('bar', '43', 0),
                          ('foo', '42', 1), ('foo', '43', 0)], rows)

        self._drop_column('test_composite', 'name')
        self.assertEqual({}, self._get_indices('test_composite'))
        rows = self._query("""SELECT * FROM test_composite
                              ORDER BY value, enabled""")
        self.assertEqual([('42', 1), ('42', 1), ('43', 0), ('43', 0)], rows)


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(PostgresTableCreationSQLTest))
    suite.addTest(unittest.makeSuite(PostgresTableAlterationSQLTest))
    if get_dburi().startswith('postgres:'):
        suite.addTest(unittest.makeSuite(PostgresConnectionTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
