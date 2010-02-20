# -*- coding: utf-8 -*-
#
# Copyright (C) 2009 Edgewall Software
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

from trac.db.mysql_backend import MySQLConnector
from trac.test import EnvironmentStub


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


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(MySQLTableAlterationSQLTest, 'test'))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
