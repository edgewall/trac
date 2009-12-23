from datetime import datetime
import unittest

from trac.util.datefmt import utc
from trac.wiki.model import WikiPage
from trac.wiki.tests import formatter

IMAGE_MACRO_TEST_CASES = u"""
============================== source: Image, no other arguments
[[Image(source:test.png)]]
------------------------------
<p>
<a style="padding:0; border:none" href="/browser/test.png"><img src="/browser/test.png?format=raw" alt="source:test.png" title="source:test.png" /></a>
</p>
------------------------------
[[Image(...)]]
============================== source: Image, nolink
[[Image(source:test.png, nolink)]]
------------------------------
<p>
<img src="/browser/test.png?format=raw" alt="source:test.png" title="source:test.png" />
</p>
------------------------------
============================== source: Image, normal args
[[Image(source:test.png, align=left, title=Test)]]
------------------------------
<p>
<a style="padding:0; border:none" href="/browser/test.png"><img src="/browser/test.png?format=raw" alt="source:test.png" style="float:left" title="Test" /></a>
</p>
------------------------------
============================== source: Image, size arg
[[Image(source:test.png, 30%)]]
------------------------------
<p>
<a style="padding:0; border:none" href="/browser/test.png"><img width="30%" alt="source:test.png" title="source:test.png" src="/browser/test.png?format=raw" /></a>
</p>
------------------------------
============================== source: Image, keyword alignment
[[Image(source:test.png, right)]]
------------------------------
<p>
<a style="padding:0; border:none" href="/browser/test.png"><img src="/browser/test.png?format=raw" alt="source:test.png" style="float:right" title="source:test.png" /></a>
</p>
------------------------------
============================== http: Image, nolink
[[Image(http://www.edgewall.com/gfx/shredder.png, nolink)]]
------------------------------
<p>
<img src="http://www.edgewall.com/gfx/shredder.png" alt="http://www.edgewall.com/gfx/shredder.png" title="http://www.edgewall.com/gfx/shredder.png" />
</p>
------------------------------
============================== http: Image, absolute, many ':'
[[Image(http://chart.apis.google.com:80/chart?cht=p3&chd=s:hW&chs=250x100&chl=Hello|World, title=Google & Charting, link=)]]
------------------------------
<p>
<img src="http://chart.apis.google.com:80/chart?cht=p3&amp;chd=s:hW&amp;chs=250x100&amp;chl=Hello|World" alt="http://chart.apis.google.com:80/chart?cht=p3&amp;chd=s:hW&amp;chs=250x100&amp;chl=Hello|World" title="Google &amp; Charting" />
</p>
------------------------------
============================== // Image, server-relative
[[Image(//browser/test.png?format=raw, link=)]]
------------------------------
<p>
<img src="/browser/test.png?format=raw" alt="/browser/test.png?format=raw" title="/browser/test.png?format=raw" />
</p>
------------------------------
============================== / Image, project-relative, link to WikiStart
[[Image(/browser/test.png?format=raw, link=wiki:WikiStart)]]
------------------------------
<p>
<a style="padding:0; border:none" href="/wiki/WikiStart"><img src="/browser/test.png?format=raw" alt="/browser/test.png?format=raw" title="/browser/test.png?format=raw" /></a>
</p>
------------------------------
"""

TITLEINDEX1_MACRO_TEST_CASES = u"""
============================== TitleIndex, default format
[[TitleIndex()]]
------------------------------
<p>
<ul><li><a href="/wiki/WikiStart">WikiStart</a></li></ul>
</p>
------------------------------
[[TitleIndex]]
============================== TitleIndex, compact format
[[TitleIndex(format=compact)]]
------------------------------
<p>
<a href="/wiki/WikiStart">WikiStart</a>
</p>
------------------------------
[[TitleIndex(...)]]
"""

TITLEINDEX2_MACRO_TEST_CASES = u"""
============================== TitleIndex, default format
[[TitleIndex()]]
------------------------------
<p>
<ul><li><a href="/wiki/WikiEnd">WikiEnd</a></li><li><a href="/wiki/WikiStart">WikiStart</a></li></ul>
</p>
------------------------------
[[TitleIndex]]
============================== TitleIndex, compact format
[[TitleIndex(format=compact)]]
------------------------------
<p>
<a href="/wiki/WikiEnd">WikiEnd</a>, <a href="/wiki/WikiStart">WikiStart</a>
</p>
------------------------------
[[TitleIndex(...)]]
"""

def title_index_setup(tc):
    w = WikiPage(tc.env)
    w.name = 'WikiEnd'
    w.text = '--'
    w.save('joe', 'the second page', '::1', datetime.now(utc))


def title_index_teardown(tc):
    tc.env.reset_db()    

def suite():
    suite = unittest.TestSuite()
    suite.addTest(formatter.suite(IMAGE_MACRO_TEST_CASES, file=__file__))
    suite.addTest(formatter.suite(TITLEINDEX1_MACRO_TEST_CASES, file=__file__))
    suite.addTest(formatter.suite(TITLEINDEX2_MACRO_TEST_CASES, file=__file__,
                                  setup=title_index_setup, 
                                  teardown=title_index_teardown))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
