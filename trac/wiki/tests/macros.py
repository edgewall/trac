# -*- coding: utf-8 -*-
from datetime import datetime
import unittest

from trac.util.datefmt import utc
from trac.wiki.model import WikiPage
from trac.wiki.tests import formatter

# == [[Image]]

# Note: using `« test »` string in the following tests for checking
#       unicode robustness and whitespace support (first space is
#       normal ASCII SPACE, second is Unicode NO-BREAK SPACE).

IMAGE_MACRO_TEST_CASES = u"""
============================== source: Image, no other arguments
[[Image(source:« test ».png)]]
------------------------------
<p>
<a style="padding:0; border:none" href="/browser/%C2%AB%20test%C2%A0%C2%BB.png"><img src="/browser/%C2%AB%20test%C2%A0%C2%BB.png?format=raw" alt="source:« test ».png" title="source:« test ».png" /></a>
</p>
------------------------------
[[Image(...)]]
============================== intertrac:source: Image, no other arguments
[[Image(trac:source:/trunk/doc/images/bkgnd_pattern_« test ».png)]]
------------------------------
<p>
<a style="padding:0; border:none" href="http://trac.edgewall.org/intertrac/source%3A/trunk/doc/images/bkgnd_pattern_%C2%AB%20test%C2%A0%C2%BB.png"><img src="http://trac.edgewall.org/intertrac/source%3A/trunk/doc/images/bkgnd_pattern_%C2%AB%20test%C2%A0%C2%BB.png%3Fformat%3Draw" alt="source:/trunk/doc/images/bkgnd_pattern_« test ».png in Trac's Trac" title="source:/trunk/doc/images/bkgnd_pattern_« test ».png in Trac's Trac" /></a>
</p>
------------------------------
[[Image(...)]]
============================== source: Image, nolink
[[Image(source:« test », nolink)]]
------------------------------
<p>
<img src="/browser/%C2%AB%20test%C2%A0%C2%BB?format=raw" alt="source:« test »" title="source:« test »" />
</p>
------------------------------
============================== source: Image, normal args
[[Image(source:« test », align=left, title=Test)]]
------------------------------
<p>
<a style="padding:0; border:none" href="/browser/%C2%AB%20test%C2%A0%C2%BB"><img src="/browser/%C2%AB%20test%C2%A0%C2%BB?format=raw" alt="source:« test »" style="float:left" title="Test" /></a>
</p>
------------------------------
============================== source: Image, size arg
[[Image(source:« test », 30%)]]
------------------------------
<p>
<a style="padding:0; border:none" href="/browser/%C2%AB%20test%C2%A0%C2%BB"><img width="30%" alt="source:« test »" title="source:« test »" src="/browser/%C2%AB%20test%C2%A0%C2%BB?format=raw" /></a>
</p>
------------------------------
============================== source: Image, keyword alignment
[[Image(source:« test », right)]]
------------------------------
<p>
<a style="padding:0; border:none" href="/browser/%C2%AB%20test%C2%A0%C2%BB"><img src="/browser/%C2%AB%20test%C2%A0%C2%BB?format=raw" alt="source:« test »" style="float:right" title="source:« test »" /></a>
</p>
------------------------------
============================== http: Image, nolink
[[Image(http://www.edgewall.com/gfx/shredder_« test ».png, nolink)]]
------------------------------
<p>
<img src="http://www.edgewall.com/gfx/shredder_« test ».png" alt="http://www.edgewall.com/gfx/shredder_« test ».png" title="http://www.edgewall.com/gfx/shredder_« test ».png" />
</p>
------------------------------
============================== http: Image, absolute, many ':'
[[Image(http://chart.apis.google.com:80/chart?cht=p3&chd=s:hW&chs=250x100&chl=Héllo|Wôrld, title=Google & Charting, link=)]]
------------------------------
<p>
<img src="http://chart.apis.google.com:80/chart?cht=p3&amp;chd=s:hW&amp;chs=250x100&amp;chl=Héllo|Wôrld" alt="http://chart.apis.google.com:80/chart" title="Google &amp; Charting" />
</p>
------------------------------
============================== // Image, server-relative
[[Image(//browser/« test »?format=raw, link=)]]
------------------------------
<p>
<img src="/browser/« test »?format=raw" alt="/browser/« test »" title="/browser/« test »" />
</p>
------------------------------
============================== / Image, project-relative, link to WikiStart
[[Image(/browser/« test »?format=raw, link=wiki:WikiStart)]]
------------------------------
<p>
<a style="padding:0; border:none" href="/wiki/WikiStart"><img src="/browser/%C2%AB%20test%C2%A0%C2%BB?format=raw" alt="/browser/« test »" title="/browser/« test »" /></a>
</p>
------------------------------
"""

# Note: in the <img> src attribute above, the Unicode characters
#       within the URI sometimes come out as %-encoded, sometimes raw
#       (server-relative case). Both forms are valid (at least
#       according to the W3C XHTML validator).



# == [[TitleIndex]]

def add_pages(tc, names):
    now = datetime.now(utc)
    for name in names:
        w = WikiPage(tc.env)
        w.name = name
        w.text = '--'
        w.save('joe', 'the page ' + name, '::1', now)

def titleindex_teardown(tc):
    tc.env.reset_db()



TITLEINDEX1_MACRO_TEST_CASES = u"""
============================== TitleIndex, default format
[[TitleIndex()]]
------------------------------
<p>
</p><div class="titleindex"><ul><li><a href="/wiki/WikiStart">WikiStart</a></li></ul></div><p>
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
</p><div class="titleindex"><ul><li><a href="/wiki/WikiEnd">WikiEnd</a></li><li><a href="/wiki/WikiStart">WikiStart</a></li></ul></div><p>
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
============================== TitleIndex, default format with prefix
[[TitleIndex(Wiki)]]
------------------------------
<p>
</p><div class="titleindex"><ul><li><a href="/wiki/WikiEnd">WikiEnd</a></li><li><a href="/wiki/WikiStart">WikiStart</a></li></ul></div><p>
</p>
------------------------------
[[TitleIndex(...)]]
============================== TitleIndex, compact format with prefix
[[TitleIndex(Wiki,format=compact)]]
------------------------------
<p>
<a href="/wiki/WikiEnd">WikiEnd</a>, <a href="/wiki/WikiStart">WikiStart</a>
</p>
------------------------------
[[TitleIndex(...)]]
============================== TitleIndex, default format with prefix hidden
[[TitleIndex(Wiki,hideprefix)]]
------------------------------
<p>
</p><div class="titleindex"><ul><li><a href="/wiki/WikiEnd">End</a></li><li><a href="/wiki/WikiStart">Start</a></li></ul></div><p>
</p>
------------------------------
[[TitleIndex(...)]]
============================== TitleIndex, compact format with prefix hidden
[[TitleIndex(Wiki,hideprefix,format=compact)]]
------------------------------
<p>
<a href="/wiki/WikiEnd">End</a>, <a href="/wiki/WikiStart">Start</a>
</p>
------------------------------
[[TitleIndex(...)]]
"""

def titleindex2_setup(tc):
    add_pages(tc, ['WikiEnd'])


TITLEINDEX3_MACRO_TEST_CASES = u"""
============================== TitleIndex, group format
[[TitleIndex(Wiki,format=group)]]
------------------------------
<p>
</p><div class="titleindex"><ul><li><strong>Wiki</strong><ul><li><strong>End</strong><ul><li><a href="/wiki/WikiEnd/First">WikiEnd/First</a></li><li><a href="/wiki/WikiEnd/Second">WikiEnd/Second</a></li></ul></li><li><strong>Start</strong><ul><li><a href="/wiki/WikiStart">WikiStart</a></li><li><a href="/wiki/WikiStart/First">WikiStart/First</a></li><li><a href="/wiki/WikiStart/Second">WikiStart/Second</a></li><li><a href="/wiki/WikiStart/Third">WikiStart/Third</a></li></ul></li></ul></li></ul></div><p>
</p>
------------------------------
============================== TitleIndex, hierarchy format
[[TitleIndex(WikiStart/, format=hierarchy)]]
------------------------------
<p>
</p><div class="titleindex"><ul><li>WikiStart<ul><li><a href="/wiki/WikiStart/First">First</a></li><li><a href="/wiki/WikiStart/Second">Second</a></li><li><a href="/wiki/WikiStart/Third">Third</a></li></ul></li></ul></div><p>
</p>
------------------------------
============================== TitleIndex, group format, prefix hidden
[[TitleIndex(Wiki,hideprefix,format=group)]]
------------------------------
<p>
</p><div class="titleindex"><ul><li><strong>End</strong><ul><li><a href="/wiki/WikiEnd/First">End/First</a></li><li><a href="/wiki/WikiEnd/Second">End/Second</a></li></ul></li><li><strong>Start</strong><ul><li><a href="/wiki/WikiStart">Start</a></li><li><a href="/wiki/WikiStart/First">Start/First</a></li><li><a href="/wiki/WikiStart/Second">Start/Second</a></li><li><a href="/wiki/WikiStart/Third">Start/Third</a></li></ul></li></ul></div><p>
</p>
------------------------------
============================== TitleIndex, hierarchy format, prefix hidden
[[TitleIndex(WikiStart/,hideprefix,format=hierarchy)]]
------------------------------
<p>
</p><div class="titleindex"><ul><li><a href="/wiki/WikiStart/First">First</a></li><li><a href="/wiki/WikiStart/Second">Second</a></li><li><a href="/wiki/WikiStart/Third">Third</a></li></ul></div><p>
</p>
------------------------------
"""

def titleindex3_setup(tc):
    add_pages(tc, [
        'WikiStart/First',
        'WikiStart/Second',
        'WikiStart/Third',
        'WikiEnd/First',
        'WikiEnd/Second',
        ])


TITLEINDEX4_MACRO_TEST_CASES = u"""
============================== TitleIndex group and page with numbers (#7919)
[[TitleIndex(format=group)]]
------------------------------
<p>
</p><div class="titleindex"><ul><li><strong>0.11</strong><ul><li><strong>Group</strong><ul><li><a href="/wiki/0.11/GroupOne">0.11/GroupOne</a></li><li><a href="/wiki/0.11/GroupTwo">0.11/GroupTwo</a></li></ul></li><li><a href="/wiki/0.11/Test">0.11/Test</a></li></ul></li><li><strong>Test</strong><ul><li><strong>0.11</strong><ul><li><a href="/wiki/Test0.11/Abc">Test0.11/Abc</a></li><li><a href="/wiki/Test0.11Abc">Test0.11Abc</a></li></ul></li><li><strong>0.12</strong><ul><li><a href="/wiki/Test0.12Def">Test0.12Def</a></li><li><a href="/wiki/Test0.12Ijk">Test0.12Ijk</a></li></ul></li><li><strong>0.13</strong><ul><li><a href="/wiki/Test0.13alpha">Test0.13alpha</a></li><li><a href="/wiki/Test0.13beta">Test0.13beta</a></li></ul></li><li><a href="/wiki/Test0.131">Test0.131</a></li><li><a href="/wiki/Test2">Test2</a></li><li><a href="/wiki/TestTest">TestTest</a></li><li><a href="/wiki/TestThing">TestThing</a></li></ul></li><li><a href="/wiki/WikiStart">WikiStart</a></li></ul></div><p>
</p>
------------------------------
"""

def titleindex4_setup(tc):
    add_pages(tc, [
        'TestTest',
        'TestThing',
        'Test2',
        'Test0.11Abc',
        'Test0.11/Abc',
        'Test0.12Def',
        'Test0.12Ijk',
        'Test0.13alpha',
        'Test0.13beta',
        'Test0.131',
        '0.11/Test',
        '0.11/GroupOne',
        '0.11/GroupTwo',
        ])


TITLEINDEX5_MACRO_TEST_CASES = u"""
============================== TitleIndex, hierarchy format with complex hierarchy
[[TitleIndex(format=hierarchy)]]
------------------------------
<p>
</p><div class="titleindex"><ul><li><a href="/wiki/TracDev">TracDev</a><ul><li><a href="/wiki/TracDev/ApiChanges">ApiChanges</a><ul><li><a href="/wiki/TracDev/ApiChanges/0.10">0.10</a></li><li><a href="/wiki/TracDev/ApiChanges/0.11">0.11</a></li><li><a href="/wiki/TracDev/ApiChanges/0.12">0.12</a><ul><li>Missing<ul><li><a href="/wiki/TracDev/ApiChanges/0.12/Missing/Exists">Exists</a></li></ul></li></ul></li></ul></li></ul></li><li><a href="/wiki/WikiStart">WikiStart</a></li></ul></div><p>
</p>
------------------------------
============================== TitleIndex, hierarchy format with complex hierarchy (and min=5)
[[TitleIndex(format=hierarchy,min=5)]]
------------------------------
<p>
</p><div class="titleindex"><ul><li><a href="/wiki/TracDev">TracDev</a><ul><li><a href="/wiki/TracDev/ApiChanges">ApiChanges</a></li><li><a href="/wiki/TracDev/ApiChanges/0.10">ApiChanges/0.10</a></li><li><a href="/wiki/TracDev/ApiChanges/0.11">ApiChanges/0.11</a></li><li><a href="/wiki/TracDev/ApiChanges/0.12">ApiChanges/0.12</a></li><li><a href="/wiki/TracDev/ApiChanges/0.12/Missing/Exists">ApiChanges/0.12/Missing/Exists</a></li></ul></li><li><a href="/wiki/WikiStart">WikiStart</a></li></ul></div><p>
</p>
------------------------------
============================== TitleIndex, group format with complex hierarchy
[[TitleIndex(format=group)]]
------------------------------
<p>
</p><div class="titleindex"><ul><li><strong>TracDev</strong><ul><li><a href="/wiki/TracDev">TracDev</a></li><li><strong>ApiChanges</strong><ul><li><a href="/wiki/TracDev/ApiChanges">TracDev/ApiChanges</a></li><li><a href="/wiki/TracDev/ApiChanges/0.10">TracDev/ApiChanges/0.10</a></li><li><a href="/wiki/TracDev/ApiChanges/0.11">TracDev/ApiChanges/0.11</a></li><li><strong>0.12</strong><ul><li><a href="/wiki/TracDev/ApiChanges/0.12">TracDev/ApiChanges/0.12</a></li><li><a href="/wiki/TracDev/ApiChanges/0.12/Missing/Exists">TracDev/ApiChanges/0.12/Missing/Exists</a></li></ul></li></ul></li></ul></li><li><a href="/wiki/WikiStart">WikiStart</a></li></ul></div><p>
</p>
------------------------------
"""

def titleindex5_setup(tc):
    add_pages(tc, [
        'TracDev',
        'TracDev/ApiChanges',
        'TracDev/ApiChanges/0.10',
        'TracDev/ApiChanges/0.11',
        'TracDev/ApiChanges/0.12',
        'TracDev/ApiChanges/0.12/Missing/Exists',
        ])


def suite():
    suite = unittest.TestSuite()
    suite.addTest(formatter.suite(IMAGE_MACRO_TEST_CASES, file=__file__))
    suite.addTest(formatter.suite(TITLEINDEX1_MACRO_TEST_CASES, file=__file__))
    suite.addTest(formatter.suite(TITLEINDEX2_MACRO_TEST_CASES, file=__file__,
                                  setup=titleindex2_setup,
                                  teardown=titleindex_teardown))
    suite.addTest(formatter.suite(TITLEINDEX3_MACRO_TEST_CASES, file=__file__,
                                  setup=titleindex3_setup,
                                  teardown=titleindex_teardown))
    suite.addTest(formatter.suite(TITLEINDEX4_MACRO_TEST_CASES, file=__file__,
                                  setup=titleindex4_setup,
                                  teardown=titleindex_teardown))
    suite.addTest(formatter.suite(TITLEINDEX5_MACRO_TEST_CASES, file=__file__,
                                  setup=titleindex5_setup,
                                  teardown=titleindex_teardown))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
