# -*- encoding: utf-8 -*-

import unittest

from trac.test import Mock
from trac.versioncontrol import NoSuchChangeset
from trac.versioncontrol.api import *
from trac.versioncontrol.web_ui import *
from trac.wiki.tests import formatter


def _get_changeset(rev):
    if rev == '1':
        return Mock(message="start", can_view=lambda perm: True)
    else:
        raise NoSuchChangeset(rev)

def _normalize_rev(rev):
    try:
        return int(rev)
    except ValueError:
        if rev == 'head':
            return '200'
        else:
            raise NoSuchChangeset(rev)
    
def _get_repository(reponame):
    return Mock(reponame=reponame, youngest_rev='200',
                get_changeset=_get_changeset,
                normalize_rev=_normalize_rev)

def repository_setup(tc):
    setattr(tc.env, 'get_repository', _get_repository)
    setattr(RepositoryManager(tc.env), 'get_repository', _get_repository)


CHANGESET_TEST_CASES = u"""
============================== changeset: link resolver
changeset:1
changeset:12
changeset:abc
changeset:1, changeset:1/README.txt
------------------------------
<p>
<a class="changeset" href="/changeset/1" title="start">changeset:1</a>
<a class="missing changeset" title="No changeset 12 in the repository">changeset:12</a>
<a class="missing changeset" title="No changeset abc in the repository">changeset:abc</a>
<a class="changeset" href="/changeset/1" title="start">changeset:1</a>, <a class="changeset" href="/changeset/1/README.txt" title="start">changeset:1/README.txt</a>
</p>
------------------------------
============================== changeset: link resolver + query and fragment
changeset:1?format=diff
changeset:1#file0
------------------------------
<p>
<a class="changeset" href="/changeset/1?format=diff" title="start">changeset:1?format=diff</a>
<a class="changeset" href="/changeset/1#file0" title="start">changeset:1#file0</a>
</p>
------------------------------
============================== changeset shorthand syntax
[1], r1
[12], r12, rABC
[1/README.txt], r1/trunk, rABC/trunk
------------------------------
<p>
<a class="changeset" href="/changeset/1" title="start">[1]</a>, <a class="changeset" href="/changeset/1" title="start">r1</a>
<a class="missing changeset" title="No changeset 12 in the repository">[12]</a>, <a class="missing changeset" title="No changeset 12 in the repository">r12</a>, rABC
<a class="changeset" href="/changeset/1/README.txt" title="start">[1/README.txt]</a>, <a class="changeset" href="/changeset/1/trunk" title="start">r1/trunk</a>, rABC/trunk
</p>
------------------------------
============================== changeset shorthand syntax + query and fragment
[1?format=diff]
[1#file0]
[1/README.txt?format=diff]
[1/README.txt#file0]
------------------------------
<p>
<a class="changeset" href="/changeset/1?format=diff" title="start">[1?format=diff]</a>
<a class="changeset" href="/changeset/1#file0" title="start">[1#file0]</a>
<a class="changeset" href="/changeset/1/README.txt?format=diff" title="start">[1/README.txt?format=diff]</a>
<a class="changeset" href="/changeset/1/README.txt#file0" title="start">[1/README.txt#file0]</a>
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

rfc and rfc:4180 should not be changeset links, neither should rfc4180
------------------------------
<p>
Change:<a class="missing changeset" title="No changeset 10 in the repository">[10]</a> There should be a link to changeset <a class="missing changeset" title="No changeset 10 in the repository">[10]</a>
</p>
<p>
rfc and rfc:4180 should not be changeset links, neither should rfc4180
</p>
------------------------------
Change:<a class="missing changeset" title="No changeset 10 in the repository">[10]</a> There should be a link to changeset <a class="missing changeset" title="No changeset 10 in the repository">[10]</a>

rfc and rfc:4180 should not be changeset links, neither should rfc4180
============================== InterTrac for changesets
trac:changeset:2081
[trac:changeset:2081 Trac r2081]
------------------------------
<p>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/changeset%3A2081" title="changeset:2081 in Trac's Trac"><span class="icon"></span>trac:changeset:2081</a>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/changeset%3A2081" title="changeset:2081 in Trac's Trac"><span class="icon"></span>Trac r2081</a>
</p>
------------------------------
============================== Changeset InterTrac shorthands
[T2081]
[trac 2081]
[trac 2081/trunk]
T:r2081
------------------------------
<p>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/changeset%3A2081" title="changeset:2081 in Trac's Trac"><span class="icon"></span>[T2081]</a>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/changeset%3A2081" title="changeset:2081 in Trac's Trac"><span class="icon"></span>[trac 2081]</a>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/changeset%3A2081/trunk" title="changeset:2081/trunk in Trac\'s Trac"><span class="icon"></span>[trac 2081/trunk]</a>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/r2081" title="r2081 in Trac's Trac"><span class="icon"></span>T:r2081</a>
</p>
------------------------------
""" #"


LOG_TEST_CASES = u"""
============================== Log range TracLinks
[1:2], r1:2, [12:23], r12:23
[1:2/trunk], r1:2/trunk
[2:1/trunk] reversed, r2:1/trunk reversed
------------------------------
<p>
<a class="source" href="/log/?revs=1-2">[1:2]</a>, <a class="source" href="/log/?revs=1-2">r1:2</a>, <a class="source" href="/log/?revs=12-23">[12:23]</a>, <a class="source" href="/log/?revs=12-23">r12:23</a>
<a class="source" href="/log/trunk?revs=1-2">[1:2/trunk]</a>, <a class="source" href="/log/trunk?revs=1-2">r1:2/trunk</a>
<a class="source" href="/log/trunk?revs=1-2">[2:1/trunk]</a> reversed, <a class="source" href="/log/trunk?revs=1-2">r2:1/trunk</a> reversed
</p>
------------------------------
============================== Big ranges (#9955 regression)
[1234567890:12345678901]
------------------------------
<p>
<a class="source" href="/log/?revs=1234567890-12345678901">[1234567890:12345678901]</a>
</p>
------------------------------
<a class="source" href="/log/?revs=1234567890-12345678901">[1234567890:12345678901]</a>
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
log:trunk:12-head
log:trunk:12@23 (bad, but shouldn't error out)
------------------------------
<p>
<a class="source" href="/log/?rev=12">log:@12</a>
<a class="source" href="/log/trunk">log:trunk</a>
<a class="source" href="/log/trunk?rev=12">log:trunk@12</a>
<a class="source" href="/log/trunk?revs=12-23">log:trunk@12:23</a>
<a class="source" href="/log/trunk?revs=12-23">log:trunk@12-23</a>
<a class="source" href="/log/trunk?revs=12-23">log:trunk:12:23</a>
<a class="source" href="/log/trunk?revs=12-23">log:trunk:12-23</a>
<a class="source" href="/log/trunk?revs=12-200">log:trunk:12-head</a>
<a class="source" href="/log/trunk">log:trunk:12@23</a> (bad, but shouldn't error out)
</p>
------------------------------
============================== log: link resolver + query
log:?limit=10
log:@12?limit=10
log:trunk?limit=10
log:trunk@12?limit=10
[10:20?verbose=yes&format=changelog]
[10:20/trunk?verbose=yes&format=changelog]
------------------------------
<p>
<a class="source" href="/log/?limit=10">log:?limit=10</a>
<a class="source" href="/log/?rev=12&amp;limit=10">log:@12?limit=10</a>
<a class="source" href="/log/trunk?limit=10">log:trunk?limit=10</a>
<a class="source" href="/log/trunk?rev=12&amp;limit=10">log:trunk@12?limit=10</a>
<a class="source" href="/log/?revs=10-20&amp;verbose=yes&amp;format=changelog">[10:20?verbose=yes&amp;format=changelog]</a>
<a class="source" href="/log/trunk?revs=10-20&amp;verbose=yes&amp;format=changelog">[10:20/trunk?verbose=yes&amp;format=changelog]</a>
</p>
------------------------------
============================== Multiple Log ranges
r12:20,25,35:56,68,69,100-120
[12:20,25,35:56,68,69,100-120]
[12:20,25,88:head,68,69] (not supported)
------------------------------
<p>
<a class="source" href="/log/?revs=12-20%2C25%2C35-56%2C68-69%2C100-120">r12:20,25,35:56,68,69,100-120</a>
<a class="source" href="/log/?revs=12-20%2C25%2C35-56%2C68-69%2C100-120">[12:20,25,35:56,68,69,100-120]</a>
[12:20,25,88:head,68,69] (not supported)
</p>
------------------------------
============================== Link resolver counter examples
rfc:4180 should not be a log link
------------------------------
<p>
rfc:4180 should not be a log link
</p>
------------------------------
============================== Log range InterTrac shorthands
[T3317:3318]
[trac 3317:3318]
[trac 3317:3318/trunk]
------------------------------
<p>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/log%3A/%403317%3A3318" title="log:/@3317:3318 in Trac\'s Trac"><span class="icon"></span>[T3317:3318]</a>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/log%3A/%403317%3A3318" title="log:/@3317:3318 in Trac\'s Trac"><span class="icon"></span>[trac 3317:3318]</a>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/log%3A/trunk%403317%3A3318" title="log:/trunk@3317:3318 in Trac\'s Trac"><span class="icon"></span>[trac 3317:3318/trunk]</a>
</p>
------------------------------
"""


DIFF_TEST_CASES = u"""
============================== diff: link resolver
diff:trunk//branch
diff:trunk@12//branch@23
diff:trunk@12:23
diff:@12:23
------------------------------
<p>
<a class="changeset" href="/changeset?new_path=branch&amp;old_path=trunk" title="Diff from trunk@latest to branch@latest">diff:trunk//branch</a>
<a class="changeset" href="/changeset?new=23&amp;new_path=branch&amp;old=12&amp;old_path=trunk" title="Diff from trunk@12 to branch@23">diff:trunk@12//branch@23</a>
<a class="changeset" href="/changeset?new=23&amp;new_path=trunk&amp;old=12&amp;old_path=trunk" title="Diff [12:23] for trunk">diff:trunk@12:23</a>
<a class="changeset" href="/changeset?new=23&amp;old=12" title="Diff [12:23] for /">diff:@12:23</a>
</p>
------------------------------
============================== diff: link resolver + query
diff:trunk//branch?format=diff
------------------------------
<p>
<a class="changeset" href="/changeset?new_path=branch&amp;old_path=trunk&amp;format=diff" title="Diff from trunk@latest to branch@latest">diff:trunk//branch?format=diff</a>
</p>
------------------------------
============================== diff: link, empty diff
diff://
------------------------------
<p>
<a class="changeset" title="Diff [latest:latest] for /">diff://</a>
</p>
------------------------------
"""


SOURCE_TEST_CASES = u"""
============================== source: link resolver
source:/foo/bar
source:/foo/bar#42   # no long works as rev spec
source:/foo/bar#head #
source:/foo/bar@42
source:/foo/bar@head
source:/foo%20bar/baz%2Bquux
source:@42
source:/foo/bar@42#L20
source:/foo/bar@head#L20
source:/foo/bar@#L20
------------------------------
<p>
<a class="source" href="/browser/foo/bar">source:/foo/bar</a>
<a class="source" href="/browser/foo/bar#42">source:/foo/bar#42</a>   # no long works as rev spec
<a class="source" href="/browser/foo/bar#head">source:/foo/bar#head</a> #
<a class="source" href="/browser/foo/bar?rev=42">source:/foo/bar@42</a>
<a class="source" href="/browser/foo/bar?rev=head">source:/foo/bar@head</a>
<a class="source" href="/browser/foo%2520bar/baz%252Bquux">source:/foo%20bar/baz%2Bquux</a>
<a class="source" href="/browser/?rev=42">source:@42</a>
<a class="source" href="/browser/foo/bar?rev=42#L20">source:/foo/bar@42#L20</a>
<a class="source" href="/browser/foo/bar?rev=head#L20">source:/foo/bar@head#L20</a>
<a class="source" href="/browser/foo/bar#L20">source:/foo/bar@#L20</a>
</p>
------------------------------
============================== source: link resolver + query 
source:/foo?order=size&desc=1
source:/foo/bar?format=raw
------------------------------
<p>
<a class="source" href="/browser/foo?order=size&amp;desc=1">source:/foo?order=size&amp;desc=1</a>
<a class="source" href="/browser/foo/bar?format=raw">source:/foo/bar?format=raw</a>
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
============================== export: link resolver
export:/foo/bar.html
export:123:/foo/pict.gif
export:/foo/pict.gif@123
------------------------------
<p>
<a class="export" href="/export/HEAD/foo/bar.html">export:/foo/bar.html</a>
<a class="export" href="/export/123/foo/pict.gif">export:123:/foo/pict.gif</a>
<a class="export" href="/export/123/foo/pict.gif">export:/foo/pict.gif@123</a>
</p>
------------------------------
============================== export: link resolver + fragment
export:/foo/bar.html#header
------------------------------
<p>
<a class="export" href="/export/HEAD/foo/bar.html#header">export:/foo/bar.html#header</a>
</p>
------------------------------
""" # " (be Emacs friendly...)



def suite():
    suite = unittest.TestSuite()
    suite.addTest(formatter.suite(CHANGESET_TEST_CASES, repository_setup,
                                  __file__))
    suite.addTest(formatter.suite(LOG_TEST_CASES, repository_setup,
                                  file=__file__))
    suite.addTest(formatter.suite(DIFF_TEST_CASES, file=__file__))
    suite.addTest(formatter.suite(SOURCE_TEST_CASES, repository_setup,
                                  file=__file__))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
