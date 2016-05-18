# -*- coding: utf-8 -*-
#
# Copyright (C) 2006-2013 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import unittest

from trac.util.datefmt import datetime_now, utc
from trac.wiki.model import WikiPage
from trac.wiki.tests import formatter


TEST_CASES = u"""
============================== wiki: link resolver
wiki:TestPage
wiki:TestPage/
wiki:/TestPage
[wiki:/TestPage]
[wiki:/TestPage ]
[wiki:/TestPage\u200B]
[wiki:/TestPage /TestPage]
wiki:"Space 1 23"
wiki:"C'est l'\xe9t\xe9"
wiki:MissingPage
wiki:12
wiki:abc
------------------------------
<p>
<a class="wiki" href="/wiki/TestPage">wiki:TestPage</a>
<a class="wiki" href="/wiki/TestPage">wiki:TestPage/</a>
<a class="wiki" href="/wiki/TestPage">wiki:/TestPage</a>
<a class="wiki" href="/wiki/TestPage">TestPage</a>
<a class="wiki" href="/wiki/TestPage">TestPage</a>
<a class="wiki" href="/wiki/TestPage">TestPage</a>
<a class="wiki" href="/wiki/TestPage">/TestPage</a>
<a class="wiki" href="/wiki/Space%201%2023">wiki:"Space 1 23"</a>
<a class="wiki" href="/wiki/C'est%20l'%C3%A9t%C3%A9">wiki:"C'est l'\xe9t\xe9"</a>
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
But not CamelCase2
nor CamelCase_
------------------------------
<p>
<a class="missing wiki" href="/wiki/CamelCase" rel="nofollow">CamelCase?</a>,<a class="missing wiki" href="/wiki/CamelCase" rel="nofollow">CamelCase?</a>.<a class="missing wiki" href="/wiki/CamelCase" rel="nofollow">CamelCase?</a>: <a class="missing wiki" href="/wiki/CamelCase" rel="nofollow">CamelCase?</a>
But not CamelCase2
nor CamelCase_
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
/absolute/path/is/NotWiki and relative/path/is/NotWiki and ../higher/is/NotWiki
but ThisIs/SubWiki and now This/Also
and ../Relative/Camel or /Absolute/Camel as well
------------------------------
<p>
/absolute/path/is/NotWiki and relative/path/is/NotWiki and ../higher/is/NotWiki
but <a class="missing wiki" href="/wiki/ThisIs/SubWiki" rel="nofollow">ThisIs/SubWiki?</a> and now <a class="missing wiki" href="/wiki/This/Also" rel="nofollow">This/Also?</a>
and <a class="missing wiki" href="/wiki/Relative/Camel" rel="nofollow">../Relative/Camel?</a> or <a class="missing wiki" href="/wiki/Absolute/Camel" rel="nofollow">/Absolute/Camel?</a> as well
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
============================== not a WikiPageNames at all (#9025 regression)
[ሀሁሂሃሄህሆለሉሊላሌልሎሏሐሑሒሓሔሕሖመሙሚማሜምሞሟሠሡሢሣሤሥሦረሩሪራሬርሮሯሰሱሲሳሴስሶሷሸሹሺሻሼሽሾሿቀቁቂቃቄቅቆቈቊቋቌቍቐቑቒቓቔቕቖቘቚቛቜቝበቡቢባቤብቦቧቨቩቪቫቬቭቮቯተቱቲታቴትቶቷቸቹቺቻቼችቾቿኀኁኂኃኄኅኆኈኊኋኌኍነኑኒናኔንኖኗኘኙኚኛኜኝኞኟአኡኢኣኤእኦኧከኩኪካኬክኮኰኲኳኴኵኸኹኺኻኼኽኾወዉዊዋዌውዎዐዑዒዓዔዕዖዘዙዚዛዜዝዞዟዠዡዢዣዤዥዦዧየዩዪያዬይዮደዱዲዳዴድዶዷጀጁጂጃጄጅጆጇገጉጊጋጌግጎጐጒጓጔጕጠጡጢጣጤጥጦጧጨጩጪጫጬጭጮጯጰጱጲጳጴጵጶጷጸጹጺጻጼጽጾጿፀፁፂፃፄፅፆፈፉፊፋፌፍፎፏፐፑፒፓፔፕፖፗፘፙፚ፩፪፫፬፭፮፯፰፱፲፳፴፵፶፷፸፹፺፻]------------------------------
<p>
[ሀሁሂሃሄህሆለሉሊላሌልሎሏሐሑሒሓሔሕሖመሙሚማሜምሞሟሠሡሢሣሤሥሦረሩሪራሬርሮሯሰሱሲሳሴስሶሷሸሹሺሻሼሽሾሿቀቁቂቃቄቅቆቈቊቋቌቍቐቑቒቓቔቕቖቘቚቛቜቝበቡቢባቤብቦቧቨቩቪቫቬቭቮቯተቱቲታቴትቶቷቸቹቺቻቼችቾቿኀኁኂኃኄኅኆኈኊኋኌኍነኑኒናኔንኖኗኘኙኚኛኜኝኞኟአኡኢኣኤእኦኧከኩኪካኬክኮኰኲኳኴኵኸኹኺኻኼኽኾወዉዊዋዌውዎዐዑዒዓዔዕዖዘዙዚዛዜዝዞዟዠዡዢዣዤዥዦዧየዩዪያዬይዮደዱዲዳዴድዶዷጀጁጂጃጄጅጆጇገጉጊጋጌግጎጐጒጓጔጕጠጡጢጣጤጥጦጧጨጩጪጫጬጭጮጯጰጱጲጳጴጵጶጷጸጹጺጻጼጽጾጿፀፁፂፃፄፅፆፈፉፊፋፌፍፎፏፐፑፒፓፔፕፖፗፘፙፚ፩፪፫፬፭፮፯፰፱፲፳፴፵፶፷፸፹፺፻]
</p>
------------------------------
[ሀሁሂሃሄህሆለሉሊላሌልሎሏሐሑሒሓሔሕሖመሙሚማሜምሞሟሠሡሢሣሤሥሦረሩሪራሬርሮሯሰሱሲሳሴስሶሷሸሹሺሻሼሽሾሿቀቁቂቃቄቅቆቈቊቋቌቍቐቑቒቓቔቕቖቘቚቛቜቝበቡቢባቤብቦቧቨቩቪቫቬቭቮቯተቱቲታቴትቶቷቸቹቺቻቼችቾቿኀኁኂኃኄኅኆኈኊኋኌኍነኑኒናኔንኖኗኘኙኚኛኜኝኞኟአኡኢኣኤእኦኧከኩኪካኬክኮኰኲኳኴኵኸኹኺኻኼኽኾወዉዊዋዌውዎዐዑዒዓዔዕዖዘዙዚዛዜዝዞዟዠዡዢዣዤዥዦዧየዩዪያዬይዮደዱዲዳዴድዶዷጀጁጂጃጄጅጆጇገጉጊጋጌግጎጐጒጓጔጕጠጡጢጣጤጥጦጧጨጩጪጫጬጭጮጯጰጱጲጳጴጵጶጷጸጹጺጻጼጽጾጿፀፁፂፃፄፅፆፈፉፊፋፌፍፎፏፐፑፒፓፔፕፖፗፘፙፚ፩፪፫፬፭፮፯፰፱፲፳፴፵፶፷፸፹፺፻]
============================== MoinMoin style forced links
This is a ["Wiki"] page link.
This is a ["Wiki" wiki page] link with label.
This is a ["Wiki?param=1#fragment"] page link with query and fragment.
------------------------------
<p>
This is a <a class="missing wiki" href="/wiki/Wiki" rel="nofollow">Wiki?</a> page link.
This is a <a class="missing wiki" href="/wiki/Wiki" rel="nofollow">wiki page?</a> link with label.
This is a <a class="missing wiki" href="/wiki/Wiki?param=1#fragment" rel="nofollow">Wiki?</a> page link with query and fragment.
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
Here's a [BadExample\fbad] example with special whitespace.
We can also [WikiLabels '"use [quotes]"']
or [WikiLabels "'use [quotes]'"]
------------------------------
<p>
See details of the <a class="missing wiki" href="/wiki/WikiPageNames" rel="nofollow">wiki page name?</a> syntax.
Here's a <a class="missing wiki" href="/wiki/BadExample" rel="nofollow">bad?</a> example with special whitespace.
We can also <a class="missing wiki" href="/wiki/WikiLabels" rel="nofollow">"use [quotes]"?</a>
or <a class="missing wiki" href="/wiki/WikiLabels" rel="nofollow">'use [quotes]'?</a>
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
<a class="ext-link" href="http://trac.edgewall.org/intertrac/wiki%3AInterTrac" title="wiki:InterTrac in Trac's Trac"><span class="icon"></span>t:wiki:InterTrac</a>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/wiki%3AInterTrac" title="wiki:InterTrac in Trac's Trac"><span class="icon"></span>trac:wiki:InterTrac</a>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/wiki%3AInterTrac" title="wiki:InterTrac in Trac's Trac"><span class="icon"></span>intertrac</a>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/wiki%3AInterTrac" title="wiki:InterTrac in Trac's Trac"><span class="icon"></span>intertrac</a>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/wiki%3AJonasBorgstr%C3%B6m" title="wiki:JonasBorgström in Trac's Trac"><span class="icon"></span>jonas</a>
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
<a class="ext-link" href="http://trac.edgewall.org/intertrac/InterTrac" title="InterTrac in Trac's Trac"><span class="icon"></span>t:InterTrac</a>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/InterTrac" title="InterTrac in Trac's Trac"><span class="icon"></span>trac:InterTrac</a>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/InterTrac" title="InterTrac in Trac's Trac"><span class="icon"></span>intertrac</a>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/InterTrac" title="InterTrac in Trac's Trac"><span class="icon"></span>intertrac</a>
<a class="ext-link" href="http://trac.edgewall.org/intertrac/JonasBorgstr%C3%B6m" title="JonasBorgström in Trac's Trac"><span class="icon"></span>jonas</a>
</p>
------------------------------
============================== InterWiki links
This is the original MeatBall:InterMapTxt wiki page.
Checkout the [tsvn:http://svn.edgewall.com/repos/trac Trac Repository].

complex link complex:a:test with positional arguments
complex link complex:a (not enough arguments)
complex link complex:a:test:more (too many arguments)

in trac.ini inter:b:resource
in trac.ini over:c:something overrides wiki

NoLink:ignored
NoLink:
NoLink: ...
------------------------------
<p>
This is the original <a class="ext-link" href="http://www.usemod.com/cgi-bin/mb.pl?InterMapTxt" title="InterMapTxt in MeatBall..."><span class="icon"></span>MeatBall:InterMapTxt</a> wiki page.
Checkout the <a class="ext-link" href="tsvn:http://svn.edgewall.com/repos/trac" title="http://svn.edgewall.com/repos/trac in tsvn"><span class="icon"></span>Trac Repository</a>.
</p>
<p>
complex link <a class="ext-link" href="http://server/a/page/test?format=txt" title="resource test in a"><span class="icon"></span>complex:a:test</a> with positional arguments
complex link <a class="ext-link" href="http://server/a/page/?format=txt" title="resource  in a"><span class="icon"></span>complex:a</a> (not enough arguments)
complex link <a class="ext-link" href="http://server/a/page/test:more?format=txt" title="resource test:more in a"><span class="icon"></span>complex:a:test:more</a> (too many arguments)
</p>
<p>
in trac.ini <a class="ext-link" href="http://inter/b/page/resource" title="Resource resource in b"><span class="icon"></span>inter:b:resource</a>
in trac.ini <a class="ext-link" href="http://over/c/page/something" title="c:something in over"><span class="icon"></span>over:c:something</a> overrides wiki
</p>
<p>
NoLink:ignored
<a class="missing wiki" href="/wiki/NoLink" rel="nofollow">NoLink?</a>:
<a class="missing wiki" href="/wiki/NoLink" rel="nofollow">NoLink?</a>: ...
</p>
------------------------------
============================== InterWiki links with parameters and fragment
See also MeatBall:InterMapTxt#there wiki page
and MeatBall:InterMapTxt?format=txt#there wiki page.

complex link complex:a:test?go#there with positional arguments
------------------------------
<p>
See also <a class="ext-link" href="http://www.usemod.com/cgi-bin/mb.pl?InterMapTxt#there" title="InterMapTxt in MeatBall..."><span class="icon"></span>MeatBall:InterMapTxt#there</a> wiki page
and <a class="ext-link" href="http://www.usemod.com/cgi-bin/mb.pl?InterMapTxt&amp;format=txt#there" title="InterMapTxt in MeatBall..."><span class="icon"></span>MeatBall:InterMapTxt?format=txt#there</a> wiki page.
</p>
<p>
complex link <a class="ext-link" href="http://server/a/page/test?format=txt&amp;go#there" title="resource test in a"><span class="icon"></span>complex:a:test?go#there</a> with positional arguments
</p>
------------------------------
============================== Regression for #9712
This is not a link: x,://localhost
------------------------------
<p>
This is not a link: x,:<em>localhost
</em></p>
------------------------------
============================== Wiki links with @version using unicode digits
WikiStart@₄₂
WikiStart@₄₂#heading
[WikiStart@₄₂]
[WikiStart@₄₂#heading]
------------------------------
<p>
<a class="wiki" href="/wiki/WikiStart">WikiStart</a>@₄₂
<a class="wiki" href="/wiki/WikiStart">WikiStart</a>@₄₂#heading
[<a class="wiki" href="/wiki/WikiStart">WikiStart</a>@₄₂]
[<a class="wiki" href="/wiki/WikiStart">WikiStart</a>@₄₂#heading]
</p>
------------------------------
""" #" Emacs likes it that way better


RELATIVE_LINKS_TESTS = u"""
============================== Relative to the project url
[//docs Documentation]
[//docs?param=1#fragment Documentation]
[//docs]
[//docs //docs]
[//docs?param=1#fragment]
[// Home]
[//]
[//?param=1#fragment]
------------------------------
<p>
<a href="/docs">Documentation</a>
<a href="/docs?param=1#fragment">Documentation</a>
<a href="/docs">docs</a>
<a href="/docs">//docs</a>
<a href="/docs?param=1#fragment">docs</a>
<a href="/">Home</a>
<a href="/">//</a>
<a href="/?param=1#fragment">//</a>
</p>
------------------------------
============================== Relative to the base url
[/newticket?priority=high#fragment bug]
[/newticket?priority=high#fragment]
[/newticket]
[/newticket /newticket]
[/ Project]
[/]
[/?param=1#fragment]
------------------------------
<p>
<a href="/newticket?priority=high#fragment">bug</a>
<a href="/newticket?priority=high#fragment">newticket</a>
<a href="/newticket">newticket</a>
<a href="/newticket">/newticket</a>
<a href="/">Project</a>
<a href="/">/</a>
<a href="/?param=1#fragment">/</a>
</p>
------------------------------
============================== Relative to the current page
[.]
[./]
[..]
[../]
[./../.]
[. this page]
[./Detail see detail]
[./Detail]
[./Detail ./Detail]
[.. see parent]
[../Other see other]
[../Other]
[../Other ../Other]
[.././../Other]
------------------------------
<p>
<a class="wiki" href="/wiki/Main/Sub">.</a>
<a class="wiki" href="/wiki/Main/Sub">./</a>
<a class="missing wiki" href="/wiki/Main" rel="nofollow">..?</a>
<a class="missing wiki" href="/wiki/Main" rel="nofollow">../?</a>
<a class="missing wiki" href="/wiki/Main" rel="nofollow">./../.?</a>
<a class="wiki" href="/wiki/Main/Sub">this page</a>
<a class="missing wiki" href="/wiki/Main/Sub/Detail" rel="nofollow">see detail?</a>
<a class="missing wiki" href="/wiki/Main/Sub/Detail" rel="nofollow">Detail?</a>
<a class="missing wiki" href="/wiki/Main/Sub/Detail" rel="nofollow">./Detail?</a>
<a class="missing wiki" href="/wiki/Main" rel="nofollow">see parent?</a>
<a class="missing wiki" href="/wiki/Main/Other" rel="nofollow">see other?</a>
<a class="missing wiki" href="/wiki/Main/Other" rel="nofollow">Other?</a>
<a class="missing wiki" href="/wiki/Main/Other" rel="nofollow">../Other?</a>
<a class="missing wiki" href="/wiki/Other" rel="nofollow">Other?</a>
</p>
------------------------------
============================== Relative to the current page, in wiki realm
[wiki:. this page]
[wiki:./Detail]
[wiki:"./Detail"]
[wiki:./Detail ./Detail]
[wiki:./Detail see detail]
[wiki:.. see parent]
[wiki:../Other see other]
[wiki:.././../Other]
["."]
[".?param=1#fragment"]
["./Detail"]
["./Detail?param=1#fragment"]
[".."]
["..?param=1#fragment"]
["../Other"]
["../Other?param=1#fragment"]
[".././../Other"]
------------------------------
<p>
<a class="wiki" href="/wiki/Main/Sub">this page</a>
<a class="missing wiki" href="/wiki/Main/Sub/Detail" rel="nofollow">Detail?</a>
<a class="missing wiki" href="/wiki/Main/Sub/Detail" rel="nofollow">Detail?</a>
<a class="missing wiki" href="/wiki/Main/Sub/Detail" rel="nofollow">./Detail?</a>
<a class="missing wiki" href="/wiki/Main/Sub/Detail" rel="nofollow">see detail?</a>
<a class="missing wiki" href="/wiki/Main" rel="nofollow">see parent?</a>
<a class="missing wiki" href="/wiki/Main/Other" rel="nofollow">see other?</a>
<a class="missing wiki" href="/wiki/Other" rel="nofollow">Other?</a>
<a class="wiki" href="/wiki/Main/Sub">.</a>
<a class="wiki" href="/wiki/Main/Sub?param=1#fragment">.</a>
<a class="missing wiki" href="/wiki/Main/Sub/Detail" rel="nofollow">Detail?</a>
<a class="missing wiki" href="/wiki/Main/Sub/Detail?param=1#fragment" rel="nofollow">Detail?</a>
<a class="missing wiki" href="/wiki/Main" rel="nofollow">..?</a>
<a class="missing wiki" href="/wiki/Main?param=1#fragment" rel="nofollow">..?</a>
<a class="missing wiki" href="/wiki/Main/Other" rel="nofollow">Other?</a>
<a class="missing wiki" href="/wiki/Main/Other?param=1#fragment" rel="nofollow">Other?</a>
<a class="missing wiki" href="/wiki/Other" rel="nofollow">Other?</a>
</p>
------------------------------
============================== Relative to the current page, as CamelCase
OnePage/SubPage
./SubPage
../SiblingPage
.././../HigherPage
/TopPage
------------------------------
<p>
<a class="missing wiki" href="/wiki/Main/OnePage/SubPage" rel="nofollow">OnePage/SubPage?</a>
<a class="missing wiki" href="/wiki/Main/Sub/SubPage" rel="nofollow">./SubPage?</a>
<a class="missing wiki" href="/wiki/Main/SiblingPage" rel="nofollow">../SiblingPage?</a>
<a class="missing wiki" href="/wiki/HigherPage" rel="nofollow">.././../HigherPage?</a>
<a class="missing wiki" href="/wiki/TopPage" rel="nofollow">/TopPage?</a>
</p>
------------------------------
============================== Relative to the current page with query strings and fragments
[#topic see topic]
[?param=1#topic see topic]
[.#topic see topic]
[.?param=1#topic see topic]
[./#topic see topic]
[./?param=1#topic see topic]
[./Detail#topic see detail]
[./Detail?param=1#topic see detail]
[./Detail?param=1#topic]
[..#topic see parent]
[..?param=1#topic see parent]
[../#topic see parent]
[../?param=1#topic see parent]
[../Other#topic see other]
[../Other?param=1#topic see other]
[../Other?param=1#topic]
[../Other/#topic see other]
[../Other/?param=1#topic see other]
------------------------------
<p>
<a class="wiki" href="/wiki/Main/Sub#topic">see topic</a>
<a class="wiki" href="/wiki/Main/Sub?param=1#topic">see topic</a>
<a class="wiki" href="/wiki/Main/Sub#topic">see topic</a>
<a class="wiki" href="/wiki/Main/Sub?param=1#topic">see topic</a>
<a class="wiki" href="/wiki/Main/Sub#topic">see topic</a>
<a class="wiki" href="/wiki/Main/Sub?param=1#topic">see topic</a>
<a class="missing wiki" href="/wiki/Main/Sub/Detail#topic" rel="nofollow">see detail?</a>
<a class="missing wiki" href="/wiki/Main/Sub/Detail?param=1#topic" rel="nofollow">see detail?</a>
<a class="missing wiki" href="/wiki/Main/Sub/Detail?param=1#topic" rel="nofollow">Detail?</a>
<a class="missing wiki" href="/wiki/Main#topic" rel="nofollow">see parent?</a>
<a class="missing wiki" href="/wiki/Main?param=1#topic" rel="nofollow">see parent?</a>
<a class="missing wiki" href="/wiki/Main#topic" rel="nofollow">see parent?</a>
<a class="missing wiki" href="/wiki/Main?param=1#topic" rel="nofollow">see parent?</a>
<a class="missing wiki" href="/wiki/Main/Other#topic" rel="nofollow">see other?</a>
<a class="missing wiki" href="/wiki/Main/Other?param=1#topic" rel="nofollow">see other?</a>
<a class="missing wiki" href="/wiki/Main/Other?param=1#topic" rel="nofollow">Other?</a>
<a class="missing wiki" href="/wiki/Main/Other#topic" rel="nofollow">see other?</a>
<a class="missing wiki" href="/wiki/Main/Other?param=1#topic" rel="nofollow">see other?</a>
</p>
------------------------------
""" # "


SPLIT_PAGE_NAMES_TESTS = u"""
============================== Splitting relative links
[//WikiPage]
[/WikiPage]
[./WikiPage]
[../WikiPage]
[//WikiPage?param=1#fragment]
[/WikiPage?param=1#fragment]
[./WikiPage?param=1#fragment]
[../WikiPage?param=1#fragment]
But not [./wiki_page]
And not [../WikiPage WikiPage]
------------------------------
<p>
<a href="/WikiPage">Wiki Page</a>
<a href="/WikiPage">Wiki Page</a>
<a class="missing wiki" href="/wiki/Main/Sub/WikiPage" rel="nofollow">Wiki Page?</a>
<a class="missing wiki" href="/wiki/Main/WikiPage" rel="nofollow">Wiki Page?</a>
<a href="/WikiPage?param=1#fragment">Wiki Page</a>
<a href="/WikiPage?param=1#fragment">Wiki Page</a>
<a class="missing wiki" href="/wiki/Main/Sub/WikiPage?param=1#fragment" rel="nofollow">Wiki Page?</a>
<a class="missing wiki" href="/wiki/Main/WikiPage?param=1#fragment" rel="nofollow">Wiki Page?</a>
But not <a class="missing wiki" href="/wiki/Main/Sub/wiki_page" rel="nofollow">wiki_page?</a>
And not <a class="missing wiki" href="/wiki/Main/WikiPage" rel="nofollow">WikiPage?</a>
</p>
------------------------------
============================== Splitting scoped links
[wiki:WikiPage]
[wiki:./WikiPage]
[wiki:../WikiPage]
[wiki:./.././WikiPage]
[wiki:"./.././WikiPage"]
[wiki:WikiPage?param=1#fragment]
[wiki:./WikiPage?param=1#fragment]
[wiki:../WikiPage?param=1#fragment]
But not [wiki:./wiki_page]
And not [wiki:../WikiPage WikiPage]
------------------------------
<p>
<a class="missing wiki" href="/wiki/Main/WikiPage" rel="nofollow">Wiki Page?</a>
<a class="missing wiki" href="/wiki/Main/Sub/WikiPage" rel="nofollow">Wiki Page?</a>
<a class="missing wiki" href="/wiki/Main/WikiPage" rel="nofollow">Wiki Page?</a>
<a class="missing wiki" href="/wiki/Main/WikiPage" rel="nofollow">Wiki Page?</a>
<a class="missing wiki" href="/wiki/Main/WikiPage" rel="nofollow">Wiki Page?</a>
<a class="missing wiki" href="/wiki/Main/WikiPage?param=1#fragment" rel="nofollow">Wiki Page?</a>
<a class="missing wiki" href="/wiki/Main/Sub/WikiPage?param=1#fragment" rel="nofollow">Wiki Page?</a>
<a class="missing wiki" href="/wiki/Main/WikiPage?param=1#fragment" rel="nofollow">Wiki Page?</a>
But not <a class="missing wiki" href="/wiki/Main/Sub/wiki_page" rel="nofollow">wiki_page?</a>
And not <a class="missing wiki" href="/wiki/Main/WikiPage" rel="nofollow">WikiPage?</a>
</p>
------------------------------
============================== Splitting internal free links
["WikiPage"]
["./WikiPage"]
["../WikiPage"]
["./.././WikiPage"]
["WikiPage?param=1#fragment"]
["./WikiPage?param=1#fragment"]
["../WikiPage?param=1#fragment"]
But not ["./wiki_page"]
And not ["../WikiPage" WikiPage]
------------------------------
<p>
<a class="missing wiki" href="/wiki/Main/WikiPage" rel="nofollow">Wiki Page?</a>
<a class="missing wiki" href="/wiki/Main/Sub/WikiPage" rel="nofollow">Wiki Page?</a>
<a class="missing wiki" href="/wiki/Main/WikiPage" rel="nofollow">Wiki Page?</a>
<a class="missing wiki" href="/wiki/Main/WikiPage" rel="nofollow">Wiki Page?</a>
<a class="missing wiki" href="/wiki/Main/WikiPage?param=1#fragment" rel="nofollow">Wiki Page?</a>
<a class="missing wiki" href="/wiki/Main/Sub/WikiPage?param=1#fragment" rel="nofollow">Wiki Page?</a>
<a class="missing wiki" href="/wiki/Main/WikiPage?param=1#fragment" rel="nofollow">Wiki Page?</a>
But not <a class="missing wiki" href="/wiki/Main/Sub/wiki_page" rel="nofollow">wiki_page?</a>
And not <a class="missing wiki" href="/wiki/Main/WikiPage" rel="nofollow">WikiPage?</a>
</p>
------------------------------
""" # "


SCOPED_LINKS_TESTS = u"""
============================== Scoped links for hierarchical pages
ThirdLevel
[wiki:ThirdLevel]
OtherThirdLevel
[wiki:OtherThirdLevel]
SecondLevel/OtherThirdLevel
[wiki:SecondLevel/OtherThirdLevel]
SecondLevel
[wiki:SecondLevel]
FirstLevel
[wiki:FirstLevel]
TestPage
[wiki:TestPage]
MissingPage
[wiki:MissingPage]
FirstLevel/MissingPage
[wiki:FirstLevel/MissingPage]
SecondLevel/MissingPage
[wiki:SecondLevel/MissingPage]
MissingFirstLevel/MissingPage
[wiki:MissingFirstLevel/MissingPage]
["/OtherThirdLevel"]
[wiki:/OtherThirdLevel]
[wiki:/OtherThirdLevel /OtherThirdLevel]
------------------------------
<p>
<a class="wiki" href="/wiki/FirstLevel/SecondLevel/ThirdLevel">ThirdLevel</a>
<a class="wiki" href="/wiki/FirstLevel/SecondLevel/ThirdLevel">ThirdLevel</a>
<a class="wiki" href="/wiki/FirstLevel/SecondLevel/OtherThirdLevel">OtherThirdLevel</a>
<a class="wiki" href="/wiki/FirstLevel/SecondLevel/OtherThirdLevel">OtherThirdLevel</a>
<a class="wiki" href="/wiki/FirstLevel/SecondLevel/OtherThirdLevel">SecondLevel/OtherThirdLevel</a>
<a class="wiki" href="/wiki/FirstLevel/SecondLevel/OtherThirdLevel">SecondLevel/OtherThirdLevel</a>
<a class="wiki" href="/wiki/FirstLevel/SecondLevel">SecondLevel</a>
<a class="wiki" href="/wiki/FirstLevel/SecondLevel">SecondLevel</a>
<a class="wiki" href="/wiki/FirstLevel">FirstLevel</a>
<a class="wiki" href="/wiki/FirstLevel">FirstLevel</a>
<a class="wiki" href="/wiki/TestPage">TestPage</a>
<a class="wiki" href="/wiki/TestPage">TestPage</a>
<a class="missing wiki" href="/wiki/FirstLevel/SecondLevel/MissingPage" rel="nofollow">MissingPage?</a>
<a class="missing wiki" href="/wiki/FirstLevel/SecondLevel/MissingPage" rel="nofollow">MissingPage?</a>
<a class="missing wiki" href="/wiki/FirstLevel/MissingPage" rel="nofollow">FirstLevel/MissingPage?</a>
<a class="missing wiki" href="/wiki/FirstLevel/MissingPage" rel="nofollow">FirstLevel/MissingPage?</a>
<a class="missing wiki" href="/wiki/FirstLevel/SecondLevel/MissingPage" rel="nofollow">SecondLevel/MissingPage?</a>
<a class="missing wiki" href="/wiki/FirstLevel/SecondLevel/MissingPage" rel="nofollow">SecondLevel/MissingPage?</a>
<a class="missing wiki" href="/wiki/FirstLevel/SecondLevel/MissingFirstLevel/MissingPage" rel="nofollow">MissingFirstLevel/MissingPage?</a>
<a class="missing wiki" href="/wiki/FirstLevel/SecondLevel/MissingFirstLevel/MissingPage" rel="nofollow">MissingFirstLevel/MissingPage?</a>
<a class="missing wiki" href="/wiki/OtherThirdLevel" rel="nofollow">OtherThirdLevel?</a>
<a class="missing wiki" href="/wiki/OtherThirdLevel" rel="nofollow">OtherThirdLevel?</a>
<a class="missing wiki" href="/wiki/OtherThirdLevel" rel="nofollow">/OtherThirdLevel?</a>
</p>
------------------------------
""" # "


SAFE_INTERWIKI_TESTS = u"""
============================== InterWiki with safe_schemes
This is the original MeatBall:InterMapTxt wiki page.

Checkout the [tsvn:http://svn.edgewall.com/repos/trac Trac Repository].

complex link complex:a:test with positional arguments.

js:"alert(1)" javasc:"ript:alert(1)"
------------------------------
<p>
This is the original <a class="ext-link" href="http://www.usemod.com/cgi-bin/mb.pl?InterMapTxt" title="InterMapTxt in MeatBall..."><span class="icon"></span>MeatBall:InterMapTxt</a> wiki page.
</p>
<p>
Checkout the <a class="ext-link" href="tsvn:http://svn.edgewall.com/repos/trac" title="http://svn.edgewall.com/repos/trac in tsvn"><span class="icon"></span>Trac Repository</a>.
</p>
<p>
complex link <a class="ext-link" href="http://server/a/page/test?format=txt" title="resource test in a"><span class="icon"></span>complex:a:test</a> with positional arguments.
</p>
<p>
js:&#34;alert(1)&#34; javasc:&#34;ript:alert(1)&#34;
</p>
------------------------------
""" # "


def wiki_setup(tc):
    tc.env.config.set('wiki', 'render_unsafe_content', True) # for #9712
    now = datetime_now(utc)
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
MeatBall        http://www.usemod.com/cgi-bin/mb.pl? # $1 in MeatBall...
tsvn            tsvn:
complex         http://server/$1/page/$2?format=txt  # resource $2 in $1
over            http://unused/? # Overridden in trac.ini
js              javascript:
javasc          javasc
}}}
----
{{{
nolink          http://noweb
}}}
"""
    imt.save('joe', 'test InterWiki links', '::1', now)
    tc.env.config.set('interwiki', 'inter',
                      'http://inter/$1/page/$2 Resource $2 in $1')
    tc.env.config.set('interwiki', 'over',
                      'http://over/$1/page/$2')

    w = WikiPage(tc.env)
    w.name = 'FirstLevel'
    w.text = '--'
    w.save('joe', 'first level of hierarchy', '::1', now)

    w = WikiPage(tc.env)
    w.name = 'FirstLevel/SecondLevel'
    w.text = '--'
    w.save('joe', 'second level of hierarchy', '::1', now)

    w = WikiPage(tc.env)
    w.name = 'FirstLevel/SecondLevel/ThirdLevel'
    w.text = '--'
    w.save('joe', 'third level of hierarchy', '::1', now)

    w = WikiPage(tc.env)
    w.name = 'FirstLevel/SecondLevel/OtherThirdLevel'
    w.text = '--'
    w.save('joe', 'other third level of hierarchy', '::1', now)

    tc.env.db_transaction("INSERT INTO ticket (id) VALUES ('123')")


def wiki_teardown(tc):
    tc.env.reset_db()


def wiki_setup_split(tc):
    tc.env.config.set('wiki', 'split_page_names', 'true')
    wiki_setup(tc)


def wiki_setup_safe_interwiki(tc):
    wiki_setup(tc)
    tc.env.config.set('wiki', 'render_unsafe_content', 'false')
    tc.env.config.set('wiki', 'safe_schemes',
                      'file,ftp,git,irc,http,https,ssh,svn,tsvn')


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(formatter.test_suite(TEST_CASES, wiki_setup, __file__,
                                       wiki_teardown))
    suite.addTest(formatter.test_suite(RELATIVE_LINKS_TESTS, wiki_setup,
                                       __file__,
                                       wiki_teardown,
                                       context=('wiki', 'Main/Sub')))
    suite.addTest(formatter.test_suite(SPLIT_PAGE_NAMES_TESTS,
                                       wiki_setup_split,
                                       __file__, wiki_teardown,
                                       context=('wiki', 'Main/Sub')))
    suite.addTest(formatter.test_suite(SCOPED_LINKS_TESTS, wiki_setup,
                                       __file__, wiki_teardown,
                                       context=('wiki', 'FirstLevel/Second'
                                                        'Level/ThirdLevel')))
    suite.addTest(formatter.test_suite(SAFE_INTERWIKI_TESTS,
                                       wiki_setup_safe_interwiki, __file__,
                                       wiki_teardown))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
