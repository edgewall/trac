import unittest

from trac.Search import SearchModule
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

def suite():
    suite = unittest.TestSuite()
    suite.addTest(formatter.suite(SEARCH_TEST_CASES, file=__file__))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')

