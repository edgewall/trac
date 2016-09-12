# -*- coding: utf-8 -*-
#
# Copyright (C) 2010-2013 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import itertools
import unittest

import trac.tests.compat
from trac.db.api import DatabaseManager, get_column_names
from trac.db.mysql_backend import MySQLConnector
from trac.db.schema import Table, Column, Index
from trac.test import EnvironmentStub, Mock, get_dburi


class MySQLTableAlterationSQLTest(unittest.TestCase):
    def setUp(self):
        self.env = EnvironmentStub()

    def test_alter_column_types(self):
        connector = MySQLConnector(self.env)
        sql = connector.alter_column_types('milestone',
                                           {'due': ('int', 'int64'),
                                            'completed': ('int', 'int64')})
        sql = list(sql)
        self.assertEqual([
            "ALTER TABLE milestone "
                "MODIFY completed bigint, "
                "MODIFY due bigint",
            ], sql)

    def test_alter_column_types_same(self):
        connector = MySQLConnector(self.env)
        sql = connector.alter_column_types('milestone',
                                           {'due': ('int', 'int'),
                                            'completed': ('int', 'int64')})
        sql = list(sql)
        self.assertEqual([
            "ALTER TABLE milestone "
                "MODIFY completed bigint",
            ], sql)

    def test_alter_column_types_none(self):
        connector = MySQLConnector(self.env)
        sql = connector.alter_column_types('milestone',
                                           {'due': ('int', 'int')})
        self.assertEqual([], list(sql))

    def test_utf8_size(self):
        connector = MySQLConnector(self.env)
        self.assertEqual(3, connector._utf8_size(Mock(charset='utf8')))
        self.assertEqual(4, connector._utf8_size(Mock(charset='utf8mb4')))

    def test_to_sql(self):
        connector = MySQLConnector(self.env)
        tab = Table('blah', key=('col1', 'col2'))[Column('col1'),
                                                  Column('col2'),
                                                  Index(['col2'])]

        sql = list(connector.to_sql(tab, utf8_size=3))
        self.assertEqual(2, len(sql))
        self.assertIn(' PRIMARY KEY (`col1`(166),`col2`(166))', sql[0])
        self.assertIn(' blah_col2_idx ON blah (`col2`(255))', sql[1])

        sql = list(connector.to_sql(tab, utf8_size=4))
        self.assertEqual(2, len(sql))
        self.assertIn(' PRIMARY KEY (`col1`(125),`col2`(125))', sql[0])
        self.assertIn(' blah_col2_idx ON blah (`col2`(191))', sql[1])


class MySQLConnectionTestCase(unittest.TestCase):

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
                Index(['name', 'enabled'], unique=True),
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

    def _show_index(self, table):
        with self.env.db_query as db:
            cursor = db.cursor()
            cursor.execute("SHOW INDEX FROM " + db.quote(table))
            columns = get_column_names(cursor)
            rows = [dict(zip(columns, row)) for row in cursor]
            results = {}
            for index, group in itertools.groupby(rows, lambda v: v['Key_name']):
                group = list(group)
                results[index] = {
                    'unique': not group[0]['Non_unique'],
                    'columns': [row['Column_name'] for row in group],
                }
            return results

    def _drop_column(self, table, column):
        with self.env.db_transaction as db:
            db.drop_column(table, column)

    def _query(self, stmt, *args):
        return self.env.db_query(stmt, args)

    def test_remove_simple_keys(self):
        indices_0 = self._show_index('test_simple')
        self.assertEqual(['PRIMARY', 'test_simple_email_idx',
                          'test_simple_username_idx'],
                         sorted(indices_0))
        self.assertEqual({'unique': True, 'columns': ['id']},
                         indices_0['PRIMARY'])
        self.assertEqual({'unique': True, 'columns': ['username']},
                         indices_0['test_simple_username_idx'])
        self.assertEqual({'unique': False, 'columns': ['email']},
                         indices_0['test_simple_email_idx'])

        self._drop_column('test_simple', 'enabled')
        self.assertEqual(indices_0, self._show_index('test_simple'))

        self._drop_column('test_simple', 'username')
        indices_1 = self._show_index('test_simple')
        self.assertEqual(['PRIMARY', 'test_simple_email_idx'],
                         sorted(indices_1))

        self._drop_column('test_simple', 'email')
        indices_2 = self._show_index('test_simple')
        self.assertEqual(['PRIMARY'], sorted(indices_2))

        self._drop_column('test_simple', 'id')
        indices_3 = self._show_index('test_simple')
        self.assertEqual({}, indices_3)

    def test_remove_composite_keys(self):
        indices_0 = self._show_index('test_composite')
        self.assertEqual(['PRIMARY', 'test_composite_name_enabled_idx',
                          'test_composite_name_value_idx'],
                         sorted(indices_0))
        self.assertEqual({'unique': True, 'columns': ['id', 'name']},
                         indices_0['PRIMARY'])
        self.assertEqual({'unique': False, 'columns': ['name', 'value']},
                         indices_0['test_composite_name_value_idx'])
        self.assertEqual({'unique': True, 'columns': ['name', 'enabled']},
                         indices_0['test_composite_name_enabled_idx'])

        self._drop_column('test_composite', 'id')
        indices_1 = self._show_index('test_composite')
        self.assertEqual(['test_composite_name_enabled_idx',
                          'test_composite_name_value_idx'],
                         sorted(indices_1))
        self.assertEqual(indices_0['test_composite_name_value_idx'],
                         indices_1['test_composite_name_value_idx'])
        self.assertEqual(indices_0['test_composite_name_enabled_idx'],
                         indices_1['test_composite_name_enabled_idx'])
        rows = self._query("""SELECT * FROM test_composite
                              ORDER BY name, value, enabled""")
        self.assertEqual([('bar', '42', 1), ('bar', '43', 0),
                          ('foo', '42', 1), ('foo', '43', 0)], rows)

        self._drop_column('test_composite', 'name')
        self.assertEqual({}, self._show_index('test_composite'))
        rows = self._query("""SELECT * FROM test_composite
                              ORDER BY value, enabled""")
        self.assertEqual([('42', 1), ('42', 1), ('43', 0), ('43', 0)], rows)


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(MySQLTableAlterationSQLTest))
    if get_dburi().startswith('mysql:'):
        suite.addTest(unittest.makeSuite(MySQLConnectionTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
