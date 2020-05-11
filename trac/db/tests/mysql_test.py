# -*- coding: utf-8 -*-
#
# Copyright (C) 2010-2020 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

import unittest

import trac.tests.compat
from trac.db.mysql_backend import MySQLConnector
from trac.db.schema import Table, Column, Index
from trac.test import EnvironmentStub, Mock


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
        self.assertEqual(3, connector._max_bytes(Mock(charset='utf8')))
        self.assertEqual(4, connector._max_bytes(Mock(charset='utf8mb4')))

    def test_to_sql(self):
        connector = MySQLConnector(self.env)
        tab = Table('blah', key=('col1', 'col2', 'col3', 'col4', 'col5')) \
              [Column('col1'), Column('col2'), Column('col3'), Column('col4'),
               Column('col5'), Column('col6'),
               Index(['col2', 'col3', 'col4', 'col5'])]

        sql = list(connector.to_sql(tab, max_bytes=3))
        self.assertEqual(2, len(sql))
        self.assertIn(' PRIMARY KEY (`col1`(204),`col2`(204),`col3`(204),'
                      '`col4`(204),`col5`(204))', sql[0])
        self.assertIn(' `blah_col2_col3_col4_col5_idx` ON `blah` (`col2`(255),'
                      '`col3`(255),`col4`(255),`col5`(255))', sql[1])

        sql = list(connector.to_sql(tab, max_bytes=4))
        self.assertEqual(2, len(sql))
        self.assertIn(' PRIMARY KEY (`col1`(153),`col2`(153),`col3`(153),'
                      '`col4`(153),`col5`(153))', sql[0])
        self.assertIn(' `blah_col2_col3_col4_col5_idx` ON `blah` (`col2`(191),'
                      '`col3`(191),`col4`(191),`col5`(191))', sql[1])


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(MySQLTableAlterationSQLTest))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
