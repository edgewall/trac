# -*- coding: utf-8 -*-
#
# Copyright (C) 2006-2018 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import doctest
import unittest
from datetime import datetime, timedelta

import trac
import trac.tests.compat
from trac.perm import PermissionSystem
from trac.resource import ResourceNotFound
from trac.ticket.model import Ticket
from trac.ticket.query import QueryModule
from trac.ticket.report import Report, ReportModule
from trac.test import EnvironmentStub, MockRequest
from trac.util.datefmt import utc
from trac.web.api import HTTPBadRequest, RequestDone
from trac.web.chrome import Chrome


class ReportModuleTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        self.report_module = ReportModule(self.env)

    def tearDown(self):
        self.env.reset_db()

    def test_create_report(self):
        req = MockRequest(self.env, method='POST', args={
            'action': 'new',
            'title': "New Report",
            'query': "SELECT 1",
            'description': "The description"})

        self.assertRaises(RequestDone,
                          self.report_module.process_request, req)
        self.assertTrue(Report(self.env, 9).exists)
        self.assertIn("The report has been created.",
                      req.chrome['notices'])
        self.assertEqual('http://example.org/trac.cgi/report/9',
                         req.headers_sent['Location'])

    def test_create_report_cancel(self):
        req = MockRequest(self.env, method='POST', args={
            'action': 'new',
            'cancel': True,
            'title': "New Report",
            'query': "SELECT 1",
            'description': "The description"})

        self.assertRaises(RequestDone, self.report_module.process_request,
                          req)
        self.assertRaises(ResourceNotFound, Report, self.env, 9)
        self.assertNotIn("The report has been created.",
                         req.chrome['notices'])
        self.assertEqual('http://example.org/trac.cgi/report',
                         req.headers_sent['Location'])

    def test_delete_report(self):
        req = MockRequest(self.env, method='POST', args={
            'action': 'delete',
            'id': '1'})

        self.assertRaises(RequestDone, self.report_module.process_request,
                          req)
        self.assertRaises(ResourceNotFound, Report, self.env, 1)
        self.assertIn("The report {1} has been deleted.",
                      req.chrome['notices'])
        self.assertEqual('http://example.org/trac.cgi/report',
                         req.headers_sent['Location'])

    def test_delete_report_cancel(self):
        req = MockRequest(self.env, method='POST', args={
            'action': 'delete',
            'cancel': True,
            'id': '1'})

        self.assertRaises(RequestDone, self.report_module.process_request,
                          req)
        self.assertTrue(Report(self.env, 1).exists)
        self.assertNotIn("The report {1} has been deleted.",
                         req.chrome['notices'])
        self.assertEqual('http://example.org/trac.cgi/report/1',
                         req.headers_sent['Location'])

    def test_update_report(self):
        report = Report(self.env)
        report.query = "SELECT 1"
        report.insert()
        req = MockRequest(self.env, method='POST', args={
            'action': 'edit',
            'id': '1',
            'title': "New Report edited",
            'query': "SELECT 2",
            'description': "The description edited"})

        self.assertRaises(RequestDone, self.report_module.process_request,
                          req)
        report = Report(self.env, 1)
        self.assertEqual("New Report edited", report.title)
        self.assertEqual("SELECT 2", report.query)
        self.assertEqual("The description edited", report.description)
        self.assertIn("Your changes have been saved.", req.chrome['notices'])

    def test_update_report_cancel(self):
        report = Report(self.env)
        report.query = "SELECT 1"
        report.insert()
        req = MockRequest(self.env, method='POST', args={
            'action': 'edit',
            'cancel': True,
            'id': '1',
            'title': "New Report edited",
            'query': "SELECT 2",
            'description': "The description edited"})

        self.assertRaises(RequestDone, self.report_module.process_request,
                          req)
        report = Report(self.env, 1)
        self.assertEqual("Active Tickets", report.title)
        self.assertEqual(" * List all active tickets by priority.\n"
                         " * Color each row based on priority.\n",
                         report.description)
        self.assertIn("SELECT p.value AS __color__", report.query)
        self.assertNotIn("Your changes have been saved.",
                         req.chrome['notices'])

    def test_render_confirm_delete(self):
        req = MockRequest(self.env, method='GET', args={
            'action': 'delete',
            'id': '1'})

        data = self.report_module.process_request(req)[1]

        self.assertEqual("Delete Report {1} Active Tickets", data['title'])
        self.assertEqual('delete', data['action'])
        self.assertEqual(1, data['report']['id'])
        self.assertEqual('Active Tickets', data['report']['title'])

    def test_render_editor(self):
        req = MockRequest(self.env, method='GET', args={
            'action': 'edit',
            'id': '1'})

        data = self.report_module.process_request(req)[1]

        self.assertEqual(1, data['report']['id'])
        self.assertEqual("Active Tickets", data['report']['title'])
        self.assertEqual(" * List all active tickets by priority.\n"
                         " * Color each row based on priority.\n",
                         data['report']['description'])
        self.assertIn("SELECT p.value AS __color__", data['report']['sql'])

    def test_render_list(self):
        req = MockRequest(self.env, method='GET', args={
            'action': 'view',
            'id': '-1'})

        data = self.report_module.process_request(req)[1]

        self.assertEqual('report', data['sort'])
        self.assertEqual(1, data['asc'])
        self.assertEqual(8, len(data['reports']))
        self.assertEqual(1, data['reports'][0][0])
        self.assertEqual('Active Tickets', data['reports'][0][1])
        self.assertEqual(" * List all active tickets by priority.\n"
                         " * Color each row based on priority.\n",
                         data['reports'][0][2])
        self.assertTrue('Active Reports', data['reports'][0][3])
        self.assertTrue('Active Reports', data['reports'][0][4])

    def test_render_view(self):
        req = MockRequest(self.env, method='GET', args={
            'action': 'view',
            'id': '1'})

        data = self.report_module.process_request(req)[1]

        self.assertEqual(1, data['report']['id'])
        self.assertEqual("{1} Active Tickets", data['title'])
        self.assertEqual(" * List all active tickets by priority.\n"
                         " * Color each row based on priority.\n",
                         data['description'])

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
        with self.env.db_query as db:
            concatenated = db.concat("''", '%s', "''")
        self.assertEqual(concatenated, sql)
        self.assertEqual(['value'], values)
        self.assertEqual([], missing_args)

    def test_sub_var_missing_args(self):
        sql, values, missing_args = self.report_module.sql_sub_vars(
            "$VAR, $PARAM, $MISSING", {'VAR': 'value'})
        self.assertEqual("%s, %s, %s", sql)
        self.assertEqual(['value', '', ''], values)
        self.assertEqual(['PARAM', 'MISSING'], missing_args)

    def test_csv_escape(self):
        req = MockRequest(self.env)
        cols = ['TEST_COL', 'TEST_ZERO']
        rows = [('value, needs escaped', 0)]

        self.assertRaises(RequestDone,
                          self.report_module._send_csv, req, cols, rows)
        self.assertEqual('\xef\xbb\xbfTEST_COL,TEST_ZERO\r\n"'
                         'value, needs escaped",0\r\n',
                         req.response_sent.getvalue())

    def test_saved_custom_query_redirect(self):
        query = u'query:?type=résumé'
        with self.env.db_transaction as db:
            cursor = db.cursor()
            cursor.execute("INSERT INTO report (title,query,description) "
                           "VALUES (%s,%s,%s)", ('redirect', query, ''))
            id = db.get_last_id(cursor, 'report')
        req = MockRequest(self.env)

        self.assertRaises(RequestDone,
                          self.report_module._render_view, req, id)
        self.assertEqual('http://example.org/trac.cgi/query?' +
                         'type=r%C3%A9sum%C3%A9&report=' + str(id),
                         req.headers_sent['Location'])

    def test_quoted_id_with_var(self):
        req = MockRequest(self.env)
        name = """%s"`'%%%?"""
        with self.env.db_query as db:
            sql = 'SELECT 1 AS %s, $USER AS user' % db.quote(name)
            rv = self.report_module.execute_paginated_report(req, 1, sql,
                                                             {'USER': 'joe'})
        self.assertEqual(5, len(rv), repr(rv))
        cols, results, num_items, missing_args, limit_offset = rv
        self.assertEqual([name, 'user'], cols)
        self.assertEqual([(1, 'joe')], results)
        self.assertEqual([], missing_args)
        self.assertEqual(None, limit_offset)

    def test_with_no_sql(self):
        with self.env.db_transaction as db:
            cursor = db.cursor()
            cursor.execute("""INSERT INTO report (title,query,description)
                              VALUES ('#12709', '', '')""")
            id_ = db.get_last_id(cursor, 'report')
        req = MockRequest(self.env, path_info='/report/%d' % id_)
        self.assertTrue(self.report_module.match_request(req))
        data = self.report_module.process_request(req)[1]
        self.assertEqual('Report failed: Report {%d} has no SQL query.' % id_,
                         data['message'])

    def test_value_error_from_get_var_args(self):
        req = MockRequest(self.env, path_info='/report/1')
        def get_var_args(req):
            raise ValueError('<error>')
        self.report_module.get_var_args = get_var_args
        self.assertTrue(self.report_module.match_request(req))
        data = self.report_module.process_request(req)[1]
        self.assertEqual('Report failed: <error>', data['message'])

    def test_title_and_description_with_sub_vars(self):
        with self.env.db_transaction as db:
            cursor = db.cursor()
            cursor.execute(
                """INSERT INTO report (title,query,description)
                   VALUES (%s,%s,%s)""",
                ('Tickets on $M for $USER',
                 'SELECT * FROM ticket WHERE milestone=$M AND owner=$USER',
                 'Show tickets on $M for $USER'))
            id_ = db.get_last_id(cursor, 'report')
            for milestone in ('milestone1', 'milestone2'):
                ticket = Ticket(self.env)
                ticket.populate({'status': 'new', 'summary': 'Test 1',
                                 'owner': 'joe', 'milestone': milestone})
                ticket.insert()
        req = MockRequest(self.env, path_info='/report/%d' % id_,
                          authname='joe', args={'M': 'milestone2'})
        self.assertTrue(self.report_module.match_request(req))
        data = self.report_module.process_request(req)[1]
        self.assertEqual('{%d} Tickets on milestone2 for joe' % id_,
                         data['title'])
        self.assertEqual('Show tickets on milestone2 for joe',
                         data['description'])
        self.assertIsNone(data['message'])
        self.assertEqual(1, data['numrows'])

    def test_clear(self):
        req = MockRequest(self.env, method='GET', path_info='/report',
                          args={'action': 'clear'})
        req.session['query_href'] = req.href.query()
        req.session['query_tickets'] = '42'
        self.assertTrue(self.report_module.match_request(req))
        self.assertEqual('report_list.html',
                         self.report_module.process_request(req)[0])
        self.assertIn('query_href', req.session)
        self.assertIn('query_tickets', req.session)

        req = MockRequest(self.env, method='POST', path_info='/report',
                          args={'action': 'clear'})
        self.assertTrue(self.report_module.match_request(req))
        self.assertRaises(RequestDone, self.report_module.process_request, req)
        self.assertNotIn('query_href', req.session)
        self.assertNotIn('query_tickets', req.session)


class ExecuteReportTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        self.report_module = ReportModule(self.env)

    def tearDown(self):
        self.env.reset_db()

    def _insert_ticket(self, when=None, **kwargs):
        ticket = Ticket(self.env)
        for name, value in kwargs.iteritems():
            ticket[name] = value
        ticket['status'] = 'new'
        ticket.insert(when=when)
        return ticket

    def _save_ticket(self, ticket, author=None, comment=None, when=None,
                     **kwargs):
        if when is None:
            when = ticket['changetime'] + timedelta(microseconds=1)
        for name, value in kwargs.iteritems():
            ticket[name] = value
        return ticket.save_changes(author=author, comment=comment, when=when)

    def _execute_report(self, id, args=None):
        mod = self.report_module
        req = MockRequest(self.env)
        report = Report(self.env, id)
        return mod.execute_paginated_report(req, id, report.query, args or {})

    def _generate_tickets(self, columns, data, attrs):
        with self.env.db_transaction as db:
            tickets = []
            when = datetime(2014, 1, 1, 0, 0, 0, 0, utc)
            for idx, line in enumerate(data.splitlines()):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                values = line.split()
                assert len(columns) == len(values), 'Line %d' % (idx + 1)
                summary = ' '.join(values)
                values = map(lambda v: None if v == 'None' else v, values)
                d = attrs.copy()
                d['summary'] = summary
                d.update(zip(columns, values))

                status = None
                if 'status' in d:
                    status = d.pop('status')
                ticket = self._insert_ticket(when=when, status='new', **d)
                if status != 'new':
                    self._save_ticket(ticket, status=status,
                                      when=when + timedelta(microseconds=1))
                tickets.append(ticket)
                when += timedelta(seconds=1)
            return tickets

    REPORT_1_DATA = """\
        # status    priority
        new         minor
        new         major
        new         critical
        closed      minor
        closed      major
        closed      critical"""

    def test_report_1_active_tickets(self):
        attrs = dict(reporter='joe', component='component1', version='1.0',
                     milestone='milestone1', type='defect', owner='joe')
        self._generate_tickets(('status', 'priority'), self.REPORT_1_DATA,
                               attrs)

        rv = self._execute_report(1)
        cols, results, num_items, missing_args, limit_offset = rv

        idx_summary = cols.index('summary')
        self.assertEqual(['new critical',
                          'new major',
                          'new minor'],
                         [r[idx_summary] for r in results])
        idx_color = cols.index('__color__')
        self.assertEqual(set(('2', '3', '4')),
                         set(r[idx_color] for r in results))

    REPORT_2_DATA = """\
        # status    version     priority
        new         2.0         minor
        new         2.0         critical
        new         1.0         minor
        new         1.0         critical
        new         None        minor
        new         None        critical
        closed      2.0         minor
        closed      2.0         critical
        closed      1.0         minor
        closed      1.0         critical
        closed      None        minor
        closed      None        critical"""

    def test_report_2_active_tickets_by_version(self):
        attrs = dict(reporter='joe', component='component1',
                     milestone='milestone1', type='defect', owner='joe')
        self._generate_tickets(('status', 'version', 'priority'),
                                self.REPORT_2_DATA, attrs)

        rv = self._execute_report(2)
        cols, results, num_items, missing_args, limit_offset = rv

        idx_summary = cols.index('summary')
        self.assertEqual(['new 1.0 critical',
                          'new 1.0 minor',
                          'new 2.0 critical',
                          'new 2.0 minor',
                          'new None critical',
                          'new None minor'],
                         [r[idx_summary] for r in results])
        idx_color = cols.index('__color__')
        self.assertEqual(set(('2', '4')),
                         set(r[idx_color] for r in results))
        idx_group = cols.index('__group__')
        self.assertEqual(set(('1.0', '2.0', None)),
                         set(r[idx_group] for r in results))

    REPORT_3_DATA = """\
        # status    milestone   priority
        new         milestone3  minor
        new         milestone3  major
        new         milestone1  minor
        new         milestone1  major
        new         None        minor
        new         None        major
        closed      milestone3  minor
        closed      milestone3  major
        closed      milestone1  minor
        closed      milestone1  major
        closed      None        minor
        closed      None        major"""

    def test_report_3_active_tickets_by_milestone(self):
        attrs = dict(reporter='joe', component='component1', version='1.0',
                     type='defect', owner='joe')
        self._generate_tickets(('status', 'milestone', 'priority'),
                                self.REPORT_3_DATA, attrs)

        rv = self._execute_report(3)
        cols, results, num_items, missing_args, limit_offset = rv

        idx_summary = cols.index('summary')
        self.assertEqual(['new milestone1 major',
                          'new milestone1 minor',
                          'new milestone3 major',
                          'new milestone3 minor',
                          'new None major',
                          'new None minor'],
                         [r[idx_summary] for r in results])
        idx_color = cols.index('__color__')
        self.assertEqual(set(('3', '4')),
                         set(r[idx_color] for r in results))
        idx_group = cols.index('__group__')
        self.assertEqual(set(('Milestone milestone1', 'Milestone milestone3',
                              None)),
                         set(r[idx_group] for r in results))

    REPORT_4_DATA = """\
        # status    owner   priority
        new         john    trivial
        new         john    blocker
        new         jack    trivial
        new         jack    blocker
        new         foo     trivial
        new         foo     blocker
        accepted    john    trivial
        accepted    john    blocker
        accepted    jack    trivial
        accepted    jack    blocker
        accepted    foo     trivial
        accepted    foo     blocker
        closed      john    trivial
        closed      john    blocker
        closed      jack    trivial
        closed      jack    blocker
        closed      foo     trivial
        closed      foo     blocker"""

    def _test_active_tickets_by_owner(self, report_id, full_description=False):
        attrs = dict(reporter='joe', component='component1',
                     milestone='milestone1', version='1.0', type='defect')
        self._generate_tickets(('status', 'owner', 'priority'),
                                self.REPORT_4_DATA, attrs)

        rv = self._execute_report(report_id)
        cols, results, num_items, missing_args, limit_offset = rv

        idx_summary = cols.index('summary')
        self.assertEqual(['accepted foo blocker',
                          'accepted foo trivial',
                          'accepted jack blocker',
                          'accepted jack trivial',
                          'accepted john blocker',
                          'accepted john trivial'],
                         [r[idx_summary] for r in results])
        idx_color = cols.index('__color__')
        self.assertEqual(set(('1', '5')),
                         set(r[idx_color] for r in results))
        idx_group = cols.index('__group__')
        self.assertEqual(set(('jack', 'john', 'foo')),
                         set(r[idx_group] for r in results))
        if full_description:
            self.assertNotIn('_description', cols)
            self.assertIn('_description_', cols)
        else:
            self.assertNotIn('_description_', cols)
            self.assertIn('_description', cols)

    def test_report_4_active_tickets_by_owner(self):
        self._test_active_tickets_by_owner(4, full_description=False)

    def test_report_5_active_tickets_by_owner_full_description(self):
        self._test_active_tickets_by_owner(5, full_description=True)

    REPORT_6_DATA = """\
        # status    milestone  priority owner
        new         milestone4 trivial  john
        new         milestone4 critical jack
        new         milestone2 trivial  jack
        new         milestone2 critical john
        new         None       trivial  john
        new         None       critical jack
        closed      milestone4 trivial  jack
        closed      milestone4 critical john
        closed      milestone2 trivial  john
        closed      milestone2 critical jack
        closed      None       trivial  jack
        closed      None       critical john"""

    def test_report_6_all_tickets_by_milestone(self):
        attrs = dict(reporter='joe', component='component1', version='1.0',
                     type='defect')
        self._generate_tickets(('status', 'milestone', 'priority', 'owner'),
                                self.REPORT_6_DATA, attrs)

        rv = self._execute_report(6, {'USER': 'john'})
        cols, results, num_items, missing_args, limit_offset = rv

        idx_summary = cols.index('summary')
        self.assertEqual(['new milestone4 critical jack',
                          'new milestone4 trivial john',
                          'closed milestone4 critical john',
                          'closed milestone4 trivial jack',
                          'new milestone2 critical john',
                          'new milestone2 trivial jack',
                          'closed milestone2 critical jack',
                          'closed milestone2 trivial john',
                          'new None critical jack',
                          'new None trivial john',
                          'closed None critical john',
                          'closed None trivial jack'],
                         [r[idx_summary] for r in results])
        idx_style = cols.index('__style__')
        self.assertEqual('color: #777; background: #ddd; border-color: #ccc;',
                         results[2][idx_style])  # closed and owned
        self.assertEqual('color: #777; background: #ddd; border-color: #ccc;',
                         results[3][idx_style])  # closed and not owned
        self.assertEqual('font-weight: bold',
                         results[1][idx_style])  # not closed and owned
        self.assertEqual(None,
                         results[0][idx_style])  # not closed and not owned
        idx_color = cols.index('__color__')
        self.assertEqual(set(('2', '5')),
                         set(r[idx_color] for r in results))
        idx_group = cols.index('__group__')
        self.assertEqual(set(('milestone2', 'milestone4', None)),
                         set(r[idx_group] for r in results))

    REPORT_7_DATA = """\
        # status    owner   reporter    priority
        accepted    john    foo         minor
        accepted    john    foo         critical
        accepted    foo     foo         major
        new         john    foo         minor
        new         john    foo         blocker
        new         foo     foo         major
        closed      john    foo         major
        closed      foo     foo         major
        new         foo     foo         major
        new         foo     john        trivial
        new         foo     john        major
        closed      foo     foo         major
        closed      foo     john        major
        new         foo     bar         major
        new         bar     foo         major"""

    def test_report_7_my_tickets(self):
        attrs = dict(component='component1', milestone='milestone1',
                     version='1.0', type='defect')
        tickets = self._generate_tickets(
            ('status', 'owner', 'reporter', 'priority'), self.REPORT_7_DATA,
            attrs)

        rv = self._execute_report(7, {'USER': 'john'})
        cols, results, num_items, missing_args, limit_offset = rv

        idx_summary = cols.index('summary')
        self.assertEqual(['accepted john foo critical',
                          'accepted john foo minor',
                          'new john foo blocker',
                          'new john foo minor',
                          'new foo john major',
                          'new foo john trivial'],
                         [r[idx_summary] for r in results])
        idx_group = cols.index('__group__')
        self.assertEqual(set(('Accepted', 'Owned', 'Reported')),
                         set(r[idx_group] for r in results))

        self._save_ticket(tickets[-1], author='john', comment='commented')
        rv = self._execute_report(7, {'USER': 'john'})
        cols, results, num_items, missing_args, limit_offset = rv

        self.assertEqual(7, len(results))
        self.assertEqual('new bar foo major', results[-1][idx_summary])
        self.assertEqual(set(('Accepted', 'Owned', 'Reported', 'Commented')),
                         set(r[idx_group] for r in results))

        rv = self._execute_report(7, {'USER': 'blah <blah@example.org>'})
        cols, results, num_items, missing_args, limit_offset = rv
        self.assertEqual(0, len(results))

        self._save_ticket(tickets[-1], author='blah <blah@example.org>',
                          comment='from anonymous')
        rv = self._execute_report(7, {'USER': 'blah <blah@example.org>'})
        cols, results, num_items, missing_args, limit_offset = rv
        self.assertEqual(1, len(results))
        self.assertEqual('new bar foo major', results[0][idx_summary])
        self.assertEqual('Commented', results[0][idx_group])

    REPORT_8_DATA = """\
        # status    owner   priority
        new         foo     minor
        new         foo     critical
        new         john    minor
        new         john    critical
        closed      john    major
        closed      foo     major"""

    def test_report_8_active_tickets_mine_first(self):
        attrs = dict(component='component1', milestone='milestone1',
                     version='1.0', type='defect')
        self._generate_tickets(('status', 'owner', 'priority'),
                                self.REPORT_8_DATA, attrs)

        rv = self._execute_report(8, {'USER': 'john'})
        cols, results, num_items, missing_args, limit_offset = rv

        idx_summary = cols.index('summary')
        self.assertEqual(['new john critical',
                          'new john minor',
                          'new foo critical',
                          'new foo minor'],
                         [r[idx_summary] for r in results])
        idx_group = cols.index('__group__')
        self.assertEqual('My Tickets', results[1][idx_group])
        self.assertEqual('Active Tickets', results[2][idx_group])

        rv = self._execute_report(8, {'USER': 'anonymous'})
        cols, results, num_items, missing_args, limit_offset = rv

        self.assertEqual(['new foo critical',
                          'new john critical',
                          'new foo minor',
                          'new john minor'],
                         [r[idx_summary] for r in results])
        idx_group = cols.index('__group__')
        self.assertEqual(['Active Tickets'],
                         sorted(set(r[idx_group] for r in results)))

    def test_execute_paginated_report_legacy_signature(self):
        """`execute_paginated_report` returns the same results with and
        without the deprecated `db` argument."""
        id = 1
        attrs = dict(reporter='joe', component='component1', version='1.0',
                     milestone='milestone1', type='defect', owner='joe')
        self._generate_tickets(('status', 'priority'), self.REPORT_1_DATA,
                               attrs)
        mod = self.report_module
        req = MockRequest(self.env)
        sql = Report(self.env, id).query

        rv1 = mod.execute_paginated_report(req, id, sql, {})
        with self.env.db_query as db:
            rv2 = mod.execute_paginated_report(req, db, id, sql, {})
        self.assertEqual(rv2, rv1)

    def test_asc_argument_is_invalid(self):
        """Invalid value for `asc` argument is coerced to default."""
        req = MockRequest(self.env, args={'asc': '--'})

        self.assertRaises(HTTPBadRequest,
                          ReportModule(self.env).process_request, req)

    def test_invalid_post_request_raises_exception(self):
        req = MockRequest(self.env, method='POST', action=None)

        self.assertRaises(HTTPBadRequest,
                          ReportModule(self.env).process_request, req)


class NavigationContributorTestCase(unittest.TestCase):

    def setUp(self):
        self.report_module = ReportModule(self.env)
        self.query_module = QueryModule(self.env)
        self.chrome_module = Chrome(self.env)

        self.perm_sys = PermissionSystem(self.env)
        if self.env.is_component_enabled(ReportModule):
            self.perm_sys.grant_permission('has_report_view',
                                           'REPORT_VIEW')
            self.perm_sys.grant_permission('has_both', 'REPORT_VIEW')
        self.perm_sys.grant_permission('has_ticket_view', 'TICKET_VIEW')
        self.perm_sys.grant_permission('has_both', 'TICKET_VIEW')

        self.tickets_link = lambda href: '<a href="%s">View Tickets</a>' \
                                         % href

    def tearDown(self):
        self.env.reset_db()

    def get_navigation_items(self, req, module):
        """Return navigation items for `module` in a list."""
        for contributor in self.chrome_module.navigation_contributors:
            if contributor is module:
                return list(contributor.get_navigation_items(req))
        return []

    def assertNavItem(self, href, navigation_items):
        """Asserts that `navigation_items` contains only one entry and
        directs to `href`.
        """
        self.assertEqual(1, len(navigation_items))
        item = navigation_items[0]
        self.assertEqual(('mainnav', 'tickets'), item[0:2])
        self.assertEqual(self.tickets_link(href), str(item[2]))


class NavContribReportModuleEnabledTestCase(NavigationContributorTestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        super(NavContribReportModuleEnabledTestCase, self).setUp()

    def test_user_has_no_perms(self):
        """No navigation item when user has neither REPORT_VIEW or
        TICKET_VIEW.
        """
        req = MockRequest(self.env, authname='anonymous')

        navigation_items = self.get_navigation_items(req, self.report_module)
        self.assertEqual(0, len(navigation_items))

        navigation_items = self.get_navigation_items(req, self.query_module)
        self.assertEqual(0, len(navigation_items))

    def test_user_has_report_view(self):
        """Navigation item directs to ReportModule when ReportModule is
        enabled
        and the user has REPORT_VIEW.
        """
        req = MockRequest(self.env, authname='has_report_view')

        navigation_items = self.get_navigation_items(req, self.report_module)
        self.assertNavItem('/trac.cgi/report', navigation_items)

        navigation_items = self.get_navigation_items(req, self.query_module)
        self.assertEqual(0, len(navigation_items))

    def test_user_has_ticket_view(self):
        """Navigation item directs to QueryModule when ReportModule is
        enabled and the user has TICKET_VIEW but not REPORT_VIEW.
        """
        req = MockRequest(self.env, authname='has_ticket_view')

        navigation_items = self.get_navigation_items(req, self.report_module)
        self.assertEqual(0, len(navigation_items))

        navigation_items = self.get_navigation_items(req, self.query_module)
        self.assertNavItem('/trac.cgi/query', navigation_items)

    def test_user_has_report_view_and_ticket_view(self):
        """Navigation item directs to ReportModule when ReportModule is
         enabled and the user has REPORT_VIEW and TICKET_VIEW.
        """
        req = MockRequest(self.env, authname='has_both')

        navigation_items = self.get_navigation_items(req, self.report_module)
        self.assertNavItem('/trac.cgi/report', navigation_items)

        navigation_items = self.get_navigation_items(req, self.query_module)
        self.assertEqual(0, len(navigation_items))


class NavContribReportModuleDisabledTestCase(NavigationContributorTestCase):

    def setUp(self):
        self.env = EnvironmentStub(disable=['trac.ticket.report.*'])
        super(NavContribReportModuleDisabledTestCase, self).setUp()

    def test_user_has_ticket_view(self):
        """Navigation item directs to QueryModule when ReportModule is
        disabled and the user has TICKET_VIEW.
        """
        req = MockRequest(self.env, authname='has_ticket_view')

        navigation_items = self.get_navigation_items(req, self.report_module)
        self.assertEqual(0, len(navigation_items))

        navigation_items = self.get_navigation_items(req, self.query_module)
        self.assertNavItem('/trac.cgi/query', navigation_items)

    def test_user_no_ticket_view(self):
        """No Navigation item when ReportModule is disabled and the user
        has only REPORT_VIEW.
        """
        req = MockRequest(self.env, authname='has_report_view')

        navigation_items = self.get_navigation_items(req, self.report_module)
        self.assertEqual(0, len(navigation_items))

        navigation_items = self.get_navigation_items(req, self.query_module)
        self.assertEqual(0, len(navigation_items))


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(doctest.DocTestSuite(trac.ticket.report))
    suite.addTest(unittest.makeSuite(ReportModuleTestCase))
    suite.addTest(unittest.makeSuite(ExecuteReportTestCase))
    suite.addTest(unittest.makeSuite(NavContribReportModuleEnabledTestCase))
    suite.addTest(unittest.makeSuite(NavContribReportModuleDisabledTestCase))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
