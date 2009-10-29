# -*- coding: utf-8 -*-

import unittest

from trac.ticket.model import Ticket
from trac.ticket.roadmap import Milestone
from trac.wiki.tests import formatter

TICKET_TEST_CASES = u"""
============================== ticket: link resolver
ticket:1
ticket:12
ticket:abc
------------------------------
<p>
<a class="new ticket" href="/ticket/1" title="This is the summary (new)">ticket:1</a>
<a class="missing ticket">ticket:12</a>
<a class="missing ticket">ticket:abc</a>
</p>
------------------------------
============================== ticket: link resolver + arguments
ticket:1?format=csv
ticket:1#comment:3
------------------------------
<p>
<a class="new ticket" href="/ticket/1?format=csv" title="This is the summary (new)">ticket:1?format=csv</a>
<a class="new ticket" href="/ticket/1#comment:3" title="This is the summary (new)">ticket:1#comment:3</a>
</p>
------------------------------
============================== ticket: link resolver with ranges
ticket:12-14,33
ticket:12,33?order=created
------------------------------
<p>
<a href="/query?id=12-14%2C33" title="Tickets 12-14,33">ticket:12-14,33</a>
<a href="/query?id=12%2C33&amp;order=created" title="Tickets 12,33">ticket:12,33?order=created</a>
</p>
------------------------------
============================== ticket link shorthand form
#1, #2
#12, #abc
------------------------------
<p>
<a class="new ticket" href="/ticket/1" title="This is the summary (new)">#1</a>, <a class="missing ticket">#2</a>
<a class="missing ticket">#12</a>, #abc
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
<a class="ext-link" href="http://trac.edgewall.org/intertrac/ticket%3A2041" title="ticket:2041 in Trac's Trac"><span class="icon">\xa0</span>trac:ticket:2041</a>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/ticket%3A2041" title="ticket:2041 in Trac's Trac"><span class="icon">\xa0</span>Trac #2041</a>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/ticket%3A2041" title="ticket:2041 in Trac's Trac"><span class="icon">\xa0</span>#T2041</a>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/ticket%3A2041" title="ticket:2041 in Trac's Trac"><span class="icon">\xa0</span>#trac2041</a>
</p>
------------------------------
============================== Ticket InterTrac shorthands
T:#2041
trac:#2041
------------------------------
<p>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/%232041" title="#2041 in Trac's Trac"><span class="icon">\xa0</span>T:#2041</a>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/%232041" title="#2041 in Trac's Trac"><span class="icon">\xa0</span>trac:#2041</a>
</p>
------------------------------
""" # " 

def ticket_setup(tc):
    ticket = Ticket(tc.env)
    ticket.values.update({'reporter': 'santa',
                          'summary': 'This is the summary',
                          'status': 'new'})
    ticket.insert()

def ticket_teardown(tc):
    tc.env.reset_db()



REPORT_TEST_CASES = u"""
============================== report link shorthand form
{1}, {2}
{12}, {abc}
------------------------------
<p>
<a class="report" href="/report/1">{1}</a>, <a class="report" href="/report/2">{2}</a>
<a class="report" href="/report/12">{12}</a>, {abc}
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
============================== InterTrac for reports
trac:report:1
[trac:report:1 Trac r1]
{T1}
{trac1}
{trac 1}
------------------------------
<p>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/report%3A1" title="report:1 in Trac's Trac"><span class="icon">\xa0</span>trac:report:1</a>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/report%3A1" title="report:1 in Trac's Trac"><span class="icon">\xa0</span>Trac r1</a>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/report%3A1" title="report:1 in Trac's Trac"><span class="icon">\xa0</span>{T1}</a>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/report%3A1" title="report:1 in Trac's Trac"><span class="icon">\xa0</span>{trac1}</a>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/report%3A1" title="report:1 in Trac's Trac"><span class="icon">\xa0</span>{trac 1}</a>
</p>
------------------------------
""" # '

def report_setup(tc):
    db = tc.env.get_db_cnx()
    # TBD


MILESTONE_TEST_CASES = """
============================== milestone: link resolver
milestone:foo
[milestone:boo Milestone Boo]
[milestone:roo Milestone Roo]
------------------------------
<p>
<a class="missing milestone" href="/milestone/foo" rel="nofollow">milestone:foo</a>
<a class="milestone" href="/milestone/boo">Milestone Boo</a>
<a class="closed milestone" href="/milestone/roo">Milestone Roo</a>
</p>
------------------------------
============================== milestone: link resolver + arguments
milestone:?action=new
[milestone:boo#KnownIssues Known Issues for 1.0]
------------------------------
<p>
<a class="missing milestone" href="/milestone/?action=new" rel="nofollow">milestone:?action=new</a>
<a class="milestone" href="/milestone/boo#KnownIssues">Known Issues for 1.0</a>
</p>
------------------------------
""" #"

def milestone_setup(tc):
    from datetime import datetime
    from trac.util.datefmt import utc
    boo = Milestone(tc.env)
    boo.name = 'boo'
    boo.completed = boo.due = None
    boo.insert()
    roo = Milestone(tc.env)
    roo.name = 'roo'
    roo.completed = datetime.now(utc)
    roo.due = None
    roo.insert()

def milestone_teardown(tc):
    tc.env.reset_db()



QUERY_TEST_CASES = u"""
============================== query: link resolver
query:?order=priority

query:?order=priority&owner=me

query:status=new|reopened

query:milestone!=

query:milestone=1.0|2.0&owner=me

query:group=owner

query:verbose=1
------------------------------
<p>
<a class="query" href="/query?order=priority">query:?order=priority</a>
</p>
<p>
<a class="query" href="/query?order=priority&amp;owner=me">query:?order=priority&amp;owner=me</a>
</p>
<p>
<a class="query" href="/query?status=new&amp;status=reopened&amp;order=priority">query:status=new|reopened</a>
</p>
<p>
<a class="query" href="/query?milestone=%21&amp;order=priority">query:milestone!=</a>
</p>
<p>
<a class="query" href="/query?owner=me&amp;milestone=1.0&amp;milestone=2.0&amp;order=priority">query:milestone=1.0|2.0&amp;owner=me</a>
</p>
<p>
<a class="query" href="/query?group=owner&amp;order=priority">query:group=owner</a>
</p>
<p>
<a class="query" href="/query?order=priority&amp;row=description">query:verbose=1</a>
</p>
------------------------------
============================== TicketQuery macro: no results, list form
Reopened tickets: [[TicketQuery(status=reopened)]]
------------------------------
<p>
Reopened tickets: <span class="query_no_results">No results</span>
</p>
------------------------------
============================== TicketQuery macro: no results, count 0
Reopened tickets: [[TicketQuery(status=reopened, format=count)]]
------------------------------
<p>
Reopened tickets: <span class="query_count" title="0 tickets for which status=reopened&amp;max=0&amp;order=id">0</span>
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
============================== TicketQuery macro: one result, count 1
New tickets: [[TicketQuery(status=new, format=count)]]
------------------------------
<p>
New tickets: <span class="query_count" title="1 tickets for which status=new&amp;max=0&amp;order=id">1</span>
</p>
------------------------------
============================== TicketQuery macro: one result, compact form
New tickets: [[TicketQuery(status=new, format=compact)]]
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
============================== TicketQuery macro: two results, count 2
New tickets: [[TicketQuery(status=new, order=reporter, format=count)]]
------------------------------
<p>
New tickets: <span class="query_count" title="2 tickets for which status=new&amp;max=0&amp;order=reporter">2</span>
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
    ticket.values.update({'reporter': 'santa',
                          'summary': 'This is the summary',
                          'status': 'new'})
    ticket.insert()
    ticket = Ticket(tc.env)
    ticket.values.update({'reporter': 'claus',
                          'summary': 'This is another summary',
                          'status': 'new'})
    ticket.insert()

def query2_teardown(tc):
    tc.env.reset_db()


COMMENT_TEST_CASES = """
============================== comment: link resolver (deprecated)
comment:ticket:123:2 (deprecated)
[comment:ticket:123:2 see above] (deprecated)
[comment:ticket:123:description see descr] (deprecated)
------------------------------
<p>
<a href="/ticket/123#comment:2" title="Comment 2 for Ticket #123">comment:ticket:123:2</a> (deprecated)
<a href="/ticket/123#comment:2" title="Comment 2 for Ticket #123">see above</a> (deprecated)
<a href="/ticket/123#comment:description" title="Comment description for Ticket #123">see descr</a> (deprecated)
</p>
------------------------------
============================== comment: link resolver
comment:2:ticket:123
[comment:2:ticket:123 see above]
[comment:description:ticket:123 see descr]
------------------------------
<p>
<a href="/ticket/123#comment:2" title="Comment 2 for Ticket #123">comment:2:ticket:123</a>
<a href="/ticket/123#comment:2" title="Comment 2 for Ticket #123">see above</a>
<a href="/ticket/123#comment:description" title="Comment description for Ticket #123">see descr</a>
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

def suite():
    suite = unittest.TestSuite()
    suite.addTest(formatter.suite(TICKET_TEST_CASES, ticket_setup, __file__,
                                  ticket_teardown))
    suite.addTest(formatter.suite(REPORT_TEST_CASES, report_setup, __file__))
    suite.addTest(formatter.suite(MILESTONE_TEST_CASES, milestone_setup,
                                  __file__, milestone_teardown))
    suite.addTest(formatter.suite(QUERY_TEST_CASES, ticket_setup, __file__,
                                  ticket_teardown))
    suite.addTest(formatter.suite(QUERY2_TEST_CASES, query2_setup, __file__,
                                  query2_teardown))
    suite.addTest(formatter.suite(COMMENT_TEST_CASES, file=__file__))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')

