# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2009 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

from HTMLParser import HTMLParser
import re

from genshi import Markup, HTML, escape, unescape
from genshi.core import END, QName, START, stripentities, striptags
from genshi.builder import Element, ElementFactory, Fragment, tag
from genshi.filters.html import HTMLSanitizer
from genshi.input import ParseError
try:
    from babel.support import LazyProxy
except ImportError:
    LazyProxy = None

from trac.core import TracError
from trac.util.text import to_unicode

__all__ = ['Deuglifier', 'FormTokenInjector', 'TracHTMLSanitizer', 'escape',
           'find_element', 'html', 'is_safe_origin', 'plaintext',
           'to_fragment', 'unescape']


class TracHTMLSanitizer(HTMLSanitizer):
    """Sanitize HTML constructions which are potentially vector of
    phishing or XSS attacks, in user-supplied HTML.

    See also `genshi.HTMLSanitizer`_.

    .. _genshi.HTMLSanitizer:
       http://genshi.edgewall.org/wiki/Documentation/filters.html#html-sanitizer
    """

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

    SAFE_CROSS_ORIGINS = frozenset(['data:'])

    def __init__(self, safe_schemes=HTMLSanitizer.SAFE_SCHEMES,
                 safe_css=SAFE_CSS, safe_origins=SAFE_CROSS_ORIGINS):
        safe_attrs = HTMLSanitizer.SAFE_ATTRS | frozenset(['style'])
        safe_schemes = frozenset(safe_schemes)
        super(TracHTMLSanitizer, self).__init__(safe_attrs=safe_attrs,
                                                safe_schemes=safe_schemes)
        self.safe_css = frozenset(safe_css)
        self.safe_origins = frozenset(safe_origins)

    # IE6 <http://heideri.ch/jso/#80>
    _EXPRESSION_SEARCH = re.compile(
        u'[eE\uFF25\uFF45]'         # FULLWIDTH LATIN CAPITAL LETTER E
                                    # FULLWIDTH LATIN SMALL LETTER E
        u'[xX\uFF38\uFF58]'         # FULLWIDTH LATIN CAPITAL LETTER X
                                    # FULLWIDTH LATIN SMALL LETTER X
        u'[pP\uFF30\uFF50]'         # FULLWIDTH LATIN CAPITAL LETTER P
                                    # FULLWIDTH LATIN SMALL LETTER P
        u'[rR\u0280\uFF32\uFF52]'   # LATIN LETTER SMALL CAPITAL R
                                    # FULLWIDTH LATIN CAPITAL LETTER R
                                    # FULLWIDTH LATIN SMALL LETTER R
        u'[eE\uFF25\uFF45]'         # FULLWIDTH LATIN CAPITAL LETTER E
                                    # FULLWIDTH LATIN SMALL LETTER E
        u'[sS\uFF33\uFF53]{2}'      # FULLWIDTH LATIN CAPITAL LETTER S
                                    # FULLWIDTH LATIN SMALL LETTER S
        u'[iI\u026A\uFF29\uFF49]'   # LATIN LETTER SMALL CAPITAL I
                                    # FULLWIDTH LATIN CAPITAL LETTER I
                                    # FULLWIDTH LATIN SMALL LETTER I
        u'[oO\uFF2F\uFF4F]'         # FULLWIDTH LATIN CAPITAL LETTER O
                                    # FULLWIDTH LATIN SMALL LETTER O
        u'[nN\u0274\uFF2E\uFF4E]'   # LATIN LETTER SMALL CAPITAL N
                                    # FULLWIDTH LATIN CAPITAL LETTER N
                                    # FULLWIDTH LATIN SMALL LETTER N
    ).search

    # IE6 <http://openmya.hacker.jp/hasegawa/security/expression.txt>
    #     7) Particular bit of Unicode characters
    _URL_FINDITER = re.compile(
        u'[Uu][Rr\u0280][Ll\u029F]\s*\(([^)]+)').finditer

    def sanitize_css(self, text):
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

    def __call__(self, stream):
        """Remove input type="password" elements from the stream
        """
        suppress = False
        for kind, data, pos in super(TracHTMLSanitizer, self).__call__(stream):
            if kind is START:
                tag, attrs = data
                if (tag == 'input' and
                    attrs.get('type', '').lower() == 'password'):
                    suppress = True
                else:
                    if tag == 'img' and \
                            not self._is_safe_origin(attrs.get('src', '')):
                        attrs |= [(QName('crossorigin'), 'anonymous')]
                        data = (tag, attrs)
                    yield kind, data, pos
            elif kind is END:
                if not suppress:
                    yield kind, data, pos
                suppress = False
            else:
                yield kind, data, pos

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
                chr = unichr(code)
                if code <= 0x1f:
                    # replace space character because IE ignores control
                    # characters
                    chr = ' '
                elif chr == '\\':
                    chr = r'\\'
                return chr
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


class FormTokenInjector(HTMLParser):
    """Identify and protect forms from CSRF attacks.

    This filter works by adding a input type=hidden field to POST forms.
    """
    def __init__(self, form_token, out):
        HTMLParser.__init__(self)
        self.out = out
        self.token = form_token

    def handle_starttag(self, tag, attrs):
        self.out.write(self.get_starttag_text())
        if tag.lower() == 'form':
            for name, value in attrs:
                if name.lower() == 'method' and value.lower() == 'post':
                    self.out.write('<input type="hidden" name="__FORM_TOKEN"'
                                   ' value="%s"/>' % self.token)
                    break

    def handle_startendtag(self, tag, attrs):
        self.out.write(self.get_starttag_text())

    def handle_charref(self, name):
        self.out.write('&#%s;' % name)

    def handle_entityref(self, name):
        self.out.write('&%s;' % name)

    def handle_comment(self, data):
        self.out.write('<!--%s-->' % data)

    def handle_decl(self, data):
        self.out.write('<!%s>' % data)

    def handle_pi(self, data):
        self.out.write('<?%s?>' % data)

    def handle_data(self, data):
        self.out.write(data)

    def handle_endtag(self, tag):
        self.out.write('</' + tag + '>')


class TransposingElementFactory(ElementFactory):
    """A `genshi.builder.ElementFactory` which applies `func` to the
    named attributes before creating a `genshi.builder.Element`.
    """

    def __init__(self, func, namespace=None):
        ElementFactory.__init__(self, namespace=namespace)
        self.func = func

    def __getattr__(self, name):
        return ElementFactory.__getattr__(self, self.func(name))

html = TransposingElementFactory(str.lower)


try:
    escape('', False)  # detect genshi:#439 on Genshi 0.6 with speedups
except TypeError:
    _escape = escape

    def escape(text, quotes=True):
        if text:
            return _escape(text, quotes=quotes)
        else:
            return Markup(u'')


def plaintext(text, keeplinebreaks=True):
    """Extract the text elements from (X)HTML content

    :param text: `unicode` or `genshi.builder.Fragment`
    :param keeplinebreaks: optionally keep linebreaks
    """
    if isinstance(text, Fragment):
        text = text.generate().render('text', encoding=None)
    else:
        text = stripentities(striptags(text))
    if not keeplinebreaks:
        text = text.replace(u'\n', u' ')
    return text


def find_element(frag, attr=None, cls=None, tag=None):
    """Return the first element in the fragment having the given attribute,
    class or tag, using a preorder depth-first search.
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


def expand_markup(stream, ctxt=None):
    """A Genshi stream filter for expanding `genshi.Markup` events.

    Note: Expansion may not be possible if the fragment is badly
    formed, or partial.
    """
    for event in stream:
        if isinstance(event[1], Markup):
            try:
                for subevent in HTML(event[1]):
                    yield subevent
            except ParseError:
                yield event
        else:
            yield event


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
