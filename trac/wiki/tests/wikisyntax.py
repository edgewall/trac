# -*- coding: utf-8 -*-

from datetime import datetime
import unittest

from trac.util.datefmt import utc
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
============================== wiki: link resolver + query and fragment
wiki:TestPage?format=txt
wiki:TestPage/?version=12
wiki:TestPage/?action=diff&version=12
wiki:"Space 1 23#heading"
------------------------------
<p>
<a class="wiki" href="/wiki/TestPage?format=txt">wiki:TestPage?format=txt</a>
<a class="wiki" href="/wiki/TestPage?version=12">wiki:TestPage/?version=12</a>
<a class="wiki" href="/wiki/TestPage?action=diff&amp;version=12">wiki:TestPage/?action=diff&amp;version=12</a>
<a class="wiki" href="/wiki/Space%201%2023#heading">wiki:"Space 1 23#heading"</a>
</p>
------------------------------
============================== WikiPageNames conformance
CamelCase AlabamA ABc AlaBamA FooBar
------------------------------
<p>
<a class="missing wiki" href="/wiki/CamelCase" rel="nofollow">CamelCase?</a> AlabamA ABc AlaBamA <a class="missing wiki" href="/wiki/FooBar" rel="nofollow">FooBar?</a>
</p>
------------------------------
============================== WikiPageNames conformance (unicode)
SmÅogstore should produce a link
and so should wiki:ÜberflüssigkeitsTheorie
------------------------------
<p>
<a class="missing wiki" href="/wiki/Sm%C3%85ogstore" rel="nofollow">SmÅogstore?</a> should produce a link
and so should <a class="missing wiki" href="/wiki/%C3%9Cberfl%C3%BCssigkeitsTheorie" rel="nofollow">wiki:ÜberflüssigkeitsTheorie?</a>
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

wiki:TracSubversion#TracandSubversion1.3.1. etc.
TracSubversion#TracandSubversion1.3.1. etc.
------------------------------
<p>
<a class="missing wiki" href="/wiki/SandBox#heading-fixed-id" rel="nofollow">SandBox#heading-fixed-id?</a>
</p>
<p>
<a class="missing wiki" href="/wiki/TracSubversion#TracandSubversion1.3.1" rel="nofollow">wiki:TracSubversion#TracandSubversion1.3.1?</a>. etc.
<a class="missing wiki" href="/wiki/TracSubversion#TracandSubversion1.3.1" rel="nofollow">TracSubversion#TracandSubversion1.3.1?</a>. etc.
</p>
------------------------------
============================== WikiPageNames with fragment id (performance test)
BillOfMaterials#get_bill_of_materials_from_room_xml(fpxml=nil)

[BillOfMaterials#get_bill_of_materials_from_room_xml(fpxml=nil)]

[BillOfMaterials#get_bill_of_materials_from_room_xml(fpxml=nil) speed]
------------------------------
<p>
<a class="missing wiki" href="/wiki/BillOfMaterials#get_bill_of_materials_from_room_xml" rel="nofollow">BillOfMaterials#get_bill_of_materials_from_room_xml?</a>(fpxml=nil)
</p>
<p>
[<a class="missing wiki" href="/wiki/BillOfMaterials#get_bill_of_materials_from_room_xml" rel="nofollow">BillOfMaterials#get_bill_of_materials_from_room_xml?</a>(fpxml=nil)]
</p>
<p>
[<a class="missing wiki" href="/wiki/BillOfMaterials#get_bill_of_materials_from_room_xml" rel="nofollow">BillOfMaterials#get_bill_of_materials_from_room_xml?</a>(fpxml=nil) speed]
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
============================== WikiPageNames counter examples (unicode)
Småbokstaver should not produce a link
neither should AbAbÅ nor AbAbÅÅb
------------------------------
<p>
Småbokstaver should not produce a link
neither should AbAbÅ nor AbAbÅÅb
</p>
------------------------------
Småbokstaver should not produce a link
neither should AbAbÅ nor AbAbÅÅb
============================== MoinMoin style forced links
This is a ["Wiki"] page link.
------------------------------
<p>
This is a <a class="missing wiki" href="/wiki/Wiki" rel="nofollow">Wiki?</a> page link.
</p>
------------------------------
============================== Wiki links with @version
wiki:page@12
WikiStart@12
WikiStart@12#heading
[WikiStart@12]
[WikiStart@12#heading]
This is a ["Wiki@12"] page link.
[wiki:WikiStart@12?format=txt v12 as text]
------------------------------
<p>
<a class="missing wiki" href="/wiki/page?version=12" rel="nofollow">wiki:page@12?</a>
<a class="wiki" href="/wiki/WikiStart?version=12">WikiStart@12</a>
<a class="wiki" href="/wiki/WikiStart?version=12#heading">WikiStart@12#heading</a>
[<a class="wiki" href="/wiki/WikiStart?version=12">WikiStart@12</a>]
[<a class="wiki" href="/wiki/WikiStart?version=12#heading">WikiStart@12#heading</a>]
This is a <a class="missing wiki" href="/wiki/Wiki?version=12" rel="nofollow">Wiki@12?</a> page link.
<a class="wiki" href="/wiki/WikiStart?version=12&amp;format=txt">v12 as text</a>
</p>
------------------------------
============================== WikiPageName with label
See details of the [WikiPageNames wiki page name] syntax.
------------------------------
<p>
See details of the <a class="missing wiki" href="/wiki/WikiPageNames" rel="nofollow">wiki page name?</a> syntax.
</p>
------------------------------
============================== WikiPageName with label should be strict...
new_channel_name [, '''integer''' handle [, '''boolean''' test]]
------------------------------
<p>
new_channel_name [, <strong>integer</strong> handle [, <strong>boolean</strong> test]]
</p>
------------------------------
============================== InterTrac for wiki
t:wiki:InterTrac
trac:wiki:InterTrac
[t:wiki:InterTrac intertrac]
[trac:wiki:InterTrac intertrac]
[trac:wiki:JonasBorgström jonas]
------------------------------
<p>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/wiki%3AInterTrac" title="wiki:InterTrac in Trac's Trac"><span class="icon">\xa0</span>t:wiki:InterTrac</a>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/wiki%3AInterTrac" title="wiki:InterTrac in Trac's Trac"><span class="icon">\xa0</span>trac:wiki:InterTrac</a>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/wiki%3AInterTrac" title="wiki:InterTrac in Trac's Trac"><span class="icon">\xa0</span>intertrac</a>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/wiki%3AInterTrac" title="wiki:InterTrac in Trac's Trac"><span class="icon">\xa0</span>intertrac</a>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/wiki%3AJonasBorgstr%C3%B6m" title="wiki:JonasBorgström in Trac's Trac"><span class="icon">\xa0</span>jonas</a>
</p>
------------------------------
============================== Wiki InterTrac shorthands
t:InterTrac
trac:InterTrac
[t:InterTrac intertrac]
[trac:InterTrac intertrac]
[trac:JonasBorgström jonas]
------------------------------
<p>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/InterTrac" title="InterTrac in Trac's Trac"><span class="icon">\xa0</span>t:InterTrac</a>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/InterTrac" title="InterTrac in Trac's Trac"><span class="icon">\xa0</span>trac:InterTrac</a>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/InterTrac" title="InterTrac in Trac's Trac"><span class="icon">\xa0</span>intertrac</a>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/InterTrac" title="InterTrac in Trac's Trac"><span class="icon">\xa0</span>intertrac</a>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/JonasBorgstr%C3%B6m" title="JonasBorgström in Trac's Trac"><span class="icon">\xa0</span>jonas</a>
</p>
------------------------------
============================== InterWiki links
This is the original MeatBall:InterMapTxt wiki page.
Checkout the [tsvn:http://svn.edgewall.com/repos/trac Trac Repository].

complex link complex:a:test with positional arguments
complex link complex:a (not enough arguments)
complex link complex:a:test:more (too many arguments)

NoLink:ignored
NoLink:
NoLink: ...
------------------------------
<p>
This is the original <a class="ext-link" href="http://www.usemod.com/cgi-bin/mb.pl?InterMapTxt" title="InterMapTxt in MeatBall..."><span class="icon">\xa0</span>MeatBall:InterMapTxt</a> wiki page.
Checkout the <a class="ext-link" href="tsvn:http://svn.edgewall.com/repos/trac" title="http://svn.edgewall.com/repos/trac in tsvn"><span class="icon">\xa0</span>Trac Repository</a>.
</p>
<p>
complex link <a class="ext-link" href="http://server/a/page/test?format=txt" title="resource test in a"><span class="icon">\xa0</span>complex:a:test</a> with positional arguments
complex link <a class="ext-link" href="http://server/a/page/?format=txt" title="resource  in a"><span class="icon">\xa0</span>complex:a</a> (not enough arguments)
complex link <a class="ext-link" href="http://server/a/page/test:more?format=txt" title="resource test:more in a"><span class="icon">\xa0</span>complex:a:test:more</a> (too many arguments)
</p>
<p>
NoLink:ignored
<a class="missing wiki" href="/wiki/NoLink" rel="nofollow">NoLink?</a>:
<a class="missing wiki" href="/wiki/NoLink" rel="nofollow">NoLink?</a>: ...
</p>
------------------------------
""" #" Emacs likes it that way better


RELATIVE_LINKS_TESTS=u"""
============================== Relative to the project url
[//docs Documentation]
[// Home]
------------------------------
<p>
<a href="/docs">Documentation</a>
<a href="/">Home</a>
</p>
------------------------------
============================== Relative to the base url
[/newticket?priority=high bug]
[/ Project]
------------------------------
<p>
<a href="/newticket?priority=high">bug</a>
<a href="/">Project</a>
</p>
------------------------------
============================== Relative to the current page
[./Detail see detail]
[.. see parent]
[../Other see other]
------------------------------
<p>
<a class="missing wiki" href="/wiki/Main/Sub/Detail" rel="nofollow">see detail?</a>
<a class="missing wiki" href="/wiki/Main" rel="nofollow">see parent?</a>
<a class="missing wiki" href="/wiki/Main/Other" rel="nofollow">see other?</a>
</p>
------------------------------
============================== Relative to the current page with anchors
[#topic see topic]
[.#topic see topic]
[./#topic see topic]
[./Detail#topic see detail]
[..#topic see parent]
[../#topic see parent]
[../Other#topic see other]
[../Other/#topic see other]
------------------------------
<p>
<a class="wiki" href="/wiki/Main/Sub#topic">see topic</a>
<a class="wiki" href="/wiki/Main/Sub#topic">see topic</a>
<a class="wiki" href="/wiki/Main/Sub#topic">see topic</a>
<a class="missing wiki" href="/wiki/Main/Sub/Detail#topic" rel="nofollow">see detail?</a>
<a class="missing wiki" href="/wiki/Main#topic" rel="nofollow">see parent?</a>
<a class="missing wiki" href="/wiki/Main#topic" rel="nofollow">see parent?</a>
<a class="missing wiki" href="/wiki/Main/Other#topic" rel="nofollow">see other?</a>
<a class="missing wiki" href="/wiki/Main/Other#topic" rel="nofollow">see other?</a>
</p>
------------------------------
""" # "


def wiki_setup(tc):
    now = datetime.now(utc)
    wiki0 = WikiPage(tc.env)
    wiki0.name = 'Main/Sub'
    wiki0.text = '--'
    wiki0.save('joe', 'subpage', '::1', now)

    wiki1 = WikiPage(tc.env)
    wiki1.name = 'TestPage'
    wiki1.text = '--'
    wiki1.save('joe', 'normal WikiPageNames', '::1', now)

    wiki2 = WikiPage(tc.env)
    wiki2.name = 'Space 1 23'
    wiki2.text = '--'
    wiki2.save('joe', 'not a WikiPageNames', '::1', now)

    wiki3 = WikiPage(tc.env)
    wiki3.name = u"C'est l'\xe9t\xe9"
    wiki3.text = '--'
    wiki3.save('joe', 'unicode WikiPageNames', '::1', now)

    imt = WikiPage(tc.env)
    imt.name = u"InterMapTxt"
    imt.text = """
This is the InterMapTxt
----
{{{
MeatBall 	http://www.usemod.com/cgi-bin/mb.pl? # $1 in MeatBall...
tsvn            tsvn:
complex         http://server/$1/page/$2?format=txt  # resource $2 in $1
}}}
----
{{{
nolink          http://noweb
}}}
""" 
    imt.save('joe', 'test InterWiki links', '::1', now)


def suite():
    suite = unittest.TestSuite()
    suite.addTest(formatter.suite(TEST_CASES, wiki_setup, __file__))
    suite.addTest(formatter.suite(RELATIVE_LINKS_TESTS, wiki_setup, __file__,
                                  context=('wiki', 'Main/Sub')))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite') 
