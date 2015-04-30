# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2009 Edgewall Software
# Copyright (C) 2005-2006 Christian Boos <cboos@edgewall.org>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.
#
# Author: Christian Boos <cboos@edgewall.org>

import re

from genshi.builder import tag

from trac.cache import cached
from trac.config import ConfigSection
from trac.core import *
from trac.util import lazy
from trac.util.translation import _, N_
from trac.wiki.api import IWikiChangeListener, IWikiMacroProvider, WikiSystem
from trac.wiki.parser import WikiParser
from trac.wiki.formatter import split_url_into_path_query_fragment


class InterWikiMap(Component):
    """InterWiki map manager."""

    implements(IWikiChangeListener, IWikiMacroProvider)

    interwiki_section = ConfigSection('interwiki',
        """Every option in the `[interwiki]` section defines one InterWiki
        prefix. The option name defines the prefix. The option value defines
        the URL, optionally followed by a description separated from the URL
        by whitespace. Parametric URLs are supported as well.

        '''Example:'''
        {{{
        [interwiki]
        MeatBall = http://www.usemod.com/cgi-bin/mb.pl?
        PEP = http://www.python.org/peps/pep-$1.html Python Enhancement Proposal $1
        tsvn = tsvn: Interact with TortoiseSvn
        }}}
        """)

    _page_name = 'InterMapTxt'
    _interwiki_re = re.compile(r"(%s)[ \t]+([^ \t]+)(?:[ \t]+#(.*))?" %
                               WikiParser.LINK_SCHEME, re.UNICODE)
    _argspec_re = re.compile(r"\$\d")

    # The component itself behaves as a read-only map

    def __contains__(self, ns):
        return ns.upper() in self.interwiki_map

    def __getitem__(self, ns):
        return self.interwiki_map[ns.upper()]

    def keys(self):
        return self.interwiki_map.keys()

    # Expansion of positional arguments ($1, $2, ...) in URL and title
    def _expand(self, txt, args):
        """Replace "$1" by the first args, "$2" by the second, etc."""
        def setarg(match):
            num = int(match.group()[1:])
            return args[num - 1] if 0 < num <= len(args) else ''
        return re.sub(InterWikiMap._argspec_re, setarg, txt)

    def _expand_or_append(self, txt, args):
        """Like expand, but also append first arg if there's no "$"."""
        if not args:
            return txt
        expanded = self._expand(txt, args)
        return txt + args[0] if expanded == txt else expanded

    def url(self, ns, target):
        """Return `(url, title)` for the given InterWiki `ns`.

        Expand the colon-separated `target` arguments.
        """
        ns, url, title = self[ns]
        maxargnum = max([0] + [int(a[1:]) for a in
                               re.findall(InterWikiMap._argspec_re, url)])
        target, query, fragment = split_url_into_path_query_fragment(target)
        if maxargnum > 0:
            args = target.split(':', (maxargnum - 1))
        else:
            args = [target]
        url = self._expand_or_append(url, args)
        ntarget, nquery, nfragment = split_url_into_path_query_fragment(url)
        if query and nquery:
            nquery = '%s&%s' % (nquery, query[1:])
        else:
            nquery = nquery or query
        nfragment = fragment or nfragment # user provided takes precedence
        expanded_url = ntarget + nquery + nfragment
        if not self._is_safe_url(expanded_url):
            expanded_url = ''
        expanded_title = self._expand(title, args)
        if expanded_title == title:
            expanded_title = _("%(target)s in %(name)s",
                               target=target, name=title)
        return expanded_url, expanded_title

    # IWikiChangeListener methods

    def wiki_page_added(self, page):
        if page.name == InterWikiMap._page_name:
            del self.interwiki_map

    def wiki_page_changed(self, page, version, t, comment, author):
        if page.name == InterWikiMap._page_name:
            del self.interwiki_map

    def wiki_page_deleted(self, page):
        if page.name == InterWikiMap._page_name:
            del self.interwiki_map

    def wiki_page_version_deleted(self, page):
        if page.name == InterWikiMap._page_name:
            del self.interwiki_map

    @cached
    def interwiki_map(self, db):
        """Map from upper-cased namespaces to (namespace, prefix, title)
        values.
        """
        from trac.wiki.model import WikiPage
        map = {}
        content = WikiPage(self.env, InterWikiMap._page_name, db=db).text
        in_map = False
        for line in content.split('\n'):
            if in_map:
                if line.startswith('----'):
                    in_map = False
                else:
                    m = re.match(InterWikiMap._interwiki_re, line)
                    if m:
                        prefix, url, title = m.groups()
                        url = url.strip()
                        title = title.strip() if title else prefix
                        map[prefix.upper()] = (prefix, url, title)
            elif line.startswith('----'):
                in_map = True
        for prefix, value in self.interwiki_section.options():
            value = value.split(None, 1)
            if value:
                url = value[0].strip()
                title = value[1].strip() if len(value) > 1 else prefix
                map[prefix.upper()] = (prefix, url, title)
        return map

    # IWikiMacroProvider methods

    def get_macros(self):
        yield 'InterWiki'

    def get_macro_description(self, name):
        return 'messages', \
               N_("Provide a description list for the known InterWiki "
                  "prefixes.")

    def expand_macro(self, formatter, name, content):
        interwikis = []
        for k in sorted(self.keys()):
            prefix, url, title = self[k]
            interwikis.append({
                'prefix': prefix, 'url': url, 'title': title,
                'rc_url': self._expand_or_append(url, ['RecentChanges']),
                'description': url if title == prefix else title})

        return tag.table(tag.tr(tag.th(tag.em(_("Prefix"))),
                                tag.th(tag.em(_("Site")))),
                         [tag.tr(tag.td(tag.a(w['prefix'], href=w['rc_url'])),
                                 tag.td(tag.a(w['description'],
                                              href=w['url'])))
                          for w in interwikis ],
                         class_="wiki interwiki")

    # Internal methods

    def _is_safe_url(self, url):
        return WikiSystem(self.env).render_unsafe_content or \
               ':' not in url or \
               url.split(':', 1)[0] in self._safe_schemes

    @lazy
    def _safe_schemes(self):
        return set(WikiSystem(self.env).safe_schemes)
