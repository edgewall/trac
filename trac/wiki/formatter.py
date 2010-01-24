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

from StringIO import StringIO

from genshi.builder import tag, Element
from genshi.core import Stream, Markup, escape
from genshi.input import HTMLParser, ParseError
from genshi.util import plaintext

from trac.core import *
from trac.mimeview import *
from trac.resource import get_relative_resource, get_resource_url
from trac.wiki.api import WikiSystem, parse_args
from trac.wiki.parser import WikiParser
from trac.util import arity
from trac.util.compat import all
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
                              'htmlcomment': self._htmlcomment_processor,
                              'default': self._default_processor,
                              'comment': self._comment_processor,
                              'div': self._div_processor,
                              'span': self._span_processor,
                              'Span': self._span_processor,
                              'td': self._td_processor,
                              'th': self._th_processor,
                              'tr': self._tr_processor,
                              }

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
            mimeview = Mimeview(formatter.env)
            for renderer in mimeview.renderers:
                if renderer.get_quality_ratio(self.name) > 1:
                    self.processor = self._mimeview_processor
                    break
            if not self.processor:
                mimetype = mimeview.get_mimetype(self.name)
                if mimetype:
                    self.name = mimetype
                    self.processor = self._mimeview_processor
        if not self.processor:
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
        
    def _htmlcomment_processor(self, text):
        if "--" in text:
            return system_message(_('Error: Forbidden character sequence '
                                    '"--" in htmlcomment wiki code block'))
        return Markup('<!--\n%s-->\n' % text)
        
    def _elt_processor(self, eltname, format_to, text, args):
        # Note: as long as _processor_param_re is not re.UNICODE, **args is OK
        elt = getattr(tag, eltname)(**args)
        if not WikiSystem(self.env).render_unsafe_content:
            sanitized_elt = getattr(tag, eltname)
            for (k, data, pos) in (Stream(elt) | self._sanitizer):
                sanitized_elt.attrib = data[1]
                break # only look at START (elt,attrs)
            elt = sanitized_elt
        elt.append(format_to(self.env, self.formatter.context, text))
        return elt

    def _div_processor(self, text):
        if 'class' not in self.args:
            self.args['class'] = 'wikipage'
        return self._elt_processor('div', format_to_html, text, self.args)
    
    def _span_processor(self, text):
        args, kwargs = parse_args(text, strict=True)
        return self._elt_processor('span', format_to_oneliner, ', '.join(args),
                                   kwargs)

    def _td_processor(self, text):
        return self._tablecell_processor('td', text)
    
    def _th_processor(self, text):
        return self._tablecell_processor('th', text)
    
    def _tr_processor(self, text):
        self.formatter.open_table()
        return self._elt_processor('tr', self._format_row, text, self.args)
    
    def _tablecell_processor(self, eltname, text):
        self.formatter.open_table_row()
        return self._elt_processor(eltname, format_to_html, text, self.args)

    def _format_row(self, env, context, text):
        if text:
            row_formatter = Formatter(env, context)
            out = StringIO()
            row_formatter.format(text, out)
            text = out.getvalue()
            # we must deal with either \n or \r\n as element separators:
            #  len('<table class="wiki">') == 20
            inner_tr_start = text.find('>', 20) + 1
            #  len('</tr></table>\r\n') == 15
            inner_tr_end = text.find('<', len(text) - 15)
            text = Markup(text[inner_tr_start:inner_tr_end])
        return text
    
    # generic processors

    def _legacy_macro_processor(self, text): # TODO: remove in 0.12
        self.env.log.warning('Executing pre-0.11 Wiki macro %s by provider %s'
                             % (self.name, self.macro_provider))
        return self.macro_provider.render_macro(self.formatter.req, self.name,
                                                text)

    def _macro_processor(self, text):
        self.env.log.debug('Executing Wiki macro %s by provider %s'
                           % (self.name, self.macro_provider))
        if arity(self.macro_provider.expand_macro) == 5:
            return self.macro_provider.expand_macro(self.formatter, self.name,
                                                    text, self.args)
        else:
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
                text = _markup_to_unicode(text)
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
                text = "</p>%s<p>" % _markup_to_unicode(text)
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

    def flush_tags(self):
        while self._open_tags != []:
            self.out.write(self._open_tags.pop()[1])


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

    def _shrefbr_formatter(self, match, fullmatch):
        ns = fullmatch.group('snsbr')
        target = self._unquote(fullmatch.group('stgtbr'))
        match = match[1:-1]
        return '&lt;%s&gt;' % \
                self._make_link(ns, target, match, match, fullmatch)

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
                if target.startswith('//'):     # for `[http://target]`
                    label = ns+':'+target       #  use `http://target`
                else:                           # for `wiki:target`
                    label = target.lstrip('/')  #  use only `target`
            else: # e.g. `[search:]` 
                label = ns
        else:
            label = self._unquote(label)
        if rel:
            if not label:
                label = rel
                while label.startswith('./') or label.startswith('../'):
                    label = label.split('/', 1)[1]
            path, query, fragment = self.split_link(rel)
            if path.startswith('//'):
                path = '/' + path.lstrip('/')
            elif path.startswith('/'):
                path = self.href + path
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
                    if resource.realm == 'wiki':
                        target = '/' + target   # Avoid wiki page scoping
                    return self._make_link(resource.realm, target, match,
                                           label, fullmatch)
                if '?' in path and query:
                    query = '&' + query.lstrip('?')
            return tag.a(label, href=path + query + fragment)
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
            chrome = Chrome(self.env)
            if chrome.never_obfuscate_mailto:
                otarget, olabel = target, label
            else:
                otarget = chrome.format_emails(self.context, target)
                olabel = chrome.format_emails(self.context, label)
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
        local_url = self.env.project_url or \
                    (self.req or self.env).abs_href.base
        if not url.startswith(local_url):
            return tag.a(tag.span(u'\xa0', class_="icon"), text,
                          class_="ext-link", href=url, title=title or None)
        else:
            return tag.a(text, href=url, title=title or None)

    def _make_mail_link(self, url, text, title=''):
        return tag.a(tag.span(u'\xa0', class_="icon"), text,
                      class_="mail-link", href=url, title=title or None)

    # Anchors
    
    def _anchor_formatter(self, match, fullmatch):
        anchor = fullmatch.group('anchorname')
        label = fullmatch.group('anchorlabel') or ''
        if label:
            label = format_to_oneliner(self.env, self.context, label)
        return '<span class="wikianchor" id="%s">%s</span>' % (anchor, label)

    # WikiMacros
    
    def _macro_formatter(self, match, fullmatch):
        name = fullmatch.group('macroname')
        if name.lower() == 'br':
            return '<br />'
        if name and name[-1] == '?': # Macro?() shortcut for MacroList(Macro)
            args = name[:-1] or '*'
            name = 'MacroList'
        else:
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

        hdepth = fullmatch.group('hdepth')
        depth = len(hdepth)
        anchor = fullmatch.group('hanchor') or ''
        htext = fullmatch.group('htext').strip()
        if htext.endswith(hdepth):
            htext = htext[:-depth]
        heading = format_to_oneliner(self.env, self.context, htext, False)
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
            heading = format_to_oneliner(self.env, self.context, htext, True)
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
            if idx > -1:
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
        if self._list_stack:
            return self._list_stack[-1][1]
        return -1

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
        def close_item():
            self.flush_tags()
            self.out.write('</li>')
        def close_list(tp):
            self._list_stack.pop()
            close_item()
            self.out.write('</%s>' % tp)

        # depending on the indent/dedent, open or close lists
        if depth > self._get_list_depth():
            open_list()
        else:
            while self._list_stack:
                deepest_type, deepest_offset = self._list_stack[-1]
                if depth >= deepest_offset:
                    break
                close_list(deepest_type)
            if depth >= 0:
                if self._list_stack:
                    old_type, old_offset = self._list_stack[-1]
                    if new_type and old_type != new_type:
                        close_list(old_type)
                        open_list()
                    else:
                        if old_offset != depth: # adjust last depth
                            self._list_stack[-1] = (old_type, depth)
                        close_item()
                        self.out.write('<li>')
                else:
                    open_list()

    def close_list(self):
        self._set_list_depth(-1, None, None, None)

    # Definition Lists

    def _definition_formatter(self, match, fullmatch):
        tmp = self.in_def_list and '</dd>' or '<dl class="wiki">'
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
    
    def _table_cell_formatter(self, match, fullmatch):
        self.open_table()
        self.open_table_row()
        self.continue_table = 1
        separator = fullmatch.group('table_cell_sep')
        is_last = fullmatch.group('table_cell_last')
        numpipes = len(separator)
        cell = 'td'
        if separator[0] == '=':
            numpipes -= 1
        if separator[-1] == '=':
            numpipes -= 1
            cell = 'th'
        colspan = numpipes/2
        if is_last is not None:
            if is_last and is_last[-1] == '\\':
                self.continue_table_row = 1
            colspan -= 1
            if not colspan:
                return ''
        attrs = ''
        if colspan > 1:
            attrs = ' colspan="%d"' % int(colspan)
        # alignment: ||left || right||default|| default ||  center  ||
        after_sep = fullmatch.end('table_cell_sep')
        alignleft = after_sep < len(self.line) and self.line[after_sep] != ' '
        # lookahead next || (FIXME: this fails on ` || ` inside the cell)
        next_sep = re.search(r'([^!])=?\|\|', self.line[after_sep:])
        alignright = next_sep and next_sep.group(1) != ' '
        textalign = None
        if alignleft:
            if not alignright:
                textalign = 'left'
        elif alignright:
            textalign = 'right'
        elif next_sep: # check for the extra spaces specifying a center align
            first_extra = after_sep + 1
            last_extra = after_sep + next_sep.start() - 1
            if first_extra < last_extra and \
                   self.line[first_extra] == self.line[last_extra] == ' ':
                textalign = 'center'                
        if textalign:
            attrs += ' style="text-align: %s"' % textalign
        td = '<%s%s>' % (cell, attrs)
        if self.in_table_cell:
            td = '</%s>' % self.in_table_cell + td
        self.in_table_cell = cell
        return td

    def _table_row_sep_formatter(self, match, fullmatch):
        self.open_table()
        self.close_table_row(force=True)
        params = fullmatch.group('table_row_params')
        if params:
            tr = WikiProcessor(self, 'tr', self.parse_processor_args(params))
            processed = _markup_to_unicode(tr.process(''))
            params = processed[3:processed.find('>')]
        self.open_table_row(params or '')
        self.continue_table = 1
        self.continue_table_row = 1

    def open_table(self):
        if not self.in_table:
            self.close_paragraph()
            self.close_list()
            self.close_def_list()
            self.in_table = 1
            self.out.write('<table class="wiki">' + os.linesep)

    def open_table_row(self, params=''):
        if not self.in_table_row:
            self.open_table()
            self.in_table_row = 1
            self.out.write('<tr%s>' % params)

    def close_table_row(self, force=False):
        if self.in_table_row and (not self.continue_table_row or force):
            self.in_table_row = 0
            if self.in_table_cell:
                self.out.write('</%s>' % self.in_table_cell)
                self.in_table_cell = ''
            self.out.write('</tr>')
        self.continue_table_row = 0

    def close_table(self):
        if self.in_table:
            self.close_table_row(force=True)
            self.out.write('</table>' + os.linesep)
            self.in_table = 0

    # Paragraphs

    def open_paragraph(self):
        if not self.paragraph_open:
            self.out.write('<p>' + os.linesep)
            self.paragraph_open = 1

    def close_paragraph(self):
        self.flush_tags()
        if self.paragraph_open:
            self.out.write('</p>' + os.linesep)
            self.paragraph_open = 0

    # Code blocks

    def parse_processor_args(self, line):
        args = WikiParser._processor_param_re.split(line)
        del args[::3]
        keys = [str(k) for k in args[::2]] # used as keyword parameters
        values = [(v and v[0] in '"\'' and [v[1:-1]] or [v])[0]
                  for v in args[1::2]]
        return dict(zip(keys, values))

    def handle_code_block(self, line, startmatch=None):
        if startmatch:
            self.in_code_block += 1
            if self.in_code_block == 1:
                name = startmatch.group(2)
                if name:
                    args = self.parse_processor_args(line[startmatch.end():])
                    self.code_processor = WikiProcessor(self, name, args)
                else:
                    self.code_processor = None
                self.code_buf = []
                self.code_prefix = line[:line.find(WikiParser.STARTBLOCK)]
            else:
                self.code_buf.append(line)
                if not self.code_processor:
                    self.code_processor = WikiProcessor(self, 'default')
        elif line.strip() == WikiParser.ENDBLOCK:
            self.in_code_block -= 1
            if self.in_code_block == 0 and self.code_processor:
                if self.code_processor.name not in ('th', 'td', 'tr'):
                    self.close_table()
                self.close_paragraph()
                if self.code_buf:
                    if self.code_prefix and all(l.startswith(self.code_prefix)
                                                for l in self.code_buf):
                        code_indent = len(self.code_prefix)
                        self.code_buf = [l[code_indent:]
                                         for l in self.code_buf]
                    self.code_buf.append('')
                code_text = os.linesep.join(self.code_buf)
                processed = self.code_processor.process(code_text)
                self.out.write(_markup_to_unicode(processed))
            else:
                self.code_buf.append(line)
        elif not self.code_processor:
            match = WikiParser._processor_re.match(line)
            if match:
                self.code_prefix = match.group(1)
                name = match.group(2)
                args = self.parse_processor_args(line[match.end():])
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
            def write(self, data):
                pass
        self.out = out or NullOut()
        self._open_tags = []
        self._list_stack = []
        self._quote_stack = []
        self._tabstops = []

        self.in_code_block = 0
        self.in_table = 0
        self.in_def_list = 0
        self.in_table_row = 0
        self.continue_table = 0
        self.continue_table_row = 0
        self.in_table_cell = ''
        self.paragraph_open = 0

    def format(self, text, out=None, escape_newlines=False):
        self.reset(text, out)
        for line in text.splitlines():
            # Handle code block
            if self.in_code_block or WikiParser.ENDBLOCK not in line:
                match = WikiParser._startblock_re.match(line)
                if match or self.in_code_block:
                    self.handle_code_block(line, match)
                    continue
            # Handle Horizontal ruler
            if line[0:4] == '----':
                self.close_table()
                self.close_paragraph()
                self.close_indentation()
                self.close_list()
                self.close_def_list()
                self.out.write('<hr />' + os.linesep)
                continue
            # Handle new paragraph
            elif line == '':
                self.close_table()
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
            self.line = line
            result = re.sub(self.wikiparser.rules, self.replace, line)

            if not self.in_list_item:
                self.close_list()

            if not self.in_quote:
                self.close_indentation()

            if self.in_def_list and not line.startswith(' '):
                self.close_def_list()

            if self.in_table and not self.continue_table:
                self.close_table()
            self.continue_table = 0

            sep = os.linesep
            if not(self.in_list_item or self.in_def_list or self.in_table):
                if len(result):
                    self.open_paragraph()
                if escape_newlines and not result.rstrip().endswith('<br />'):
                    sep = '<br />' + sep
            self.out.write(result + sep)
            self.close_table_row()

        self.close_code_blocks()
        self.close_table()
        self.close_paragraph()
        self.close_indentation()
        self.close_list()
        self.close_def_list()


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
    def _list_formatter(self, match, fullmatch):
        return match
    def _indent_formatter(self, match, fullmatch):
        return match
    def _citation_formatter(self, match, fullmatch):
        return escape(match, False)
    def _heading_formatter(self, match, fullmatch):
        return escape(match, False)
    def _definition_formatter(self, match, fullmatch):
        return escape(match, False)
    def _table_cell_formatter(self, match, fullmatch):
        return match
    def _table_row_sep_formatter(self, match, fullmatch):
        return ''

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
            if WikiParser.ENDBLOCK not in line and \
                   WikiParser._startblock_re.match(line):
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

        self.out.write(result)
        # Close all open 'one line'-tags
        self.flush_tags()
        # Flush unterminated code blocks
        if in_code_block > 0:
            self.out.write(u'[\u2026]')


class OutlineFormatter(Formatter):
    """Special formatter that generates an outline of all the headings."""
    flavor = 'outline'
    
    def __init__(self, env, context):
        Formatter.__init__(self, env, context)

    # Avoid the possible side-effects of rendering WikiProcessors

    def _macro_formatter(self, match, fullmatch):
        return ''

    def handle_code_block(self, line):
        if WikiParser.ENDBLOCK not in line and \
               WikiParser._startblock_re.match(line):
            self.in_code_block += 1
        elif line.strip() == WikiParser.ENDBLOCK:
            self.in_code_block -= 1

    def format(self, text, out, max_depth=6, min_depth=1):
        whitespace_indent = '  '
        self.outline = []
        Formatter.format(self, text)

        if min_depth > max_depth:
            min_depth, max_depth = max_depth, min_depth
        max_depth = min(6, max_depth)
        min_depth = max(1, min_depth)

        curr_depth = min_depth - 1
        out.write('\n')
        for depth, anchor, text in self.outline:
            if depth < min_depth or depth > max_depth:
                continue
            if depth > curr_depth: # Deeper indent
                for i in range(curr_depth, depth):
                    out.write(whitespace_indent * (2*i) + '<ol>\n' +
                              whitespace_indent * (2*i+1) + '<li>\n')
            elif depth < curr_depth: # Shallower indent
                for i in range(curr_depth-1, depth-1, -1):
                    out.write(whitespace_indent * (2*i+1) + '</li>\n' +
                              whitespace_indent * (2*i) + '</ol>\n')
                out.write(whitespace_indent * (2*depth-1) + '</li>\n' +
                          whitespace_indent * (2*depth-1) + '<li>\n')
            else: # Same indent
                out.write( whitespace_indent * (2*depth-1) + '</li>\n' +
                           whitespace_indent * (2*depth-1) + '<li>\n')
            curr_depth = depth
            out.write(whitespace_indent * (2*depth) +
                      '<a href="#%s">%s</a>\n' % (anchor, text))
        # Close out all indentation
        for i in range(curr_depth-1, min_depth-2, -1):
            out.write(whitespace_indent * (2*i+1) + '</li>\n' +
                      whitespace_indent * (2*i) + '</ol>\n')

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
