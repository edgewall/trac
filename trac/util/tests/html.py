# -*- coding: utf-8 -*-
#
# Copyright (C) 2007-2019 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

from __future__ import unicode_literals

import doctest
import io
import sys
import unittest

from trac.core import TracError
from trac.util import html
from trac.util.html import (
    Element, FormTokenInjector, Fragment, HTML, Markup, TracHTMLSanitizer,
    escape, find_element, genshi, html_attribute, is_safe_origin,
    tag, to_fragment, xml
)
from trac.util.translation import gettext, tgettext


class EscapeFragmentTestCase(unittest.TestCase):

    def test_escape_element(self):
        self.assertEqual(Markup('<b class="em&#34;ph&#34;">"1 &lt; 2"</b>'),
                         escape(tag.b('"1 < 2"', class_='em"ph"')))
        self.assertEqual(Markup('<b class="em&#34;ph&#34;">"1 &lt; 2"</b>'),
                         escape(tag.b('"1 < 2"', class_='em"ph"'),
                                quotes=False))

    def test_escape_fragment(self):
        self.assertEqual(Markup('<b class="em&#34;ph&#34;">"1 &lt; 2"</b>'),
                         escape(tag(tag.b('"1 < 2"', class_='em"ph"'))))
        self.assertEqual(Markup('<b class="em&#34;ph&#34;">"1 &lt; 2"</b>'),
                         escape(tag(tag.b('"1 < 2"', class_='em"ph"')),
                                    quotes=False))

class HtmlAttributeTestCase(unittest.TestCase):

    def test_html_attribute_special_None(self):
        self.assertEqual('async', html_attribute('async', True))
        self.assertEqual(None, html_attribute('async', False))
        self.assertEqual(None, html_attribute('async', None))

    def test_html_attribute_special_no_yes(self):
        self.assertEqual('yes', html_attribute('translate', True))
        self.assertEqual('no', html_attribute('translate', False))
        self.assertEqual('no', html_attribute('translate', None))

    def test_html_attribute_special_off_on(self):
        self.assertEqual('on', html_attribute('autocomplete', True))
        self.assertEqual('off', html_attribute('autocomplete', False))
        self.assertEqual('off', html_attribute('autocomplete', None))

    def test_html_attribute_special_false_true(self):
        self.assertEqual('true', html_attribute('spellcheck', True))
        self.assertEqual('false', html_attribute('spellcheck', False))
        self.assertEqual('false', html_attribute('spellcheck', None))

    def test_html_attribute_normal(self):
        self.assertEqual('https://trac.edgewall.org',
                         html_attribute('src', 'https://trac.edgewall.org'))
        self.assertEqual(None, html_attribute('src', None))

class FragmentTestCase(unittest.TestCase):

    def test_zeros(self):
        self.assertEqual(Markup('0<b>0</b> and <b>0</b>'),
                         Markup(tag(0, tag.b(0), ' and ', tag.b(0.0))))

    def test_unicode(self):
        self.assertEqual('<b>M</b>essäge',
                         unicode(tag(tag.b('M'), 'essäge')))

    def test_str(self):
        self.assertEqual(b'<b>M</b>ess\xc3\xa4ge',
                         str(tag(tag.b('M'), 'essäge')))


class XMLElementTestCase(unittest.TestCase):

    def test_xml(self):
        self.assertEqual(Markup('0<a>0</a> and <b>0</b> and <c/> and'
                                ' <d class="[\'a\', \'\', \'b\']"'
                                ' more_="[\'a\']"/>'),
                         Markup(xml(0, xml.a(0), ' and ', xml.b(0.0),
                                    ' and ', xml.c(None), ' and ',
                                    xml.d('', class_=[b'a', b'', b'b'],
                                          more__=[b'a']))))


class ElementTestCase(unittest.TestCase):

    def test_tag(self):
        self.assertEqual(Markup('0<a>0</a> and <b>0</b> and <c></c>'
                                ' and <d class="a b" more_="[\'a\']"></d>'),
                         Markup(tag(0, tag.a(0, href=''), b' and ', tag.b(0.0),
                                    ' and ', tag.c(None), ' and ',
                                    tag.d('', class_=['a', '', 'b'],
                                          more__=[b'a']))))

    def test_unicode(self):
        self.assertEqual('<b>M<em>essäge</em></b>',
                         unicode(tag.b('M', tag.em('essäge'))))

    def test_str(self):
        self.assertEqual(b'<b>M<em>ess\xc3\xa4ge</em></b>',
                         str(tag.b('M', tag.em('essäge'))))


class FormTokenInjectorTestCase(unittest.TestCase):

    def test_no_form(self):
        html = '<div><img src="trac.png"/></div>'
        injector = FormTokenInjector('123123', io.StringIO())
        injector.feed(html)
        injector.close()
        self.assertEqual(html, injector.out.getvalue())

    def test_form_get(self):
        html = '<form method="get"><input name="age" value=""/></form>'
        injector = FormTokenInjector('123123', io.StringIO())
        injector.feed(html)
        injector.close()
        self.assertEqual(html, injector.out.getvalue())

    def test_form_post(self):
        html = '<form method="POST">%s<input name="age" value=""/></form>'
        injector = FormTokenInjector('123123', io.StringIO())
        injector.feed(html % '')
        injector.close()
        html %= ('<input type="hidden" name="__FORM_TOKEN" value="%s"/>'
                 % injector.token)
        self.assertEqual(html, injector.out.getvalue())


class TracHTMLSanitizerTestCaseBase(unittest.TestCase):

    safe_schemes = ('http', 'data')
    safe_origins = ('data:', 'http://example.net', 'https://example.org/')

    def sanitize(self, html):
        sanitizer = TracHTMLSanitizer(safe_schemes=self.safe_schemes,
                                      safe_origins=self.safe_origins)
        return unicode(sanitizer.sanitize(html))

    def test_input_type_password(self):
        html = '<input type="password" />'
        self.assertEqual('', self.sanitize(html))

    def test_empty_attribute(self):
        html = '<option value="1236" selected>Family B</option>'
        self.assertEqual(
            '<option selected="selected" value="1236">Family B</option>',
            self.sanitize(html))

    def test_expression(self):
        html = '<div style="top:expression(alert())">XSS</div>'
        self.assertEqual('<div>XSS</div>', self.sanitize(html))

    def test_capital_expression(self):
        html = '<div style="top:EXPRESSION(alert())">XSS</div>'
        self.assertEqual('<div>XSS</div>', self.sanitize(html))

    def test_expression_with_comments(self):
        html = r'<div style="top:exp/**/ression(alert())">XSS</div>'
        self.assertEqual('<div style="top:exp ression(alert())">XSS</div>',
                         self.sanitize(html))
        html = r'<div style="top:exp//**/**/ression(alert())">XSS</div>'
        self.assertEqual(
            '<div style="top:exp/ **/ression(alert())">XSS</div>',
            self.sanitize(html))
        html = r'<div style="top:ex/*p*/ression(alert())">XSS</div>'
        self.assertEqual('<div style="top:ex ression(alert())">XSS</div>',
                         self.sanitize(html))

    def test_url_with_javascript(self):
        html = (
            '<div style="background-image:url(javascript:alert())">XSS</div>'
        )
        self.assertEqual('<div>XSS</div>', self.sanitize(html))

    def test_capital_url_with_javascript(self):
        html = (
            '<div style="background-image:URL(javascript:alert())">XSS</div>'
        )
        self.assertEqual('<div>XSS</div>', self.sanitize(html))

    def test_unicode_escapes(self):
        html = r'<div style="top:exp\72 ess\000069 on(alert())">XSS</div>'
        self.assertEqual('<div>XSS</div>', self.sanitize(html))
        # escaped backslash
        html = r'<div style="top:exp\5c ression(alert())">XSS</div>'
        self.assertEqual(r'<div style="top:exp\\ression(alert())">XSS</div>',
                         self.sanitize(html))
        html = r'<div style="top:exp\5c 72 ession(alert())">XSS</div>'
        self.assertEqual(r'<div style="top:exp\\72 ession(alert())">XSS</div>',
                         self.sanitize(html))
        # escaped control characters
        html = r'<div style="top:exp\000000res\1f sion(alert())">XSS</div>'
        self.assertEqual('<div style="top:exp res sion(alert())">XSS</div>',
                         self.sanitize(html))

    def test_backslash_without_hex(self):
        html = r'<div style="top:e\xp\ression(alert())">XSS</div>'
        self.assertEqual('<div>XSS</div>', self.sanitize(html))
        html = r'<div style="top:e\\xp\\ression(alert())">XSS</div>'
        self.assertEqual(r'<div style="top:e\\xp\\ression(alert())">XSS</div>',
                         self.sanitize(html))

    def test_unsafe_props(self):
        html = '<div style="POSITION:RELATIVE">XSS</div>'
        self.assertEqual('<div>XSS</div>', self.sanitize(html))
        html = '<div style="position:STATIC">safe</div>'
        self.assertEqual('<div style="position:STATIC">safe</div>',
                         self.sanitize(html))
        html = '<div style="behavior:url(test.htc)">XSS</div>'
        self.assertEqual('<div>XSS</div>', self.sanitize(html))
        html = '<div style="-ms-behavior:url(test.htc) url(#obj)">XSS</div>'
        self.assertEqual('<div>XSS</div>', self.sanitize(html))
        html = ("""<div style="-o-link:'javascript:alert(1)';"""
                """-o-link-source:current">XSS</div>""")
        self.assertEqual('<div>XSS</div>', self.sanitize(html))
        html = """<div style="-moz-binding:url(xss.xbl)">XSS</div>"""
        self.assertEqual('<div>XSS</div>', self.sanitize(html))

    def test_nagative_margin(self):
        html = '<div style="margin-top:-9999px">XSS</div>'
        self.assertEqual('<div>XSS</div>', self.sanitize(html))
        html = '<div style="margin:0 -9999px">XSS</div>'
        self.assertEqual('<div>XSS</div>', self.sanitize(html))

    def test_css_hack(self):
        html = '<div style="*position:static">XSS</div>'
        self.assertEqual('<div>XSS</div>', self.sanitize(html))
        html = '<div style="_margin:-10px">XSS</div>'
        self.assertEqual('<div>XSS</div>', self.sanitize(html))

    def test_property_name(self):
        html = ('<div style="display:none;border-left-color:red;'
                'user_defined:1;-moz-user-selct:-moz-all">prop</div>')
        self.assertEqual('<div style="display:none; border-left-color:red'
                         '">prop</div>',
                         self.sanitize(html))

    def test_unicode_expression(self):
        # Fullwidth small letters
        html = '<div style="top:ｅｘｐｒｅｓｓｉｏｎ(alert())">XSS</div>'
        self.assertEqual('<div>XSS</div>', self.sanitize(html))
        # Fullwidth capital letters
        html = '<div style="top:ＥＸＰＲＥＳＳＩＯＮ(alert())">XSS</div>'
        self.assertEqual('<div>XSS</div>', self.sanitize(html))
        # IPA extensions
        html = '<div style="top:expʀessɪoɴ(alert())">XSS</div>'
        self.assertEqual('<div>XSS</div>', self.sanitize(html))

    def test_unicode_url(self):
        # IPA extensions
        html = (
            '<div style="background-image:uʀʟ(javascript:alert())">XSS</div>'
        )
        self.assertEqual('<div>XSS</div>', self.sanitize(html))

    def test_cross_origin(self):
        test = self._assert_sanitize

        test('<img src="data:image/png,...."/>',
             '<img src="data:image/png,...."/>')
        test('<img src="http://example.org/login" crossorigin="anonymous"/>',
             '<img src="http://example.org/login"/>')
        test('<img src="http://example.org/login" crossorigin="anonymous"/>',
             '<img src="http://example.org/login"'
             ' crossorigin="use-credentials"/>')
        test('<img src="http://example.net/bar.png"/>',
             '<img src="http://example.net/bar.png"/>')
        test('<img src="http://example.net:443/qux.png"'
             ' crossorigin="anonymous"/>',
             '<img src="http://example.net:443/qux.png"/>')
        test('<img src="/path/foo.png"/>', '<img src="/path/foo.png"/>')
        test('<img src="../../bar.png"/>', '<img src="../../bar.png"/>')
        test('<img src="qux.png"/>', '<img src="qux.png"/>')

        test('<div>x</div>',
             '<div style="background:url(http://example.org/login)">x</div>')
        test('<div style="background:url(http://example.net/1.png)">x</div>',
             '<div style="background:url(http://example.net/1.png)">x</div>')
        test('<div>x</div>',
             '<div style="background:url(http://example.net:443/1.png)">'
             'x</div>')
        test('<div style="background:url(data:image/png,...)">x</div>',
             '<div style="background:url(data:image/png,...)">x</div>')
        test('<div>x</div>',
             '<div style="background:url(//example.net/foo.png)">x</div>')
        test('<div style="background:url(/path/to/foo.png)">safe</div>',
             '<div style="background:url(/path/to/foo.png)">safe</div>')
        test('<div style="background:url(../../bar.png)">safe</div>',
             '<div style="background:url(../../bar.png)">safe</div>')
        test('<div style="background:url(qux.png)">safe</div>',
             '<div style="background:url(qux.png)">safe</div>')

    def test_special_characters_data(self):
        test = self._assert_sanitize
        test('<p>&amp;hellip;</p>',     '<p>&amp;hellip;</p>')
        test('<p>&amp;</p>',            '<p>&amp;</p>')
        test('<p>&amp;</p>',            '<p>&</p>')
        test('<p>&amp;&lt;&gt;</p>',    '<p>&<></p>')
        test('<p>&amp;&amp;</p>',       '<p>&amp;&amp;</p>')
        test('<p>&amp;\u2026</p>',      '<p>&amp;&hellip;</p>')
        test("<p>&amp;unknown;</p>",    '<p>&unknown;</p>')
        test("<p>\U0010ffff</p>",       '<p>&#1114111;</p>')
        test("<p>\U0010ffff</p>",       '<p>&#x10ffff;</p>')
        test("<p>\U0010ffff</p>",       '<p>&#X10FFFF;</p>')
        test("<p>&amp;#1114112;</p>",   '<p>&#1114112;</p>')
        test("<p>&amp;#x110000;</p>",   '<p>&#x110000;</p>')
        test("<p>&amp;#X110000;</p>",   '<p>&#X110000;</p>')
        test("<p>&amp;#abcd;</p>",      '<p>&#abcd;</p>')
        test('<p>&amp;#%d;</p>' % (sys.maxint + 1),
             '<p>&#%d;</p>' % (sys.maxint + 1))

    def test_special_characters_attribute(self):
        self._assert_sanitize('<img title="&amp;"/>', '<img title="&amp;"/>')
        self._assert_sanitize('''<img title="&amp;&lt;&gt;&#34;'"/>''',
                              '''<img title="&amp;&lt;&gt;&quot;&apos;"/>''')
        self._assert_sanitize('''<img title="&amp;&lt;&gt;&#34;'"/>''',
                              '''<img title="&#38;&#60;&#62;&#34;&#39;"/>''')
        self._assert_sanitize("""<img title="&amp;&lt;&gt;'"/>""",
                              """<img title="&<>'"/>""")
        self._assert_sanitize('<img title="&amp;&amp;"/>',
                              '<img title="&amp;&amp;"/>')
        self._assert_sanitize('<img title="&amp;\u2026"/>',
                              '<img title="&amp;&hellip;"/>')
        self._assert_sanitize('<img title="&amp;hellip;"/>',
                              '<img title="&amp;hellip;"/>')
        self._assert_sanitize('<img title="&amp;unknown;"/>',
                              '<img title="&unknown;"/>')
        self._assert_sanitize('<img title="\U0010ffff"/>',
                              '<img title="&#1114111;"/>')
        self._assert_sanitize('<img title="\U0010ffff"/>',
                              '<img title="&#x10ffff;"/>')
        self._assert_sanitize('<img title="\U0010ffff"/>',
                              '<img title="&#X10FFFF;"/>')
        self._assert_sanitize('<img title="&amp;#1114112;"/>',
                              '<img title="&#1114112;"/>')
        self._assert_sanitize('<img title="&amp;#x110000;"/>',
                              '<img title="&#x110000;"/>')
        self._assert_sanitize('<img title="&amp;#X110000;"/>',
                              '<img title="&#X110000;"/>')
        self._assert_sanitize('<img title="&amp;#abcd;"/>',
                              '<img title="&#abcd;"/>')
        self._assert_sanitize('<img title="&amp;#%d;"/>' % (sys.maxint + 1),
                              '<img title="&#%d;"/>' % (sys.maxint + 1))

    def _assert_sanitize(self, expected, content):
        self.assertEqual(expected, self.sanitize(content))


class TracHTMLSanitizerTestCase(TracHTMLSanitizerTestCaseBase):

    def test_special_characters_data_jinja2(self):
        test = self._assert_sanitize
        test("<p>&amp;&lt;&gt;&#34;'</p>",
             '<p>&amp;&lt;&gt;&quot;&apos;</p>')
        test("<p>&amp;&lt;&gt;&#34;'</p>",
             '<p>&#38;&#60;&#62;&#34;&#39;</p>')


if genshi:
    class TracHTMLSanitizerLegacyGenshiTestCase(TracHTMLSanitizerTestCaseBase):
        def sanitize(self, html):
            sanitizer = TracHTMLSanitizer(safe_schemes=self.safe_schemes,
                                          safe_origins=self.safe_origins)
            return unicode(HTML(html, encoding='utf-8') | sanitizer)

        def test_special_characters_data_genshi(self):
            test = self._assert_sanitize
            test('''<p>&amp;&lt;&gt;"'</p>''',
                 '<p>&amp;&lt;&gt;&quot;&apos;</p>')
            test('''<p>&amp;&lt;&gt;"'</p>''',
                 '<p>&#38;&#60;&#62;&#34;&#39;</p>')


class FindElementTestCase(unittest.TestCase):

    def test_find_element_with_tag(self):
        frag = tag(tag.p('Paragraph with a ',
                   tag.a('link', href='http://www.edgewall.org'),
                   ' and some ', tag.strong('strong text')))
        self.assertIsNotNone(find_element(frag, tag='p'))
        self.assertIsNotNone(find_element(frag, tag='a'))
        self.assertIsNotNone(find_element(frag, tag='strong'))
        self.assertIsNone(find_element(frag, tag='input'))
        self.assertIsNone(find_element(frag, tag='textarea'))


class IsSafeOriginTestCase(unittest.TestCase):

    def test_schemes(self):
        uris = ['data:', 'https:']
        self.assertTrue(is_safe_origin(uris, 'data:text/plain,blah'))
        self.assertFalse(is_safe_origin(uris, 'http://127.0.0.1/'))
        self.assertTrue(is_safe_origin(uris, 'https://127.0.0.1/'))
        self.assertFalse(is_safe_origin(uris, 'blob:'))
        self.assertTrue(is_safe_origin(uris, '/path/to'))
        self.assertTrue(is_safe_origin(uris, 'file.txt'))

    def test_wild_card(self):
        uris = ['*']
        self.assertTrue(is_safe_origin(uris, 'data:text/plain,blah'))
        self.assertTrue(is_safe_origin(uris, 'http://127.0.0.1/'))
        self.assertTrue(is_safe_origin(uris, 'https://127.0.0.1/'))
        self.assertTrue(is_safe_origin(uris, 'blob:'))
        self.assertTrue(is_safe_origin(uris, '/path/to'))
        self.assertTrue(is_safe_origin(uris, 'file.txt'))

    def test_hostname(self):
        uris = ['https://example.org/', 'http://example.net']
        self.assertFalse(is_safe_origin(uris, 'data:text/plain,blah'))
        self.assertTrue(is_safe_origin(uris, 'https://example.org'))
        self.assertTrue(is_safe_origin(uris, 'https://example.org/'))
        self.assertTrue(is_safe_origin(uris, 'https://example.org/path/'))
        self.assertTrue(is_safe_origin(uris, 'http://example.net'))
        self.assertTrue(is_safe_origin(uris, 'http://example.net/'))
        self.assertTrue(is_safe_origin(uris, 'http://example.net/path'))
        self.assertFalse(is_safe_origin(uris, 'https://example.com'))
        self.assertFalse(is_safe_origin(uris, 'blob:'))
        self.assertTrue(is_safe_origin(uris, '/path/to'))
        self.assertTrue(is_safe_origin(uris, 'file.txt'))

    def test_path(self):
        uris = ['https://example.org/path/to', 'http://example.net/path/to/']
        self.assertFalse(is_safe_origin(uris, 'https://example.org'))
        self.assertFalse(is_safe_origin(uris, 'https://example.org/'))
        self.assertFalse(is_safe_origin(uris, 'https://example.org/path'))
        self.assertFalse(is_safe_origin(uris, 'https://example.org/path/'))
        self.assertTrue(is_safe_origin(uris, 'https://example.org/path/to'))
        self.assertTrue(is_safe_origin(uris, 'https://example.org/path/to/'))
        self.assertTrue(is_safe_origin(
            uris, 'https://example.org/path/to/image.png'))
        self.assertFalse(is_safe_origin(uris, 'http://example.net'))
        self.assertFalse(is_safe_origin(uris, 'http://example.net/'))
        self.assertFalse(is_safe_origin(uris, 'http://example.net/path'))
        self.assertFalse(is_safe_origin(uris, 'http://example.net/path/'))
        self.assertFalse(is_safe_origin(uris, 'http://example.net/path/to'))
        self.assertTrue(is_safe_origin(uris, 'http://example.net/path/to/'))
        self.assertTrue(is_safe_origin(
            uris, 'http://example.net/path/to/image.png'))
        self.assertFalse(is_safe_origin(uris, 'blob:'))
        self.assertTrue(is_safe_origin(uris, '/path/to'))
        self.assertTrue(is_safe_origin(uris, 'file.txt'))


class ToFragmentTestCase(unittest.TestCase):

    def test_unicode(self):
        rv = to_fragment('blah')
        self.assertEqual(Fragment, type(rv))
        self.assertEqual('blah', unicode(rv))

    def test_fragment(self):
        rv = to_fragment(tag('blah'))
        self.assertEqual(Fragment, type(rv))
        self.assertEqual('blah', unicode(rv))

    def test_element(self):
        rv = to_fragment(tag.p('blah'))
        self.assertEqual(Element, type(rv))
        self.assertEqual('<p>blah</p>', unicode(rv))

    def test_tracerror(self):
        rv = to_fragment(TracError('blah'))
        self.assertEqual(Fragment, type(rv))
        self.assertEqual('blah', unicode(rv))

    def test_tracerror_with_fragment(self):
        message = tag('Powered by ',
                      tag.a('Trac', href='https://trac.edgewall.org/'))
        rv = to_fragment(TracError(message))
        self.assertEqual(Fragment, type(rv))
        self.assertEqual('Powered by <a href="https://trac.edgewall.org/">Trac'
                         '</a>', unicode(rv))

    def test_tracerror_with_element(self):
        message = tag.p('Powered by ',
                        tag.a('Trac', href='https://trac.edgewall.org/'))
        rv = to_fragment(TracError(message))
        self.assertEqual(Element, type(rv))
        self.assertEqual('<p>Powered by <a href="https://trac.edgewall.org/">'
                         'Trac</a></p>', unicode(rv))

    def test_tracerror_with_tracerror_with_fragment(self):
        message = tag('Powered by ',
                      tag.a('Trac', href='https://trac.edgewall.org/'))
        rv = to_fragment(TracError(TracError(message)))
        self.assertEqual(Fragment, type(rv))
        self.assertEqual('Powered by <a href="https://trac.edgewall.org/">Trac'
                         '</a>', unicode(rv))

    def test_tracerror_with_tracerror_with_element(self):
        message = tag.p('Powered by ',
                        tag.a('Trac', href='https://trac.edgewall.org/'))
        rv = to_fragment(TracError(TracError(message)))
        self.assertEqual(Element, type(rv))
        self.assertEqual('<p>Powered by <a href="https://trac.edgewall.org/">'
                         'Trac</a></p>', unicode(rv))

    def test_error(self):
        rv = to_fragment(ValueError('invalid literal for int(): blah'))
        self.assertEqual(Fragment, type(rv))
        self.assertEqual('invalid literal for int(): blah', unicode(rv))

    def test_error_with_fragment(self):
        rv = to_fragment(ValueError(tag('invalid literal for int(): ',
                                        tag.b('blah'))))
        self.assertEqual(Fragment, type(rv))
        self.assertEqual('invalid literal for int(): <b>blah</b>', unicode(rv))

    def test_error_with_error_with_fragment(self):
        v1 = ValueError(tag('invalid literal for int(): ', tag.b('blah')))
        rv = to_fragment(ValueError(v1))
        self.assertEqual(Fragment, type(rv))
        self.assertEqual('invalid literal for int(): <b>blah</b>', unicode(rv))

    def test_gettext(self):
        rv = to_fragment(gettext('%(size)s bytes', size=0))
        self.assertEqual(Fragment, type(rv))
        self.assertEqual('0 bytes', unicode(rv))

    def test_tgettext(self):
        rv = to_fragment(tgettext('Back to %(parent)s',
                                  parent=tag.a('WikiStart',
                                               href='http://localhost/')))
        self.assertEqual(Fragment, type(rv))
        self.assertEqual('Back to <a href="http://localhost/">WikiStart</a>',
                         unicode(rv))

    def test_tracerror_with_gettext(self):
        e = TracError(gettext('%(size)s bytes', size=0))
        rv = to_fragment(e)
        self.assertEqual(Fragment, type(rv))
        self.assertEqual('0 bytes', unicode(rv))

    def test_tracerror_with_tgettext(self):
        e = TracError(tgettext('Back to %(parent)s',
                               parent=tag.a('WikiStart',
                                            href='http://localhost/')))
        rv = to_fragment(e)
        self.assertEqual(Fragment, type(rv))
        self.assertEqual('Back to <a href="http://localhost/">WikiStart</a>',
                         unicode(rv))

    def _ioerror(self, filename):
        try:
            open(filename)
        except IOError as e:
            return e
        else:
            self.fail('IOError not raised')

    def test_ioerror(self):
        rv = to_fragment(self._ioerror(b'./notfound'))
        self.assertEqual(Fragment, type(rv))
        self.assertEqual("[Errno 2] No such file or directory: './notfound'",
                         unicode(rv))

    def test_error_with_ioerror(self):
        e = self._ioerror(b'./notfound')
        rv = to_fragment(ValueError(e))
        self.assertEqual(Fragment, type(rv))
        self.assertEqual("[Errno 2] No such file or directory: './notfound'",
                         unicode(rv))


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(doctest.DocTestSuite(html))
    suite.addTest(unittest.makeSuite(EscapeFragmentTestCase))
    suite.addTest(unittest.makeSuite(HtmlAttributeTestCase))
    suite.addTest(unittest.makeSuite(FragmentTestCase))
    suite.addTest(unittest.makeSuite(XMLElementTestCase))
    suite.addTest(unittest.makeSuite(ElementTestCase))
    suite.addTest(unittest.makeSuite(FormTokenInjectorTestCase))
    suite.addTest(unittest.makeSuite(TracHTMLSanitizerTestCase))
    if genshi:
        suite.addTest(unittest.makeSuite(TracHTMLSanitizerLegacyGenshiTestCase))
    suite.addTest(unittest.makeSuite(FindElementTestCase))
    suite.addTest(unittest.makeSuite(IsSafeOriginTestCase))
    suite.addTest(unittest.makeSuite(ToFragmentTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
