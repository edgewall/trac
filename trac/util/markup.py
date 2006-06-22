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
import sys

__all__ = ['escape', 'unescape', 'html']

_EMPTY_TAGS = frozenset(['br', 'hr', 'img', 'input'])
_BOOLEAN_ATTRS = frozenset(['selected', 'checked', 'compact', 'declare',
                            'defer', 'disabled', 'ismap', 'multiple', 'nohref',
                            'noresize', 'noshade', 'nowrap'])


class Markup(unicode):
    """Marks a string as being safe for inclusion in XML output without needing
    to be escaped.
    
    Strings are normally automatically escaped when added to the HDF.
    `Markup`-strings are however an exception. Use with care.
    
    (since Trac 0.9.3)
    """
    def __new__(self, text='', *args):
        if args:
            text %= tuple([escape(arg) for arg in args])
        return unicode.__new__(self, text)

    def __add__(self, other):
        return Markup(unicode(self) + Markup.escape(other))

    def __mod__(self, args):
        if not isinstance(args, (list, tuple)):
            args = [args]
        return Markup(unicode.__mod__(self,
                                      tuple([escape(arg) for arg in args])))

    def __mul__(self, num):
        return Markup(unicode(self) * num)

    def join(self, seq):
        return Markup(unicode(self).join([Markup.escape(item) for item in seq]))

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
                return unichr(ref)
            else: # character entity
                ref = match.group(2)
                if keepxmlentities and ref in ('amp', 'apos', 'gt', 'lt', 'quot'):
                    return '&%s;' % ref
                try:
                    codepoint = htmlentitydefs.name2codepoint[ref]
                    return unichr(codepoint)
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
        it may contain (<, >, & and \").
        
        If the `quotes` parameter is set to `False`, the \" character is left
        as is. Escaping quotes is generally only required for strings that are
        to be used in attribute values.
        """
        if isinstance(text, (cls, Element)):
            return text
        text = unicode(text)
        if not text:
            return cls()
        text = text.replace('&', '&amp;') \
                   .replace('<', '&lt;') \
                   .replace('>', '&gt;')
        if quotes:
            text = text.replace('"', '&#34;')
        return cls(text)
    escape = classmethod(escape)

    def unescape(self):
        """Reverse-escapes &, <, > and \" and returns a `unicode` object."""
        if not self:
            return ''
        return unicode(self).replace('&#34;', '"') \
                            .replace('&gt;', '>') \
                            .replace('&lt;', '<') \
                            .replace('&amp;', '&')

    def plaintext(self, keeplinebreaks=True):
        """Returns the text as a `unicode`with all entities and tags removed."""
        text = unicode(self.striptags().stripentities())
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
        sanitizer = HTMLSanitizer(buf)
        sanitizer.feed(self.stripentities(keepxmlentities=True))
        return Markup(buf.getvalue())


escape = Markup.escape

def unescape(text):
    """Reverse-escapes &, <, > and \" and returns a `unicode` object."""
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


class HTMLSanitizer(HTMLParser):

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
        'accesskey', 'action', 'align', 'alt', 'axis', 'border', 'bgcolor',
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

    def __init__(self, out):
        HTMLParser.__init__(self)
        self.out = out
        self.waiting_for = None

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

        if tag in _EMPTY_TAGS:
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
        if tag not in _EMPTY_TAGS:
            self.out.write('</' + tag + '>')


class Fragment(object):
    __slots__ = ['children']

    def __init__(self):
        self.children = []

    def append(self, node):
        """Append an element or string as child node."""
        if isinstance(node, (Element, Markup, basestring, int, float, long)):
            # For objects of a known/primitive type, we avoid the check for
            # whether it is iterable for better performance
            self.children.append(node)
        elif isinstance(node, Fragment):
            self.children += node.children
        elif node is not None:
            try:
                for child in node:
                    self.append(child)
            except TypeError:
                self.children.append(node)

    def __call__(self, *args):
        for arg in args:
            self.append(arg)
        return self

    def serialize(self):
        """Generator that yield tags and text nodes as strings."""
        for child in self.children:
            if isinstance(child, Fragment):
                yield unicode(child)
            else:
                yield escape(child, quotes=False)

    def __str__(self):
        return Markup(''.join(self.serialize()))

    def __add__(self, other):
        return Fragment()(self, other)


class Element(Fragment):
    """Simple XHTML output generator based on the builder pattern.
    
    Construct XHTML elements by passing the tag name to the constructor:
    
    >>> print Element('strong')
    <strong></strong>
    
    Attributes can be specified using keyword arguments. The values of the
    arguments will be converted to strings and any special XML characters
    escaped:
    
    >>> print Element('textarea', rows=10, cols=60)
    <textarea rows="10" cols="60"></textarea>
    >>> print Element('span', title='1 < 2')
    <span title="1 &lt; 2"></span>
    >>> print Element('span', title='"baz"')
    <span title="&#34;baz&#34;"></span>
    
    The " character is escaped using a numerical entity.
    The order in which attributes are rendered is undefined.
    
    If an attribute value evaluates to `None`, that attribute is not included
    in the output:
    
    >>> print Element('a', name=None)
    <a></a>
    
    Attribute names that conflict with Python keywords can be specified by
    appending an underscore:
    
    >>> print Element('div', class_='warning')
    <div class="warning"></div>
    
    While the tag names and attributes are not restricted to the XHTML language,
    some HTML characteristics such as boolean (minimized) attributes and empty
    elements get special treatment.
    
    For compatibility with HTML user agents, some XHTML elements need to be
    closed using a separate closing tag even if they are empty. For this, the
    close tag is only ommitted for a small set of elements which are known be
    be safe for use as empty elements:
    
    >>> print Element('br')
    <br />
    
    Trying to add nested elements to such an element will cause an
    `AssertionError`:
    
    >>> Element('br')('Oops')
    Traceback (most recent call last):
        ...
    AssertionError: 'br' elements must not have content
    
    Furthermore, boolean attributes such as "selected" or "checked" are omitted
    if the value evaluates to `False`. Otherwise, the name of the attribute is
    used for the value:
    
    >>> print Element('option', value=0, selected=False)
    <option value="0"></option>
    >>> print Element('option', selected='yeah')
    <option selected="selected"></option>
    
    
    Nested elements can be added to an element by calling the instance using
    positional arguments. The same technique can also be used for adding
    attributes using keyword arguments, as one would do in the constructor:
    
    >>> print Element('ul')(Element('li'), Element('li'))
    <ul><li></li><li></li></ul>
    >>> print Element('a')('Label')
    <a>Label</a>
    >>> print Element('a')('Label', href="target")
    <a href="target">Label</a>

    Text nodes can be nested in an element by adding strings instead of
    elements. Any special characters in the strings are escaped automatically:

    >>> print Element('em')('Hello world')
    <em>Hello world</em>
    >>> print Element('em')(42)
    <em>42</em>
    >>> print Element('em')('1 < 2')
    <em>1 &lt; 2</em>

    This technique also allows mixed content:

    >>> print Element('p')('Hello ', Element('b')('world'))
    <p>Hello <b>world</b></p>

    Elements can also be combined with other elements or strings using the
    addition operator, which results in a `Fragment` object that contains the
    operands:
    
    >>> print Element('br') + 'some text' + Element('br')
    <br />some text<br />
    """
    __slots__ = ['tagname', 'attr']

    def __init__(self, tagname_=None, **attr):
        Fragment.__init__(self)
        if tagname_:
            self.tagname = tagname_
        self.attr = {}
        self(**attr)

    def __call__(self, *args, **attr):
        self.attr.update(attr)
        return Fragment.__call__(self, *args)

    def append(self, node):
        """Append an element or string as child node."""
        assert self.tagname not in _EMPTY_TAGS, \
            "'%s' elements must not have content" % self.tagname
        Fragment.append(self, node)

    def serialize(self):
        """Generator that yield tags and text nodes as strings."""
        starttag = ['<', self.tagname]
        for name, value in self.attr.items():
            if value is None:
                continue
            if name in _BOOLEAN_ATTRS:
                if not value:
                    continue
                value = name
            else:
                name = name.rstrip('_').replace('_', '-')
            starttag.append(' %s="%s"' % (name.lower(), escape(value)))

        if self.children or self.tagname not in _EMPTY_TAGS:
            starttag.append('>')
            yield Markup(''.join(starttag))
            for part in Fragment.serialize(self):
                yield part
            yield Markup('</%s>', self.tagname)

        else:
            starttag.append(' />')
            yield Markup(''.join(starttag))


class Tags(object):

    def __getattribute__(self, name):
        return Element(name.lower())


html = Tags()
