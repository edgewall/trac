# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2009 Edgewall Software
# Copyright (C) 2005-2006 Christian Boos <cboos@neuf.fr>
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
# Author: Christian Boos <cboos@neuf.fr>

import re
try:
    import threading
except ImportError:
    import dummy_threading as threading

from genshi.builder import tag

from trac.core import *
from trac.wiki.formatter import Formatter
from trac.wiki.parser import WikiParser
from trac.wiki.api import IWikiChangeListener, IWikiMacroProvider


class InterWikiMap(Component):
    """Implements support for InterWiki maps."""

    implements(IWikiChangeListener, IWikiMacroProvider)

    _page_name = 'InterMapTxt'
    _interwiki_re = re.compile(r"(%s)[ \t]+([^ \t]+)(?:[ \t]+#(.*))?" %
                               WikiParser.LINK_SCHEME, re.UNICODE)
    _argspec_re = re.compile(r"\$\d")
    _interwiki_map = None

    def __init__(self):
        self._interwiki_lock = threading.RLock()

    def reset(self):
        self._interwiki_map = None
        self.config.touch()
        # This dictionary maps upper-cased namespaces
        # to (namespace, prefix, title) values;

    # The component itself behaves as a map

    def __contains__(self, ns):
        return ns.upper() in self.interwiki_map

    def __getitem__(self, ns):
        return self.interwiki_map[ns.upper()]

    def __setitem__(self, ns, value):
        self.interwiki_map[ns.upper()] = value

    def keys(self):
        return self.interwiki_map.keys()

    # Expansion of positional arguments ($1, $2, ...) in URL and title
    def _expand(self, txt, args):
        """Replace "$1" by the first args, "$2" by the second, etc."""
        def setarg(match):
            num = int(match.group()[1:])
            return 0 < num <= len(args) and args[num-1] or ''
        return re.sub(InterWikiMap._argspec_re, setarg, txt)

    def _expand_or_append(self, txt, args):
        """Like expand, but also append first arg if there's no "$"."""
        if not args:
            return txt
        expanded = self._expand(txt, args)
        return expanded == txt and txt + args[0] or expanded

    def url(self, ns, target):
        """Return `(url, title)` for the given InterWiki `ns`.
        
        Expand the colon-separated `target` arguments.
        """
        ns, url, title = self[ns]
        maxargnum = max([0]+[int(a[1:]) for a in
                             re.findall(InterWikiMap._argspec_re, url)])
        if maxargnum > 0:
            args = target.split(':', (maxargnum - 1))
        else:
            args = [target]
        expanded_url = self._expand_or_append(url, args)
        expanded_title = self._expand(title, args)
        if expanded_title == title:
            expanded_title = target+' in '+title
        return expanded_url, expanded_title

    # IWikiChangeListener methods

    def wiki_page_added(self, page):
        pass

    def wiki_page_changed(self, page, version, t, comment, author, ipnr):
        if page.name == InterWikiMap._page_name:
            self.reset()

    def wiki_page_deleted(self, page):
        if page.name == InterWikiMap._page_name:
            self.reset()

    def wiki_page_version_deleted(self, page):
        if page.name == InterWikiMap._page_name:
            self.reset()

    def _get_interwiki_map(self):
        from trac.wiki.model import WikiPage
        if self._interwiki_map is None:
            self._interwiki_lock.acquire()
            try:
                if self._interwiki_map is None:
                    self._interwiki_map = {}
                    content = WikiPage(self.env, InterWikiMap._page_name).text
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
                                    title = title and title.strip() or prefix
                                    self[prefix] = (prefix, url, title)
                        elif line.startswith('----'):
                            in_map = True
            finally:
                self._interwiki_lock.release()
        return self._interwiki_map
    interwiki_map = property(_get_interwiki_map)

    # IWikiMacroProvider methods

    def get_macros(self):
        yield 'InterWiki'

    def get_macro_description(self, name): 
        return "Provide a description list for the known InterWiki prefixes."

    def expand_macro(self, formatter, name, content):
        from trac.util import sorted
        interwikis = []
        for k in sorted(self.keys()):
            prefix, url, title = self[k]
            interwikis.append({
                'prefix': prefix, 'url': url, 'title': title,
                'rc_url': self._expand_or_append(url, ['RecentChanges']),
                'description': title == prefix and url or title})

        return tag.table(tag.tr(tag.th(tag.em("Prefix")),
                                tag.th(tag.em("Site"))),
                         [tag.tr(tag.td(tag.a(w['prefix'], href=w['rc_url'])),
                                 tag.td(tag.a(w['description'],
                                              href=w['url'])))
                          for w in interwikis ],
                         class_="wiki interwiki")
