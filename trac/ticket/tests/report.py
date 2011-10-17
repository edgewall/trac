# -*- coding: utf-8 -*-

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

    def tearDown(self):
        self.env.reset_db()

    def _make_environ(self, scheme='http', server_name='example.org',
                      server_port=80, method='GET', script_name='/trac',
                      **kwargs):
        environ = {'wsgi.url_scheme': scheme, 'wsgi.input': StringIO(''),
                   'REQUEST_METHOD': method, 'SERVER_NAME': server_name,
                   'SERVER_PORT': server_port, 'SCRIPT_NAME': script_name}
        environ.update(kwargs)
        return environ

    def test_sub_var_no_quotes(self):
        sql, values, missing_args = self.report_module.sql_sub_vars(
            "$VAR", {'VAR': 'value'})
        self.assertEqual("%s", sql)
        self.assertEqual(['value'], values)
        self.assertEqual([], missing_args)

    def test_sub_var_digits_underscore(self):
        sql, values, missing_args = self.report_module.sql_sub_vars(
            "$_VAR, $VAR2, $2VAR", {'_VAR': 'value1', 'VAR2': 'value2'})
        self.assertEqual("%s, %s, $2VAR", sql)
        self.assertEqual(['value1', 'value2'], values)
        self.assertEqual([], missing_args)
        
    def test_sub_var_quotes(self):
        sql, values, missing_args = self.report_module.sql_sub_vars(
            "'$VAR'", {'VAR': 'value'})
        self.assertEqual(self.env.get_db_cnx().concat("''", '%s', "''"), sql)
        self.assertEqual(['value'], values)
        self.assertEqual([], missing_args)

    # Probably not needed anymore
    def test_sub_var_mysql(self):
        env = EnvironmentStub()
        env.db = MockMySQLConnection() # ditto
        sql, values, missing_args = ReportModule(env).sql_sub_vars(
            "'$VAR'", {'VAR': 'value'})
        self.assertEqual("concat('', %s, '')", sql)
        self.assertEqual(['value'], values)
        self.assertEqual([], missing_args)

    def test_sub_var_missing_args(self):
        sql, values, missing_args = self.report_module.sql_sub_vars(
            "$VAR, $PARAM, $MISSING", {'VAR': 'value'})
        self.assertEqual("%s, %s, %s", sql)
        self.assertEqual(['value', '', ''], values)
        self.assertEqual(['PARAM', 'MISSING'], missing_args)

    def test_csv_escape(self):
        buf = StringIO()
        def start_response(status, headers):
            return buf.write
        environ = self._make_environ()
        req = Request(environ, start_response)
        cols = ['TEST_COL', 'TEST_ZERO']
        rows = [('value, needs escaped', 0)]
        try:
            self.report_module._send_csv(req, cols, rows)
        except RequestDone:
            pass
        self.assertEqual('TEST_COL,TEST_ZERO\r\n"value, needs escaped",0\r\n',
                         buf.getvalue())

    def test_saved_custom_query_redirect(self):
        query = u'query:?type=résumé'
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("INSERT INTO report (title,query,description) "
                       "VALUES (%s,%s,%s)", ('redirect', query, ''))
        id = db.get_last_id(cursor, 'report')
        db.commit()

        headers_sent = {}
        def start_response(status, headers):
            headers_sent.update(dict(headers))
        environ = self._make_environ()
        req = Request(environ, start_response)
        req.authname = 'anonymous'
        req.session = Mock(save=lambda: None)
        self.assertRaises(RequestDone,
                          self.report_module._render_view, req, id)
        self.assertEqual('http://example.org/trac/query?' + \
                         'type=r%C3%A9sum%C3%A9&report=' + str(id),
                         headers_sent['Location'])


def suite():
    return unittest.makeSuite(ReportTestCase, 'test')

if __name__ == '__main__':
    unittest.main()
