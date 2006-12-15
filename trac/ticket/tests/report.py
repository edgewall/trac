from trac.db.mysql_backend import MySQLConnection
from trac.ticket.report import ReportModule
from trac.test import EnvironmentStub, Mock
from trac.web.api import Request, RequestDone

import unittest

class MockMySQLConnection(MySQLConnection):
    def __init__(self):
        pass


class ReportTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.report_module = ReportModule(self.env)

    def test_sub_var_no_quotes(self):
        sql, args = self.report_module.sql_sub_vars("$VAR", {'VAR': 'value'})
        self.assertEqual("%s", sql)
        self.assertEqual(['value'], args)

    def test_sub_var_quotes(self):
        sql, args = self.report_module.sql_sub_vars("'$VAR'", {'VAR': 'value'})
        self.assertEqual("''||%s||''", sql)
        self.assertEqual(['value'], args)

    def test_sub_var_mysql(self):
        env = EnvironmentStub()
        env.db = MockMySQLConnection()
        sql, args = ReportModule(env).sql_sub_vars("'$VAR'", {'VAR': 'value'})
        self.assertEqual("concat('', %s, '')", sql)
        self.assertEqual(['value'], args)


def suite():
    return unittest.makeSuite(ReportTestCase, 'test')

if __name__ == '__main__':
    unittest.main()
