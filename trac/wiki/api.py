# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2009 Edgewall Software
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

import re

from genshi.builder import tag

from trac.cache import cached
from trac.config import BoolOption, ListOption
from trac.core import *
from trac.resource import IResourceManager
from trac.util.translation import _
from trac.wiki.parser import WikiParser


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

    def wiki_page_renamed(page, old_name): 
        """Called when a page has been renamed.""" 


class IWikiPageManipulator(Interface):
    """Extension point interface for components that need to do specific
    pre and post processing of wiki page changes.
    
    Unlike change listeners, a manipulator can reject changes being committed
    to the database.
    """

    def prepare_wiki_page(req, page, fields):
        """Validate a wiki page before rendering it.

        `page` is the `WikiPage` being viewed.
        `fields` is a dictionary which contains the wiki `text` of the page,
        initially identical to `page.text` but it  can eventually be
        transformed in place before being used as input to the formatter.
        """

    def validate_wiki_page(req, page):
        """Validate a wiki page after it's been populated from user input.

        `page` is the `WikiPage` being edited.
        
        Must return a list of `(field, message)` tuples, one for each problem
        detected. `field` can be `None` to indicate an overall problem with the
        page. Therefore, a return value of `[]` means everything is OK.
        """


class IWikiMacroProvider(Interface):
    """Extension point interface for components that provide Wiki macros

    New Wiki processors can also be added that way. (''since 0.12'')
    """

    def get_macros():
        """Return an iterable that provides the names of the provided macros.
        """

    def get_macro_description(name):
        """Return a plain text description of the macro with the specified
        name."""

    def render_macro(req, name, content):
        """Return the HTML output of the macro (deprecated)"""

    def expand_macro(formatter, name, content, args=None):
        """Called by the formatter when rendering the parsed wiki text.

        This form is preferred over `render_macro`, as you get the
        formatter, which knows the current `.context` (and the `.req`,
        but ideally you shouldn't use it in your macros). (''since 0.11'')

        `name` is the name by which the macro has been called; remember
        that via `get_macros`, multiple names could be associated to this
        macros. Note that the macro names are case sensitive.
        
        `content` is the content of the macro call. When called using macro
        syntax (`[[Macro(content)]]`), this is the string contained between
        parentheses, usually containing macro arguments. When called using wiki
        processor syntax (`{{{!#Macro ...}}}`), it is the content of the
        processor block, that is, the text starting on the line following the
        macro name.

        `args` will be a dictionary containing the named parameters which you
        can specify when calling the macro using the wiki processor syntax:
        `{{{#!Macro arg1=value1 arg2="value 2"`. In this example, `args` will
        be `{'arg1': 'value1', 'arg2': 'value 2'}`).
        If no named parameters are given, `args` will be `{}`. That makes it
        possible to differentiate with a call using the macro syntax, in which
        case `args` will be `None` (see `parse_args` for a convenient way to
        extract arguments and name parameters from the `content` inside the
        parentheses, in the latter situation). (''since 0.12'')
        """


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

        Each formatter should be a function of the form:
        {{{#!python
        def format(formatter, ns, target, label, fullmatch=None):
            pass
        }}}
        and should return some HTML fragment. The `label` is already
        HTML escaped, whereas the `target` is not. The `fullmatch` argument
        is optional, and is bound to the regexp match object for the link.
        """


def parse_args(args, strict=True):
    """Utility for parsing macro "content" and splitting them into arguments.

    The content is split along commas, unless they are escaped with a
    backquote (like this: \,).
    
    :param args: macros arguments, as plain text
    :param strict: if `True`, only Python-like identifiers will be
                   recognized as keyword arguments 

    Example usage:

    >>> parse_args('')
    ([], {})
    >>> parse_args('Some text')
    (['Some text'], {})
    >>> parse_args('Some text, mode= 3, some other arg\, with a comma.')
    (['Some text', ' some other arg, with a comma.'], {'mode': ' 3'})
    >>> parse_args('milestone=milestone1,status!=closed', strict=False)
    ([], {'status!': 'closed', 'milestone': 'milestone1'})
    
    """    
    largs, kwargs = [], {}
    if args:
        for arg in re.split(r'(?<!\\),', args):
            arg = arg.replace(r'\,', ',')
            if strict:
                m = re.match(r'\s*[a-zA-Z_]\w+=', arg)
            else:
                m = re.match(r'\s*[^=]+=', arg)
            if m:
                kw = arg[:m.end()-1].strip()
                if strict:
                    kw = unicode(kw).encode('utf-8')
                kwargs[kw] = arg[m.end():]
            else:
                largs.append(arg)
    return largs, kwargs


class WikiSystem(Component):
    """Wiki system manager."""

    implements(IWikiSyntaxProvider, IResourceManager)

    change_listeners = ExtensionPoint(IWikiChangeListener)
    macro_providers = ExtensionPoint(IWikiMacroProvider)
    syntax_providers = ExtensionPoint(IWikiSyntaxProvider)

    ignore_missing_pages = BoolOption('wiki', 'ignore_missing_pages', 'false',
        """Enable/disable highlighting CamelCase links to missing pages
        (''since 0.9'').""")

    split_page_names = BoolOption('wiki', 'split_page_names', 'false',
        """Enable/disable splitting the WikiPageNames with space characters
        (''since 0.10'').""")

    render_unsafe_content = BoolOption('wiki', 'render_unsafe_content', 'false',
        """Enable/disable the use of unsafe HTML tags such as `<script>` or
        `<embed>` with the HTML [wiki:WikiProcessors WikiProcessor]
        (''since 0.10.4'').

        For public sites where anonymous users can edit the wiki it is
        recommended to leave this option disabled (which is the default).""")

    safe_schemes = ListOption('wiki', 'safe_schemes',
        'cvs,file,ftp,git,irc,http,https,news,sftp,smb,ssh,svn,svn+ssh',
        doc="""List of URI schemes considered "safe", that will be rendered as
        external links even if `[wiki] render_unsafe_content` is `false`.
        (''since 0.11.8'')""")

    @cached
    def pages(self, db):
        """Return the names of all existing wiki pages."""
        cursor = db.cursor()
        cursor.execute("SELECT DISTINCT name FROM wiki")
        return set(row[0] for row in cursor)

    # Public API

    def get_pages(self, prefix=None):
        """Iterate over the names of existing Wiki pages.

        If the `prefix` parameter is given, only names that start with that
        prefix are included.
        """
        for page in self.pages:
            if not prefix or page.startswith(prefix):
                yield page

    def has_page(self, pagename):
        """Whether a page with the specified name exists."""
        return pagename.rstrip('/') in self.pages

    # IWikiSyntaxProvider methods

    XML_NAME = r"[\w:](?<!\d)(?:[\w:.-]*[\w-])?"
    # See http://www.w3.org/TR/REC-xml/#id,
    # here adapted to exclude terminal "." and ":" characters

    PAGE_SPLIT_RE = re.compile(r"([a-z])([A-Z])(?=[a-z])")

    Lu = ''.join(unichr(c) for c in range(0, 0x10000) if unichr(c).isupper())
    Ll = ''.join(unichr(c) for c in range(0, 0x10000) if unichr(c).islower())

    def format_page_name(self, page, split=False):
        if split or self.split_page_names:
            return self.PAGE_SPLIT_RE.sub(r"\1 \2", page)
        return page

    def make_label_from_target(self, target):
        """Create a label from a wiki target.
        
        A trailing fragment and query string is stripped. Then, leading `./`,
        `../` and '/' elements are stripped, except when this would lead to an
        empty label. Finally, if `[wiki] split_page_names` is true, the label
        is split accordingly.
        """
        label = target.split('#', 1)[0].split('?', 1)[0]
        if not label:
            return target
        components = label.split('/')
        for i, comp in enumerate(components):
            if comp not in ('', '.', '..'):
                label = '/'.join(components[i:])
                break
        return self.format_page_name(label)

    def get_wiki_syntax(self):
        wiki_page_name = (
            r"(?:[%(upper)s](?:[%(lower)s])+/?){2,}" # wiki words
            r"(?:@\d+)?"                             # optional version
            r"(?:#%(xml)s)?"                         # optional fragment id
            r"(?=:(?:\Z|\s)|[^:\w%(upper)s%(lower)s]|\s|\Z)"
            # what should follow it
            % {'upper': self.Lu, 'lower': self.Ll, 'xml': self.XML_NAME})
        
        # Regular WikiPageNames
        def wikipagename_link(formatter, match, fullmatch):
            return self._format_link(formatter, 'wiki', match,
                                     self.format_page_name(match),
                                     self.ignore_missing_pages, match)
        
        # Start after any non-word char except '/', with optional relative or
        # absolute prefix
        yield (r"!?(?<![\w/])(?:\.?\.?/)*"
               + wiki_page_name, wikipagename_link)

        # [WikiPageNames with label]
        def wikipagename_with_label_link(formatter, match, fullmatch):
            page = fullmatch.group('wiki_page')
            label = fullmatch.group('wiki_label')
            return self._format_link(formatter, 'wiki', page, label.strip(),
                                     self.ignore_missing_pages, match)
        yield (r"!?\[(?P<wiki_page>%s)\s+(?P<wiki_label>%s|[^\]]+)\]"
               % (wiki_page_name, WikiParser.QUOTED_STRING),
               wikipagename_with_label_link)

        # MoinMoin's ["internal free link"] and ["free link" with label]
        def internal_free_link(fmt, m, fullmatch): 
            page = fullmatch.group('ifl_page')[1:-1]
            label = fullmatch.group('ifl_label')
            if label is None:
                label = self.make_label_from_target(page)
            return self._format_link(fmt, 'wiki', page, label.strip(), False)
        yield (r"!?\[(?P<ifl_page>%s)(?:\s+(?P<ifl_label>%s|[^\]]+))?\]"
               % (WikiParser.QUOTED_STRING, WikiParser.QUOTED_STRING),
               internal_free_link)

    def get_link_resolvers(self):
        def link_resolver(formatter, ns, target, label, fullmatch=None):
            if fullmatch is not None:
                # If no explicit label was specified for a [wiki:...] link,
                # generate a "nice" label instead of keeping the label
                # generated by the Formatter (usually the target itself).
                groups = fullmatch.groupdict()
                if groups.get('lns') and not groups.get('label'):
                    label = self.make_label_from_target(target)
            return self._format_link(formatter, ns, target, label, False)
        yield ('wiki', link_resolver)

    def _format_link(self, formatter, ns, pagename, label, ignore_missing,
                     original_label=None):
        pagename, query, fragment = formatter.split_link(pagename)
        version = None
        if '@' in pagename:
            pagename, version = pagename.split('@', 1)
        if version and query:
            query = '&' + query[1:]
        pagename = pagename.rstrip('/') or 'WikiStart'
        referrer = ''
        if formatter.resource and formatter.resource.realm == 'wiki':
            referrer = formatter.resource.id
        if pagename.startswith('/'):
            pagename = pagename.lstrip('/')
        elif pagename.startswith('./') or pagename.startswith('../') \
                                                or pagename in ('.', '..'):
            pagename = self._resolve_relative_name(pagename, referrer)
        else:
            pagename = self._resolve_scoped_name(pagename, referrer)
        if 'WIKI_VIEW' in formatter.perm('wiki', pagename, version):
            href = formatter.href.wiki(pagename, version=version) + query \
                   + fragment
            if self.has_page(pagename):
                return tag.a(label, href=href, class_='wiki')
            else:
                if ignore_missing:
                    return original_label or label
                if 'WIKI_CREATE' in formatter.perm('wiki', pagename, version):
                    return tag.a(label + '?', class_='missing wiki',
                                 href=href, rel='nofollow')
                else:
                    return tag.a(label + '?', class_='missing wiki')
        elif ignore_missing and not self.has_page(pagename):
            return original_label or label
        else:
            return tag.a(label, class_='forbidden wiki',
                         title=_("no permission to view this wiki page"))

    def _resolve_relative_name(self, pagename, referrer):
        base = referrer.split('/')
        components = pagename.split('/')
        for i, comp in enumerate(components):
            if comp == '..':
                if base:
                    base.pop()
            elif comp and comp != '.':
                base.extend(components[i:])
                break
        return '/'.join(base)
    
    def _resolve_scoped_name(self, pagename, referrer):
        referrer = referrer.split('/')
        if len(referrer) == 1:           # Non-hierarchical referrer
            return pagename
        # Test for pages with same name, higher in the hierarchy
        for i in range(len(referrer) - 1, 0, -1):
            name = '/'.join(referrer[:i]) + '/' + pagename
            if self.has_page(name):
                return name
        if self.has_page(pagename):
            return pagename
        # If we are on First/Second/Third, and pagename is Second/Other,
        # resolve to First/Second/Other instead of First/Second/Second/Other
        # See http://trac.edgewall.org/ticket/4507#comment:12
        if '/' in pagename:
            (first, rest) = pagename.split('/', 1)
            for (i, part) in enumerate(referrer):
                if first == part:
                    anchor = '/'.join(referrer[:i + 1])
                    if self.has_page(anchor):
                        return anchor + '/' + rest
        # Assume the user wants a sibling of referrer
        return '/'.join(referrer[:-1]) + '/' + pagename

    # IResourceManager methods

    def get_resource_realms(self):
        yield 'wiki'

    def get_resource_description(self, resource, format, **kwargs):
        """
        >>> from trac.test import EnvironmentStub
        >>> from trac.resource import Resource, get_resource_description
        >>> env = EnvironmentStub()
        >>> main = Resource('wiki', 'WikiStart')
        >>> get_resource_description(env, main)
        'WikiStart'

        >>> get_resource_description(env, main(version=3))
        'WikiStart'

        >>> get_resource_description(env, main(version=3), format='summary')
        'WikiStart'

        >>> env.config['wiki'].set('split_page_names', 'true')
        >>> get_resource_description(env, main(version=3))
        'Wiki Start'
        """
        return self.format_page_name(resource.id)

    def resource_exists(self, resource):
        """
        >>> from trac.test import EnvironmentStub
        >>> from trac.resource import Resource, resource_exists
        >>> env = EnvironmentStub()

        >>> resource_exists(env, Resource('wiki', 'WikiStart'))
        False

        >>> from trac.wiki.model import WikiPage
        >>> main = WikiPage(env, 'WikiStart')
        >>> main.text = 'some content'
        >>> main.save('author', 'no comment', '::1')
        >>> resource_exists(env, main.resource)
        True
        """
        if resource.version is None:
            return resource.id in self.pages
        db = self.env.get_read_db()
        cursor = db.cursor()
        cursor.execute("SELECT name FROM wiki WHERE name=%s AND version=%s",
                       (resource.id, resource.version))
        return bool(cursor.fetchall())
