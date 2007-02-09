from trac.db.mysql_backend import MySQLConnection
from trac.ticket.report import ReportModule
from trac.test import EnvironmentStub, Mock
from trac.web.api import Request, RequestDone

import unittest
from StringIO import StringIO

class MockMySQLConnection(MySQLConnection):
    def __init__(self):
        pass


class ReportTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.report_module = ReportModule(self.env)

    def _make_environ(self, scheme='http', server_name='example.org',
                      server_port=80, method='GET', script_name='/trac',
                      **kwargs):
        environ = {'wsgi.url_scheme': scheme, 'wsgi.input': StringIO(''),
                   'REQUEST_METHOD': method, 'SERVER_NAME': server_name,
                   'SERVER_PORT': server_port, 'SCRIPT_NAME': script_name}
        environ.update(kwargs)
        return environ

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

    def test_csv_escape(self):
        buf = StringIO()
        def start_response(status, headers):
            return buf.write
        environ = self._make_environ()
        req = Request(environ, start_response)
        cols = ['TEST_COL']
        rows = [('value, needs escaped',)]
        try:
            self.report_module._send_csv(req, cols, rows)
        except RequestDone:
            pass
        self.assertEqual('TEST_COL\r\n"value, needs escaped"\r\n',
                         buf.getvalue())


def suite():
    return unittest.makeSuite(ReportTestCase, 'test')

if __name__ == '__main__':
    unittest.main()
