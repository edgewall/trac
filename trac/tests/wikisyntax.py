import os
import shutil
import tempfile
import unittest

from trac.Search import SearchModule
from trac.attachment import Attachment
from trac.wiki.tests import formatter

SEARCH_TEST_CASES="""
============================== search: link resolver
search:foo
search:"foo bar"
[search:bar Bar]
[search:bar]
[search:]
------------------------------
<p>
<a class="search" href="/search?q=foo">search:foo</a>
<a class="search" href="/search?q=foo+bar">search:"foo bar"</a>
<a class="search" href="/search?q=bar">Bar</a>
<a class="search" href="/search?q=bar">bar</a>
<a class="search" href="/search?q=">search</a>
</p>
------------------------------
============================== search: link resolver with query arguments
search:?q=foo&wiki=on
search:"?q=foo bar&wiki=on"
[search:?q=bar&ticket=on Bar in Tickets]
------------------------------
<p>
<a class="search" href="/search?q=foo&amp;wiki=on">search:?q=foo&amp;wiki=on</a>
<a class="search" href="/search?q=foo+bar&amp;wiki=on">search:"?q=foo bar&amp;wiki=on"</a>
<a class="search" href="/search?q=bar&amp;ticket=on">Bar in Tickets</a>
</p>
------------------------------
"""

ATTACHMENT_TEST_CASES="""
============================== attachment: link resolver
attachment:wiki:WikiStart:file.txt
attachment:ticket:123:file.txt
[attachment:wiki:WikiStart:file.txt file.txt]
[attachment:ticket:123:file.txt]
------------------------------
<p>
<a class="attachment" href="/attachment/wiki/WikiStart/file.txt" title="Attachment WikiStart: file.txt">attachment:wiki:WikiStart:file.txt</a>
<a class="attachment" href="/attachment/ticket/123/file.txt" title="Attachment #123: file.txt">attachment:ticket:123:file.txt</a>
<a class="attachment" href="/attachment/wiki/WikiStart/file.txt" title="Attachment WikiStart: file.txt">file.txt</a>
<a class="attachment" href="/attachment/ticket/123/file.txt" title="Attachment #123: file.txt">ticket:123:file.txt</a>
</p>
------------------------------
""" # "

def attachment_setup(tc):
    tc.env.path = os.path.join(tempfile.gettempdir(), 'trac-tempenv')
    os.mkdir(tc.env.path)
    wiki_attachment = Attachment(tc.env, 'wiki', 'WikiStart')
    wiki_attachment.insert('file.txt', tempfile.TemporaryFile(), 0)
    ticket_attachment = Attachment(tc.env, 'ticket', 123)
    ticket_attachment.insert('file.txt', tempfile.TemporaryFile(), 0)

def attachment_teardown(tc):
    shutil.rmtree(tc.env.path)

def suite():
    suite = unittest.TestSuite()
    suite.addTest(formatter.suite(SEARCH_TEST_CASES, file=__file__))
    suite.addTest(formatter.suite(ATTACHMENT_TEST_CASES, file=__file__,
                                  setup=attachment_setup,
                                  teardown=attachment_teardown))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')

