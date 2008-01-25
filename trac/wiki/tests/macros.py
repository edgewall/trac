import unittest

import trac.wiki.macros
from trac.wiki.tests import formatter

IMAGE_MACRO_TEST_CASES=u"""
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


def suite():
    suite = unittest.TestSuite()
    suite.addTest(formatter.suite(IMAGE_MACRO_TEST_CASES, file=__file__))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
