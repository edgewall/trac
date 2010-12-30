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

from genshi import Markup, escape, unescape
from genshi.core import stripentities, striptags, START, END
from genshi.builder import Element, ElementFactory, Fragment
from genshi.filters.html import HTMLSanitizer

__all__ = ['escape', 'unescape', 'html', 'plaintext', 'TracHTMLSanitizer',
           'Deuglifier', 'FormTokenInjector']


class TracHTMLSanitizer(HTMLSanitizer):
    """Sanitize HTML constructions which are potentially vector of
    phishing or XSS attacks, in user-supplied HTML.

    See also `genshi.HTMLSanitizer`_.

    .. _genshi.HTMLSanitizer:
       http://genshi.edgewall.org/wiki/Documentation/filters.html#html-sanitizer
    """

    UNSAFE_CSS = ['position']

    def __init__(self, safe_schemes=HTMLSanitizer.SAFE_SCHEMES):
        safe_attrs = HTMLSanitizer.SAFE_ATTRS | frozenset(['style'])
        safe_schemes = frozenset(safe_schemes)
        super(TracHTMLSanitizer, self).__init__(safe_attrs=safe_attrs,
                                                safe_schemes=safe_schemes)

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
            if 'expression' in decl:
                is_evil = True
            for match in re.finditer(r'url\s*\(([^)]+)', decl):
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
        if prop in self.UNSAFE_CSS:
            return False
        # Negative margins can be used for phishing
        elif prop.startswith('margin') and '-' in value:
            return False
        return True


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
