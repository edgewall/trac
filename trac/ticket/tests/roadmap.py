# -*- coding: utf-8 -*-
#
# Copyright (C) 2006-2013 Edgewall Software
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

from trac.core import ComponentManager
from trac.perm import PermissionSystem
from trac.resource import Resource, ResourceNotFound, render_resource_link
from trac.test import EnvironmentStub, MockRequest
from trac.ticket.roadmap import (
    DefaultTicketGroupStatsProvider, Milestone, MilestoneModule,
    RoadmapModule, TicketGroupStats, get_tickets_for_all_milestones,
    get_tickets_for_milestone)
from trac.ticket.test import insert_ticket
from trac.util.datefmt import datetime_now, utc
from trac.web.api import HTTPBadRequest, RequestDone
from trac.web.chrome import web_context
from trac.web.tests.api import RequestHandlerPermissionsTestCaseBase


class TicketGroupStatsTestCase(unittest.TestCase):

    def setUp(self):
        self.stats = TicketGroupStats('title', 'units')

    def test_init(self):
        self.assertEqual('title', self.stats.title, 'title incorrect')
        self.assertEqual('units', self.stats.unit, 'unit incorrect')
        self.assertEqual(0, self.stats.count, 'count not zero')
        self.assertEqual(0, len(self.stats.intervals), 'intervals not empty')

    def test_add_iterval(self):
        self.stats.add_interval('intTitle', 3, {'k1': 'v1'}, 'css', 0)
        self.stats.refresh_calcs()
        self.assertEqual(3, self.stats.count, 'count not incremented')
        int = self.stats.intervals[0]
        self.assertEqual('intTitle', int['title'], 'title incorrect')
        self.assertEqual(3, int['count'], 'count incorrect')
        self.assertEqual({'k1': 'v1'}, int['qry_args'],
                         'query args incorrect')
        self.assertEqual('css', int['css_class'], 'css class incorrect')
        self.assertEqual(100, int['percent'], 'percent incorrect')
        self.stats.add_interval('intTitle', 3, {'k1': 'v1'}, 'css', 0)
        self.stats.refresh_calcs()
        self.assertEqual(50, int['percent'], 'percent not being updated')

    def test_add_interval_no_prog(self):
        self.stats.add_interval('intTitle', 3, {'k1': 'v1'}, 'css', 0)
        self.stats.add_interval('intTitle', 5, {'k1': 'v1'}, 'css', 0)
        self.stats.refresh_calcs()
        self.assertEqual(0, self.stats.done_count, 'count added for no prog')
        self.assertEqual(0, self.stats.done_percent, 'percent incremented')

    def test_add_interval_prog(self):
        self.stats.add_interval('intTitle', 3, {'k1': 'v1'}, 'css', 0)
        self.stats.add_interval('intTitle', 1, {'k1': 'v1'}, 'css', 1)
        self.stats.refresh_calcs()
        self.assertEqual(4, self.stats.count, 'count not incremented')
        self.assertEqual(1, self.stats.done_count, 'count not added to prog')
        self.assertEqual(25, self.stats.done_percent, 'done percent not incr')

    def test_add_interval_fudging(self):
        self.stats.add_interval('intTitle', 3, {'k1': 'v1'}, 'css', 0)
        self.stats.add_interval('intTitle', 5, {'k1': 'v1'}, 'css', 1)
        self.stats.refresh_calcs()
        self.assertEqual(8, self.stats.count, 'count not incremented')
        self.assertEqual(5, self.stats.done_count, 'count not added to prog')
        self.assertEqual(62, self.stats.done_percent,
                         'done percnt not fudged downward')
        self.assertEqual(62, self.stats.intervals[1]['percent'],
                         'interval percent not fudged downward')
        self.assertEqual(38, self.stats.intervals[0]['percent'],
                         'interval percent not fudged upward')


class DefaultTicketGroupStatsProviderTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)

        self.milestone1 = Milestone(self.env)
        self.milestone1.name = 'Test'
        self.milestone1.insert()
        self.milestone2 = Milestone(self.env)
        self.milestone2.name = 'Test2'
        self.milestone2.insert()

        tkt1 = insert_ticket(self.env, summary='Foo', milestone='Test',
                             owner='foman', status='new')
        tkt2 = insert_ticket(self.env, summary='Bar', milestone='Test',
                             status='closed', owner='barman')
        tkt3 = insert_ticket(self.env, summary='Sum', milestone='Test',
                             owner='suman', status='reopened')
        self.tkt1 = tkt1
        self.tkt2 = tkt2
        self.tkt3 = tkt3

        prov = DefaultTicketGroupStatsProvider(ComponentManager())
        prov.env = self.env
        prov.config = self.env.config
        self.stats = prov.get_ticket_group_stats([tkt1.id, tkt2.id, tkt3.id])

    def tearDown(self):
        self.env.reset_db()

    def test_stats(self):
        self.assertEqual(self.stats.title, 'ticket status', 'title incorrect')
        self.assertEqual(self.stats.unit, 'tickets', 'unit incorrect')
        self.assertEqual(2, len(self.stats.intervals),
                         'more than 2 intervals')

    def test_closed_interval(self):
        closed = self.stats.intervals[0]
        self.assertEqual('closed', closed['title'], 'closed title incorrect')
        self.assertEqual('closed', closed['css_class'],
                         'closed class incorrect')
        self.assertTrue(closed['overall_completion'],
                        'closed should contribute to overall completion')
        self.assertEqual({'status': ['closed'], 'group': ['resolution']},
                         closed['qry_args'], 'qry_args incorrect')
        self.assertEqual(1, closed['count'], 'closed count incorrect')
        self.assertEqual(33, closed['percent'], 'closed percent incorrect')

    def test_open_interval(self):
        open = self.stats.intervals[1]
        self.assertEqual('active', open['title'], 'open title incorrect')
        self.assertEqual('open', open['css_class'], 'open class incorrect')
        self.assertFalse(open['overall_completion'],
                         "open shouldn't contribute to overall completion")
        self.assertEqual({'status':
                          [u'assigned', u'new', u'accepted', u'reopened']},
                         open['qry_args'], 'qry_args incorrect')
        self.assertEqual(2, open['count'], 'open count incorrect')
        self.assertEqual(67, open['percent'], 'open percent incorrect')


class MilestoneModuleTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)
        self.mmodule = MilestoneModule(self.env)
        self.terms = ['MilestoneAlpha', 'MilestoneBeta', 'MilestoneGamma']
        for term in self.terms + [' '.join(self.terms)]:
            m = Milestone(self.env)
            m.name = term
            m.due = datetime_now(utc)
            m.description = u"""\
Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod \
tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim \
veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea \
commodo consequat. Duis aute irure dolor in reprehenderit in voluptate \
velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat \
cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id \
est laborum."""
            m.insert()

    def tearDown(self):
        self.env.reset_db()

    def test_invalid_post_request_raises_exception(self):
        req = MockRequest(self.env, method='POST', action=None,
                          args={'id': 'milestone1'})

        self.assertRaises(HTTPBadRequest,
                          MilestoneModule(self.env).process_request, req)

    def test_milestone_redirects_to_roadmap(self):
        """The path /milestone redirects to /roadmap."""
        def test_milestone_redirect(authname=None):
            req = MockRequest(self.env, method='GET', path_info='/milestone',
                              authname=authname)
            with self.assertRaises(RequestDone):
                self.mmodule.process_request(req)
            self.assertEqual('http://example.org/trac.cgi/roadmap',
                             req.headers_sent['Location'])
            self.assertEqual('302 Found', req._status)
            return req

        # Redirects for user with MILESTONE_VIEW
        req = test_milestone_redirect()
        self.assertIn('MILESTONE_VIEW', req.perm)

        # Redirects for user without MILESTONE_VIEW
        perm_sys = PermissionSystem(self.env)
        perm_sys.revoke_permission('anonymous', 'MILESTONE_VIEW')
        req = test_milestone_redirect('user1')
        self.assertNotIn('MILESTONE_VIEW', req.perm)

    def test_get_search_filters(self):
        req = MockRequest(self.env)
        filters = self.mmodule.get_search_filters(req)
        filters = list(filters)
        self.assertEqual(1, len(filters))
        self.assertEqual(2, len(filters[0]))
        self.assertEqual('milestone', filters[0][0])
        self.assertEqual('Milestones', filters[0][1])

    def test_get_search_results_milestone_not_in_filters(self):
        req = MockRequest(self.env)
        results = self.mmodule.get_search_results(req, self.terms, [])
        self.assertEqual([], list(results))

    def test_get_search_results_matches_all_terms(self):
        req = MockRequest(self.env)
        milestone = Milestone(self.env, ' '.join(self.terms))
        results = self.mmodule.get_search_results(req, self.terms,
                                                  ['milestone'])
        results = list(results)
        self.assertEqual(1, len(results))
        self.assertEqual(5, len(results[0]))
        self.assertEqual('/trac.cgi/milestone/' +
                         milestone.name.replace(' ', '%20'),
                         results[0][0])
        self.assertEqual('Milestone ' + milestone.name, results[0][1])
        self.assertEqual(milestone.due, results[0][2])
        self.assertEqual('', results[0][3])
        shorten_desc = u"""\
Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod \
tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, \
quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo \
consequat. Duis a ..."""
        self.assertEqual(shorten_desc, results[0][4])

    def test_default_group_by_default(self):
        """Default `default_group_by` is `component`."""
        req = MockRequest(self.env, args={'id': 'milestone1'})

        data = self.mmodule.process_request(req)[1]

        self.assertIn('grouped_by', data)
        self.assertEqual('component', data['grouped_by'])

    def test_default_group_by(self):
        """Option `default_group_by` is set in configuration."""
        self.env.config.set('milestone', 'default_group_by', 'priority')
        req = MockRequest(self.env, args={'id': 'milestone1'})

        data = self.mmodule.process_request(req)[1]

        self.assertIn('grouped_by', data)
        self.assertEqual('priority', data['grouped_by'])

    def test_get_search_results_matches_ignorecase(self):
        req = MockRequest(self.env)

        def search(terms):
            return list(self.mmodule.get_search_results(req, terms,
                                                        ['milestone']))

        results = search(self.terms)
        self.assertEqual(results, search([t.lower() for t in self.terms]))
        self.assertEqual(results, search([t.upper() for t in self.terms]))


class MilestoneModulePermissionsTestCase(RequestHandlerPermissionsTestCaseBase):

    def setUp(self):
        super(MilestoneModulePermissionsTestCase, self).setUp(MilestoneModule)

    def test_milestone_notfound_with_milestone_create(self):
        self.grant_perm('anonymous', 'MILESTONE_VIEW')
        self.grant_perm('anonymous', 'MILESTONE_CREATE')

        req = MockRequest(self.env, path_info='/milestone/milestone5')
        res = self.process_request(req)

        self.assertEqual('milestone_edit.html', res[0])
        self.assertEqual('milestone5', res[1]['milestone'].name)
        self.assertEqual("Milestone milestone5 does not exist. You can"
                         " create it here.", req.chrome['notices'][0])

    def test_milestone_notfound_without_milestone_create(self):
        self.grant_perm('anonymous', 'MILESTONE_VIEW')

        req = MockRequest(self.env, authname='anonymous',
                          path_info='/milestone/milestone5')

        self.assertRaises(ResourceNotFound, self.process_request, req)


class RoadmapTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        values = [
            ('Summary', 'new', 'milestone1', 'joe'),
            ('Summary', 'new', 'milestone2', 'joe'),
            ('Summary', 'new', '',           'joe'),
            ('Summary', 'new', None,         'john'),
            ('Summary', 'new', 'milestone1', 'john'),
            ('Summary', 'new', 'milestone2', 'blah'),
            ('Summary', 'new', '',           'blah'),
            ('Summary', 'new', None,         'blah'),
            ('Summary', 'new', 'milestone1', 'blah'),
            ('Summary', 'new', 'milestone2', 'blah'),
        ]
        with self.env.db_transaction as db:
            cursor = db.cursor()
            cursor.executemany("""
                INSERT INTO ticket (summary,status,milestone,owner)
                VALUES (%s,%s,%s,%s)
                """, values)

    def tearDown(self):
        self.env.reset_db()

    def insert_milestone(self, name, due=None):
        milestone = Milestone(self.env)
        milestone.name = name
        milestone.due = due
        milestone.insert()
        return milestone

    def test_get_tickets_for_all_milestones(self):
        tickets = get_tickets_for_all_milestones(self.env, field='owner')
        milestone1 = [{'id': 9, 'status': 'new', 'owner': 'blah'},
                      {'id': 1, 'status': 'new', 'owner': 'joe'},
                      {'id': 5, 'status': 'new', 'owner': 'john'}]
        milestone2 = [{'id': 6, 'status': 'new', 'owner': 'blah'},
                      {'id': 10, 'status': 'new', 'owner': 'blah'},
                      {'id': 2, 'status': 'new', 'owner': 'joe'}]
        self.assertEqual(milestone1, tickets['milestone1'])
        self.assertEqual(milestone1,
                         get_tickets_for_milestone(self.env,
                                                   milestone='milestone1',
                                                   field='owner'))
        self.assertEqual(milestone2, tickets['milestone2'])
        self.assertEqual(milestone2,
                         get_tickets_for_milestone(self.env,
                                                   milestone='milestone2',
                                                   field='owner'))
        self.assertEqual(['milestone1', 'milestone2'], sorted(tickets))

    def test_export_ical_from_roadmap(self):
        self.insert_milestone('milestone1', datetime_now(utc))
        self.insert_milestone('milestone2')
        rm = RoadmapModule(self.env)
        req = MockRequest(self.env, path_info='/roadmap',
                          args={'format': 'ics'})

        self.assertTrue(rm.match_request(req))
        with self.assertRaises(RequestDone):
            rm.process_request(req)

        self.assertEqual('200 Ok', req.status_sent[0])
        self.assertRegexpMatches(req.response_sent.getvalue(), """\
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Edgewall Software//NONSGML Trac [\.\w]+//EN
METHOD:PUBLISH
X-WR-CALNAME:My Project - Roadmap
X-WR-CALDESC:My example project
X-WR-TIMEZONE:UTC
BEGIN:VEVENT
UID:</trac.cgi/milestone/milestone1@example.org/trac.cgi>
DTSTAMP:\w+
DTSTART;VALUE=DATE:\w+
SUMMARY:Milestone milestone1
URL:http://example.org/trac.cgi/milestone/milestone1
END:VEVENT
END:VCALENDAR
""".replace('\n', '\r\n'))


class ResourceTestCase(unittest.TestCase):
    """Test cases for milestone resources."""

    def setUp(self):
        self.env = EnvironmentStub()

    def test_resource_link_ticket_context_milestone_exists(self):
        """Resource link in ticket context for viewable milestone.
        """
        milestone = Milestone(self.env)
        milestone.name = 'milestone1'
        milestone.insert()
        req = MockRequest(self.env, path_info='/ticket/1')
        resource = Resource('milestone', 'milestone1')
        context = web_context(req)
        link = render_resource_link(self.env, context, resource,
                                    format='compact')
        self.assertEqual('<a class="milestone" href="/trac.cgi/milestone/'
                         'milestone1" title="No date set">milestone1</a>',
                         unicode(link))

    def test_resource_link_ticket_context_milestone_missing(self):
        """Resource link in ticket context for non-existent milestone.
        """
        req = MockRequest(self.env, path_info='/ticket/1', authname='user1')
        resource = Resource('milestone', 'milestone1')
        context = web_context(req)
        link = render_resource_link(self.env, context, resource,
                                    format='compact')
        self.assertEqual('<a class="milestone missing">milestone1</a>',
                         unicode(link))

    def test_resource_link_ticket_context_milestone_no_view_perm(self):
        """Resource link in ticket context with no milestone view permission.
        """
        milestone = Milestone(self.env)
        milestone.name = 'milestone1'
        milestone.insert()
        req = MockRequest(self.env, path_info='/ticket/1', authname='user1')
        resource = Resource('milestone', 'milestone1')
        context = web_context(req)
        link = render_resource_link(self.env, context, resource,
                                    format='compact')
        self.assertEqual('<a class="milestone">milestone1</a>',
                         unicode(link))


def in_tlist(ticket, list):
    return len([t for t in list if t['id'] == ticket.id]) > 0


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TicketGroupStatsTestCase))
    suite.addTest(unittest.makeSuite(DefaultTicketGroupStatsProviderTestCase))
    suite.addTest(unittest.makeSuite(MilestoneModuleTestCase))
    suite.addTest(unittest.makeSuite(MilestoneModulePermissionsTestCase))
    suite.addTest(unittest.makeSuite(RoadmapTestCase))
    suite.addTest(unittest.makeSuite(ResourceTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
