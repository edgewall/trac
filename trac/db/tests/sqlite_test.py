# -*- coding: utf-8 -*-
#
# Copyright (C) 2015 Edgewall Software
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
import tempfile
import unittest

from trac.config import ConfigurationError
from trac.db.api import DatabaseManager
from trac.db.schema import Column, Index, Table
from trac.env import Environment
from trac.test import EnvironmentStub, MockRequest, get_dburi, rmtree
from trac.util import translation


class DatabaseFileTestCase(unittest.TestCase):

    def setUp(self):
        self.env_path = tempfile.mkdtemp(prefix='trac-tempenv-')
        self.db_path = os.path.join(self.env_path, 'db', 'trac.db')
        self.env = None

    def tearDown(self):
        if self.env:
            self.env.shutdown()
        rmtree(self.env_path)

    def _create_env(self):
        env = Environment(self.env_path, create=True)
        env.shutdown()

    def _db_query(self, env):
        env.db_query("SELECT name FROM system")

    def test_missing_tracdb(self):
        self._create_env()
        os.remove(self.db_path)
        self.env = Environment(self.env_path)
        try:
            self._db_query(self.env)
            self.fail('ConfigurationError not raised')
        except ConfigurationError as e:
            self.assertIn('Database "', unicode(e))
            self.assertIn('" not found.', unicode(e))

    def test_no_permissions(self):
        self._create_env()
        os.chmod(self.db_path, 0444)
        self.env = Environment(self.env_path)
        try:
            self._db_query(self.env)
            self.fail('ConfigurationError not raised')
        except ConfigurationError as e:
            self.assertIn('requires read _and_ write permissions', unicode(e))

    if os.name == 'posix' and os.getuid() == 0:
        del test_no_permissions  # For root, os.access() always returns True

    def test_error_with_lazy_translation(self):
        self._create_env()
        os.remove(self.db_path)
        self.env = Environment(self.env_path)
        req = MockRequest(self.env, authname='trac_auth=1234567890')
        translation.make_activable(lambda: req.locale, self.env.path)
        try:
            self._db_query(self.env)
            self.fail('ConfigurationError not raised')
        except ConfigurationError as e:
            message = unicode(e)
            self.assertIn('Database "', message)
            self.assertIn('" not found.', message)
        finally:
            translation.deactivate()


class SQLiteConnectionTestCase(unittest.TestCase):

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

    def _table_info(self, table):
        names = ('column', 'type', 'notnull', 'default', 'pk')
        with self.env.db_query as db:
            cursor = db.cursor()
            cursor.execute("PRAGMA table_info(%s)" % db.quote(table))
            return [dict(zip(names, row[1:6])) for row in cursor]

    def _index_info(self, table):
        with self.env.db_query as db:
            cursor = db.cursor()
            cursor.execute("PRAGMA index_list(%s)" % db.quote(table))
            results = dict((row[1], {'unique': row[2]}) for row in cursor)
            for index, info in results.iteritems():
                cursor.execute("PRAGMA index_info(%s)" % db.quote(index))
                info['columns'] = [row[2] for row in cursor]
        return results

    def _drop_column(self, table, column):
        with self.env.db_transaction as db:
            db.drop_column(table, column)

    def _query(self, stmt, *args):
        return self.env.db_query(stmt, args)

    def test_remove_simple_keys(self):
        coldef = {
            'id':       {'column': 'id', 'type': 'integer', 'notnull': 0,
                         'default': None, 'pk': 1},
            'username': {'column': 'username', 'type': 'text',
                         'notnull': 0, 'default': None, 'pk': 0},
            'email':    {'column': 'email', 'type': 'text', 'notnull': 0,
                         'default': None, 'pk': 0},
            'enabled':  {'column': 'enabled', 'type': 'integer',
                         'notnull': 0, 'default': None, 'pk': 0},
            'extra':    {'column': 'extra', 'type': 'text',
                         'notnull': 0, 'default': None, 'pk': 0},
        }
        columns_0 = self._table_info('test_simple')
        self.assertEqual([coldef['id'], coldef['username'], coldef['email'],
                          coldef['enabled'], coldef['extra']], columns_0)
        indices_0 = self._index_info('test_simple')
        self.assertEqual(['test_simple_email_idx', 'test_simple_username_idx'],
                         sorted(indices_0))

        self._drop_column('test_simple', 'extra')
        columns_1 = self._table_info('test_simple')
        indices_1 = self._index_info('test_simple')
        self.assertEqual([coldef['id'], coldef['username'], coldef['email'],
                          coldef['enabled']], columns_1)
        self.assertEqual(indices_1, indices_0)

        self._drop_column('test_simple', 'id')
        columns_2 = self._table_info('test_simple')
        indices_2 = self._index_info('test_simple')
        self.assertEqual([coldef['username'], coldef['email'],
                          coldef['enabled']], columns_2)
        self.assertEqual(indices_2, indices_0)

        self._drop_column('test_simple', 'username')
        columns_3 = self._table_info('test_simple')
        indices_3 = self._index_info('test_simple')
        self.assertEqual([coldef['email'], coldef['enabled']], columns_3)
        self.assertEqual(['test_simple_email_idx'], sorted(indices_3))

        self._drop_column('test_simple', 'email')
        columns_4 = self._table_info('test_simple')
        indices_4 = self._index_info('test_simple')
        self.assertEqual([coldef['enabled']], columns_4)
        self.assertEqual({}, indices_4)

    def test_remove_composite_keys(self):
        indices_0 = self._index_info('test_composite')
        self.assertEqual(['sqlite_autoindex_test_composite_1',
                          'test_composite_name_enabled_idx',
                          'test_composite_name_value_idx'],
                         sorted(indices_0))
        self.assertEqual({'unique': 1, 'columns': ['id', 'name']},
                         indices_0['sqlite_autoindex_test_composite_1'])
        self.assertEqual({'unique': 0, 'columns': ['name', 'value']},
                         indices_0['test_composite_name_value_idx'])
        self.assertEqual({'unique': 1, 'columns': ['name', 'enabled']},
                         indices_0['test_composite_name_enabled_idx'])

        self._drop_column('test_composite', 'id')
        indices_1 = self._index_info('test_composite')
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
        self.assertEqual({}, self._index_info('test_composite'))
        rows = self._query("""SELECT * FROM test_composite
                              ORDER BY value, enabled""")
        self.assertEqual([('42', 1), ('42', 1), ('43', 0), ('43', 0)], rows)


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(DatabaseFileTestCase))
    if get_dburi().startswith('sqlite:'):
        suite.addTest(unittest.makeSuite(SQLiteConnectionTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
