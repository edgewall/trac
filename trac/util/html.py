# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2020 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

# Note that a significant part of the code in this module was taken
# from the Genshi project (http://genshi.edgewall.org):
#  - escape utilities from genshi.core,
#  - strip utilities from genshi.util,
#  - the tag builder API from genshi.builder,
#  - the HTMLSanitizer from genshi.filters.html.

import io
import re
import sys
from html import entities
from html.parser import HTMLParser

from markupsafe import Markup, escape as escape_quotes

try:
    from babel.support import LazyProxy
except ImportError:
    LazyProxy = None

from trac.core import TracError
from trac.util.text import to_unicode

__all__ = ['Deuglifier', 'FormTokenInjector', 'TracHTMLSanitizer', 'escape',
           'find_element', 'html', 'is_safe_origin', 'plaintext', 'tag',
           'to_fragment', 'stripentities', 'striptags', 'valid_html_bytes',
           'unescape']


_name2codepoint = entities.name2codepoint.copy()
_name2codepoint['apos'] = 39  # single quote


def escape(text, quotes=True):
    """Create a Markup instance from a string and escape special characters
    it may contain (<, >, & and \").

    :param text: the string to escape; if not a string, it is assumed that
                 the input can be converted to a string
    :param quotes: if ``True``, double quote characters are escaped in
                   addition to the other special characters

    >>> escape('"1 < 2"')
    Markup('&#34;1 &lt; 2&#34;')

    >>> escape(['"1 < 2"'])
    Markup("['&#34;1 &lt; 2&#34;']")

    If the `quotes` parameter is set to `False`, the \" character is left
    as is. Escaping quotes is generally only required for strings that are
    to be used in attribute values.

    >>> escape('"1 < 2"', quotes=False)
    Markup('"1 &lt; 2"')

    >>> escape(['"1 < 2"'], quotes=False)
    Markup('[\\'"1 &lt; 2"\\']')

    However, `escape` behaves slightly differently with `Markup` and
    `Fragment` behave instances, as they are passed through
    unmodified.

    >>> escape(Markup('"1 < 2 &#39;"'))
    Markup('"1 < 2 &#39;"')

    >>> escape(Markup('"1 < 2 &#39;"'), quotes=False)
    Markup('"1 < 2 &#39;"')

    >>> escape(tag.b('"1 < 2"'))
    Markup('<b>"1 &lt; 2"</b>')

    >>> escape(tag.b('"1 < 2"'), quotes=False)
    Markup('<b>"1 &lt; 2"</b>')

    :return: the escaped `Markup` string
    :rtype: `Markup`

    """
    if isinstance(text, Markup):
        return text
    if isinstance(text, Fragment):
        return Markup(text)
    e = escape_quotes(text)
    if quotes:
        if '&#39;' not in e:
            return e
        return Markup(str(e).replace('&#39;', "'"))
    elif '&#3' not in e:
        return e
    return Markup(str(e).replace('&#34;', '"').replace('&#39;', "'"))


def unescape(text):
    """Reverse-escapes &, <, >, and \" and returns a `str` object.

    >>> unescape(Markup('1 &lt; 2'))
    '1 < 2'

    If the provided `text` object is not a `Markup` instance, it is returned
    unchanged.

    >>> unescape('1 &lt; 2')
    '1 &lt; 2'

    :param text: the text to unescape
    :return: the unescsaped string
    :rtype: `str`
    """
    if not text:
        return ''
    if not isinstance(text, Markup):
        return text
    return text.unescape()


_STRIPENTITIES_RE = re.compile(r'&(?:#((?:\d+)|(?:[xX][0-9a-fA-F]+));?|(\w+);)')
def stripentities(text, keepxmlentities=False):
    """Return a copy of the given text with any character or numeric entities
    replaced by the equivalent UTF-8 characters.

    >>> stripentities('1 &lt; 2')
    '1 < 2'
    >>> stripentities('more &hellip;')
    'more \u2026'
    >>> stripentities('&#8230;')
    '\u2026'
    >>> stripentities('&#x2026;')
    '\u2026'
    >>> stripentities(Markup('\u2026'))
    '\u2026'

    If the `keepxmlentities` parameter is provided and is a truth value, the
    core XML entities (&amp;, &apos;, &gt;, &lt; and &quot;) are left intact.

    >>> stripentities('1 &lt; 2 &hellip;', keepxmlentities=True)
    '1 &lt; 2 \u2026'

    :return: a `str` instance with entities removed
    :rtype: `str`
    """
    def _replace_entity(match):
        if match.group(1): # numeric entity
            ref = match.group(1)
            if ref.startswith(('x', 'X')):
                ref = int(ref[1:], 16)
            else:
                ref = int(ref, 10)
            return chr(ref)
        else: # character entity
            ref = match.group(2)
            if keepxmlentities and ref in ('amp', 'apos', 'gt', 'lt', 'quot'):
                return '&%s;' % ref
            try:
                return chr(_name2codepoint[ref])
            except KeyError:
                if keepxmlentities:
                    return '&amp;%s;' % ref
                else:
                    return ref
    if isinstance(text, Markup):
        text = str(text)
    return _STRIPENTITIES_RE.sub(_replace_entity, text)


def striptags(text):
    """Return a copy of the text with any XML/HTML tags removed.

    >>> striptags('<span>Foo</span> bar')
    'Foo bar'
    >>> striptags('<span class="bar">Foo</span>')
    'Foo'
    >>> striptags('Foo<br />')
    'Foo'

    HTML/XML comments are stripped, too:

    >>> striptags('<!-- <blub>hehe</blah> -->test')
    'test'

    :param text: the string to remove tags from
    :return: a `str` instance with all tags removed
    :rtype: `str`
    """
    return Markup(text).striptags()


# -- Simplified genshi.builder API


NO_YES = ('no', 'yes')
OFF_ON = ('off', 'on')
FALSE_TRUE = ('false', 'true')

SPECIAL_HTML_ATTRS = dict(
    autofocus=None, autoplay=None, checked=None, controls=None,
    default=None, defer=None, disabled=None, formnovalidate=None, hidden=None,
    ismap=None, loop=None, multiple=None, muted=None, novalidate=None,
    open=None, readonly=None, required=None, reversed=None, scoped=None,
    seamless=None, selected=None,
    contenteditable=FALSE_TRUE, draggable=FALSE_TRUE, spellcheck=FALSE_TRUE,
    translate=NO_YES,
    autocomplete=OFF_ON,
)
SPECIAL_HTML_ATTRS['async'] = None

def html_attribute(key, val):
    """Returns the actual value for the attribute ``key``, for the given
    ``value``.

    This follows the rules described in the HTML5_ spec (Double-quoted
    attribute value syntax).

    .. _HTML5: https://www.w3.org/TR/html-markup/global-attributes.html#global-attributes

    In addition, it treats the ``'class'`` and the ``'style'``
    attributes in a special way, as it processes them through
    `classes` and `styles`.

    :rtype: a `Markup` object containing the escaped attribute value,
            but it can also be `None` to indicate that the attribute
            should be omitted from the output

    """
    if key == 'class':
        if isinstance(val, dict):
            val = classes(**val) or None
        elif isinstance(val, list):
            val = classes(*val) or None
    elif key == 'style':
        if isinstance(val, list):
            val = styles(*val) or None
        else:
            val = styles(val) or None
    else:
        if key in SPECIAL_HTML_ATTRS:
            values = SPECIAL_HTML_ATTRS[key]
            if values is None:
                val = key if val else None
            else:
                val = values[bool(val)]
    return None if val is None else escape(val)

def classes(*args, **kwargs):
    """Helper function for dynamically assembling a list of CSS class
    names in templates.

    Any positional arguments are added to the list of class names. All
    positional arguments must be strings:

    >>> classes('foo', 'bar')
    'foo bar'

    In addition, the names of any supplied keyword arguments are added
    if they have a truth value:

    >>> classes('foo', bar=True)
    'foo bar'
    >>> classes('foo', bar=False)
    'foo'
    >>> classes(foo=True, bar=True)
    'bar foo'

    If none of the arguments are added to the list, this function
    returns `''`:

    >>> classes(bar=False)
    ''

    """
    classes = list(filter(None, args))
    classes.extend(k for k in sorted(kwargs) if kwargs[k])
    return ' '.join(classes)

def styles(*args, **kwargs):
    """Helper function for dynamically assembling a list of CSS style name
    and values in templates.

    Any positional arguments are added to the list of styles. All
    positional arguments must be strings or dicts:

    >>> styles('foo: bar', 'fu: baz', {'bottom-right': '1em'})
    'foo: bar; fu: baz; bottom-right: 1em'

    In addition, the names of any supplied keyword arguments are added
    if they have a string value:

    >>> styles('foo: bar', fu='baz')
    'foo: bar; fu: baz'
    >>> styles('foo: bar', bar=False)
    'foo: bar'

    If none of the arguments are added to the list, this function
    returns `''`:

    >>> styles(bar=False)
    ''

    """
    d = {}
    styles = []
    for arg in filter(None, args):
        if isinstance(arg, dict):
            d.update(arg)
        else:
            styles.append(arg)
    d.update(kwargs)
    styles.extend('%s: %s' % (k, v)
                  for k, v in sorted(d.items(), key=lambda i: i[0])
                  if v)
    return '; '.join(styles)


class Fragment(object):
    """A fragment represents a sequence of strings or elements."""

    __slots__ = ('children',)

    def __init__(self, *args):
        self.children = []
        for arg in args:
            self.append(arg)

    def __html__(self):
        return Markup(str(self))

    def __str__(self):
        return ''.join(escape(c, False) for c in self.children)

    def __add__(self, other):
        return Fragment(self, other)

    def append(self, arg):
        if arg: # ignore most false values (None, False, [], (), ''), except 0!
            if isinstance(arg, (Fragment, str, bytes, int, float)):
                self.children.append(arg)
            else:
                # support iterators and generators
                try:
                    for elt in arg:
                        self.append(elt)
                except TypeError:
                    self.children.append(arg)
        elif arg == 0:
            self.children.append('0')

    def as_text(self):
        return ''.join(c.as_text() if isinstance(c, Fragment) else str(c)
                        for c in self.children)


class XMLElement(Fragment):
    """An element represents an XML element, with a tag name, attributes
    and content.

    """

    __slots__ = ('tag', 'attrib')

    EMPTY_ATTRIB = {}

    VOID_ELEMENTS = ()

    CLOSE_TAG = '/>'

    def __init__(self, tag, *args, **kwargs):
        Fragment.__init__(self, *args)
        self.tag = str(tag)
        self.attrib = self._dict_from_kwargs(kwargs) \
                      if kwargs else self.EMPTY_ATTRIB

    def _attr_value(self, k, v):
        return v

    def _dict_from_kwargs(self, kwargs):
        attrs = []
        for k, v in kwargs.items():
            if v is not None:
                if k[-1:] == '_':
                    k = k[:-1]
                v = self._attr_value(k, v)
                if v is not None:
                    attrs.append((k, escape(v)))
        return dict(attrs)

    def __call__(self, *args, **kwargs):
        if kwargs:
            d = self._dict_from_kwargs(kwargs)
            if d:
                if self.attrib:
                    self.attrib.update(d)
                else:
                    self.attrib = d
        for arg in args:
            self.append(arg)
        return self

    def __str__(self):
        elt = '<' + self.tag
        if self.attrib:
            # Sorting the attributes makes the unit-tests more robust
            attrs = []
            for k in sorted(self.attrib):
                v = self.attrib[k]
                if v:
                    attrs.append(' %s="%s"' % (k, v))
            if attrs:
                elt += ''.join(attrs)
        if self.children or (self.VOID_ELEMENTS and
                             self.tag not in self.VOID_ELEMENTS):
            elt += '>' + Fragment.__str__(self) + '</' + self.tag + '>'
        else:
            elt += self.CLOSE_TAG
        return elt


class Element(XMLElement):
    """An element represents an HTML element, with a tag name, attributes
    and content.

    Some elements and attributes are rendered specially, according to
    the HTML5 specification (or going there...)

    """

    VOID_ELEMENTS = {'area', 'base', 'br', 'col', 'command', 'embed', 'hr',
                     'img', 'input', 'keygen', 'link', 'meta', 'param',
                     'source', 'track', 'wbr'}
    CLOSE_TAG = ' />'

    __slots__ = ()

    def _attr_value(self, k, v):
        return html_attribute(k, v)


class XMLElementFactory(object):
    """An XML element factory can be used to build Fragments and
    XMLElements for arbitrary tag names.

    """

    def __call__(self, *args):
        return Fragment(*args)

    def __getattr__(self, tag):
        return XMLElement(tag)

xml = XMLElementFactory()

class ElementFactory(XMLElementFactory):
    """An element factory can be used to build Fragments and Elements for
    arbitrary tag names.

    """

    def __getattr__(self, tag):
        return Element(tag)

tag = html = ElementFactory()


class TracHTMLSanitizer(object):

    """Sanitize HTML constructions which are potentially vector of
    phishing or XSS attacks, in user-supplied HTML.

    The usual way to use the sanitizer is to call the `sanitize`
    method on some potentially unsafe HTML content.

    See also `genshi.HTMLSanitizer`_ from which the TracHTMLSanitizer
    has evolved.

    .. _genshi.HTMLSanitizer:
       http://genshi.edgewall.org/wiki/Documentation/filters.html#html-sanitizer

    """

    # TODO: check from time to time if there are any upstream changes
    #       we could integrate.

    SAFE_TAGS = frozenset(['a', 'abbr', 'acronym', 'address', 'area', 'b',
        'big', 'blockquote', 'br', 'button', 'caption', 'center', 'cite',
        'code', 'col', 'colgroup', 'dd', 'del', 'dfn', 'dir', 'div', 'dl', 'dt',
        'em', 'fieldset', 'font', 'form', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'hr', 'i', 'img', 'input', 'ins', 'kbd', 'label', 'legend', 'li', 'map',
        'menu', 'ol', 'optgroup', 'option', 'p', 'pre', 'q', 's', 'samp',
        'select', 'small', 'span', 'strike', 'strong', 'sub', 'sup', 'table',
        'tbody', 'td', 'textarea', 'tfoot', 'th', 'thead', 'tr', 'tt', 'u',
        'ul', 'var'])

    SAFE_ATTRS = frozenset(['abbr', 'accept', 'accept-charset', 'accesskey',
        'action', 'align', 'alt', 'axis', 'bgcolor', 'border', 'cellpadding',
        'cellspacing', 'char', 'charoff', 'charset', 'checked', 'cite', 'class',
        'clear', 'cols', 'colspan', 'color', 'compact', 'coords', 'datetime',
        'dir', 'disabled', 'enctype', 'for', 'frame', 'headers', 'height',
        'href', 'hreflang', 'hspace', 'id', 'ismap', 'label', 'lang',
        'longdesc', 'maxlength', 'media', 'method', 'multiple', 'name',
        'nohref', 'noshade', 'nowrap', 'prompt', 'readonly', 'rel', 'rev',
        'rows', 'rowspan', 'rules', 'scope', 'selected', 'shape', 'size',
        'span', 'src', 'start', 'style',
        'summary', 'tabindex', 'target', 'title',
        'type', 'usemap', 'valign', 'value', 'vspace', 'width'])

    SAFE_CSS = frozenset([
        # CSS 3 properties <http://www.w3.org/TR/CSS/#properties>
        'background', 'background-attachment', 'background-color',
        'background-image', 'background-position', 'background-repeat',
        'border', 'border-bottom', 'border-bottom-color',
        'border-bottom-style', 'border-bottom-left-radius',
        'border-bottom-right-radius', 'border-bottom-width',
        'border-collapse', 'border-color', 'border-left', 'border-left-color',
        'border-left-style', 'border-left-width', 'border-radius',
        'border-right', 'border-right-color', 'border-right-style',
        'border-right-width', 'border-spacing', 'border-style', 'border-top',
        'border-top-color', 'border-top-left-radius', 'border-top-right-radius',
        'border-top-style', 'border-top-width', 'border-width', 'bottom',
        'caption-side', 'clear', 'clip', 'color', 'content',
        'counter-increment', 'counter-reset', 'cursor', 'direction',
        'display', 'empty-cells', 'float', 'font', 'font-family', 'font-size',
        'font-style', 'font-variant', 'font-weight', 'height', 'left',
        'letter-spacing', 'line-height', 'list-style', 'list-style-image',
        'list-style-position', 'list-style-type', 'margin', 'margin-bottom',
        'margin-left', 'margin-right', 'margin-top', 'max-height', 'max-width',
        'min-height', 'min-width', 'opacity', 'orphans', 'outline',
        'outline-color', 'outline-style', 'outline-width', 'overflow',
        'padding', 'padding-bottom', 'padding-left', 'padding-right',
        'padding-top', 'page-break-after', 'page-break-before',
        'page-break-inside', 'position', 'quotes', 'right', 'table-layout',
        'text-align', 'text-decoration', 'text-indent', 'text-transform',
        'top', 'unicode-bidi', 'vertical-align', 'visibility', 'white-space',
        'widows', 'width', 'word-spacing', 'z-index',
    ])

    SAFE_SCHEMES = frozenset(['file', 'ftp', 'http', 'https', 'mailto', None])

    URI_ATTRS = frozenset(['action', 'background', 'dynsrc', 'href', 'lowsrc',
        'src'])

    SAFE_CROSS_ORIGINS = frozenset(['data:'])

    def __init__(self, safe_schemes=SAFE_SCHEMES, safe_css=SAFE_CSS,
                 safe_tags=SAFE_TAGS, safe_attrs=SAFE_ATTRS,
                 uri_attrs=URI_ATTRS, safe_origins=SAFE_CROSS_ORIGINS):
        """Note: safe_schemes and safe_css have to remain the first
        parameters, for backward-compatibility purpose.
        """
        self.safe_tags = safe_tags
        # The set of tag names that are considered safe.
        self.safe_attrs = safe_attrs
        # The set of attribute names that are considered safe.
        self.safe_css = safe_css
        # The set of CSS properties that are considered safe.
        self.uri_attrs = uri_attrs
        # The set of names of attributes that may contain URIs.
        self.safe_schemes = safe_schemes
        # The set of URI schemes that are considered safe.
        self.safe_origins = safe_origins
        # The set of URI cross origins that are considered safe.

    # IE6 <http://heideri.ch/jso/#80>
    _EXPRESSION_SEARCH = re.compile(
        '[eE\uFF25\uFF45]'         # FULLWIDTH LATIN CAPITAL LETTER E
                                    # FULLWIDTH LATIN SMALL LETTER E
        '[xX\uFF38\uFF58]'         # FULLWIDTH LATIN CAPITAL LETTER X
                                    # FULLWIDTH LATIN SMALL LETTER X
        '[pP\uFF30\uFF50]'         # FULLWIDTH LATIN CAPITAL LETTER P
                                    # FULLWIDTH LATIN SMALL LETTER P
        '[rR\u0280\uFF32\uFF52]'   # LATIN LETTER SMALL CAPITAL R
                                    # FULLWIDTH LATIN CAPITAL LETTER R
                                    # FULLWIDTH LATIN SMALL LETTER R
        '[eE\uFF25\uFF45]'         # FULLWIDTH LATIN CAPITAL LETTER E
                                    # FULLWIDTH LATIN SMALL LETTER E
        '[sS\uFF33\uFF53]{2}'      # FULLWIDTH LATIN CAPITAL LETTER S
                                    # FULLWIDTH LATIN SMALL LETTER S
        '[iI\u026A\uFF29\uFF49]'   # LATIN LETTER SMALL CAPITAL I
                                    # FULLWIDTH LATIN CAPITAL LETTER I
                                    # FULLWIDTH LATIN SMALL LETTER I
        '[oO\uFF2F\uFF4F]'         # FULLWIDTH LATIN CAPITAL LETTER O
                                    # FULLWIDTH LATIN SMALL LETTER O
        '[nN\u0274\uFF2E\uFF4E]'   # LATIN LETTER SMALL CAPITAL N
                                    # FULLWIDTH LATIN CAPITAL LETTER N
                                    # FULLWIDTH LATIN SMALL LETTER N
    ).search

    # IE6 <http://openmya.hacker.jp/hasegawa/security/expression.txt>
    #     7) Particular bit of Unicode characters
    _URL_FINDITER = re.compile(
        '[Uu][Rr\u0280][Ll\u029F]\s*\(([^)]+)').finditer

    def sanitize(self, html):
        """Transforms the incoming HTML by removing anything's that deemed
        unsafe.

        :param html: the input HTML
        :type: str
        :return: the sanitized content
        :rtype: Markup

        """
        transform = HTMLSanitization(self, io.StringIO())
        transform.feed(html)
        transform.close()
        return Markup(transform.out.getvalue())

    def is_safe_css(self, prop, value):
        """Determine whether the given css property declaration is to be
        considered safe for inclusion in the output.

        """
        if prop not in self.safe_css:
            return False
        # Position can be used for phishing, 'static' excepted
        if prop == 'position':
            return value.lower() == 'static'
        # Negative margins can be used for phishing
        if prop.startswith('margin'):
            return '-' not in value
        return True

    def is_safe_elem(self, tag, attrs):
        """Determine whether the given element should be considered safe for
        inclusion in the output.

        :param tag: the tag name of the element
        :type tag: str
        :param attrs: the element attributes
        :type attrs: list
        :return: whether the element should be considered safe
        :rtype: bool

        """
        if tag not in self.safe_tags:
            return False
        if tag == 'input' and ('type', 'password') in attrs:
            return False
        return True

    def is_safe_uri(self, uri):
        """Determine whether the given URI is to be considered safe for
        inclusion in the output.

        The default implementation checks whether the scheme of the URI is in
        the set of allowed URIs (`safe_schemes`).

        >>> sanitizer = TracHTMLSanitizer()
        >>> sanitizer.is_safe_uri('http://example.org/')
        True
        >>> sanitizer.is_safe_uri('javascript:alert(document.cookie)')
        False

        :param uri: the URI to check
        :return: `True` if the URI can be considered safe, `False` otherwise
        :rtype: `bool`

        """
        if '#' in uri:
            uri = uri.split('#', 1)[0] # Strip out the fragment identifier
        if ':' not in uri:
            return True # This is a relative URI
        chars = [char for char in uri.split(':', 1)[0] if char.isalnum()]
        return ''.join(chars).lower() in self.safe_schemes

    def sanitize_attrs(self, tag, attrs):
        """Remove potentially dangerous attributes and sanitize the style
        attribute .

        :param tag: the tag name of the element
        :type attrs: dict corresponding to tag attributes
        :return: a dict containing only safe or sanitized attributes
        :rtype: dict

        """
        new_attrs = {}
        for attr, value in attrs.items():
            if value is None:
                value = attr
            if attr not in self.safe_attrs:
                continue
            elif attr in self.uri_attrs:
                # Don't allow URI schemes such as "javascript:"
                if not self.is_safe_uri(value):
                    continue
            elif attr == 'style':
                # Remove dangerous CSS declarations from inline styles
                decls = self.sanitize_css(value)
                if not decls:
                    continue
                value = '; '.join(decls)
            new_attrs[attr] = value
        if tag == 'img' and 'src' in new_attrs and \
                not self._is_safe_origin(new_attrs['src']):
            attr = 'crossorigin'
            new_attrs[attr] = 'anonymous'
        return new_attrs

    def sanitize_css(self, text):
        """Remove potentially dangerous property declarations from CSS code.

        In particular, properties using the CSS ``url()`` function
        with a scheme that is not considered safe are removed:

        >>> sanitizer = TracHTMLSanitizer()
        >>> sanitizer.sanitize_css('''
        ...   background: url(javascript:alert("foo"));
        ...   color: #000;
        ... ''')
        ['color: #000']

        Also, the proprietary Internet Explorer function
        ``expression()`` is always stripped:

        >>> sanitizer.sanitize_css('''
        ...   background: #fff;
        ...   color: #000;
        ...   width: e/**/xpression(alert("F"));
        ... ''')
        ['background: #fff', 'color: #000', 'width: e xpression(alert("F"))']

        :param text: the CSS text; this is expected to be `str` and to not
                     contain any character or numeric references
        :return: a list of declarations that are considered safe
        :rtype: `list`

        """
        decls = []
        text = self._strip_css_comments(self._replace_unicode_escapes(text))
        for decl in filter(None, text.split(';')):
            decl = decl.strip()
            if not decl:
                continue
            try:
                prop, value = decl.split(':', 1)
            except ValueError:
                continue
            if not self.is_safe_css(prop.strip().lower(), value.strip()):
                continue
            if not self._EXPRESSION_SEARCH(decl) and \
                    all(self._is_safe_origin(match.group(1))
                            for match in self._URL_FINDITER(decl)):
                decls.append(decl.strip())
        return decls

    _NORMALIZE_NEWLINES = re.compile(r'\r\n').sub
    _UNICODE_ESCAPE = re.compile(
        r"""\\([0-9a-fA-F]{1,6})\s?|\\([^\r\n\f0-9a-fA-F'"{};:()#*])""",
        re.UNICODE).sub

    def _is_safe_origin(self, uri):
        return (self.is_safe_uri(uri) and
                is_safe_origin(self.safe_origins, uri))

    def _replace_unicode_escapes(self, text):
        def _repl(match):
            t = match.group(1)
            if t:
                code = int(t, 16)
                c = chr(code)
                if code <= 0x1f:
                    # replace space character because IE ignores control
                    # characters
                    c = ' '
                elif c == '\\':
                    c = r'\\'
                return c
            t = match.group(2)
            if t == '\\':
                return r'\\'
            else:
                return t
        return self._UNICODE_ESCAPE(_repl,
                                    self._NORMALIZE_NEWLINES('\n', text))

    _CSS_COMMENTS = re.compile(r'/\*.*?\*/').sub

    def _strip_css_comments(self, text):
        """Replace comments with space character instead of superclass which
        removes comments to avoid problems when nested comments.
        """
        return self._CSS_COMMENTS(' ', text)


class Deuglifier(object):
    """Help base class used for cleaning up HTML riddled with ``<FONT
    COLOR=...>`` tags and replace them with appropriate ``<span
    class="...">``.

    The subclass must define a `rules()` static method returning a
    list of regular expression fragments, each defining a capture
    group in which the name will be reused for the span's class. Two
    special group names, ``font`` and ``endfont`` are used to emit
    ``<span>`` and ``</span>``, respectively.

    """
    def __new__(cls):
        self = object.__new__(cls)
        if not hasattr(cls, '_compiled_rules'):
            cls._compiled_rules = re.compile('(?:%s)' % '|'.join(cls.rules()))
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


class HTMLTransform(HTMLParser):
    """Convenience base class for writing HTMLParsers.

    The default implementation of the HTMLParser ``handle_*`` methods
    do nothing, while in our case we try to rewrite the incoming
    document unmodified.

    """

    def __init__(self, out):
        HTMLParser.__init__(self)
        self.out = out
        if isinstance(out, io.TextIOBase):
            self._convert = lambda v: v.decode('utf-8') \
                                      if isinstance(v, bytes) else v
        elif isinstance(out, io.IOBase):
            self._convert = lambda v: v.encode('utf-8') \
                                      if isinstance(v, str) else v
        else:
            self._convert = lambda v: v

    def handle_starttag(self, tag, attrs):
        self._write(self.get_starttag_text())

    def handle_startendtag(self, tag, attrs):
        self._write(self.get_starttag_text())

    def handle_comment(self, data):
        self._write('<!--%s-->' % data)

    def handle_decl(self, data):
        self._write('<!%s>' % data)

    def handle_pi(self, data):
        self._write('<?%s?>' % data)

    def handle_data(self, data):
        self._write(data)

    def handle_endtag(self, tag):
        self._write('</' + tag + '>')

    def _write(self, data):
        self.out.write(self._convert(data))


class FormTokenInjector(HTMLTransform):
    """Identify and protect forms from CSRF attacks.

    This filter works by adding a input type=hidden field to POST
    forms.

    """
    def __init__(self, form_token, out):
        HTMLTransform.__init__(self, out)
        self.token = form_token

    def handle_starttag(self, tag, attrs):
        HTMLTransform.handle_starttag(self, tag, attrs)
        if tag.lower() == 'form':
            for name, value in attrs:
                if name == 'method' and value.lower() == 'post':
                    self._write('<input type="hidden" name="__FORM_TOKEN"'
                                ' value="%s"/>' % self.token)
                    break

class HTMLSanitization(HTMLTransform):
    """Sanitize parsed HTML using TracHTMLSanitizer."""

    def __init__(self, sanitizer, out):
        HTMLTransform.__init__(self, out)
        self.sanitizer = sanitizer
        self.waiting_for = None

    def _handle_start(self, tag, attrs, startend):
        if self.waiting_for:
            return
        if not self.sanitizer.is_safe_elem(tag, attrs):
            self.waiting_for = tag
            return

        new_attrs = self.sanitizer.sanitize_attrs(tag, dict(attrs))
        html_attrs = ''.join(' %s="%s"' % (name, escape(new_attrs[name]))
                             for name in sorted(new_attrs))
        self._write('<%s%s%s>' % (tag, html_attrs, startend))

    def handle_starttag(self, tag, attrs):
        if not self.waiting_for:
            self._handle_start(tag, attrs, '')

    def handle_startendtag(self, tag, attrs):
        if not self.waiting_for:
            self._handle_start(tag, attrs, '/')

    def handle_comment(self, data):
        pass

    def handle_decl(self, data):
        if not self.waiting_for:
            self._write('<!%s>' % data)

    def handle_pi(self, data):
        if not self.waiting_for:
            self._write('<?%s?>' % data.replace('?>', ''))

    def handle_data(self, data):
        if not self.waiting_for:
            self._write(escape(data))

    def handle_endtag(self, tag):
        if self.waiting_for:
            if self.waiting_for == tag:
                self.waiting_for = None
        else:
            self._write('</' + tag + '>')


def plaintext(text, keeplinebreaks=True):
    """Extract the text elements from (X)HTML content

    >>> plaintext('<b>1 &lt; 2</b>')
    '1 < 2'

    >>> plaintext(tag('1 ', tag.b('<'), ' 2'))
    '1 < 2'

    >>> plaintext('''<b>1
    ... &lt;
    ... 2</b>''', keeplinebreaks=False)
    '1 < 2'

    :param text: `unicode` or `Fragment`
    :param keeplinebreaks: optionally keep linebreaks

    """
    if isinstance(text, Fragment):
        text = text.as_text()
    else:
        text = stripentities(striptags(text))
    if not keeplinebreaks:
        text = text.replace('\n', ' ')
    return text


def find_element(frag, attr=None, cls=None, tag=None):
    """Return the first element in the fragment having the given
    attribute, class or tag, using a preorder depth-first search.

    """
    if isinstance(frag, Element):
        if attr is not None and attr in frag.attrib:
            return frag
        if cls is not None and cls in frag.attrib.get('class', '').split():
            return frag
        if tag is not None and tag == frag.tag:
            return frag
    if isinstance(frag, Fragment):
        for child in frag.children:
            elt = find_element(child, attr, cls, tag)
            if elt is not None:
                return elt


def is_safe_origin(safe_origins, uri, req=None):
    """Whether the given uri is a safe cross-origin."""
    if not uri or ':' not in uri and not uri.startswith('//'):
        return True
    if any(safe == '*' for safe in safe_origins):
        return True
    if uri.startswith('//') and req:
        uri = '%s:%s' % (req.scheme, uri)

    normalize_re = re.compile(r'(?:[a-zA-Z][-a-zA-Z0-9+._]*:)?//[^/]+$')

    def normalize_uri(uri):
        if normalize_re.match(uri):
            uri += '/'
        return uri

    uri = normalize_uri(uri)
    for safe in safe_origins:
        safe = normalize_uri(safe)
        if safe == uri:
            return True
        if safe.endswith(':') and uri.startswith(safe):
            return True
        if uri.startswith(safe if safe.endswith('/') else safe + '/'):
            return True
    return False


def to_fragment(input):
    """Convert input to a `Fragment` object."""

    while isinstance(input, TracError) or \
            isinstance(input, Exception) and len(input.args) == 1:
        input = input.args[0]
    if LazyProxy and isinstance(input, LazyProxy):
        input = input.value
    if isinstance(input, Fragment):
        return input
    return tag(to_unicode(input))


# Mappings for removal of control characters
_invalid_control_chars = bytes(i for i in range(32)
                                 if i not in (0x09, 0x0a, 0x0d))

def valid_html_bytes(data):
    """Return only valid bytes in XML/HTML from the given data.

    >>> valid_html_bytes(b'blah')
    b'blah'

    >>> list(valid_html_bytes(bytes(range(33)) + b'\x7F'))
    [9, 10, 13, 32, 127]

    """
    return data.translate(None, _invalid_control_chars)
