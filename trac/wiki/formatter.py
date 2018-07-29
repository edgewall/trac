# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2018 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2004-2005 Christopher Lenz <cmlenz@gmx.de>
# Copyright (C) 2005-2007 Christian Boos <cboos@edgewall.org>
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
#         Christian Boos <cboos@edgewall.org>

import re
import os

from StringIO import StringIO

from genshi.builder import tag, Element
from genshi.core import Stream
from genshi.input import HTMLParser, ParseError
from genshi.util import plaintext

from trac.core import *
from trac.mimeview import *
from trac.resource import get_relative_resource, get_resource_url
from trac.util import arity, as_int
from trac.util.html import Markup, TracHTMLSanitizer, escape, to_fragment
from trac.util.text import exception_to_unicode, shorten_line, to_unicode, \
                           unicode_quote, unquote_label
from trac.util.translation import _, tag_
from trac.wiki.api import WikiSystem, parse_args
from trac.wiki.parser import WikiParser, parse_processor_args

__all__ = ['wiki_to_html', 'wiki_to_oneliner', 'wiki_to_outline',
           'Formatter', 'MacroError', 'ProcessorError', 'format_to',
           'format_to_html', 'format_to_oneliner', 'extract_link',
           'split_url_into_path_query_fragment', 'concat_path_query_fragment']



def system_message(msg, text=None):
    return tag.div(tag.strong(msg), text and tag.pre(text),
                   class_="system-message")


def split_url_into_path_query_fragment(target):
    """Split a target along `?` and `#` in `(path, query, fragment)`.

    >>> split_url_into_path_query_fragment('http://path?a=1&b=2#frag?ment')
    ('http://path', '?a=1&b=2', '#frag?ment')
    >>> split_url_into_path_query_fragment('http://path#frag?ment')
    ('http://path', '', '#frag?ment')
    >>> split_url_into_path_query_fragment('http://path?a=1&b=2')
    ('http://path', '?a=1&b=2', '')
    >>> split_url_into_path_query_fragment('http://path')
    ('http://path', '', '')
    """
    query = fragment = ''
    idx = target.find('#')
    if idx >= 0:
        target, fragment = target[:idx], target[idx:]
    idx = target.find('?')
    if idx >= 0:
        target, query = target[:idx], target[idx:]
    return target, query, fragment


def concat_path_query_fragment(path, query, fragment=None):
    """Assemble `path`, `query` and `fragment` into a proper URL.

    Can be used to re-assemble an URL decomposed using
    `split_url_into_path_query_fragment` after modification.

    >>> concat_path_query_fragment('/wiki/page', '?version=1')
    '/wiki/page?version=1'
    >>> concat_path_query_fragment('/wiki/page#a', '?version=1', '#b')
    '/wiki/page?version=1#b'
    >>> concat_path_query_fragment('/wiki/page?version=1#a', '?format=txt')
    '/wiki/page?version=1&format=txt#a'
    >>> concat_path_query_fragment('/wiki/page?version=1', '&format=txt')
    '/wiki/page?version=1&format=txt'
    >>> concat_path_query_fragment('/wiki/page?version=1', 'format=txt')
    '/wiki/page?version=1&format=txt'
    >>> concat_path_query_fragment('/wiki/page?version=1#a', '?format=txt', '#')
    '/wiki/page?version=1&format=txt'
    """
    p, q, f = split_url_into_path_query_fragment(path)
    if query:
        q += ('&' if q else '?') + query.lstrip('?&')
    if fragment:
        f = fragment
    return p + q + ('' if f == '#' else f)


def _markup_to_unicode(markup):
    stream = None
    if isinstance(markup, Element):
        stream = markup.generate()
    elif isinstance(markup, Stream):
        stream = markup
    if stream:
        markup = stream.render('xhtml', encoding=None, strip_whitespace=False)
    return to_unicode(markup)


class MacroError(TracError):
    """Exception raised on incorrect macro usage.

    The exception is trapped by the wiki formatter and the message is
    rendered in a `pre` tag, wrapped in a div with class `system-message`.

    :since: 1.0.11
    """
    pass


class ProcessorError(TracError):
    """Exception raised on incorrect processor usage.

    The exception is trapped by the wiki formatter and the message is
    rendered in a `pre` tag, wrapped in a div with class `system-message`.

    :since: 0.12
    """
    pass


class WikiProcessor(object):

    _code_block_re = re.compile('^<div(?:\s+class="([^"]+)")?>(.*)</div>$')
    _block_elem_re = re.compile(r'^\s*<(?:div|table)(?:\s+[^>]+)?>',
                                re.I | re.M)

    def __init__(self, formatter, name, args=None):
        """Find the processor by name

        :param formatter: the formatter embedding a call for this processor
        :param name: the name of the processor
        :param args: extra parameters for the processor

        (''since 0.11'')
        """
        self.formatter = formatter
        self.env = formatter.env
        self.name = name
        self.args = args
        self.error = None
        self.macro_provider = None

        # FIXME: move these tables outside of __init__
        builtin_processors = {'html': self._html_processor,
                              'htmlcomment': self._htmlcomment_processor,
                              'default': self._default_processor,
                              'comment': self._comment_processor,
                              'div': self._div_processor,
                              'rtl': self._rtl_processor,
                              'span': self._span_processor,
                              'Span': self._span_processor,
                              'td': self._td_processor,
                              'th': self._th_processor,
                              'tr': self._tr_processor,
                              'table': self._table_processor,
                              }

        self.inline_check = {'html': self._html_is_inline,
                             'htmlcomment': True, 'comment': True,
                             'span': True, 'Span': True,
                             }.get(name)

        self._sanitizer = TracHTMLSanitizer(
            safe_schemes=formatter.wiki.safe_schemes,
            safe_origins=formatter.wiki.safe_origins)

        self.processor = builtin_processors.get(name)
        if not self.processor:
            # Find a matching wiki macro
            for macro_provider in WikiSystem(self.env).macro_providers:
                for macro_name in macro_provider.get_macros() or []:
                    if self.name == macro_name:
                        if hasattr(macro_provider, 'expand_macro'):
                            self.processor = self._macro_processor
                        else:
                            raise TracError(
                                tag_("Pre-0.11 macros with the %(method)s "
                                     "method are no longer supported.",
                                     method=tag.code("render_macro")))
                        self.macro_provider = macro_provider
                        self.inline_check = getattr(macro_provider, 'is_inline',
                                                    False)
                        break
        if not self.processor:
            # Find a matching mimeview renderer
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
            self.error = _("No macro or processor named '%(name)s' found",
                           name=name)

    # inline checks

    def _html_is_inline(self, text):
        if text:
            tag = text[1:].lstrip()
            idx = tag.find(' ')
            if idx > -1:
                tag = tag[:idx]
            return tag.lower() in ('a', 'span', 'bdo', 'img',
                                   'big', 'small', 'font',
                                   'tt', 'i', 'b', 'u', 's', 'strike',
                                   'em', 'strong', 'dfn', 'code', 'q',
                                   'samp', 'kbd', 'var', 'cite', 'abbr',
                                   'acronym', 'sub', 'sup')
    # builtin processors

    def _comment_processor(self, text):
        return ''

    def _default_processor(self, text):
        if self.args and 'lineno' in self.args:
            self.name = \
                Mimeview(self.formatter.env).get_mimetype('text/plain')
            return self._mimeview_processor(text)
        else:
            return tag.pre(text, class_="wiki")

    def _html_processor(self, text):
        if WikiSystem(self.env).render_unsafe_content:
            return Markup(text)
        try:
            stream = Stream(HTMLParser(StringIO(text)))
            return (stream | self._sanitizer).render('xhtml', encoding=None)
        except ParseError as e:
            self.env.log.warn(e)
            line = unicode(text).splitlines()[e.lineno - 1].strip()
            return system_message(_('HTML parsing error: %(message)s',
                                    message=escape(e.msg)), line)

    def _htmlcomment_processor(self, text):
        if "--" in text:
            return system_message(_('Error: Forbidden character sequence '
                                    '"--" in htmlcomment wiki code block'))
        return Markup('<!--\n%s-->\n' % text)

    def _elt_processor(self, eltname, format_to, text):
        # Note: as long as _processor_param_re is not re.UNICODE, **args is OK.
        # Also, parse_args is using strict mode when processing [[span(...)]].
        elt = getattr(tag, eltname)(**(self.args or {}))
        if not WikiSystem(self.env).render_unsafe_content:
            sanitized_elt = getattr(tag, eltname)
            for (k, data, pos) in (Stream(elt) | self._sanitizer):
                sanitized_elt.attrib = data[1]
                break # only look at START (elt,attrs)
            elt = sanitized_elt
        elt.append(format_to(self.env, self.formatter.context, text))
        return elt

    def _div_processor(self, text):
        if not self.args:
            self.args = {}
        self.args.setdefault('class', 'wikipage')
        return self._elt_processor('div', format_to_html, text)

    def _rtl_processor(self, text):
        if not self.args:
            self.args = {}
        self.args['class'] = ('rtl ' + self.args.get('class', '')).rstrip()
        return self._elt_processor('div', format_to_html, text)

    def _span_processor(self, text):
        if self.args is None:
            args, self.args = parse_args(text, strict=True)
            text = ', '.join(args)
        return self._elt_processor('span', format_to_oneliner, text)

    def _td_processor(self, text):
        return self._tablecell_processor('td', text)

    def _th_processor(self, text):
        return self._tablecell_processor('th', text)

    def _tr_processor(self, text):
        try:
            elt = self._elt_processor('tr', self._format_row, text)
            self.formatter.open_table()
            return elt
        except ProcessorError as e:
            return system_message(e)

    def _table_processor(self, text):
        if not self.args:
            self.args = {}
        self.args.setdefault('class', 'wiki')
        try:
            return self._elt_processor('table', self._format_table, text)
        except ProcessorError as e:
            return system_message(e)

    def _tablecell_processor(self, eltname, text):
        self.formatter.open_table_row()
        return self._elt_processor(eltname, format_to_html, text)

    _has_multiple_tables_re = re.compile(r"</table>.*?<table",
                                         re.MULTILINE | re.DOTALL)

    _inner_table_re = re.compile(r"""\s*
      <table[^>]*>\s*
        ((?:<tr[^>]*>)?
          (.*?)
        (?:</tr>)?)\s*
      </table>\s*$
      """, re.MULTILINE | re.DOTALL | re.VERBOSE)

    # Note: the need for "parsing" that crude way the formatted content
    #       will go away as soon as we have a WikiDOM to manipulate...

    def _parse_inner_table(self, text):
        if self._has_multiple_tables_re.search(text):
            raise ProcessorError(_("!#%(name)s must contain at most one table",
                                   name=self.name))
        match = self._inner_table_re.match(text)
        if not match:
            raise ProcessorError(_("!#%(name)s must contain at least one table"
                                   " cell (and table cells only)",
                                   name=self.name))
        return Markup(match.group(1 if self.name == 'table' else 2))

    def _format_row(self, env, context, text):
        if text:
            out = StringIO()
            Formatter(env, context).format(text, out)
            text = self._parse_inner_table(out.getvalue())
        return text

    def _format_table(self, env, context, text):
        if text:
            out = StringIO()
            Formatter(env, context).format(text, out)
            text = self._parse_inner_table(out.getvalue())
        return text

    # generic processors

    def _macro_processor(self, text):
        self.env.log.debug('Executing Wiki macro %s by provider %s',
                           self.name, self.macro_provider)
        if arity(self.macro_provider.expand_macro) == 4:
            return self.macro_provider.expand_macro(self.formatter, self.name,
                                                    text, self.args)
        else:
            return self.macro_provider.expand_macro(self.formatter, self.name,
                                                    text)

    def _mimeview_processor(self, text):
        annotations = []
        context = self.formatter.context.child()
        args = self.args.copy() if self.args else self.args
        if args and 'lineno' in args:
            lineno = as_int(args.pop('lineno'), 1, min=1)
            context.set_hints(lineno=lineno)
            id = str(args.pop('id', '')) or \
                 self.formatter._unique_anchor('a')
            context.set_hints(id=id + '-')
            if 'marks' in args:
                context.set_hints(marks=args.pop('marks'))
            annotations.append('lineno')
        if args:  # Remaining args are assumed to be lexer options
            context.set_hints(lexer_options=args)
        return tag.div(class_='wiki-code')(
            Mimeview(self.env).render(context, self.name, text,
                                      annotations=annotations))
    # TODO: use convert('text/html') instead of render

    def process(self, text, in_paragraph=False):
        if self.error:
            text = system_message(tag_("Error: Failed to load processor "
                                       "%(name)s", name=tag.code(self.name)),
                                  self.error)
        else:
            text = self.processor(text)
        return text or ''

    def is_inline(self, text):
        if callable(self.inline_check):
            return self.inline_check(text)
        else:
            return self.inline_check

    def ensure_inline(self, text, in_paragraph=True):
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
        elif interrupt_paragraph and in_paragraph:
            text = "</p>%s<p>" % _markup_to_unicode(text)
        return text


class Formatter(object):
    """Base Wiki formatter.

    Parses and formats wiki text, in a given `Context`.
    """

    flavor = 'default'

    def __init__(self, env, context):
        self.env = env
        self.context = context.child()
        self.context.set_hints(disable_warnings=True)
        self.req = context.req
        self.href = context.href
        self.resource = context.resource
        self.perm = context.perm
        self.wiki = WikiSystem(self.env)
        self.wikiparser = WikiParser(self.env)
        self._anchors = {}
        self._open_tags = []
        self._safe_schemes = None
        if not self.wiki.render_unsafe_content:
            self._safe_schemes = set(self.wiki.safe_schemes)


    def split_link(self, target):
        return split_url_into_path_query_fragment(target)

    # -- Pre- IWikiSyntaxProvider rules (Font styles)

    _indirect_tags = {
        'MM_BOLD': ('<strong>', '</strong>'),
        'WC_BOLD': ('<strong>', '</strong>'),
        'MM_ITALIC': ('<em>', '</em>'),
        'WC_ITALIC': ('<em>', '</em>'),
        'MM_UNDERLINE': ('<span class="underline">', '</span>'),
        'MM_STRIKE': ('<del>', '</del>'),
        'MM_SUBSCRIPT': ('<sub>', '</sub>'),
        'MM_SUPERSCRIPT': ('<sup>', '</sup>'),
    }

    def _get_open_tag(self, tag):
        """Retrieve opening tag for direct or indirect `tag`."""
        if not isinstance(tag, tuple):
            tag = self._indirect_tags[tag]
        return tag[0]

    def _get_close_tag(self, tag):
        """Retrieve closing tag for direct or indirect `tag`."""
        if not isinstance(tag, tuple):
            tag = self._indirect_tags[tag]
        return tag[1]

    def tag_open_p(self, tag):
        """Do we currently have any open tag with `tag` as end-tag?"""
        return tag in self._open_tags

    def flush_tags(self):
        while self._open_tags != []:
            self.out.write(self._get_close_tag(self._open_tags.pop()))

    def open_tag(self, tag_open, tag_close=None):
        """Open an inline style tag.

        If `tag_close` is not specified, `tag_open` is an indirect tag (0.12)
        """
        if tag_close:
            self._open_tags.append((tag_open, tag_close))
        else:
            self._open_tags.append(tag_open)
            tag_open = self._get_open_tag(tag_open)
        return tag_open

    def close_tag(self, open_tag, close_tag=None):
        """Open a inline style tag.

        If `close_tag` is not specified, it's an indirect tag (0.12)
        """
        tmp = ''
        for i in xrange(len(self._open_tags) - 1, -1, -1):
            tag = self._open_tags[i]
            tmp += self._get_close_tag(tag)
            if (open_tag == tag,
                    (open_tag, close_tag) == tag)[bool(close_tag)]:
                del self._open_tags[i]
                for j in xrange(i, len(self._open_tags)):
                    tmp += self._get_open_tag(self._open_tags[j])
                break
        return tmp

    def _indirect_tag_handler(self, match, tag):
        """Handle binary inline style tags (indirect way, 0.12)"""
        if self._list_stack and not self.in_list_item:
            self.close_list()

        if self.tag_open_p(tag):
            return self.close_tag(tag)
        else:
            return self.open_tag(tag)

    def _bolditalic_formatter(self, match, fullmatch):
        if self._list_stack and not self.in_list_item:
            self.close_list()

        bold_open = self.tag_open_p('MM_BOLD')
        italic_open = self.tag_open_p('MM_ITALIC')
        if bold_open and italic_open:
            bold_idx = self._open_tags.index('MM_BOLD')
            italic_idx = self._open_tags.index('MM_ITALIC')
            if italic_idx < bold_idx:
                close_tags = ('MM_BOLD', 'MM_ITALIC')
            else:
                close_tags = ('MM_ITALIC', 'MM_BOLD')
            open_tags = ()
        elif bold_open:
            close_tags = ('MM_BOLD',)
            open_tags = ('MM_ITALIC',)
        elif italic_open:
            close_tags = ('MM_ITALIC',)
            open_tags = ('MM_BOLD',)
        else:
            close_tags = ()
            open_tags = ('MM_BOLD', 'MM_ITALIC')

        tmp = []
        tmp.extend(self.close_tag(tag) for tag in close_tags)
        tmp.extend(self.open_tag(tag) for tag in open_tags)
        return ''.join(tmp)

    def _bold_formatter(self, match, fullmatch):
        return self._indirect_tag_handler(match, 'MM_BOLD')

    def _bold_wc_formatter(self, match, fullmatch):
        return self._indirect_tag_handler(match, 'WC_BOLD')

    def _italic_formatter(self, match, fullmatch):
        return self._indirect_tag_handler(match, 'MM_ITALIC')

    def _italic_wc_formatter(self, match, fullmatch):
        return self._indirect_tag_handler(match, 'WC_ITALIC')

    def _underline_formatter(self, match, fullmatch):
        return self._indirect_tag_handler(match, 'MM_UNDERLINE')

    def _strike_formatter(self, match, fullmatch):
        return self._indirect_tag_handler(match, 'MM_STRIKE')

    def _subscript_formatter(self, match, fullmatch):
        return self._indirect_tag_handler(match, 'MM_SUBSCRIPT')

    def _superscript_formatter(self, match, fullmatch):
        return self._indirect_tag_handler(match, 'MM_SUPERSCRIPT')

    def _inlinecode_formatter(self, match, fullmatch):
        return tag.code(fullmatch.group('inline'))

    def _inlinecode2_formatter(self, match, fullmatch):
        return tag.code(fullmatch.group('inline2'))

    # pre-0.12 public API (no longer used by Trac itself but kept for plugins)

    def simple_tag_handler(self, match, open_tag, close_tag):
        """Generic handler for simple binary style tags"""
        if self.tag_open_p((open_tag, close_tag)):
            return self.close_tag(open_tag, close_tag)
        else:
            self.open_tag(open_tag, close_tag)
        return open_tag

    # -- Post- IWikiSyntaxProvider rules

    # WikiCreole line breaks

    def _linebreak_wc_formatter(self, match, fullmatch):
        return '<br />'

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
        return "&amp;" if match == "&" else "&lt;" if match == "<" else "&gt;"

    # Short form (shref) and long form (lhref) of TracLinks

    def _shrefbr_formatter(self, match, fullmatch):
        ns = fullmatch.group('snsbr')
        target = unquote_label(fullmatch.group('stgtbr'))
        match = match[1:-1]
        return u'&lt;%s&gt;' % \
                self._make_link(ns, target, match, match, fullmatch)

    def _shref_formatter(self, match, fullmatch):
        ns = fullmatch.group('sns')
        target = unquote_label(fullmatch.group('stgt'))
        return self._make_link(ns, target, match, match, fullmatch)

    def _lhref_formatter(self, match, fullmatch):
        rel = fullmatch.group('rel')
        ns = fullmatch.group('lns')
        target = unquote_label(fullmatch.group('ltgt'))
        label = fullmatch.group('label')
        return self._make_lhref_link(match, fullmatch, rel, ns, target, label)

    def _make_lhref_link(self, match, fullmatch, rel, ns, target, label):
        if not label: # e.g. `[http://target]` or `[wiki:target]`
            if target:
                if ns and target.startswith('//'):     # for `[http://target]`
                    label = ns + ':' + target   #  use `http://target`
                else:                           # for `wiki:target`
                    label = target.lstrip('/')  #  use only `target`
            else: # e.g. `[search:]`
                label = ns
        else:
            label = unquote_label(label)
        if rel:
            if not label:
                label = self.wiki.make_label_from_target(rel)
            path, query, fragment = self.split_link(rel)
            if path.startswith('//'):
                path = '/' + path.lstrip('/')
            elif path.startswith('/'):
                path = self.href + path
            else:
                resource = get_relative_resource(self.resource, path)
                path = get_resource_url(self.env, resource, self.href)
                if resource.id:
                    target = concat_path_query_fragment(unicode(resource.id),
                                                        query, fragment)
                    if resource.realm == 'wiki':
                        target = '/' + target   # Avoid wiki page scoping
                    return self._make_link(resource.realm, target, match,
                                           label, fullmatch)
            return tag.a(label,
                         href=concat_path_query_fragment(path, query, fragment))
        else:
            return self._make_link(ns or 'wiki', target or '', match, label,
                                   fullmatch)

    def _make_link(self, ns, target, match, label, fullmatch):
        # first check for an alias defined in trac.ini
        ns = self.env.config['intertrac'].get(ns, ns)
        if ns in self.wikiparser.link_resolvers:
            resolver = self.wikiparser.link_resolvers[ns]
            if arity(resolver) == 5:
                return resolver(self, ns, target, escape(label, False),
                                fullmatch)
            else:
                return resolver(self, ns, target, escape(label, False))
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
        elif target.startswith('//'):
            if self._safe_schemes is None or ns in self._safe_schemes:
                return self._make_ext_link(ns + ':' + target, label)
            else:
                return escape(match)
        else:
            return self._make_intertrac_link(ns, target, label) or \
                   self._make_interwiki_link(ns, target, label) or \
                   escape(match)

    def _make_intertrac_link(self, ns, target, label):
        res = self.get_intertrac_url(ns, target)
        if res:
            return self._make_ext_link(res[0], label, res[1])

    def get_intertrac_url(self, ns, target):
        intertrac = self.env.config['intertrac']
        url = intertrac.get(ns + '.url')
        if not url and ns == 'trac':
            url = 'http://trac.edgewall.org'
        if url:
            name = intertrac.get(ns + '.title', 'Trac project %s' % ns)
            url = '%s/intertrac/%s' % (url, unicode_quote(target))
            if target:
                title = _('%(target)s in %(name)s', target=target, name=name)
            else:
                title = name
            return (url, title)

    def shorthand_intertrac_helper(self, ns, target, label, fullmatch):
        if fullmatch: # short form
            it_group = fullmatch.groupdict().get('it_' + ns)
            if it_group:
                alias = it_group.strip()
                intertrac = self.env.config['intertrac']
                target = '%s:%s' % (ns, target[len(it_group):])
                return self._make_intertrac_link(intertrac.get(alias, alias),
                                                 target, label) or label

    def _make_interwiki_link(self, ns, target, label):
        from trac.wiki.interwiki import InterWikiMap
        interwiki = InterWikiMap(self.env)
        if ns in interwiki:
            url, title = interwiki.url(ns, target)
            if url:
                return self._make_ext_link(url, label, title)

    def _make_ext_link(self, url, text, title=''):
        local_url = self.env.project_url or self.env.abs_href.base
        if not url.startswith(local_url):
            return tag.a(tag.span(u'\u200b', class_="icon"), text,
                         class_="ext-link", href=url, title=title or None)
        else:
            return tag.a(text, href=url, title=title or None)

    def _make_mail_link(self, url, text, title=''):
        return tag.a(tag.span(u'\u200b', class_="icon"), text,
                     class_="mail-link", href=url, title=title or None)

    # Anchors

    def _anchor_formatter(self, match, fullmatch):
        anchor = fullmatch.group('anchorname')
        label = fullmatch.group('anchorlabel') or ''
        if label:
            label = format_to_oneliner(self.env, self.context, label)
        return '<span class="wikianchor" id="%s">%s</span>' % (anchor, label)

    def _unique_anchor(self, anchor):
        i = 1
        anchor_base = anchor
        while anchor in self._anchors:
            anchor = anchor_base + str(i)
            i += 1
        self._anchors[anchor] = True
        return anchor

    # WikiMacros or WikiCreole links

    def _macrolink_formatter(self, match, fullmatch):
        # check for a known [[macro]]
        macro_or_link = match[2:-2]
        if macro_or_link.startswith('=#'):
            fullmatch = WikiParser._set_anchor_wc_re.match(macro_or_link)
            if fullmatch:
                return self._anchor_formatter(macro_or_link, fullmatch)
        fullmatch = WikiParser._macro_re.match(macro_or_link)
        if fullmatch:
            name = fullmatch.group('macroname')
            args = fullmatch.group('macroargs')
            macro = False # not a macro
            macrolist = name[-1] == '?'
            if name.lower() == 'br' or name == '?':
                macro = None
            else:
                macro = WikiProcessor(self, (name, name[:-1])[macrolist])
                if macro.error:
                    macro = False
            if macro is not False:
                if macrolist:
                    macro = WikiProcessor(self, 'MacroList')
                return self._macro_formatter(match, fullmatch, macro)
        fullmatch = WikiParser._creolelink_re.match(macro_or_link)
        return self._lhref_formatter(match, fullmatch)

    def _macro_formatter(self, match, fullmatch, macro, only_inline=False):
        name = fullmatch.group('macroname')
        if name.lower() == 'br':
            return '<br />'
        if name and name[-1] == '?': # Macro?() shortcut for MacroList(Macro)
            args = name[:-1] or '*'
        else:
            args = fullmatch.group('macroargs')
        in_paragraph = not (getattr(self, 'in_list_item', True) or
                            getattr(self, 'in_table', True) or
                            getattr(self, 'in_def_list', True))
        try:
            return macro.ensure_inline(macro.process(args), in_paragraph)
        except MacroError as e:
            return system_message(_("Macro %(name)s(%(args)s) failed",
                                    name=name, args=args), to_fragment(e))
        except Exception as e:
            self.env.log.error("Macro %s(%s) failed for %s:%s", name,
                               args, self.resource,
                               exception_to_unicode(e, traceback=True))
            return system_message(_("Error: Macro %(name)s(%(args)s) failed",
                                    name=name, args=args), to_fragment(e))

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
        anchor = self._unique_anchor(anchor)
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
        if listid in WikiParser.BULLET_CHARS:
            type_ = 'ul'
        else:
            type_ = 'ol'
            lstart = fullmatch.group('lstart')
            if listid == 'i':
                class_ = 'lowerroman'
            elif listid == 'I':
                class_ = 'upperroman'
            elif listid.isdigit() and lstart != '1':
                start = int(lstart)
            elif listid.islower():
                class_ = 'loweralpha'
                if len(lstart) == 1 and lstart != 'a':
                    start = ord(lstart) - ord('a') + 1
            elif listid.isupper():
                class_ = 'upperalpha'
                if len(lstart) == 1 and lstart != 'A':
                    start = ord(lstart) - ord('A') + 1
        self._set_list_depth(ldepth, type_, class_, start)
        return ''

    def _get_list_depth(self):
        """Return the space offset associated to the deepest opened list."""
        if self._list_stack:
            return self._list_stack[-1][1]
        return -1

    def _set_list_depth(self, depth, new_type=None, lclass=None, start=None):
        def open_list():
            self.close_table()
            self.close_paragraph()
            self.close_indentation() # FIXME: why not lists in quotes?
            self._list_stack.append((new_type, depth))
            self._set_tab(depth)
            class_attr = ' class="%s"' % lclass if lclass else ''
            start_attr = ' start="%s"' % start if start is not None else ''
            self.out.write('<' + new_type + class_attr + start_attr + '><li>')
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
            if new_type and depth >= 0:
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

    def close_list(self, depth=-1):
        self._set_list_depth(depth)

    # Definition Lists

    def _definition_formatter(self, match, fullmatch):
        if self.in_def_list:
            tmp = '</dd>'
        else:
            self.close_paragraph()
            tmp = '<dl class="wiki">'
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
                        self._set_list_depth(idepth)
                        return ''
            elif idepth <= ldepth + (3 if ltype == 'ol' else 2):
                self.in_list_item = True
                return ''
        if not self.in_def_list:
            self._set_quote_depth(idepth)
        return ''

    def close_indentation(self):
        self._set_quote_depth(0)

    def _get_quote_depth(self):
        """Return the space offset associated to the deepest opened quote."""
        return self._quote_stack[-1] if self._quote_stack else 0

    def _set_quote_depth(self, depth, citation=False):
        def open_quote(depth):
            self.close_table()
            self.close_paragraph()
            self.close_list()
            def open_one_quote(d):
                self._quote_stack.append(d)
                self._set_tab(d)
                class_attr = ' class="citation"' if citation else ''
                self.out.write('<blockquote%s>\n' % class_attr)
            if citation:
                for d in range(quote_depth+1, depth+1):
                    open_one_quote(d)
            else:
                open_one_quote(depth)
        def close_quote():
            self.close_table()
            self.close_paragraph()
            self._quote_stack.pop()
            self.out.write('</blockquote>\n')
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
        colspan = numpipes / 2
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
            self.out.write('<table class="wiki">\n')

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
            self.out.write('</table>\n')
            self.in_table = 0

    # Paragraphs

    def open_paragraph(self):
        if not self.paragraph_open:
            self.out.write('<p>\n')
            self.paragraph_open = 1

    def close_paragraph(self):
        self.flush_tags()
        if self.paragraph_open:
            self.out.write('</p>\n')
            self.paragraph_open = 0

    # Code blocks

    def parse_processor_args(self, line):
        return parse_processor_args(line)

    def handle_code_block(self, line, startmatch=None):
        if startmatch:
            self.in_code_block += 1
            if self.in_code_block == 1:
                name = startmatch.group(2)
                if name:
                    args = parse_processor_args(line[startmatch.end():])
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
                    if self.code_prefix and all(not l or
                                                l.startswith(self.code_prefix)
                                                for l in self.code_buf):
                        code_indent = len(self.code_prefix)
                        self.code_buf = [l[code_indent:]
                                         for l in self.code_buf]
                    self.code_buf.append('')
                code_text = '\n'.join(self.code_buf)
                processed = self._exec_processor(self.code_processor,
                                                 code_text)
                self.out.write(_markup_to_unicode(processed))
            else:
                self.code_buf.append(line)
        elif not self.code_processor:
            match = WikiParser._processor_re.match(line)
            if match:
                self.code_prefix = match.group(1)
                name = match.group(2)
                args = parse_processor_args(line[match.end():])
                self.code_processor = WikiProcessor(self, name, args)
            else:
                self.code_buf.append(line)
                self.code_processor = WikiProcessor(self, 'default')
        else:
            self.code_buf.append(line)

    def close_code_blocks(self):
        while self.in_code_block > 0:
            self.handle_code_block(WikiParser.ENDBLOCK)

    def _exec_processor(self, processor, text):
        try:
            return processor.process(text)
        except ProcessorError as e:
            return system_message(_("Processor %(name)s failed",
                                    name=processor.name), to_fragment(e))
        except Exception as e:
            self.env.log.error("Processor %s failed for %s:%s",
                               processor.name, self.resource,
                               exception_to_unicode(e, traceback=True))
            return system_message(_("Error: Processor %(name)s failed",
                                    name=processor.name), to_fragment(e))

    # > quotes

    def handle_quote_block(self, line):
        self.close_paragraph()
        depth = line.find('>')
        # Close lists up to current level:
        #
        #  - first level item
        #    - second level item
        #    > citation part of first level item
        #
        #  (depth == 3, _list_stack == [1, 3])
        if not self._quote_buffer and depth < self._get_list_depth():
            self.close_list(depth)
        self._quote_buffer.append(line[depth + 1:])

    def close_quote_block(self, escape_newlines):
        if self._quote_buffer:
            # avoid an extra <blockquote> when there's consistently one space
            # after the '>'
            if all(not line or line[0] in '> ' for line in self._quote_buffer):
                self._quote_buffer = [line[bool(line and line[0] == ' '):]
                                      for line in self._quote_buffer]
            self.out.write('<blockquote class="citation">\n')
            Formatter(self.env, self.context).format(self._quote_buffer,
                                                     self.out, escape_newlines)
            self.out.write('</blockquote>\n')
            self._quote_buffer = []

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

    _normalize_re = re.compile(r'[\v\f]', re.UNICODE)

    def reset(self, source, out=None):
        if isinstance(source, basestring):
            source = re.sub(self._normalize_re, ' ', source)
        self.source = source
        class NullOut(object):
            def write(self, data):
                pass
        self.out = out or NullOut()
        self._open_tags = []
        self._list_stack = []
        self._quote_stack = []
        self._tabstops = []
        self._quote_buffer = []

        self.in_code_block = 0
        self.in_table = 0
        self.in_def_list = 0
        self.in_table_row = 0
        self.continue_table = 0
        self.continue_table_row = 0
        self.in_table_cell = ''
        self.paragraph_open = 0
        return source

    def format(self, text, out=None, escape_newlines=False):
        text = self.reset(text, out)
        if isinstance(text, basestring):
            text = text.splitlines()

        for line in text:
            # Detect start of code block (new block or embedded block)
            block_start_match = None
            if WikiParser.ENDBLOCK not in line:
                block_start_match = WikiParser._startblock_re.match(line)
            # Handle content or end of code block
            if self.in_code_block:
                self.handle_code_block(line, block_start_match)
                continue
            # Handle citation quotes '> ...'
            if line.strip().startswith('>'):
                self.handle_quote_block(line)
                continue
            # Handle end of citation quotes
            self.close_quote_block(escape_newlines)
            # Handle start of a new block
            if block_start_match:
                self.handle_code_block(line, block_start_match)
                continue
            # Handle Horizontal ruler
            if line[0:4] == '----':
                self.close_table()
                self.close_paragraph()
                self.close_indentation()
                self.close_list()
                self.close_def_list()
                self.out.write('<hr />\n')
                continue
            # Handle new paragraph
            if line == '':
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

            # Handle end of indentation
            if not line.startswith(' ') and self._quote_stack:
                self.close_indentation()

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

            sep = '\n'
            if not(self.in_list_item or self.in_def_list or self.in_table):
                if len(result):
                    self.open_paragraph()
                if escape_newlines and self.paragraph_open and \
                       not result.rstrip().endswith('<br />'):
                    sep = '<br />' + sep
            self.out.write(result + sep)
            self.close_table_row()

        self.close_code_blocks()
        self.close_quote_block(escape_newlines)
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

    def _linebreak_wc_formatter(self, match, fullmatch):
        return ' '

    def _macro_formatter(self, match, fullmatch, macro):
        name = fullmatch.group('macroname')
        if name.lower() == 'br':
            return ' '
        args = fullmatch.group('macroargs')
        if macro.is_inline(args):
            return Formatter._macro_formatter(self, match, fullmatch, macro)
        else:
            return '[[%s%s]]' % (name, '(...)' if args else '')

    def format(self, text, out, shorten=False):
        if not text:
            return
        text = self.reset(text, out)

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
                            buf.write(' [...]\n')
                        processor = None
            elif in_code_block:
                if not processor:
                    if line.startswith('#!'):
                        processor = line[2:].strip()
            else:
                buf.write(line + '\n')
        result = buf.getvalue()[:-len('\n')]

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

    # Avoid the possible side-effects of rendering WikiProcessors
    def _macro_formatter(self, match, fullmatch, macro):
        name = fullmatch.group('macroname')
        if name.lower() == 'br':
            return ' '
        args = fullmatch.group('macroargs')
        if macro.is_inline(args):
            return Formatter._macro_formatter(self, match, fullmatch, macro)
        return ''

    def handle_code_block(self, line, startmatch=None):
        if WikiParser.ENDBLOCK not in line and \
               WikiParser._startblock_re.match(line):
            self.in_code_block += 1
        elif line.strip() == WikiParser.ENDBLOCK:
            self.in_code_block -= 1

    def format(self, text, out, max_depth=6, min_depth=1, shorten=True):
        self.shorten = shorten
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
        depth, heading, anchor = self._parse_heading(match, fullmatch,
                                                     self.shorten)
        heading = re.sub(r'</?a(?: .*?)?>', '', heading) # Strip out link tags
        self.outline.append((depth, anchor, heading))


class LinkFormatter(OutlineFormatter):
    """Special formatter that focuses on TracLinks."""
    flavor = 'link'

    def _heading_formatter(self, match, fullmatch):
        return ''

    def match(self, wikitext):
        """Return the Wiki match found at the beginning of the `wikitext`"""
        wikitext = self.reset(wikitext)
        self.line = wikitext
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

    Block level content will be discarded or compacted.
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
    """deprecated in favor of format_to_html (will be removed in 1.0)"""
    if not wikitext:
        return Markup()
    abs_ref, href = (req or env).abs_href, (req or env).href
    from trac.web.chrome import web_context
    context = web_context(req, absurls=absurls)
    out = StringIO()
    Formatter(env, context).format(wikitext, out, escape_newlines)
    return Markup(out.getvalue())

def wiki_to_oneliner(wikitext, env, db=None, shorten=False, absurls=False,
                     req=None):
    """:deprecated: in favor of format_to_oneliner (will be removed in 1.0)"""
    if not wikitext:
        return Markup()
    abs_ref, href = (req or env).abs_href, (req or env).href
    from trac.web.chrome import web_context
    context = web_context(req, absurls=absurls)
    out = StringIO()
    OneLinerFormatter(env, context).format(wikitext, out, shorten)
    return Markup(out.getvalue())

def wiki_to_outline(wikitext, env, db=None,
                    absurls=False, max_depth=None, min_depth=None, req=None):
    """:deprecated: will be removed in 1.0 and replaced by something else"""
    if not wikitext:
        return Markup()
    abs_ref, href = (req or env).abs_href, (req or env).href
    from trac.web.chrome import web_context
    context = web_context(req, absurls=absurls)
    out = StringIO()
    OutlineFormatter(env, context).format(wikitext, out, max_depth, min_depth)
    return Markup(out.getvalue())
