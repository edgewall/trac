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

def titleindex2_setup(tc):
    w = WikiPage(tc.env)
    w.name = 'WikiEnd'
    w.text = '--'
    w.save('joe', 'the second page', '::1', datetime.now(utc))

def titleindex2_teardown(tc):
    tc.env.reset_db()    

TITLEINDEX3_MACRO_TEST_CASES = u"""
============================== TitleIndex, group format
[[TitleIndex(Wiki,format=group)]]
------------------------------
<p>
<ul class="titleindex"><li><strong>Wiki </strong><ul><li><strong>End/</strong><ul><li><a href="/wiki/WikiEnd/First">WikiEnd/First</a></li><li><a href="/wiki/WikiEnd/Second">WikiEnd/Second</a></li></ul></li><li><strong>Start</strong><ul><li><a href="/wiki/WikiStart">WikiStart</a></li><li><strong>/</strong><ul><li><a href="/wiki/WikiStart/First">WikiStart/First</a></li><li><a href="/wiki/WikiStart/Second">WikiStart/Second</a></li><li><a href="/wiki/WikiStart/Third">WikiStart/Third</a></li></ul></li></ul></li></ul></li></ul>
</p>
------------------------------
============================== TitleIndex, hierarchy format
[[TitleIndex(WikiStart/, format=hierarchy)]]
------------------------------
<p>
<ul class="titleindex"><li><a href="/wiki/WikiStart">WikiStart</a><ul><li><a href="/wiki/WikiStart/First">First</a></li><li><a href="/wiki/WikiStart/Second">Second</a></li><li><a href="/wiki/WikiStart/Third">Third</a></li></ul></li></ul>
</p>
------------------------------
"""

def titleindex3_setup(tc):
    now = datetime.now(utc)
    def add_page(name):
        w = WikiPage(tc.env)
        w.name = name
        w.text = '--'
        w.save('joe', 'the page ' + name, '::1', now)
    add_page('WikiStart/First')
    add_page('WikiStart/Second')
    add_page('WikiStart/Third')
    add_page('WikiEnd/First')
    add_page('WikiEnd/Second')

def titleindex3_teardown(tc):
    tc.env.reset_db()    


def suite():
    suite = unittest.TestSuite()
    suite.addTest(formatter.suite(IMAGE_MACRO_TEST_CASES, file=__file__))
    suite.addTest(formatter.suite(TITLEINDEX1_MACRO_TEST_CASES, file=__file__))
    suite.addTest(formatter.suite(TITLEINDEX2_MACRO_TEST_CASES, file=__file__,
                                  setup=titleindex2_setup, 
                                  teardown=titleindex2_teardown))
    suite.addTest(formatter.suite(TITLEINDEX3_MACRO_TEST_CASES, file=__file__,
                                  setup=titleindex3_setup, 
                                  teardown=titleindex3_teardown))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
