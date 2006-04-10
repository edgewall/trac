import unittest

from trac.ticket.model import Ticket
from trac.wiki.tests import formatter

TEST_CASES="""
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
"""

def ticket_setup(tc):
    ticket = Ticket(tc.env)
    ticket['reporter'] = 'santa'
    ticket['summary'] = 'This is the summary'
    ticket.insert()
    ticket['status'] = 'new'
    ticket.save_changes('claus', 'set status', 0)

def suite():
    return formatter.suite(TEST_CASES, ticket_setup)

if __name__ == '__main__':
    runner = unittest.TextTestRunner()
    runner.run(suite())

