# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2009 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2004-2005 Christopher Lenz <cmlenz@gmx.de>
# Copyright (C) 2005-2007 Christian Boos <cboos@neuf.fr>
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
#         Christian Boos <cboos@neuf.fr>

import re
import os
import urllib

from StringIO import StringIO

from genshi.builder import tag, Element
from genshi.core import Stream, Markup, escape
from genshi.input import HTMLParser, ParseError
from genshi.util import plaintext

from trac.core import *
from trac.mimeview import *
from trac.resource import get_relative_resource, get_resource_url
from trac.util.compat import set
from trac.wiki.api import WikiSystem, parse_args
from trac.wiki.parser import WikiParser
from trac.util.text import exception_to_unicode, shorten_line, to_unicode, \
                           unicode_quote, unicode_quote_plus
from trac.util.html import TracHTMLSanitizer
from trac.util.translation import _

__all__ = ['wiki_to_html', 'wiki_to_oneliner', 'wiki_to_outline',
           'Formatter', 'format_to', 'format_to_html', 'format_to_oneliner',
           'extract_link']

def system_message(msg, text=None):
    return tag.div(tag.strong(msg), text and tag.pre(text),
                   class_="system-message")

def _markup_to_unicode(markup):
    stream = None
    if isinstance(markup, Element):
        stream = markup.generate()
    elif isinstance(markup, Stream):
        stream = markup
    if stream:
        markup = stream.render('xhtml', encoding=None, strip_whitespace=False)
    return to_unicode(markup)


class WikiProcessor(object):

    _code_block_re = re.compile('^<div(?:\s+class="([^"]+)")?>(.*)</div>$')
    _block_elem_re = re.compile(r'^\s*<(?:div|table)(?:\s+[^>]+)?>',
                                re.I | re.M)

    def __init__(self, formatter, name, args={}):
        """Find the processor by name
        
        :param formatter: the formatter embedding a call for this processor 
        :param name: the name of the processor 
        :param args: extra parameters for the processor

        (since 0.11)
        """
        self.formatter = formatter
        self.env = formatter.env
        self.name = name
        self.args = args
        self.error = None
        self.macro_provider = None

        builtin_processors = {'html': self._html_processor,
                              'default': self._default_processor,
                              'comment': self._comment_processor,
                              'div': self._div_processor,
                              'span': self._span_processor,
                              'Span': self._span_processor}

        self._sanitizer = TracHTMLSanitizer()
        
        self.processor = builtin_processors.get(name)
        if not self.processor:
            # Find a matching wiki macro
            for macro_provider in WikiSystem(self.env).macro_providers:
                for macro_name in macro_provider.get_macros():
                    if self.name == macro_name:
                        if hasattr(macro_provider, 'expand_macro'):
                            self.processor = self._macro_processor
                        else:
                            self.processor = self._legacy_macro_processor
                        self.macro_provider = macro_provider
                        break
        if not self.processor:
            # Find a matching mimeview renderer
            from trac.mimeview.api import Mimeview
            mimetype = Mimeview(formatter.env).get_mimetype(self.name)
            if mimetype:
                self.name = mimetype
                self.processor = self._mimeview_processor
            else:
                self.processor = self._default_processor
                self.error = "No macro or processor named '%s' found" % name

    # builtin processors

    def _comment_processor(self, text):
        return ''

    def _default_processor(self, text):
        return tag.pre(text, class_="wiki")

    def _html_processor(self, text):
        if WikiSystem(self.env).render_unsafe_content:
            return Markup(text)
        try:
            stream = Stream(HTMLParser(StringIO(text)))
            return (stream | self._sanitizer).render('xhtml', encoding=None)
        except ParseError, e:
            self.env.log.warn(e)
            line = unicode(text).splitlines()[e.lineno - 1].strip()
            return system_message(_('HTML parsing error: %(message)s',
                                    message=escape(e.msg)), line)
        
    def _elt_processor(self, eltname, format_to, text, args):
        elt = getattr(tag, eltname)(**args)
        if not WikiSystem(self.env).render_unsafe_content:
            sanitized_elt = getattr(tag, eltname)
            for (k,data,pos) in (Stream(elt) | self._sanitizer):
                sanitized_elt.attrib = data[1]
                break # only look at START (elt,attrs)
            elt = sanitized_elt
        elt.append(format_to(self.env, self.formatter.context, text))
        return elt

    def _div_processor(self, text):
        return self._elt_processor('div', format_to_html, text, self.args)
    
    def _span_processor(self, text):
        args, kwargs = parse_args(text, strict=True)
        return self._elt_processor('span', format_to_oneliner, ', '.join(args),
                                   kwargs)

    # generic processors

    def _legacy_macro_processor(self, text): # TODO: remove in 0.12
        self.env.log.warning('Executing pre-0.11 Wiki macro %s by provider %s'
                             % (self.name, self.macro_provider))
        return self.macro_provider.render_macro(self.formatter.req, self.name,
                                                text)

    def _macro_processor(self, text):
        self.env.log.debug('Executing Wiki macro %s by provider %s'
                           % (self.name, self.macro_provider))
        return self.macro_provider.expand_macro(self.formatter, self.name,
                                                text)

    def _mimeview_processor(self, text):
        return Mimeview(self.env).render(self.formatter.context,
                                         self.name, text)
    # TODO: use convert('text/html') instead of render

    def process(self, text, in_paragraph=False):
        if self.error:
            text = system_message(tag('Error: Failed to load processor ',
                                      tag.code(self.name)),
                                  self.error)
        else:
            text = self.processor(text)
        if not text:
            return ''
        if in_paragraph:
            content_for_span = None
            interrupt_paragraph = False
            if isinstance(text, Element):
                tagname = text.tag.lower()
                if tagname == 'div':
                    class_ = text.attrib.get('class', '')
                    if class_ and 'code' in class_:
                        content_for_span = text.children
                    else:
                        interrupt_paragraph = True
                elif tagname == 'table':
                    interrupt_paragraph = True
            else:
                # FIXME: do something smarter for Streams
                text = to_unicode(text)
                match = re.match(self._code_block_re, text)
                if match:
                    if match.group(1) and 'code' in match.group(1):
                        content_for_span = match.group(2)
                    else:
                        interrupt_paragraph = True
                elif re.match(self._block_elem_re, text):
                    interrupt_paragraph = True
            if content_for_span:
                text = tag.span(class_='code-block')(*content_for_span)
            elif interrupt_paragraph:
                text = "</p>%s<p>" % to_unicode(text)
        return text


class Formatter(object):
    """Base Wiki formatter.

    Parses and formats wiki text, in a given `Context`.
    """
    
    flavor = 'default'

    # 0.10 compatibility
    INTERTRAC_SCHEME = WikiParser.INTERTRAC_SCHEME
    QUOTED_STRING = WikiParser.QUOTED_STRING
    LINK_SCHEME = WikiParser.LINK_SCHEME

    def __init__(self, env, context):
        """Note: `req` is still temporarily used."""
        self.env = env
        self.context = context
        self.req = context.req
        self.href = context.href
        self.resource = context.resource
        self.perm = context.perm
        self.db = self.env.get_db_cnx() # FIXME: remove
        self.wiki = WikiSystem(self.env)
        self.wikiparser = WikiParser(self.env)
        self._anchors = {}
        self._open_tags = []

    def split_link(self, target):
        """Split a target along "?" and "#" in `(path, query, fragment)`."""
        query = fragment = ''
        idx = target.find('#')
        if idx >= 0:
            target, fragment = target[:idx], target[idx:]
        idx = target.find('?')
        if idx >= 0:
            target, query = target[:idx], target[idx:]
        return (target, query, fragment)

    # -- Pre- IWikiSyntaxProvider rules (Font styles)
    
    def tag_open_p(self, tag):
        """Do we currently have any open tag with `tag` as end-tag?"""
        return tag in self._open_tags

    def close_tag(self, tag):
        tmp =  ''
        for i in xrange(len(self._open_tags)-1, -1, -1):
            tmp += self._open_tags[i][1]
            if self._open_tags[i][1] == tag:
                del self._open_tags[i]
                for j in xrange(i, len(self._open_tags)):
                    tmp += self._open_tags[j][0]
                break
        return tmp

    def open_tag(self, open, close):
        self._open_tags.append((open, close))

    def simple_tag_handler(self, match, open_tag, close_tag):
        """Generic handler for simple binary style tags"""
        if self.tag_open_p((open_tag, close_tag)):
            return self.close_tag(close_tag)
        else:
            self.open_tag(open_tag, close_tag)
        return open_tag

    def _bolditalic_formatter(self, match, fullmatch):
        italic = ('<i>', '</i>')
        italic_open = self.tag_open_p(italic)
        tmp = ''
        if italic_open:
            tmp += italic[1]
            self.close_tag(italic[1])
        tmp += self._bold_formatter(match, fullmatch)
        if not italic_open:
            tmp += italic[0]
            self.open_tag(*italic)
        return tmp

    def _bold_formatter(self, match, fullmatch):
        return self.simple_tag_handler(match, '<strong>', '</strong>')

    def _italic_formatter(self, match, fullmatch):
        return self.simple_tag_handler(match, '<i>', '</i>')

    def _underline_formatter(self, match, fullmatch):
        return self.simple_tag_handler(match, '<span class="underline">',
                                       '</span>')

    def _strike_formatter(self, match, fullmatch):
        return self.simple_tag_handler(match, '<del>', '</del>')

    def _subscript_formatter(self, match, fullmatch):
        return self.simple_tag_handler(match, '<sub>', '</sub>')

    def _superscript_formatter(self, match, fullmatch):
        return self.simple_tag_handler(match, '<sup>', '</sup>')

    def _inlinecode_formatter(self, match, fullmatch):
        return tag.tt(fullmatch.group('inline'))

    def _inlinecode2_formatter(self, match, fullmatch):
        return tag.tt(fullmatch.group('inline2'))

    # -- Post- IWikiSyntaxProvider rules

    # E-mails

    def _email_formatter(self, match, fullmatch):
        from trac.web.chrome import Chrome
        omatch = Chrome(self.env).format_emails(self.context, match)
        if omatch == match: # not obfuscated, make a link
            return self._make_mail_link('mailto:'+match, match)
        else:
            return omatch

    # HTML escape of &, < and >

    def _htmlescape_formatter(self, match, fullmatch):
        return match == "&" and "&amp;" or match == "<" and "&lt;" or "&gt;"

    # Short form (shref) and long form (lhref) of TracLinks

    def _unquote(self, text):
        if text and text[0] in "'\"" and text[0] == text[-1]:
            return text[1:-1]
        else:
            return text

    def _shref_formatter(self, match, fullmatch):
        ns = fullmatch.group('sns')
        target = self._unquote(fullmatch.group('stgt'))
        return self._make_link(ns, target, match, match, fullmatch)

    def _lhref_formatter(self, match, fullmatch):
        rel = fullmatch.group('rel')
        ns = fullmatch.group('lns')
        target = self._unquote(fullmatch.group('ltgt'))
        label = fullmatch.group('label')
        if not label: # e.g. `[http://target]` or `[wiki:target]`
            if target:
                if target.startswith('//'): # for `[http://target]`
                    label = ns+':'+target   #  use `http://target`
                else:                       # for `wiki:target`
                    label = target          #  use only `target`
            else: # e.g. `[search:]` 
                label = ns
        else:
            label = self._unquote(label)
        if rel:
            path, query, fragment = self.split_link(rel)
            if path.startswith('//'):
                path = '/' + path.lstrip('/')
            elif path.startswith('/'):
                path = self.href(path) or '/'
            else:
                resource = get_relative_resource(self.resource, path)
                path = get_resource_url(self.env, resource, self.href)
                if resource.id:
                    idx = path.find('?')
                    if idx >= 0:
                        if query:
                            query = path[idx:] + '&' + query.lstrip('?')
                        else:
                            query = path[idx:]
                    target = unicode(resource.id) + query + fragment
                    return self._make_link(resource.realm, target, match,
                                           label or rel, fullmatch)
                if '?' in path and query:
                    query = '&' + query.lstrip('?')
            return tag.a(label or rel, href=path + query + fragment)
        else:
            return self._make_link(ns, target, match, label, fullmatch)

    def _make_link(self, ns, target, match, label, fullmatch):
        # first check for an alias defined in trac.ini
        ns = self.env.config['intertrac'].get(ns, ns)
        if ns in self.wikiparser.link_resolvers:
            return self.wikiparser.link_resolvers[ns](self, ns, target,
                                                      escape(label, False))
        elif target.startswith('//'):
            return self._make_ext_link(ns+':'+target, label)
        elif ns == "mailto":
            from trac.web.chrome import Chrome
            otarget = Chrome(self.env).format_emails(self.context, target)
            olabel = Chrome(self.env).format_emails(self.context, label)
            if (otarget, olabel) == (target, label):
                return self._make_mail_link('mailto:'+target, label)
            else:
                return olabel or otarget
        else:
            if label == target and not fullmatch.group('label'):
                # add ns for Inter* links when nothing is set
                label = ns+':'+label
            return self._make_intertrac_link(ns, target, label) or \
                   self._make_interwiki_link(ns, target, label) or \
                   escape(match)

    def _make_intertrac_link(self, ns, target, label):
        intertrac = self.env.config['intertrac']
        url = intertrac.get(ns+'.url')
        if not url and ns == 'trac':
            url = 'http://trac.edgewall.org'
        if url:
            name = intertrac.get(ns+'.title', 'Trac project %s' % ns)
            compat = intertrac.getbool(ns+'.compat', 'false')
            # set `compat` default to False now that 0.10 is widely used
            # TODO: remove compatibility code completely for 1.0 release
            if compat:
                sep = target.find(':')
                if sep != -1:
                    url = '%s/%s/%s' % (url, target[:sep], target[sep + 1:])
                else: 
                    url = '%s/search?q=%s' % (url, unicode_quote_plus(target))
            else:
                url = '%s/intertrac/%s' % (url, unicode_quote(target))
            if target:
                title = '%s in %s' % (target, name)
            else:
                title = name
            return self._make_ext_link(url, label, title)
        else:
            return None

    def shorthand_intertrac_helper(self, ns, target, label, fullmatch):
        if fullmatch: # short form
            it_group = fullmatch.group('it_%s' % ns)
            if it_group:
                alias = it_group.strip()
                intertrac = self.env.config['intertrac']
                target = '%s:%s' % (ns, target[len(it_group):])
                return self._make_intertrac_link(intertrac.get(alias, alias),
                                                 target, label) or label
        return None

    def _make_interwiki_link(self, ns, target, label):
        from trac.wiki.interwiki import InterWikiMap        
        interwiki = InterWikiMap(self.env)
        if ns in interwiki:
            url, title = interwiki.url(ns, target)
            return self._make_ext_link(url, label, title)
        else:
            return None

    def _make_ext_link(self, url, text, title=''):
        local_url = self.env.config.get('project', 'url') or \
                    (self.req or self.env).abs_href.base
        if not url.startswith(local_url):
            return tag.a(tag.span(u'\xa0', class_="icon"), text,
                          class_="ext-link", href=url, title=title or None)
        else:
            return tag.a(text, href=url, title=title or None)

    def _make_mail_link(self, url, text, title=''):
        return tag.a(tag.span(u'\xa0', class_="icon"), text,
                      class_="mail-link", href=url, title=title or None)

    # WikiMacros
    
    def _macro_formatter(self, match, fullmatch):
        name = fullmatch.group('macroname')
        if name.lower() == 'br':
            return '<br />'
        args = fullmatch.group('macroargs')
        try:
            macro = WikiProcessor(self, name)
            return macro.process(args, in_paragraph=True)
        except Exception, e:
            self.env.log.error('Macro %s(%s) failed: %s' % 
                    (name, args, exception_to_unicode(e, traceback=True)))
            return system_message('Error: Macro %s(%s) failed' % (name, args),
                                  e)

    # Headings

    def _parse_heading(self, match, fullmatch, shorten):
        match = match.strip()

        depth = min(len(fullmatch.group('hdepth')), 5)
        anchor = fullmatch.group('hanchor') or ''
        heading_text = match[depth+1:-depth-1-len(anchor)]
        heading = format_to_oneliner(self.env, self.context, heading_text,
                                     False)
        if anchor:
            anchor = anchor[1:]
        else:
            sans_markup = plaintext(heading, keeplinebreaks=False)
            anchor = WikiParser._anchor_re.sub('', sans_markup)
            if not anchor or anchor[0].isdigit() or anchor[0] in '.-':
                # an ID must start with a Name-start character in XHTML
                anchor = 'a' + anchor # keeping 'a' for backward compat
        i = 1
        anchor_base = anchor
        while anchor in self._anchors:
            anchor = anchor_base + str(i)
            i += 1
        self._anchors[anchor] = True
        if shorten:
            heading = format_to_oneliner(self.env, self.context, heading_text,
                                         True)
        return (depth, heading, anchor)

    def _heading_formatter(self, match, fullmatch):
        self.close_table()
        self.close_paragraph()
        self.close_indentation()
        self.close_list()
        self.close_def_list()
        depth, heading, anchor = self._parse_heading(match, fullmatch, False)
        self.out.write('<h%d id="%s">%s</h%d>' %
                       (depth, anchor, heading, depth))

    # Generic indentation (as defined by lists and quotes)

    def _set_tab(self, depth):
        """Append a new tab if needed and truncate tabs deeper than `depth`

        given:       -*-----*--*---*--
        setting:              *
        results in:  -*-----*-*-------
        """
        tabstops = []
        for ts in self._tabstops:
            if ts >= depth:
                break
            tabstops.append(ts)
        tabstops.append(depth)
        self._tabstops = tabstops

    # Lists
    
    def _list_formatter(self, match, fullmatch):
        ldepth = len(fullmatch.group('ldepth'))
        listid = match[ldepth]
        self.in_list_item = True
        class_ = start = None
        if listid in '-*':
            type_ = 'ul'
        else:
            type_ = 'ol'
            idx = '01iI'.find(listid)
            if idx >= 0:
                class_ = ('arabiczero', None, 'lowerroman', 'upperroman')[idx]
            elif listid.isdigit():
                start = match[ldepth:match.find('.')]
            elif listid.islower():
                class_ = 'loweralpha'
            elif listid.isupper():
                class_ = 'upperalpha'
        self._set_list_depth(ldepth, type_, class_, start)
        return ''
        
    def _get_list_depth(self):
        """Return the space offset associated to the deepest opened list."""
        return self._list_stack and self._list_stack[-1][1] or 0

    def _set_list_depth(self, depth, new_type, list_class, start):
        def open_list():
            self.close_table()
            self.close_paragraph()
            self.close_indentation() # FIXME: why not lists in quotes?
            self._list_stack.append((new_type, depth))
            self._set_tab(depth)
            class_attr = (list_class and ' class="%s"' % list_class) or ''
            start_attr = (start and ' start="%s"' % start) or ''
            self.out.write('<'+new_type+class_attr+start_attr+'><li>')
        def close_list(tp):
            self._list_stack.pop()
            self.out.write('</li></%s>' % tp)

        # depending on the indent/dedent, open or close lists
        if depth > self._get_list_depth():
            open_list()
        else:
            while self._list_stack:
                deepest_type, deepest_offset = self._list_stack[-1]
                if depth >= deepest_offset:
                    break
                close_list(deepest_type)
            if depth > 0:
                if self._list_stack:
                    old_type, old_offset = self._list_stack[-1]
                    if new_type and old_type != new_type:
                        close_list(old_type)
                        open_list()
                    else:
                        if old_offset != depth: # adjust last depth
                            self._list_stack[-1] = (old_type, depth)
                        self.out.write('</li><li>')
                else:
                    open_list()

    def close_list(self):
        self._set_list_depth(0, None, None, None)

    # Definition Lists

    def _definition_formatter(self, match, fullmatch):
        tmp = self.in_def_list and '</dd>' or '<dl>'
        definition = match[:match.find('::')]
        tmp += '<dt>%s</dt><dd>' % format_to_oneliner(self.env, self.context,
                                                      definition)
        self.in_def_list = True
        return tmp

    def close_def_list(self):
        if self.in_def_list:
            self.out.write('</dd></dl>\n')
        self.in_def_list = False

    # Blockquote

    def _indent_formatter(self, match, fullmatch):
        idepth = len(fullmatch.group('idepth'))
        if self._list_stack:
            ltype, ldepth = self._list_stack[-1]
            if idepth < ldepth:
                for _, ldepth in self._list_stack:
                    if idepth > ldepth:
                        self.in_list_item = True
                        self._set_list_depth(idepth, None, None, None)
                        return ''
            elif idepth <= ldepth + (ltype == 'ol' and 3 or 2):
                self.in_list_item = True
                return ''
        if not self.in_def_list:
            self._set_quote_depth(idepth)
        return ''

    def _citation_formatter(self, match, fullmatch):
        cdepth = len(fullmatch.group('cdepth').replace(' ', ''))
        self._set_quote_depth(cdepth, True)
        return ''

    def close_indentation(self):
        self._set_quote_depth(0)

    def _get_quote_depth(self):
        """Return the space offset associated to the deepest opened quote."""
        return self._quote_stack and self._quote_stack[-1] or 0

    def _set_quote_depth(self, depth, citation=False):
        def open_quote(depth):
            self.close_table()
            self.close_paragraph()
            self.close_list()
            def open_one_quote(d):
                self._quote_stack.append(d)
                self._set_tab(d)
                class_attr = citation and ' class="citation"' or ''
                self.out.write('<blockquote%s>' % class_attr + os.linesep)
            if citation:
                for d in range(quote_depth+1, depth+1):
                    open_one_quote(d)
            else:
                open_one_quote(depth)
        def close_quote():
            self.close_table()
            self.close_paragraph()
            self._quote_stack.pop()
            self.out.write('</blockquote>' + os.linesep)
        quote_depth = self._get_quote_depth()
        if depth > quote_depth:
            self._set_tab(depth)
            tabstops = self._tabstops[::-1]
            while tabstops:
                tab = tabstops.pop()
                if tab > quote_depth:
                    open_quote(tab)
        else:
            while self._quote_stack:
                deepest_offset = self._quote_stack[-1]
                if depth >= deepest_offset:
                    break
                close_quote()
            if not citation and depth > 0:
                if self._quote_stack:
                    old_offset = self._quote_stack[-1]
                    if old_offset != depth: # adjust last depth
                        self._quote_stack[-1] = depth
                else:
                    open_quote(depth)
        if depth > 0:
            self.in_quote = True

    # Table
    
    def _last_table_cell_formatter(self, match, fullmatch):
        return ''

    def _table_cell_formatter(self, match, fullmatch):
        self.open_table()
        self.open_table_row()
        if self.in_table_cell:
            return '</td><td>'
        else:
            self.in_table_cell = 1
            return '<td>'

    def open_table(self):
        if not self.in_table:
            self.close_paragraph()
            self.close_list()
            self.close_def_list()
            self.in_table = 1
            self.out.write('<table class="wiki">' + os.linesep)

    def open_table_row(self):
        if not self.in_table_row:
            self.open_table()
            self.in_table_row = 1
            self.out.write('<tr>')

    def close_table_row(self):
        if self.in_table_row:
            self.in_table_row = 0
            if self.in_table_cell:
                self.in_table_cell = 0
                self.out.write('</td>')

            self.out.write('</tr>')

    def close_table(self):
        if self.in_table:
            self.close_table_row()
            self.out.write('</table>' + os.linesep)
            self.in_table = 0

    # Paragraphs

    def open_paragraph(self):
        if not self.paragraph_open:
            self.out.write('<p>' + os.linesep)
            self.paragraph_open = 1

    def close_paragraph(self):
        if self.paragraph_open:
            while self._open_tags != []:
                self.out.write(self._open_tags.pop()[1])
            self.out.write('</p>' + os.linesep)
            self.paragraph_open = 0

    # Code blocks
    
    def handle_code_block(self, line):
        if line.strip() == WikiParser.STARTBLOCK:
            self.in_code_block += 1
            if self.in_code_block == 1:
                self.code_processor = None
                self.code_buf = []
            else:
                self.code_buf.append(line)
                if not self.code_processor:
                    self.code_processor = WikiProcessor(self, 'default')
        elif line.strip() == WikiParser.ENDBLOCK:
            self.in_code_block -= 1
            if self.in_code_block == 0 and self.code_processor:
                self.close_table()
                self.close_paragraph()
                if self.code_buf:
                    self.code_buf.append('')
                code_text = os.linesep.join(self.code_buf)
                processed = self.code_processor.process(code_text)
                self.out.write(_markup_to_unicode(processed))

            else:
                self.code_buf.append(line)
        elif not self.code_processor:
            match = WikiParser._processor_re.match(line)
            if match:
                name = match.group(1)
                args = WikiParser._processor_param_re.split(line[len(name):])
                del args[::3]
                keys = [str(k) for k in args[::2]] # used as keyword parameters
                values = [v and v[0] in '"\'' and v[1:-1] or v
                          for v in args[1::2]]
                args = dict(zip(keys, values))
                if 'class' not in args:
                    args['class'] = 'wikipage'
                self.code_processor = WikiProcessor(self, name, args)
            else:
                self.code_buf.append(line)
                self.code_processor = WikiProcessor(self, 'default')
        else:
            self.code_buf.append(line)

    def close_code_blocks(self):
        while self.in_code_block > 0:
            self.handle_code_block(WikiParser.ENDBLOCK)

    # -- Wiki engine
    
    def handle_match(self, fullmatch):
        for itype, match in fullmatch.groupdict().items():
            if match and not itype in self.wikiparser.helper_patterns:
                # Check for preceding escape character '!'
                if match[0] == '!':
                    return escape(match[1:])
                if itype in self.wikiparser.external_handlers:
                    external_handler = self.wikiparser.external_handlers[itype]
                    return external_handler(self, match, fullmatch)
                else:
                    internal_handler = getattr(self, '_%s_formatter' % itype)
                    return internal_handler(match, fullmatch)

    def replace(self, fullmatch):
        """Replace one match with its corresponding expansion"""
        replacement = self.handle_match(fullmatch)
        if replacement:
            return _markup_to_unicode(replacement)

    def reset(self, source, out=None):
        self.source = source
        class NullOut(object):
            def write(self, data): pass
        self.out = out or NullOut()
        self._open_tags = []
        self._list_stack = []
        self._quote_stack = []
        self._tabstops = []

        self.in_code_block = 0
        self.in_table = 0
        self.in_def_list = 0
        self.in_table_row = 0
        self.in_table_cell = 0
        self.paragraph_open = 0

    def format(self, text, out=None, escape_newlines=False):
        self.reset(text, out)
        for line in text.splitlines():
            # Handle code block
            if self.in_code_block or line.strip() == WikiParser.STARTBLOCK:
                self.handle_code_block(line)
                continue
            # Handle Horizontal ruler
            elif line[0:4] == '----':
                self.close_table()
                self.close_paragraph()
                self.close_indentation()
                self.close_list()
                self.close_def_list()
                self.out.write('<hr />' + os.linesep)
                continue
            # Handle new paragraph
            elif line == '':
                self.close_paragraph()
                self.close_indentation()
                self.close_list()
                self.close_def_list()
                continue

            # Tab expansion and clear tabstops if no indent
            line = line.replace('\t', ' '*8)
            if not line.startswith(' '):
                self._tabstops = []

            self.in_list_item = False
            self.in_quote = False
            # Throw a bunch of regexps on the problem
            result = re.sub(self.wikiparser.rules, self.replace, line)

            if not self.in_list_item:
                self.close_list()

            if not self.in_quote:
                self.close_indentation()

            if self.in_def_list and not line.startswith(' '):
                self.close_def_list()

            if self.in_table and not line.lstrip().startswith('||'):
                self.close_table()

            sep = os.linesep
            if not(self.in_list_item or self.in_def_list or self.in_table):
                if len(result):
                    self.open_paragraph()
                if escape_newlines and not result.rstrip().endswith('<br />'):
                    sep = '<br />' + sep
            self.out.write(result + sep)
            self.close_table_row()

        self.close_table()
        self.close_paragraph()
        self.close_indentation()
        self.close_list()
        self.close_def_list()
        self.close_code_blocks()


class OneLinerFormatter(Formatter):
    """
    A special version of the wiki formatter that only implement a
    subset of the wiki formatting functions. This version is useful
    for rendering short wiki-formatted messages on a single line
    """
    flavor = 'oneliner'

    def __init__(self, env, context):
        Formatter.__init__(self, env, context)

    # Override a few formatters to disable some wiki syntax in "oneliner"-mode
    def _list_formatter(self, match, fullmatch): return match
    def _indent_formatter(self, match, fullmatch): return match
    def _citation_formatter(self, match, fullmatch):
        return escape(match, False)
    def _heading_formatter(self, match, fullmatch):
        return escape(match, False)
    def _definition_formatter(self, match, fullmatch):
        return escape(match, False)
    def _table_cell_formatter(self, match, fullmatch): return match
    def _last_table_cell_formatter(self, match, fullmatch): return match

    def _macro_formatter(self, match, fullmatch):
        name = fullmatch.group('macroname')
        if name.lower() == 'br':
            return ' '
        elif name == 'comment':
            return ''
        else:
            args = fullmatch.group('macroargs')
            return '[[%s%s]]' % (name,  args and '(...)' or '')

    def format(self, text, out, shorten=False):
        if not text:
            return
        self.reset(text, out)

        # Simplify code blocks
        in_code_block = 0
        processor = None
        buf = StringIO()
        for line in text.strip().splitlines():
            if line.strip() == WikiParser.STARTBLOCK:
                in_code_block += 1
            elif line.strip() == WikiParser.ENDBLOCK:
                if in_code_block:
                    in_code_block -= 1
                    if in_code_block == 0:
                        if processor != 'comment':
                            buf.write(' [...]' + os.linesep)
                        processor = None
            elif in_code_block:
                if not processor:
                    if line.startswith('#!'):
                        processor = line[2:].strip()
            else:
                buf.write(line + os.linesep)
        result = buf.getvalue()[:-len(os.linesep)]

        if shorten:
            result = shorten_line(result)

        result = re.sub(self.wikiparser.rules, self.replace, result)
        result = result.replace('[...]', u'[\u2026]')
        if result.endswith('...'):
            result = result[:-3] + u'\u2026'

        # Close all open 'one line'-tags
        result += self.close_tag(None)
        # Flush unterminated code blocks
        if in_code_block > 0:
            result += u'[\u2026]'
        out.write(result)


class OutlineFormatter(Formatter):
    """Special formatter that generates an outline of all the headings."""
    flavor = 'outline'
    
    def __init__(self, env, context):
        Formatter.__init__(self, env, context)

    # Avoid the possible side-effects of rendering WikiProcessors

    def _macro_formatter(self, match, fullmatch):
        return ''

    def handle_code_block(self, line):
        if line.strip() == WikiParser.STARTBLOCK:
            self.in_code_block += 1
        elif line.strip() == WikiParser.ENDBLOCK:
            self.in_code_block -= 1

    def format(self, text, out, max_depth=6, min_depth=1):
        self.outline = []
        Formatter.format(self, text)

        if min_depth > max_depth:
            min_depth, max_depth = max_depth, min_depth
        max_depth = min(6, max_depth)
        min_depth = max(1, min_depth)

        curr_depth = min_depth - 1
        for depth, anchor, text in self.outline:
            if depth < min_depth or depth > max_depth:
                continue
            if depth < curr_depth:
                out.write('</li></ol>' * (curr_depth - depth))
                out.write("</li><li>\n")
            elif depth > curr_depth:
                out.write('<ol><li>' * (depth - curr_depth))
            else:
                out.write("</li><li>\n")
            curr_depth = depth
            out.write('<a href="#%s">%s</a>' % (anchor, text))
        out.write('</li></ol>' * curr_depth)

    def _heading_formatter(self, match, fullmatch):
        depth, heading, anchor = self._parse_heading(match, fullmatch, True)
        heading = re.sub(r'</?a(?: .*?)?>', '', heading) # Strip out link tags
        self.outline.append((depth, anchor, heading))


class LinkFormatter(OutlineFormatter):
    """Special formatter that focuses on TracLinks."""
    flavor = 'link'
    
    def __init__(self, env, context):
        OutlineFormatter.__init__(self, env, context)

    def _heading_formatter(self, match, fullmatch):
         return ''

    def match(self, wikitext):
        """Return the Wiki match found at the beginning of the `wikitext`"""
        self.reset(wikitext)        
        match = re.match(self.wikiparser.rules, wikitext)
        if match:
            return self.handle_match(match)


# Pure Wiki Formatter

class HtmlFormatter(object):
    """Format parsed wiki text to HTML"""

    flavor = 'default'
    
    def __init__(self, env, context, wikidom):
        self.env = env
        self.context = context
        if isinstance(wikidom, basestring):
            wikidom = WikiParser(env).parse(wikidom)
        self.wikidom = wikidom

    def generate(self, escape_newlines=False):
        """Generate HTML elements.

        newlines in the wikidom will be preserved if `escape_newlines` is set.
        """
        # FIXME: compatibility code only for now
        out = StringIO()
        Formatter(self.env, self.context).format(self.wikidom, out,
                                                 escape_newlines)
        return Markup(out.getvalue())


class InlineHtmlFormatter(object):
    """Format parsed wiki text to inline elements HTML.

    Block level content will be disguarded or compacted.
    """
    
    flavor = 'oneliner'

    def __init__(self, env, context, wikidom):
        self.env = env
        self.context = context
        if isinstance(wikidom, basestring):
            wikidom = WikiParser(env).parse(wikidom)
        self.wikidom = wikidom

    def generate(self, shorten=False):
        """Generate HTML inline elements.

        If `shorten` is set, the generation will stop once enough characters
        have been emitted.
        """
        # FIXME: compatibility code only for now
        out = StringIO()
        OneLinerFormatter(self.env, self.context).format(self.wikidom, out,
                                                         shorten)
        return Markup(out.getvalue())


def format_to(env, flavor, context, wikidom, **options):
    if flavor is None:
        flavor = context.get_hint('wiki_flavor', 'html')
    if flavor == 'oneliner':
        return format_to_oneliner(env, context, wikidom, **options)
    else:
        return format_to_html(env, context, wikidom, **options)

def format_to_html(env, context, wikidom, escape_newlines=None):
    if not wikidom:
        return Markup()
    if escape_newlines is None:
        escape_newlines = context.get_hint('preserve_newlines', False)
    return HtmlFormatter(env, context, wikidom).generate(escape_newlines)

def format_to_oneliner(env, context, wikidom, shorten=None):
    if not wikidom:
        return Markup()
    if shorten is None:
        shorten = context.get_hint('shorten_lines', False)
    return InlineHtmlFormatter(env, context, wikidom).generate(shorten)

def extract_link(env, context, wikidom):
    if not wikidom:
        return Markup()
    return LinkFormatter(env, context).match(wikidom)


# pre-0.11 wiki text to Markup compatibility methods

def wiki_to_html(wikitext, env, req, db=None,
                 absurls=False, escape_newlines=False):
    if not wikitext:
        return Markup()
    abs_ref, href = (req or env).abs_href, (req or env).href
    context = Context.from_request(req, absurls=absurls)
    out = StringIO()
    Formatter(env, context).format(wikitext, out, escape_newlines)
    return Markup(out.getvalue())

def wiki_to_oneliner(wikitext, env, db=None, shorten=False, absurls=False,
                     req=None):
    if not wikitext:
        return Markup()
    abs_ref, href = (req or env).abs_href, (req or env).href
    context = Context.from_request(req, absurls=absurls)
    out = StringIO()
    OneLinerFormatter(env, context).format(wikitext, out, shorten)
    return Markup(out.getvalue())

def wiki_to_outline(wikitext, env, db=None,
                    absurls=False, max_depth=None, min_depth=None):
    if not wikitext:
        return Markup()
    abs_ref, href = (req or env).abs_href, (req or env).href
    context = Context.from_request(req, absurls=absurls)
    out = StringIO()
    OutlineFormatter(env, context).format(wikitext, out, max_depth, min_depth)
    return Markup(out.getvalue())
