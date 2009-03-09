# -*- coding: utf-8 -*-

import re
import unittest

from trac.db import Table, Column, Index
from trac.db.postgres_backend import PostgreSQLConnector
from trac.test import EnvironmentStub


class PostgresTableCreationSQLTest(unittest.TestCase):
    def setUp(self):
        self.env = EnvironmentStub()
        self.db = self.env.get_db_cnx()
    
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
        table = Table('foo bar')
        table[Column('name'),]
        sql_generator = PostgreSQLConnector(self.env).to_sql(table)
        sql_commands = self._normalize_sql(sql_generator)
        self.assertEqual(1, len(sql_commands))
        self.assertEqual('CREATE TABLE "foo bar" ( "name" text)', sql_commands[0])
    
    def test_quote_column_names(self):
        table = Table('foo')
        table[Column('my name'),]
        sql_generator = PostgreSQLConnector(self.env).to_sql(table)
        sql_commands = self._normalize_sql(sql_generator)
        self.assertEqual(1, len(sql_commands))
        self.assertEqual('CREATE TABLE "foo" ( "my name" text)', sql_commands[0])
    
    def test_quote_compound_primary_key_declaration(self):
        table = Table('foo bar', key=['my name', 'your name'])
        table[Column('my name'), Column('your name'),]
        sql_generator = PostgreSQLConnector(self.env).to_sql(table)
        sql_commands = self._normalize_sql(sql_generator)
        self.assertEqual(1, len(sql_commands))
        expected_sql = 'CREATE TABLE "foo bar" ( "my name" text, ' + \
                       '"your name" text, CONSTRAINT "foo bar_pk" ' +\
                       'PRIMARY KEY ("my name","your name"))'
        self.assertEqual(expected_sql, sql_commands[0])
    
    def test_quote_index_declaration(self):
        table = Table('foo')
        table[Column('my name'), Index(['my name'])]
        sql_generator = PostgreSQLConnector(self.env).to_sql(table)
        sql_commands = self._normalize_sql(sql_generator)
        self.assertEqual(2, len(sql_commands))
        self.assertEqual('CREATE TABLE "foo" ( "my name" text)', sql_commands[0])
        index_sql = 'CREATE INDEX "foo_my name_idx" ON "foo" ("my name")'
        self.assertEqual(index_sql, sql_commands[1])
    
    def test_quote_index_declaration_for_multiple_indexes(self):
        table = Table('foo')
        table[Column('a'), Column('b'), 
              Index(['a', 'b'])]
        sql_generator = PostgreSQLConnector(self.env).to_sql(table)
        sql_commands = self._normalize_sql(sql_generator)
        self.assertEqual(2, len(sql_commands))
        self.assertEqual('CREATE TABLE "foo" ( "a" text, "b" text)', sql_commands[0])
        index_sql = 'CREATE INDEX "foo_a_b_idx" ON "foo" ("a","b")'
        self.assertEqual(index_sql, sql_commands[1])


def suite():
    return unittest.makeSuite(PostgresTableCreationSQLTest, 'test')

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
