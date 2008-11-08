= Support for InterWiki links =

''(since [trac:milestone:0.10 0.10])''

== Definition ==

An InterWiki link can be used for referring to a Wiki page
located in another Wiki system, and by extension, to any object
located in any other Web application, provided a simple URL 
mapping can be done.

At the extreme, InterWiki prefixes can even be used to simply introduce
links to new protocols, such as `tsvn:` used by [trac:TortoiseSvn TortoiseSvn].

== Link Syntax ==

{{{
<target_wiki>(:<identifier>)+
}}}

The link is composed by the targeted Wiki (or system) name,
followed by a colon (e.g. `MeatBall:`),
followed by a page specification in the target.
Note that, as for InterTrac prefixes, '''InterWiki prefixes are case insensitive'''.

The target Wiki URL is looked up in the InterMapTxt wiki page, 
modelled after MeatBall:InterMapTxt.

In addition to traditional InterWiki links, where the target
is simply ''appended'' to the URL, 
Trac supports parametric InterWiki URLs:
identifiers `$1`, `$2`, ... in the URL
will be replaced by corresponding arguments.
The argument list is formed by splitting the page identifier
using the ":" separator.

== Examples ==

If the following is an excerpt of the InterMapTxt page:

{{{
= InterMapTxt =
== This is the place for defining InterWiki prefixes ==

Currently active prefixes: [[InterWiki]]

This page is modelled after the MeatBall:InterMapTxt page.
In addition, an optional comment is allowed after the mapping.
----
{{{
PEP      http://www.python.org/peps/pep-$1.html           # Python Enhancement Proposal $1 
Trac-ML  http://thread.gmane.org/gmane.comp.version-control.subversion.trac.general/$1  # Message $1 in Trac Mailing List

tsvn     tsvn:                                            # Interact with TortoiseSvn
...
MeatBall http://www.usemod.com/cgi-bin/mb.pl?
MetaWiki http://sunir.org/apps/meta.pl?
MetaWikiPedia http://meta.wikipedia.org/wiki/
MoinMoin http://moinmoin.wikiwikiweb.de/
...
}}}
}}}

Then, 
 * `MoinMoin:InterWikiMap` should be rendered as MoinMoin:InterWikiMap
   and the ''title'' for that link would be "!InterWikiMap in !MoinMoin"
 * `Trac-ML:4346` should be rendered as Trac-ML:4346
   and the ''title'' for that link would be "Message 4346 in Trac Mailing List"

----
See also: InterTrac, InterMapTxt