import unittest

from trac.test import Mock
from trac.wiki.tests import formatter
from trac.versioncontrol.web_ui import *

CHANGESET_TEST_CASES="""
============================== changeset: link resolver
changeset:1
changeset:12
changeset:abc
changeset:1, changeset:1/README.txt
------------------------------
<p>
<a class="missing changeset" href="/changeset/1" rel="nofollow">changeset:1</a>
<a class="missing changeset" href="/changeset/12" rel="nofollow">changeset:12</a>
<a class="missing changeset" href="/changeset/abc" rel="nofollow">changeset:abc</a>
<a class="missing changeset" href="/changeset/1" rel="nofollow">changeset:1</a>, <a class="missing changeset" href="/changeset/1/README.txt" rel="nofollow">changeset:1/README.txt</a>
</p>
------------------------------
============================== changeset shorthand syntax
[1], r1
[12], r12, rABC
[1/README.txt]
------------------------------
<p>
<a class="missing changeset" href="/changeset/1" rel="nofollow">[1]</a>, <a class="missing changeset" href="/changeset/1" rel="nofollow">r1</a>
<a class="missing changeset" href="/changeset/12" rel="nofollow">[12]</a>, <a class="missing changeset" href="/changeset/12" rel="nofollow">r12</a>, rABC
<a class="missing changeset" href="/changeset/1/README.txt" rel="nofollow">[1/README.txt]</a>
</p>
------------------------------
============================== escaping the above
![1], !r1
------------------------------
<p>
[1], r1
</p>
------------------------------
[1], r1
============================== Link resolver counter examples
Change:[10] There should be a link to changeset [10]
------------------------------
<p>
Change:<a class="missing changeset" href="/changeset/10" rel="nofollow">[10]</a> There should be a link to changeset <a class="missing changeset" href="/changeset/10" rel="nofollow">[10]</a>
</p>
------------------------------
Change:<a class="missing changeset" href="/changeset/10" rel="nofollow">[10]</a> There should be a link to changeset <a class="missing changeset" href="/changeset/10" rel="nofollow">[10]</a>
============================== InterTrac for changesets
trac:changeset:2081
[trac:changeset:2081 Trac r2081]
[T2081]
[trac 2081]
------------------------------
<p>
<a class="ext-link" href="http://projects.edgewall.com/trac/changeset/2081" title="changeset:2081 in Trac's Trac"><span class="icon"></span>trac:changeset:2081</a>
<a class="ext-link" href="http://projects.edgewall.com/trac/changeset/2081" title="changeset:2081 in Trac's Trac"><span class="icon"></span>Trac r2081</a>
<a class="ext-link" href="http://projects.edgewall.com/trac/changeset/2081" title="changeset:2081 in Trac's Trac"><span class="icon"></span>[T2081]</a>
<a class="ext-link" href="http://projects.edgewall.com/trac/changeset/2081" title="changeset:2081 in Trac's Trac"><span class="icon"></span>[trac 2081]</a>
</p>
------------------------------
============================== Changeset InterTrac shorthands
t:InterTrac
trac:InterTrac
[t:InterTrac intertrac]
[trac:InterTrac intertrac]
T:r2081
------------------------------
<p>
<a class="ext-link" href="http://projects.edgewall.com/trac/search?q=InterTrac" title="InterTrac in Trac's Trac"><span class="icon"></span>t:InterTrac</a>
<a class="ext-link" href="http://projects.edgewall.com/trac/search?q=InterTrac" title="InterTrac in Trac's Trac"><span class="icon"></span>trac:InterTrac</a>
<a class="ext-link" href="http://projects.edgewall.com/trac/search?q=InterTrac" title="InterTrac in Trac's Trac"><span class="icon"></span>intertrac</a>
<a class="ext-link" href="http://projects.edgewall.com/trac/search?q=InterTrac" title="InterTrac in Trac's Trac"><span class="icon"></span>intertrac</a>
<a class="ext-link" href="http://projects.edgewall.com/trac/search?q=r2081" title="r2081 in Trac's Trac"><span class="icon"></span>T:r2081</a>
</p>
------------------------------
"""

def _get_changeset(self, x):
    raise TracError("No changeset")

def _get_repository(self):
    return Mock(get_changeset=_get_changeset)

def changeset_setup(tc):
    setattr(tc.env, 'get_repository', _get_repository)


LOG_TEST_CASES="""
============================== Log range TracLinks
[1:2], r1:2, [12:23], r12:23
------------------------------
<p>
<a class="source" href="/log/?rev=2&amp;stop_rev=1">[1:2]</a>, <a class="source" href="/log/?rev=2&amp;stop_rev=1">r1:2</a>, <a class="source" href="/log/?rev=23&amp;stop_rev=12">[12:23]</a>, <a class="source" href="/log/?rev=23&amp;stop_rev=12">r12:23</a>
</p>
------------------------------
============================== Escaping Log range TracLinks
![1:2], !r1:2, ![12:23], !r12:23
------------------------------
<p>
[1:2], r1:2, [12:23], r12:23
</p>
------------------------------
[1:2], r1:2, [12:23], r12:23
============================== log: link resolver
log:@12
log:trunk
log:trunk@12
log:trunk@12:23
log:trunk@12-23
log:trunk:12:23
log:trunk:12-23
------------------------------
<p>
<a class="source" href="/log/?rev=12">log:@12</a>
<a class="source" href="/log/trunk">log:trunk</a>
<a class="source" href="/log/trunk?rev=12">log:trunk@12</a>
<a class="source" href="/log/trunk?rev=23&amp;stop_rev=12">log:trunk@12:23</a>
<a class="source" href="/log/trunk?rev=23&amp;stop_rev=12">log:trunk@12-23</a>
<a class="source" href="/log/trunk?rev=23&amp;stop_rev=12">log:trunk:12:23</a>
<a class="source" href="/log/trunk?rev=23&amp;stop_rev=12">log:trunk:12-23</a>
</p>
------------------------------
"""


DIFF_TEST_CASES="""
============================== diff: link resolver
diff:trunk//branch
diff:trunk@12//branch@23
diff:trunk@12:23
diff:@12:23
------------------------------
<p>
<a class="changeset" title="Diff from trunk@latest to branch@latest" href="/changeset?new_path=branch&old_path=trunk">diff:trunk//branch</a>
<a class="changeset" title="Diff from trunk@12 to branch@23" href="/changeset?new=23&new_path=branch&old=12&old_path=trunk">diff:trunk@12//branch@23</a>
<a class="changeset" title="Diff r12:23 for trunk" href="/changeset?new=23&new_path=trunk&old=12&old_path=trunk">diff:trunk@12:23</a>
<a class="changeset" title="Diff r12:23 for /" href="/changeset?new=23&old=12">diff:@12:23</a>
</p>
------------------------------
"""


SOURCE_TEST_CASES="""
============================== source: link resolver
source:/foo/bar
source:/foo/bar#42
source:/foo/bar#head
source:/foo/bar@42
source:/foo/bar@head
source:/foo%20bar/baz%2Bquux
source:/foo%2520bar/baz%252Bquux#42
source:#42
source:@42
source:/foo/bar@42#L20
source:/foo/bar@head#L20
------------------------------
<p>
<a class="source" href="/browser/foo/bar">source:/foo/bar</a>
<a class="source" href="/browser/foo/bar?rev=42">source:/foo/bar#42</a>
<a class="source" href="/browser/foo/bar?rev=head">source:/foo/bar#head</a>
<a class="source" href="/browser/foo/bar?rev=42">source:/foo/bar@42</a>
<a class="source" href="/browser/foo/bar?rev=head">source:/foo/bar@head</a>
<a class="source" href="/browser/foo%20bar/baz%2Bquux">source:/foo bar/baz+quux</a>
<a class="source" href="/browser/foo%2520bar/baz%252Bquux?rev=42">source:/foo%20bar/baz%2Bquux#42</a>
<a class="source" href="/browser/?rev=42">source:#42</a>
<a class="source" href="/browser/?rev=42">source:@42</a>
<a class="source" href="/browser/foo/bar?rev=42#L20">source:/foo/bar@42#L20</a>
<a class="source" href="/browser/foo/bar?rev=head#L20">source:/foo/bar@head#L20</a>
</p>
------------------------------
============================== source: provider, with quoting
source:'even with whitespaces'
source:"even with whitespaces"
[source:'even with whitespaces' Path with spaces]
[source:"even with whitespaces" Path with spaces]
------------------------------
<p>
<a class="source" href="/browser/even%20with%20whitespaces">source:'even with whitespaces'</a>
<a class="source" href="/browser/even%20with%20whitespaces">source:"even with whitespaces"</a>
<a class="source" href="/browser/even%20with%20whitespaces">Path with spaces</a>
<a class="source" href="/browser/even%20with%20whitespaces">Path with spaces</a>
</p>
------------------------------
""" # " (be Emacs friendly...)



def suite():
    suite = unittest.TestSuite()
    suite.addTest(formatter.suite(CHANGESET_TEST_CASES, changeset_setup,
                                  __file__))
    suite.addTest(formatter.suite(LOG_TEST_CASES, file=__file__))
    suite.addTest(formatter.suite(DIFF_TEST_CASES, file=__file__))
    suite.addTest(formatter.suite(SOURCE_TEST_CASES, file=__file__))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
