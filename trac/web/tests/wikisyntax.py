import unittest

from trac.wiki.tests import formatter

TEST_CASES = """
============================== htdocs: links resolver
htdocs:release-1.0.tar.gz

[htdocs:release-1.0.tar.gz Release 1.0]
------------------------------
<p>
<a href="/chrome/site/release-1.0.tar.gz">htdocs:release-1.0.tar.gz</a>
</p>
<p>
<a href="/chrome/site/release-1.0.tar.gz">Release 1.0</a>
</p>
------------------------------
"""

def suite():
    return formatter.suite(TEST_CASES, file=__file__)

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
