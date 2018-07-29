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

import unittest
from datetime import timedelta

from trac.test import locale_en
from trac.ticket.query import QueryModule
from trac.ticket.report import ReportModule
from trac.ticket.roadmap import RoadmapModule
from trac.ticket.model import Milestone, Ticket
from trac.util.datefmt import (datetime_now, format_datetime, pretty_timedelta,
                               utc)
from trac.wiki.tests import formatter


TICKET_TEST_CASES = u"""
============================== ticket: link resolver
bug:1
issue:1
ticket:1
ticket:12
ticket:abc
------------------------------
<p>
<a class="new ticket" href="/ticket/1" title="#1: This is the summary (new)">bug:1</a>
<a class="new ticket" href="/ticket/1" title="#1: This is the summary (new)">issue:1</a>
<a class="new ticket" href="/ticket/1" title="#1: This is the summary (new)">ticket:1</a>
<a class="missing ticket">ticket:12</a>
<a class="missing ticket">ticket:abc</a>
</p>
------------------------------
============================== ticket: link resolver + arguments
bug:1#comment:3
issue:1#comment:3
ticket:1#comment:3
ticket:1?format=csv
------------------------------
<p>
<a class="new ticket" href="/ticket/1#comment:3" title="#1: This is the summary (new)">bug:1#comment:3</a>
<a class="new ticket" href="/ticket/1#comment:3" title="#1: This is the summary (new)">issue:1#comment:3</a>
<a class="new ticket" href="/ticket/1#comment:3" title="#1: This is the summary (new)">ticket:1#comment:3</a>
<a class="new ticket" href="/ticket/1?format=csv" title="#1: This is the summary (new)">ticket:1?format=csv</a>
</p>
------------------------------
============================== ticket: link resolver with ranges
bug:12-14,33
issue:12-14,33
ticket:12-14,33
ticket:12,33?order=created
------------------------------
<p>
<a href="/query?id=12-14%2C33" title="Tickets 12-14, 33">bug:12-14,33</a>
<a href="/query?id=12-14%2C33" title="Tickets 12-14, 33">issue:12-14,33</a>
<a href="/query?id=12-14%2C33" title="Tickets 12-14, 33">ticket:12-14,33</a>
<a href="/query?id=12%2C33&amp;order=created" title="Tickets 12, 33">ticket:12,33?order=created</a>
</p>
------------------------------
============================== ticket link shorthand form
#1, #2
#12, #abc
------------------------------
<p>
<a class="new ticket" href="/ticket/1" title="#1: This is the summary (new)">#1</a>, <a class="missing ticket">#2</a>
<a class="missing ticket">#12</a>, #abc
</p>
------------------------------
============================== ticket link shorthand form with ranges
#1-5,42
#1,3,5,7
------------------------------
<p>
<a href="/query?id=1-5%2C42" title="Tickets 1-5, 42">#1-5,42</a>
<a href="/query?id=1%2C3%2C5%2C7" title="Tickets 1, 3, 5, 7">#1,3,5,7</a>
</p>
------------------------------
============================== ticket link shorthand form with long ranges (#10111 regression)
#1-123456789012345678901234
------------------------------
<p>
<a href="/query?id=1-123456789012345678901234" title="Tickets 1-123456789012345678901234">#1-123456789012345678901234</a>
</p>
------------------------------
============================== escaping the above
!#1
------------------------------
<p>
#1
</p>
------------------------------
#1
============================== InterTrac for tickets
trac:ticket:2041
[trac:ticket:2041 Trac #2041]
#T2041
#trac2041
------------------------------
<p>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/ticket%3A2041" title="ticket:2041 in Trac's Trac"><span class="icon"></span>trac:ticket:2041</a>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/ticket%3A2041" title="ticket:2041 in Trac's Trac"><span class="icon"></span>Trac #2041</a>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/ticket%3A2041" title="ticket:2041 in Trac's Trac"><span class="icon"></span>#T2041</a>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/ticket%3A2041" title="ticket:2041 in Trac's Trac"><span class="icon"></span>#trac2041</a>
</p>
------------------------------
============================== Ticket InterTrac shorthands
T:#2041
trac:#2041
------------------------------
<p>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/%232041" title="#2041 in Trac's Trac"><span class="icon"></span>T:#2041</a>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/%232041" title="#2041 in Trac's Trac"><span class="icon"></span>trac:#2041</a>
</p>
------------------------------
============================== ticket syntax with unicode digits
#⁴²
#1-⁵,42
#1,³,5,7
#T²⁰⁴¹
#trac²⁰⁴¹
------------------------------
<p>
#⁴²
<a class="new ticket" href="/ticket/1" title="#1: This is the summary (new)">#1</a>-⁵,42
<a class="new ticket" href="/ticket/1" title="#1: This is the summary (new)">#1</a>,³,5,7
#T²⁰⁴¹
#trac²⁰⁴¹
</p>
------------------------------
""" # "


def ticket_setup(tc):
    config = tc.env.config
    config.set('ticket-custom', 'custom1', 'text')
    config.save()
    ticket = Ticket(tc.env)

    ticket.populate({'reporter': 'santa',
                     'summary': 'This is the summary',
                     'status': 'new'})
    ticket.insert()

def ticket_teardown(tc):
    config = tc.env.config
    config.remove('ticket-custom', 'custom1')
    config.save()
    tc.env.reset_db()



REPORT_TEST_CASES = u"""
============================== report link shorthand form
{1}, {2}
{12}, {abc}
------------------------------
<p>
<a class="report" href="/report/1">{1}</a>, <a class="report" href="/report/2">{2}</a>
<a class="missing report" title="report does not exist">{12}</a>, {abc}
</p>
------------------------------
============================== escaping the above
!{1}
------------------------------
<p>
{1}
</p>
------------------------------
{1}
============================== ticket shorthands, not numerical HTML entities
&#1; &#23;
------------------------------
<p>
&amp;#1; &amp;#23;
</p>
------------------------------
&amp;#1; &amp;#23;
============================== report link with non-digits
report:blah
------------------------------
<p>
<a class="missing report" title="report does not exist">report:blah</a>
</p>
------------------------------
<a class="missing report" title="report does not exist">report:blah</a>
============================== InterTrac for reports
trac:report:1
[trac:report:1 Trac r1]
{T1}
{trac1}
{trac 1}
------------------------------
<p>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/report%3A1" title="report:1 in Trac's Trac"><span class="icon"></span>trac:report:1</a>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/report%3A1" title="report:1 in Trac's Trac"><span class="icon"></span>Trac r1</a>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/report%3A1" title="report:1 in Trac's Trac"><span class="icon"></span>{T1}</a>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/report%3A1" title="report:1 in Trac's Trac"><span class="icon"></span>{trac1}</a>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/report%3A1" title="report:1 in Trac's Trac"><span class="icon"></span>{trac 1}</a>
</p>
------------------------------
============================== report syntax with unicode digits
{⁴²} !{⁴²}
{T⁴²}
{trac⁴²}
------------------------------
<p>
{⁴²} !{⁴²}
{T⁴²}
{trac⁴²}
</p>
------------------------------
""" # '

def report_setup(tc):
    def create_report(tc, id):
        tc.env.db_transaction("""
            INSERT INTO report (id,title,query,description)
            VALUES (%s,%s,'SELECT 1','')""", (id, 'Report %s' % id))
    create_report(tc, 1)
    create_report(tc, 2)


dt_past = datetime_now(utc) - timedelta(days=1)
dt_future = datetime_now(utc) + timedelta(days=1)


MILESTONE_TEST_CASES = u"""
============================== milestone: link resolver
milestone:foo
[milestone:boo Milestone Boo]
[milestone:roo Milestone Roo]
[milestone:woo Milestone Woo]
[milestone:zoo Milestone Zoo]
------------------------------
<p>
<a class="missing milestone" href="/milestone/foo" rel="nofollow">milestone:foo</a>
<a class="milestone" href="/milestone/boo" title="No date set">Milestone Boo</a>
<a class="closed milestone" href="/milestone/roo" title="Completed %(dt_past)s ago (%(datestr_past)s)">Milestone Roo</a>
<a class="milestone" href="/milestone/woo" title="Due in %(dt_future)s (%(datestr_future)s)">Milestone Woo</a>
<a class="milestone" href="/milestone/zoo" title="%(dt_past)s late (%(datestr_past)s)">Milestone Zoo</a>
</p>
------------------------------
============================== milestone: link resolver + arguments
milestone:?action=new
[milestone:boo#KnownIssues Known Issues for 1.0]
------------------------------
<p>
<a class="missing milestone" href="/milestone/?action=new" rel="nofollow">milestone:?action=new</a>
<a class="milestone" href="/milestone/boo#KnownIssues" title="No date set">Known Issues for 1.0</a>
</p>
------------------------------
""" % {'dt_past': pretty_timedelta(dt_past),
       'dt_future': pretty_timedelta(dt_future),
       'datestr_past': format_datetime(dt_past, locale=locale_en, tzinfo=utc),
       'datestr_future': format_datetime(dt_future, locale=locale_en,
                                         tzinfo=utc)} #"

def milestone_setup(tc):
    boo = Milestone(tc.env)
    boo.name = 'boo'
    boo.completed = boo.due = None
    boo.insert()
    roo = Milestone(tc.env)
    roo.name = 'roo'
    roo.completed = dt_past
    roo.due = None
    roo.insert()
    woo = Milestone(tc.env)
    woo.name = 'woo'
    woo.completed = None
    woo.due = dt_future
    woo.insert()
    zoo = Milestone(tc.env)
    zoo.name = 'zoo'
    zoo.completed = None
    zoo.due = dt_past
    zoo.insert()

def milestone_teardown(tc):
    tc.env.reset_db()



QUERY_TEST_CASES = u"""
============================== query: link resolver
query:?order=priority

query:?order=priority&owner=me

query:?type=résumé

query:status=new|reopened

query:reporter!=

query:reporter=joe|jack&owner=me

query:group=owner

query:verbose=1

query:summary=résumé
------------------------------
<p>
<a class="query" href="/query?order=priority">query:?order=priority</a>
</p>
<p>
<a class="query" href="/query?order=priority&amp;owner=me">query:?order=priority&amp;owner=me</a>
</p>
<p>
<a class="query" href="/query?type=r%C3%A9sum%C3%A9">query:?type=résumé</a>
</p>
<p>
<a class="query" href="/query?status=new&amp;status=reopened&amp;order=priority">query:status=new|reopened</a>
</p>
<p>
<a class="query" href="/query?reporter=!&amp;order=priority">query:reporter!=</a>
</p>
<p>
<a class="query" href="/query?owner=me&amp;reporter=joe&amp;reporter=jack&amp;order=priority">query:reporter=joe|jack&amp;owner=me</a>
</p>
<p>
<a class="query" href="/query?group=owner&amp;order=priority">query:group=owner</a>
</p>
<p>
<a class="query" href="/query?order=priority&amp;row=description">query:verbose=1</a>
</p>
<p>
<a class="query" href="/query?summary=r%C3%A9sum%C3%A9&amp;order=priority">query:summary=résumé</a>
</p>
------------------------------
============================== TicketQuery macro: no results, list form
Reopened tickets: [[TicketQuery(status=reopened)]]
------------------------------
<p>
Reopened tickets: <span class="query_no_results">No results</span>
</p>
------------------------------
============================== TicketQuery macro: no results, count 0 (raw)
Reopened tickets: [[TicketQuery(status=reopened, format=rawcount)]]
------------------------------
<p>
Reopened tickets: <span class="query_count" title="0 tickets matching status=reopened, max=0, order=id">0</span>
</p>
------------------------------
============================== TicketQuery macro: no results, count 0
Reopened tickets: [[TicketQuery(status=reopened, format=count)]]
------------------------------
<p>
Reopened tickets: <a href="/query?status=reopened&amp;max=0&amp;order=id" title="0 tickets matching status=reopened, max=0, order=id">0</a>
</p>
------------------------------
============================== TicketQuery macro: no results, compact form
Reopened tickets: [[TicketQuery(status=reopened, format=compact)]]
------------------------------
<p>
Reopened tickets: <span class="query_no_results">No results</span>
</p>
------------------------------
============================== TicketQuery macro: one result, list form
New tickets: [[TicketQuery(status=new)]]
------------------------------
<p>
New tickets: </p><div><dl class="wiki compact"><dt><a class="new" href="/ticket/1" title="This is the summary">#1</a></dt><dd>This is the summary</dd></dl></div><p>
</p>
------------------------------
============================== TicketQuery macro: one result, count 1 (raw)
New tickets: [[TicketQuery(status=new, format=rawcount)]]
------------------------------
<p>
New tickets: <span class="query_count" title="1 ticket matching status=new, max=0, order=id">1</span>
</p>
------------------------------
============================== TicketQuery macro: one result, count 1
New tickets: [[TicketQuery(status=new, format=count)]]
------------------------------
<p>
New tickets: <a href="/query?status=new&amp;max=0&amp;order=id" title="1 ticket matching status=new, max=0, order=id">1</a>
</p>
------------------------------
============================== TicketQuery macro: one result, compact form
New tickets: [[TicketQuery(status=new, format=compact)]]
------------------------------
<p>
New tickets: <span><a class="new" href="/ticket/1" title="This is the summary">#1</a></span>
</p>
------------------------------
============================== TicketQuery macro: duplicated fields
New tickets: [[TicketQuery(status=new, format=compact, col=summary|status|status)]]
------------------------------
<p>
New tickets: <span><a class="new" href="/ticket/1" title="This is the summary">#1</a></span>
</p>
------------------------------
============================== TicketQuery macro: duplicated custom fields
New tickets: [[TicketQuery(status=new, format=compact, col=summary|custom1|custom1)]]
------------------------------
<p>
New tickets: <span><a class="new" href="/ticket/1" title="This is the summary">#1</a></span>
</p>
------------------------------
"""

QUERY2_TEST_CASES = u"""
============================== TicketQuery macro: two results, list form
New tickets: [[TicketQuery(status=new, order=reporter)]]
------------------------------
<p>
New tickets: </p><div><dl class="wiki compact"><dt><a class="new" href="/ticket/2" title="This is another summary">#2</a></dt><dd>This is another summary</dd><dt><a class="new" href="/ticket/1" title="This is the summary">#1</a></dt><dd>This is the summary</dd></dl></div><p>
</p>
------------------------------
============================== TicketQuery macro: two results, count 2 (raw)
New tickets: [[TicketQuery(status=new, order=reporter, format=rawcount)]]
------------------------------
<p>
New tickets: <span class="query_count" title="2 tickets matching status=new, max=0, order=reporter">2</span>
</p>
------------------------------
============================== TicketQuery macro: two results, count 2
New tickets: [[TicketQuery(status=new, order=reporter, format=count)]]
------------------------------
<p>
New tickets: <a href="/query?status=new&amp;max=0&amp;order=reporter" title="2 tickets matching status=new, max=0, order=reporter">2</a>
</p>
------------------------------
============================== TicketQuery macro: two results, compact form
New tickets: [[TicketQuery(status=new, order=reporter, format=compact)]]
------------------------------
<p>
New tickets: <span><a class="new" href="/ticket/2" title="This is another summary">#2</a>, <a class="new" href="/ticket/1" title="This is the summary">#1</a></span>
</p>
------------------------------
"""

def query2_setup(tc):
    ticket = Ticket(tc.env)
    ticket.populate({'reporter': 'santa',
                     'summary': 'This is the summary',
                     'status': 'new'})
    ticket.insert()
    ticket = Ticket(tc.env)
    ticket.populate({'reporter': 'claus',
                     'summary': 'This is another summary',
                     'status': 'new'})
    ticket.insert()

def query2_teardown(tc):
    tc.env.reset_db()


COMMENT_TEST_CASES = u"""
============================== comment: link resolver (deprecated)
comment:ticket:1:1 (deprecated)
[comment:ticket:1:1 see above] (deprecated)
comment:ticket:1:description (deprecated)
[comment:ticket:1:description see descr] (deprecated)
comment:ticket:2:1 (deprecated)
comment:ticket:2:3 (deprecated)
comment:ticket:3:1 (deprecated)
comment:tiket:2:1 (deprecated)
comment:ticket:two:1 (deprecated)
comment:ticket:2:1a (deprecated)
comment:ticket:2:one (deprecated)
comment:ticket:1: (deprecated)
comment:ticket::2 (deprecated)
comment:ticket:: (deprecated)
------------------------------
<p>
<a class="new ticket" href="/ticket/1#comment:1" title="Comment 1 for #1: This is the summary for ticket 1 (new)">comment:ticket:1:1</a> (deprecated)
<a class="new ticket" href="/ticket/1#comment:1" title="Comment 1 for #1: This is the summary for ticket 1 (new)">see above</a> (deprecated)
<a class="new ticket" href="/ticket/1#comment:description" title="Description for #1: This is the summary for ticket 1 (new)">comment:ticket:1:description</a> (deprecated)
<a class="new ticket" href="/ticket/1#comment:description" title="Description for #1: This is the summary for ticket 1 (new)">see descr</a> (deprecated)
<a class="ticket" href="/ticket/2#comment:1" title="Comment 1">comment:ticket:2:1</a> (deprecated)
<a class="missing ticket" title="ticket comment does not exist">comment:ticket:2:3</a> (deprecated)
<a class="missing ticket" title="ticket does not exist">comment:ticket:3:1</a> (deprecated)
comment:tiket:2:1 (deprecated)
comment:ticket:two:1 (deprecated)
comment:ticket:2:1a (deprecated)
comment:ticket:2:one (deprecated)
comment:ticket:1: (deprecated)
comment:ticket::2 (deprecated)
comment:ticket:: (deprecated)
</p>
------------------------------
============================== comment: link resolver
comment:1
comment:₁
[comment:1 see above]
comment:description
[comment:description see descr]
comment:
comment:one
comment:1a
------------------------------
<p>
<a class="ticket" href="/ticket/2#comment:1" title="Comment 1">comment:1</a>
<a class="missing ticket" title="ticket comment does not exist">comment:₁</a>
<a class="ticket" href="/ticket/2#comment:1" title="Comment 1">see above</a>
<a class="ticket" href="/ticket/2#comment:description" title="Description">comment:description</a>
<a class="ticket" href="/ticket/2#comment:description" title="Description">see descr</a>
comment:
comment:one
comment:1a
</p>
------------------------------
============================== comment: link resolver with ticket number
comment:1:bug:1
comment:1:issue:1
comment:1:ticket:1
comment:₁:ticket:1
[comment:1:ticket:1 see above]
comment:description:ticket:1
[comment:description:ticket:1 see descr]
comment:1:ticket:2
comment:3:ticket:2
comment:1:ticket:3
comment:2:tiket:1
comment:1:ticket:two
comment:one:ticket:1
comment:1a:ticket:1
comment:ticket:1
comment:2:ticket:
comment::ticket:
------------------------------
<p>
<a class="new ticket" href="/ticket/1#comment:1" title="Comment 1 for #1: This is the summary for ticket 1 (new)">comment:1:bug:1</a>
<a class="new ticket" href="/ticket/1#comment:1" title="Comment 1 for #1: This is the summary for ticket 1 (new)">comment:1:issue:1</a>
<a class="new ticket" href="/ticket/1#comment:1" title="Comment 1 for #1: This is the summary for ticket 1 (new)">comment:1:ticket:1</a>
<a class="missing ticket" title="ticket comment does not exist">comment:₁:ticket:1</a>
<a class="new ticket" href="/ticket/1#comment:1" title="Comment 1 for #1: This is the summary for ticket 1 (new)">see above</a>
<a class="new ticket" href="/ticket/1#comment:description" title="Description for #1: This is the summary for ticket 1 (new)">comment:description:ticket:1</a>
<a class="new ticket" href="/ticket/1#comment:description" title="Description for #1: This is the summary for ticket 1 (new)">see descr</a>
<a class="ticket" href="/ticket/2#comment:1" title="Comment 1">comment:1:ticket:2</a>
<a class="missing ticket" title="ticket comment does not exist">comment:3:ticket:2</a>
<a class="missing ticket" title="ticket does not exist">comment:1:ticket:3</a>
comment:2:tiket:1
comment:1:ticket:two
comment:one:ticket:1
comment:1a:ticket:1
comment:ticket:1
comment:2:ticket:
comment::ticket:
</p>
------------------------------
""" # "

# NOTE: the following test cases:
#
#  comment:2
#  [comment:2 see above]
#
# would trigger an error in the workaround code ../api.py, line 235
# As it's a problem with a temp workaround, I think there's no need
# to fix it for now.

def comment_setup(tc):
    ticket1 = Ticket(tc.env)
    ticket1.populate({'reporter': 'santa',
                      'summary': 'This is the summary for ticket 1',
                      'status': 'new'})
    ticket1.insert()
    ticket1.save_changes(comment='This is the comment for ticket 1')
    ticket2 = Ticket(tc.env)
    ticket2.populate({'reporter': 'claws',
                      'summary': 'This is the summary for ticket 2',
                      'status': 'closed'})
    ticket2.insert()
    ticket2.save_changes(comment='This is the comment for ticket 2')

def comment_teardown(tc):
    tc.env.reset_db()


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(formatter.test_suite(TICKET_TEST_CASES, ticket_setup,
                                       __file__, ticket_teardown))
    suite.addTest(formatter.test_suite(REPORT_TEST_CASES, report_setup,
                                       __file__))
    suite.addTest(formatter.test_suite(MILESTONE_TEST_CASES, milestone_setup,
                                       __file__, milestone_teardown))
    suite.addTest(formatter.test_suite(QUERY_TEST_CASES, ticket_setup,
                                       __file__, ticket_teardown))
    suite.addTest(formatter.test_suite(QUERY2_TEST_CASES, query2_setup,
                                       __file__, query2_teardown))
    suite.addTest(formatter.test_suite(COMMENT_TEST_CASES, comment_setup,
                                       __file__, comment_teardown,
                                       ('ticket', 2)))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
