# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2005 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2004-2005 Christopher Lenz <cmlenz@gmx.de>
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
# Author: Jonas Borgström <jonas@edgewall.com>
#         Christopher Lenz <cmlenz@gmx.de>

try:
    import threading
except ImportError:
    import dummy_threading as threading
import time
import urllib
import re

from trac.config import BoolOption
from trac.core import *
from trac.util.html import html


class IWikiChangeListener(Interface):
    """Extension point interface for components that should get notified about
    the creation, deletion and modification of wiki pages.
    """

    def wiki_page_added(page):
        """Called whenever a new Wiki page is added."""

    def wiki_page_changed(page, version, t, comment, author, ipnr):
        """Called when a page has been modified."""

    def wiki_page_deleted(page):
        """Called when a page has been deleted."""

    def wiki_page_version_deleted(page):
        """Called when a version of a page has been deleted."""


class IWikiPageManipulator(Interface):
    """Extension point interface for components that need to to specific
    pre and post processing of wiki page changes.
    
    Unlike change listeners, a manipulator can reject changes being committed
    to the database.
    """

    def prepare_wiki_page(req, page, fields):
        """Not currently called, but should be provided for future
        compatibility."""

    def validate_wiki_page(req, page):
        """Validate a wiki page after it's been populated from user input.
        
        Must return a list of `(field, message)` tuples, one for each problem
        detected. `field` can be `None` to indicate an overall problem with the
        page. Therefore, a return value of `[]` means everything is OK."""


class IWikiMacroProvider(Interface):
    """Extension point interface for components that provide Wiki macros."""

    def get_macros():
        """Return an iterable that provides the names of the provided macros."""

    def get_macro_description(name):
        """Return a plain text description of the macro with the specified name.
        """

    def render_macro(req, name, content):
        """Return the HTML output of the macro."""


class IWikiSyntaxProvider(Interface):
 
    def get_wiki_syntax():
        """Return an iterable that provides additional wiki syntax.

        Additional wiki syntax correspond to a pair of (regexp, cb),
        the `regexp` for the additional syntax and the callback `cb`
        which will be called if there's a match.
        That function is of the form cb(formatter, ns, match).
        """
 
    def get_link_resolvers():
        """Return an iterable over (namespace, formatter) tuples.

        Each formatter should be a function of the form
        fmt(formatter, ns, target, label), and should
        return some HTML fragment.
        The `label` is already HTML escaped, whereas the `target` is not.
        """


def parse_args(args):
    """Utility for parsing macro "content" and splitting them into arguments.

    The content is split along commas, unless they are escaped with a
    backquote (like this: \,).
    Named arguments a la Python are supported, and keys must be  valid python
    identifiers immediately followed by the "=" sign.

    >>> parse_args('')
    ([], {})
    >>> parse_args('Some text')
    (['Some text'], {})
    >>> parse_args('Some text, mode= 3, some other arg\, with a comma.')
    (['Some text', ' some other arg, with a comma.'], {'mode': ' 3'})
    
    """    
    largs, kwargs = [], {}
    if args:
        for arg in re.split(r'(?<!\\),', args):
            arg = arg.replace(r'\,', ',')
            m = re.match(r'\s*[a-zA-Z_]\w+=', arg)
            if m:
                kwargs[arg[:m.end()-1].lstrip()] = arg[m.end():]
            else:
                largs.append(arg)
    return largs, kwargs


class WikiSystem(Component):
    """Represents the wiki system."""

    implements(IWikiChangeListener, IWikiSyntaxProvider)

    change_listeners = ExtensionPoint(IWikiChangeListener)
    macro_providers = ExtensionPoint(IWikiMacroProvider)
    syntax_providers = ExtensionPoint(IWikiSyntaxProvider)

    INDEX_UPDATE_INTERVAL = 5 # seconds

    ignore_missing_pages = BoolOption('wiki', 'ignore_missing_pages', 'false',
        """Enable/disable highlighting CamelCase links to missing pages
        (''since 0.9'').""")

    split_page_names = BoolOption('wiki', 'split_page_names', 'false',
        """Enable/disable splitting the WikiPageNames with space characters
        (''since 0.10'').""")

    def __init__(self):
        self._index = None
        self._last_index_update = 0
        self._index_lock = threading.RLock()
        self._compiled_rules = None
        self._link_resolvers = None
        self._helper_patterns = None
        self._external_handlers = None

    def _update_index(self):
        self._index_lock.acquire()
        try:
            now = time.time()
            if now > self._last_index_update + WikiSystem.INDEX_UPDATE_INTERVAL:
                self.log.debug('Updating wiki page index')
                db = self.env.get_db_cnx()
                cursor = db.cursor()
                cursor.execute("SELECT DISTINCT name FROM wiki WHERE version=1")
                self._index = {}
                for (name,) in cursor:
                    self._index[name] = True
                self._last_index_update = now
        finally:
            self._index_lock.release()

    # Public API

    def get_pages(self, prefix=None):
        """Iterate over the names of existing Wiki pages.

        If the `prefix` parameter is given, only names that start with that
        prefix are included.
        """
        self._update_index()
        # Note: use of keys() is intentional since iterkeys() is prone to
        # errors with concurrent modification
        for page in self._index.keys():
            if not prefix or page.startswith(prefix):
                yield page

    def has_page(self, pagename):
        """Whether a page with the specified name exists."""
        self._update_index()
        return self._index.has_key(pagename.rstrip('/'))

    def _get_rules(self):
        self._prepare_rules()
        return self._compiled_rules
    rules = property(_get_rules)

    def _get_helper_patterns(self):
        self._prepare_rules()
        return self._helper_patterns
    helper_patterns = property(_get_helper_patterns)

    def _get_external_handlers(self):
        self._prepare_rules()
        return self._external_handlers
    external_handlers = property(_get_external_handlers)

    def _prepare_rules(self):
        from trac.wiki.formatter import Formatter
        if not self._compiled_rules:
            helpers = []
            handlers = {}
            syntax = Formatter._pre_rules[:]
            i = 0
            for resolver in self.syntax_providers:
                for regexp, handler in resolver.get_wiki_syntax():
                    handlers['i' + str(i)] = handler
                    syntax.append('(?P<i%d>%s)' % (i, regexp))
                    i += 1
            syntax += Formatter._post_rules[:]
            helper_re = re.compile(r'\?P<([a-z\d_]+)>')
            for rule in syntax:
                helpers += helper_re.findall(rule)[1:]
            rules = re.compile('(?:' + '|'.join(syntax) + ')')
            self._external_handlers = handlers
            self._helper_patterns = helpers
            self._compiled_rules = rules

    def _get_link_resolvers(self):
        if not self._link_resolvers:
            resolvers = {}
            for resolver in self.syntax_providers:
                for namespace, handler in resolver.get_link_resolvers():
                    resolvers[namespace] = handler
            self._link_resolvers = resolvers
        return self._link_resolvers
    link_resolvers = property(_get_link_resolvers)

    # IWikiChangeListener methods

    def wiki_page_added(self, page):
        if not self.has_page(page.name):
            self.log.debug('Adding page %s to index' % page.name)
            self._index[page.name] = True

    def wiki_page_changed(self, page, version, t, comment, author, ipnr):
        pass

    def wiki_page_deleted(self, page):
        if self.has_page(page.name):
            self.log.debug('Removing page %s from index' % page.name)
            del self._index[page.name]

    def wiki_page_version_deleted(self, page):
        pass

    # IWikiSyntaxProvider methods

    XML_NAME = r"[\w:](?<!\d)(?:[\w:.-]*[\w-])?"
    # See http://www.w3.org/TR/REC-xml/#id,
    # here adapted to exclude terminal "." and ":" characters

    PAGE_SPLIT_RE = re.compile(r"([a-z])([A-Z][a-z])")
    
    def format_page_name(self, page, split=False):
        if split or self.split_page_names:
            return self.PAGE_SPLIT_RE.sub(r"\1 \2", page)
        return page
    
    def get_wiki_syntax(self):
        from trac.wiki.formatter import Formatter
        wiki_page_name = (
            r"[A-Z][a-z]+(?:[A-Z][a-z]*[a-z/])+" # wiki words
            r"(?:#%s)?" % self.XML_NAME + # optional fragment id
            r"(?=:(?:\Z|\s)|[^:a-zA-Z]|\s|\Z)" # what should follow it
            )
        
        # Regular WikiPageNames
        def wikipagename_link(formatter, match, fullmatch):
            return self._format_link(formatter, 'wiki', match,
                                     self.format_page_name(match),
                                     self.ignore_missing_pages)
        
        yield (r"!?(?<!/)\b" + # start at a word boundary but not after '/'
               wiki_page_name, wikipagename_link)

        # [WikiPageNames with label]
        def wikipagename_with_label_link(formatter, match, fullmatch):
            page, label = match[1:-1].split(' ', 1)
            return self._format_link(formatter, 'wiki', page, label.strip(),
                                     self.ignore_missing_pages)
        yield (r"!?\[%s\s+(?:%s|[^\]]+)\]" % (wiki_page_name,
                                              Formatter.QUOTED_STRING),
               wikipagename_with_label_link)

        # MoinMoin's ["internal free link"] 
        def internal_free_link(fmt, m, fullmatch): 
            return self._format_link(fmt, 'wiki', m[2:-2], m[2:-2], False) 
        yield (r"!?\[(?:%s)\]" % Formatter.QUOTED_STRING, internal_free_link) 

    def get_link_resolvers(self):
        def link_resolver(formatter, ns, target, label):
            return self._format_link(formatter, ns, target, label, False)
        yield ('wiki', link_resolver)

    def _format_link(self, formatter, ns, page, label, ignore_missing):
        page, query, fragment = formatter.split_link(page)
        href = formatter.href.wiki(page) + fragment
        if not self.has_page(page):
            if ignore_missing:
                return label
            return html.A(label+'?', href=href, class_='missing wiki',
                          rel='nofollow')
        else:
            return html.A(label, href=href, class_='wiki')
