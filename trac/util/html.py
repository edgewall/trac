# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2006 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For exact contribution history, see the revision
# history and logs, available at http://projects.edgewall.com/trac/.

import htmlentitydefs
from HTMLParser import HTMLParser, HTMLParseError
import re
try:
    frozenset
except NameError:
    from sets import ImmutableSet as frozenset
from StringIO import StringIO


class Markup(str):
    """Marks a string as being safe for inclusion in XML output without needing
    to be escaped.
    
    Strings are normally automatically escaped when added to the HDF.
    `Markup`-strings are however an exception. Use with care.
    
    (since Trac 0.9.3)
    """
    def __new__(self, text='', *args):
        if args:
            text %= tuple([escape(arg) for arg in args])
        return str.__new__(self, text)

    def __add__(self, other):
        return Markup(str(self) + Markup.escape(other))

    def __mul__(self, num):
        return Markup(str(self) * num)

    def join(self, seq):
        return Markup(str(self).join([Markup.escape(item) for item in seq]))

    def stripentities(self, keepxmlentities=False):
        """Return a copy of the text with any character or numeric entities
        replaced by the equivalent UTF-8 characters.
        
        If the `keepxmlentities` parameter is provided and evaluates to `True`,
        the core XML entities (&amp;, &apos;, &gt;, &lt; and &quot;).
        
        (Since Trac 0.10)
        """
        def _replace_entity(match):
            if match.group(1): # numeric entity
                ref = match.group(1)
                if ref.startswith('x'):
                    ref = int(ref[1:], 16)
                else:
                    ref = int(ref, 10)
                return unichr(ref).encode('utf-8')
            else: # character entity
                ref = match.group(2)
                if keepxmlentities and ref in ('amp', 'apos', 'gt', 'lt', 'quot'):
                    return '&%s;' % ref
                try:
                    codepoint = htmlentitydefs.name2codepoint[ref]
                    return unichr(codepoint).encode('utf-8')
                except KeyError:
                    if keepxmlentities:
                        return '&amp;%s;' % ref
                    else:
                        return ref
        return Markup(re.sub(r'&(?:#((?:\d+)|(?:[xX][0-9a-fA-F]+));?|(\w+);)',
                             _replace_entity, self))

    def striptags(self):
        """Return a copy of the text with all XML/HTML tags removed."""
        return Markup(re.sub(r'<[^>]*?>', '', self))

    def escape(cls, text, quotes=True):
        """Create a Markup instance from a string and escape special characters
        it may contain (<, >, & and ").
        
        If the `quotes` parameter is set to `False`, the " character is left as
        is. Escaping quotes is generally only required for strings that are to
        be used in attribute values.
        """
        if isinstance(text, cls):
            return text
        if not text:
            return cls()
        text = str(text).replace('&', '&amp;') \
                        .replace('<', '&lt;') \
                        .replace('>', '&gt;')
        if quotes:
            text = text.replace('"', '&#34;')
        return cls(text)
    escape = classmethod(escape)

    def unescape(self):
        """Reverse-escapes &, <, > and " and returns a `str`."""
        if not self:
            return ''
        return str(self).replace('&#34;', '"') \
                        .replace('&gt;', '>') \
                        .replace('&lt;', '<') \
                        .replace('&amp;', '&')

    def plaintext(self, keeplinebreaks=True):
        """Returns the text as a `str`with all entities and tags removed."""
        text = self.striptags().stripentities()
        if not keeplinebreaks:
            text = text.replace('\n', ' ')
        return text

    def sanitize(self):
        """Parse the text as HTML and return a cleaned up XHTML representation.
        
        This will remove any javascript code or other potentially dangerous
        elements.
        
        If the HTML cannot be parsed, an `HTMLParseError` will be raised by the
        underlying `HTMLParser` module, which should be handled by the caller of
        this function.
        """
        buf = StringIO()
        sanitizer = Sanitizer(buf)
        sanitizer.feed(self.stripentities(keepxmlentities=True))
        return Markup(buf.getvalue())


escape = Markup.escape

def unescape(text):
    """Reverse-escapes &, <, > and \"."""
    if not isinstance(text, Markup):
        return text
    return text.unescape()


class Deuglifier(object):

    def __new__(cls):
        self = object.__new__(cls)
        if not hasattr(cls, '_compiled_rules'):
            cls._compiled_rules = re.compile('(?:' + '|'.join(cls.rules()) + ')')
        self._compiled_rules = cls._compiled_rules
        return self
    
    def format(self, indata):
        return re.sub(self._compiled_rules, self.replace, indata)

    def replace(self, fullmatch):
        for mtype, match in fullmatch.groupdict().items():
            if match:
                if mtype == 'font':
                    return '<span>'
                elif mtype == 'endfont':
                    return '</span>'
                return '<span class="code-%s">' % mtype


class Sanitizer(HTMLParser):

    safe_tags = frozenset(['a', 'abbr', 'acronym', 'address', 'area',
        'b', 'big', 'blockquote', 'br', 'button', 'caption', 'center',
        'cite', 'code', 'col', 'colgroup', 'dd', 'del', 'dfn', 'dir',
        'div', 'dl', 'dt', 'em', 'fieldset', 'font', 'form', 'h1', 'h2',
        'h3', 'h4', 'h5', 'h6', 'hr', 'i', 'img', 'input', 'ins', 'kbd',
        'label', 'legend', 'li', 'map', 'menu', 'ol', 'optgroup',
        'option', 'p', 'pre', 'q', 's', 'samp', 'select', 'small',
        'span', 'strike', 'strong', 'sub', 'sup', 'table', 'tbody',
        'td', 'textarea', 'tfoot', 'th', 'thead', 'tr', 'tt', 'u', 'ul',
        'var'])
    safe_attrs = frozenset(['abbr', 'accept', 'accept-charset',
        'accesskey', 'action', 'align', 'alt', 'axis', 'border',
        'cellpadding', 'cellspacing', 'char', 'charoff', 'charset',
        'checked', 'cite', 'class', 'clear', 'cols', 'colspan', 'color',
        'compact', 'coords', 'datetime', 'dir', 'disabled', 'enctype',
        'for', 'frame', 'headers', 'height', 'href', 'hreflang',
        'hspace', 'id', 'ismap', 'label', 'lang', 'longdesc',
        'maxlength', 'media', 'method', 'multiple', 'name', 'nohref',
        'noshade', 'nowrap', 'prompt', 'readonly', 'rel', 'rev', 'rows',
        'rowspan', 'rules', 'scope', 'selected', 'shape', 'size',
        'span', 'src', 'start', 'style', 'summary', 'tabindex',
        'target', 'title', 'type', 'usemap', 'valign', 'value',
        'vspace', 'width'])
    uri_attrs = frozenset(['action', 'background', 'dynsrc', 'href',
                          'lowsrc', 'src'])
    safe_schemes = frozenset(['file', 'ftp', 'http', 'https', 'mailto',
                              None])
    empty_tags = frozenset(['br', 'hr', 'img', 'input'])
    waiting_for = None

    def __init__(self, out):
        HTMLParser.__init__(self)
        self.out = out

    def handle_starttag(self, tag, attrs):
        if self.waiting_for:
            return
        if tag not in self.safe_tags:
            self.waiting_for = tag
            return
        self.out.write('<' + tag)

        def _get_scheme(text):
            if ':' not in text:
                return None
            chars = [char for char in text.split(':', 1)[0]
                     if char.isalnum()]
            return ''.join(chars).lower()

        for attrname, attrval in attrs:
            if attrname not in self.safe_attrs:
                continue
            elif attrname in self.uri_attrs:
                # Don't allow URI schemes such as "javascript:"
                if _get_scheme(attrval) not in self.safe_schemes:
                    continue
            elif attrname == 'style':
                # Remove dangerous CSS declarations from inline styles
                decls = []
                for decl in filter(None, attrval.split(';')):
                    is_evil = False
                    if 'expression' in decl:
                        is_evil = True
                    for m in re.finditer(r'url\s*\(([^)]+)', decl):
                        if _get_scheme(m.group(1)) not in self.safe_schemes:
                            is_evil = True
                            break
                    if not is_evil:
                        decls.append(decl.strip())
                if not decls:
                    continue
                attrval = '; '.join(decls)
            self.out.write(' ' + attrname + '="' + escape(attrval) + '"')

        if tag in self.empty_tags:
            self.out.write(' />')
        else:
            self.out.write('>')

    def handle_entityref(self, name):
        if not self.waiting_for:
            self.out.write('&%s;' % name)

    def handle_data(self, data):
        if not self.waiting_for:
            self.out.write(escape(data, quotes=False))

    def handle_endtag(self, tag):
        if self.waiting_for:
            if self.waiting_for == tag:
                self.waiting_for = None
            return
        if tag not in self.empty_tags:
            self.out.write('</' + tag + '>')
