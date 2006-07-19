import unittest

from trac.wiki.api import WikiSystem
from trac.wiki.model import WikiPage
from trac.wiki.tests import formatter

TEST_CASES=u"""
============================== wiki: link resolver
wiki:TestPage
wiki:TestPage/
wiki:"Space 1 23"
wiki:"C'est l'\xe9t\xe9"
wiki:MissingPage
wiki:12
wiki:abc
------------------------------
<p>
<a class="wiki" href="/wiki/TestPage">wiki:TestPage</a>
<a class="wiki" href="/wiki/TestPage">wiki:TestPage/</a>
<a class="wiki" href="/wiki/Space%201%2023">wiki:"Space 1 23"</a>
<a class="wiki" href="/wiki/C%27est%20l%27%C3%A9t%C3%A9">wiki:"C'est l'\xe9t\xe9"</a>
<a class="missing wiki" href="/wiki/MissingPage" rel="nofollow">wiki:MissingPage?</a>
<a class="missing wiki" href="/wiki/12" rel="nofollow">wiki:12?</a>
<a class="missing wiki" href="/wiki/abc" rel="nofollow">wiki:abc?</a>
</p>
------------------------------
============================== WikiPageNames conformance
CamelCase AlabamA ABc AlaBamA FooBar
------------------------------
<p>
<a class="missing wiki" href="/wiki/CamelCase" rel="nofollow">CamelCase?</a> AlabamA ABc AlaBamA <a class="missing wiki" href="/wiki/FooBar" rel="nofollow">FooBar?</a>
</p>
------------------------------
============================== More WikiPageNames conformance
CamelCase,CamelCase.CamelCase: CamelCase
------------------------------
<p>
<a class="missing wiki" href="/wiki/CamelCase" rel="nofollow">CamelCase?</a>,<a class="missing wiki" href="/wiki/CamelCase" rel="nofollow">CamelCase?</a>.<a class="missing wiki" href="/wiki/CamelCase" rel="nofollow">CamelCase?</a>: <a class="missing wiki" href="/wiki/CamelCase" rel="nofollow">CamelCase?</a>
</p>
------------------------------
============================== Escaping WikiPageNames
!CamelCase
------------------------------
<p>
CamelCase
</p>
------------------------------
============================== WikiPageNames endings
foo (FooBar )
foo FooBar: something
foo FooBar.
FooBar, foo
foo FooBar;
foo FooBar!
foo FooBar?
foo (FooBar)
foo {FooBar}
foo 'FooBar'
foo "FooBar"
foo [FooBar]
------------------------------
<p>
foo (<a class="missing wiki" href="/wiki/FooBar" rel="nofollow">FooBar?</a> )
foo <a class="missing wiki" href="/wiki/FooBar" rel="nofollow">FooBar?</a>: something
foo <a class="missing wiki" href="/wiki/FooBar" rel="nofollow">FooBar?</a>.
<a class="missing wiki" href="/wiki/FooBar" rel="nofollow">FooBar?</a>, foo
foo <a class="missing wiki" href="/wiki/FooBar" rel="nofollow">FooBar?</a>;
foo <a class="missing wiki" href="/wiki/FooBar" rel="nofollow">FooBar?</a>!
foo <a class="missing wiki" href="/wiki/FooBar" rel="nofollow">FooBar?</a>?
foo (<a class="missing wiki" href="/wiki/FooBar" rel="nofollow">FooBar?</a>)
foo {<a class="missing wiki" href="/wiki/FooBar" rel="nofollow">FooBar?</a>}
foo '<a class="missing wiki" href="/wiki/FooBar" rel="nofollow">FooBar?</a>'
foo "<a class="missing wiki" href="/wiki/FooBar" rel="nofollow">FooBar?</a>"
foo [<a class="missing wiki" href="/wiki/FooBar" rel="nofollow">FooBar?</a>]
</p>
------------------------------
============================== WikiPageNames counter examples
A0B1, ST62T53C6, IR32V1H000
------------------------------
<p>
A0B1, ST62T53C6, IR32V1H000
</p>
------------------------------
============================== WikiPageNames with fragment identifier
SandBox#heading-fixed-id
------------------------------
<p>
<a class="missing wiki" href="/wiki/SandBox#heading-fixed-id" rel="nofollow">SandBox#heading-fixed-id?</a>
</p>
------------------------------
============================== WikiPageNames counter examples (paths)
/absolute/path/is/NotWiki and relative/path/is/NotWiki
/ThisIsNotWikiEither and /ThisIs/NotWikiEither but ThisIs/SubWiki
------------------------------
<p>
/absolute/path/is/NotWiki and relative/path/is/NotWiki
/ThisIsNotWikiEither and /ThisIs/NotWikiEither but <a class="missing wiki" href="/wiki/ThisIs/SubWiki" rel="nofollow">ThisIs/SubWiki?</a>
</p>
------------------------------
============================== WikiPageNames counter examples (numbers)
8FjBpOmy
anotherWikiPageName
------------------------------
<p>
8FjBpOmy
anotherWikiPageName
</p>
------------------------------
8FjBpOmy
anotherWikiPageName
============================== MoinMoin style forced links
This is a ["Wiki"] page link.
------------------------------
<p>
This is a <a class="missing wiki" href="/wiki/Wiki" rel="nofollow">Wiki?</a> page link.
</p>
------------------------------
============================== InterTrac for wiki
t:wiki:InterTrac
trac:wiki:InterTrac
[t:wiki:InterTrac intertrac]
[trac:wiki:InterTrac intertrac]
------------------------------
<p>
<a class="ext-link" href="http://projects.edgewall.com/trac/wiki/InterTrac" title="wiki:InterTrac in Trac's Trac"><span class="icon">t:wiki:InterTrac</span></a>
<a class="ext-link" href="http://projects.edgewall.com/trac/wiki/InterTrac" title="wiki:InterTrac in Trac's Trac"><span class="icon">trac:wiki:InterTrac</span></a>
<a class="ext-link" href="http://projects.edgewall.com/trac/wiki/InterTrac" title="wiki:InterTrac in Trac's Trac"><span class="icon">intertrac</span></a>
<a class="ext-link" href="http://projects.edgewall.com/trac/wiki/InterTrac" title="wiki:InterTrac in Trac's Trac"><span class="icon">intertrac</span></a>
</p>
------------------------------
============================== Wiki InterTrac shorthands
t:InterTrac
trac:InterTrac
[t:InterTrac intertrac]
[trac:InterTrac intertrac]
------------------------------
<p>
<a class="ext-link" href="http://projects.edgewall.com/trac/search?q=InterTrac" title="InterTrac in Trac's Trac"><span class="icon">t:InterTrac</span></a>
<a class="ext-link" href="http://projects.edgewall.com/trac/search?q=InterTrac" title="InterTrac in Trac's Trac"><span class="icon">trac:InterTrac</span></a>
<a class="ext-link" href="http://projects.edgewall.com/trac/search?q=InterTrac" title="InterTrac in Trac's Trac"><span class="icon">intertrac</span></a>
<a class="ext-link" href="http://projects.edgewall.com/trac/search?q=InterTrac" title="InterTrac in Trac's Trac"><span class="icon">intertrac</span></a>
</p>
------------------------------
"""

def wiki_setup(tc):
    wiki1 = WikiPage(tc.env)
    wiki1.name = 'TestPage'
    wiki1.text = '--'
    wiki1.save('joe', 'normal WikiPageNames', '::1', 42)

    wiki2 = WikiPage(tc.env)
    wiki2.name = 'Space 1 23'
    wiki2.text = '--'
    wiki2.save('joe', 'not a WikiPageNames', '::1', 42)

    wiki3 = WikiPage(tc.env)
    wiki3.name = u"C'est l'\xe9t\xe9"
    wiki3.text = '--'
    wiki3.save('joe', 'unicode WikiPageNames', '::1', 42)

def suite():
    return formatter.suite(TEST_CASES, wiki_setup, __file__)

if __name__ == '__main__':
    unittest.main(defaultTest='suite') 
