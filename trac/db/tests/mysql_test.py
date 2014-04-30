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


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(MySQLTableAlterationSQLTest))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
