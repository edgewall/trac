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

from trac.db import Table, Column, Index
from trac.db.postgres_backend import PostgreSQLConnector, assemble_pg_dsn
from trac.test import EnvironmentStub


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


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(PostgresTableCreationSQLTest))
    suite.addTest(unittest.makeSuite(PostgresTableAlterationSQLTest))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
