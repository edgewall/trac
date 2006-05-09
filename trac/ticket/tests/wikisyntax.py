import unittest

from trac.ticket.model import Ticket
from trac.ticket.roadmap import Milestone
from trac.ticket.query import QueryModule
from trac.ticket.report import ReportModule
from trac.wiki.tests import formatter

TICKET_TEST_CASES="""
============================== ticket: link resolver
ticket:1
ticket:12
ticket:abc
------------------------------
<p>
<a class="new ticket" href="/ticket/1" title="This is the summary (new)">ticket:1</a>
<a class="missing ticket" href="/ticket/12" rel="nofollow">ticket:12</a>
<a class="missing ticket" href="/ticket/abc" rel="nofollow">ticket:abc</a>
</p>
------------------------------
============================== ticket link shorthand form
#1, #2
#12, #abc
------------------------------
<p>
<a class="new ticket" href="/ticket/1" title="This is the summary (new)">#1</a>, <a class="missing ticket" href="/ticket/2" rel="nofollow">#2</a>
<a class="missing ticket" href="/ticket/12" rel="nofollow">#12</a>, #abc
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
<a class="ext-link" href="http://projects.edgewall.com/trac/ticket/2041" title="ticket:2041 in Trac's Trac"><span class="icon">trac:ticket:2041</span></a>
<a class="ext-link" href="http://projects.edgewall.com/trac/ticket/2041" title="ticket:2041 in Trac's Trac"><span class="icon">Trac #2041</span></a>
<a class="ext-link" href="http://projects.edgewall.com/trac/ticket/2041" title="ticket:2041 in Trac's Trac"><span class="icon">#T2041</span></a>
<a class="ext-link" href="http://projects.edgewall.com/trac/ticket/2041" title="ticket:2041 in Trac's Trac"><span class="icon">#trac2041</span></a>
</p>
------------------------------
============================== Ticket InterTrac shorthands
T:#2041
trac:#2041
------------------------------
<p>
<a class="ext-link" href="http://projects.edgewall.com/trac/search?q=%232041" title="#2041 in Trac's Trac"><span class="icon">T:#2041</span></a>
<a class="ext-link" href="http://projects.edgewall.com/trac/search?q=%232041" title="#2041 in Trac's Trac"><span class="icon">trac:#2041</span></a>
</p>
------------------------------
"""

def ticket_setup(tc):
    ticket = Ticket(tc.env)
    ticket['reporter'] = 'santa'
    ticket['summary'] = 'This is the summary'
    ticket.insert()
    ticket['status'] = 'new'
    ticket.save_changes('claus', 'set status', 0)



REPORT_TEST_CASES="""
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
<a class="ext-link" href="http://projects.edgewall.com/trac/report/1" title="report:1 in Trac's Trac"><span class="icon">trac:report:1</span></a>
<a class="ext-link" href="http://projects.edgewall.com/trac/report/1" title="report:1 in Trac's Trac"><span class="icon">Trac r1</span></a>
<a class="ext-link" href="http://projects.edgewall.com/trac/report/1" title="report:1 in Trac's Trac"><span class="icon">{T1}</span></a>
<a class="ext-link" href="http://projects.edgewall.com/trac/report/1" title="report:1 in Trac's Trac"><span class="icon">{trac1}</span></a>
<a class="ext-link" href="http://projects.edgewall.com/trac/report/1" title="report:1 in Trac's Trac"><span class="icon">{trac 1}</span></a>
</p>
------------------------------
"""

def report_setup(tc):
    db = tc.env.get_db_cnx()
    # TBD


MILESTONE_TEST_CASES="""
============================== milestone: link resolver
milestone:foo
[milestone:boo Milestone Boo]
------------------------------
<p>
<a class="milestone" href="/milestone/foo">milestone:foo</a>
<a class="milestone" href="/milestone/boo">Milestone Boo</a>
</p>
------------------------------
"""


QUERY_TEST_CASES="""
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
<a class="query" href="/query?milestone=1.0&amp;milestone=2.0&amp;owner=me&amp;order=priority">query:milestone=1.0|2.0&amp;owner=me</a>
</p>
<p>
<a class="query" href="/query?group=owner&amp;order=priority">query:group=owner</a>
</p>
<p>
<a class="query" href="/query?verbose=1&amp;order=priority">query:verbose=1</a>
</p>
------------------------------
"""


def suite():
    suite = unittest.TestSuite()
    suite.addTest(formatter.suite(TICKET_TEST_CASES, ticket_setup, __file__))
    suite.addTest(formatter.suite(REPORT_TEST_CASES, report_setup, __file__))
    suite.addTest(formatter.suite(MILESTONE_TEST_CASES, file=__file__))
    suite.addTest(formatter.suite(QUERY_TEST_CASES, file=__file__))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')

