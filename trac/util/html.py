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

import re

from genshi import Markup, HTML, escape, unescape
from genshi.core import stripentities, striptags, START, END
from genshi.builder import Element, ElementFactory, Fragment
from genshi.filters.html import HTMLSanitizer
from genshi.input import ParseError

__all__ = ['escape', 'unescape', 'html', 'plaintext', 'find_element',
           'TracHTMLSanitizer']


class TracHTMLSanitizer(HTMLSanitizer):

    SAFE_CSS = frozenset([
        # CSS 3 properties <http://www.w3.org/TR/CSS/#properties>
        'background', 'background-attachment', 'background-color',
        'background-image', 'background-position', 'background-repeat',
        'border', 'border-bottom', 'border-bottom-color',
        'border-bottom-style', 'border-bottom-width', 'border-collapse',
        'border-color', 'border-left', 'border-left-color',
        'border-left-style', 'border-left-width', 'border-right',
        'border-right-color', 'border-right-style', 'border-right-width',
        'border-spacing', 'border-style', 'border-top', 'border-top-color',
        'border-top-style', 'border-top-width', 'border-width', 'bottom',
        'caption-side', 'clear', 'clip', 'color', 'content',
        'counter-increment', 'counter-reset', 'cursor', 'direction', 'display',
        'empty-cells', 'float', 'font', 'font-family', 'font-size',
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

    def __init__(self, safe_schemes=HTMLSanitizer.SAFE_SCHEMES,
                 safe_css=SAFE_CSS):
        safe_attrs = HTMLSanitizer.SAFE_ATTRS | frozenset(['style'])
        safe_schemes = frozenset(safe_schemes)
        super(TracHTMLSanitizer, self).__init__(safe_attrs=safe_attrs,
                                                safe_schemes=safe_schemes)
        self.safe_css = frozenset(safe_css)

    # IE6 <http://heideri.ch/jso/#80>
    _EXPRESSION_SEARCH = re.compile(u"""
        [eE
         \uFF25 # FULLWIDTH LATIN CAPITAL LETTER E
         \uFF45 # FULLWIDTH LATIN SMALL LETTER E
        ]
        [xX
         \uFF38 # FULLWIDTH LATIN CAPITAL LETTER X
         \uFF58 # FULLWIDTH LATIN SMALL LETTER X
        ]
        [pP
         \uFF30 # FULLWIDTH LATIN CAPITAL LETTER P
         \uFF50 # FULLWIDTH LATIN SMALL LETTER P
        ]
        [rR
         \u0280 # LATIN LETTER SMALL CAPITAL R
         \uFF32 # FULLWIDTH LATIN CAPITAL LETTER R
         \uFF52 # FULLWIDTH LATIN SMALL LETTER R
        ]
        [eE
         \uFF25 # FULLWIDTH LATIN CAPITAL LETTER E
         \uFF45 # FULLWIDTH LATIN SMALL LETTER E
        ]
        [sS
         \uFF33 # FULLWIDTH LATIN CAPITAL LETTER S
         \uFF53 # FULLWIDTH LATIN SMALL LETTER S
        ]{2}
        [iI
         \u026A # LATIN LETTER SMALL CAPITAL I
         \uFF29 # FULLWIDTH LATIN CAPITAL LETTER I
         \uFF49 # FULLWIDTH LATIN SMALL LETTER I
        ]
        [oO
         \uFF2F # FULLWIDTH LATIN CAPITAL LETTER O
         \uFF4F # FULLWIDTH LATIN SMALL LETTER O
        ]
        [nN
         \u0274 # LATIN LETTER SMALL CAPITAL N
         \uFF2E # FULLWIDTH LATIN CAPITAL LETTER N
         \uFF4E # FULLWIDTH LATIN SMALL LETTER N
        ]
        """, re.VERBOSE).search

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
            is_evil = False
            if self._EXPRESSION_SEARCH(decl):
                is_evil = True
            for match in self._URL_FINDITER(decl):
                if not self.is_safe_uri(match.group(1)):
                    is_evil = True
                    break
            if not is_evil:
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

    def _replace_unicode_escapes(self, text):
        def _repl(match):
            t = match.group(1)
            if t:
                return unichr(int(t, 16))
            t = match.group(2)
            if t == '\\':
                return r'\\'
            else:
                return t
        return self._UNICODE_ESCAPE(_repl,
                                    self._NORMALIZE_NEWLINES('\n', text))


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


class TransposingElementFactory(ElementFactory):

    def __init__(self, func, namespace=None):
        ElementFactory.__init__(self, namespace=namespace)
        self.func = func

    def __getattr__(self, name):
        return ElementFactory.__getattr__(self, self.func(name))


def plaintext(text, keeplinebreaks=True):
    if isinstance(text, Fragment):
        text = text.generate().render('text', encoding=None)
    else:
        text = stripentities(striptags(text))
    if not keeplinebreaks:
        text = text.replace(u'\n', u' ')
    return text


def find_element(frag, attr=None, cls=None):
    """Return the first element in the fragment having the given attribute or
    class, using a preorder depth-first search.
    """
    if isinstance(frag, Element):
        if attr is not None and attr in frag.attrib:
            return frag
        if cls is not None and cls in frag.attrib.get('class', '').split():
            return frag
    if isinstance(frag, Fragment):
        for child in frag.children:
            elt = find_element(child, attr, cls)
            if elt is not None:
                return elt


def expand_markup(stream, ctxt=None):
    """A Genshi stream filter for expanding Markup events.

    Note: Expansion may not be possible if the fragment is badly formed, or
    partial.
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


html = TransposingElementFactory(str.lower)
