# -*- coding: utf-8 -*-
#
# Copyright (C) 2007-2013 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

from StringIO import StringIO
import doctest
import unittest

from trac.core import TracError
from trac.util import html
from trac.util.html import (
    Element, FormTokenInjector, Fragment, HTML, Markup, TracHTMLSanitizer,
    escape, find_element, genshi, tag, to_fragment, xml
)
from trac.util.translation import gettext, tgettext

class EscapeFragmentTestCase(unittest.TestCase):
    def test_escape_element(self):
        self.assertEqual(Markup(u'<b class="em&#34;ph&#34;">"1 &lt; 2"</b>'),
                         escape(tag.b('"1 < 2"', class_='em"ph"')))
        self.assertEqual(Markup(u'<b class="em&#34;ph&#34;">"1 &lt; 2"</b>'),
                         escape(tag.b('"1 < 2"', class_='em"ph"'),
                                quotes=False))

    def test_escape_fragment(self):
        self.assertEqual(Markup(u'<b class="em&#34;ph&#34;">"1 &lt; 2"</b>'),
                         escape(tag(tag.b('"1 < 2"', class_='em"ph"'))))
        self.assertEqual(Markup(u'<b class="em&#34;ph&#34;">"1 &lt; 2"</b>'),
                         escape(tag(tag.b('"1 < 2"', class_='em"ph"')),
                                    quotes=False))

class FragmentTestCase(unittest.TestCase):
    def test_zeros(self):
        self.assertEqual(Markup(u'0<b>0</b> and <b>0</b>'),
                         Markup(tag(0, tag.b(0L), ' and ', tag.b(0.0))))


class XMLElementTestCase(unittest.TestCase):
    def test_xml(self):
        self.assertEqual(Markup(u'0<a>0</a> and <b>0</b> and <c/> and'
                                ' <d class="[\'a\', \'\', \'b\']"'
                                ' more_="[\'a\']"/>'),
                         Markup(xml(0, xml.a(0L), ' and ', xml.b(0.0),
                                    ' and ', xml.c(None), ' and ',
                                    xml.d('', class_=['a', '', 'b'],
                                          more__=['a']))))

class ElementTestCase(unittest.TestCase):
    def test_tag(self):
        self.assertEqual(Markup(u'0<a>0</a> and <b>0</b> and <c></c>'
                                u' and <d class="a b" more_="[\'a\']"></d>'),
                         Markup(tag(0, tag.a(0L, href=''), ' and ', tag.b(0.0),
                                    ' and ', tag.c(None), ' and ',
                                    tag.d('', class_=['a', '', 'b'],
                                          more__=['a']))))

class FragmentTestCase(unittest.TestCase):
    def test_zeros(self):
        self.assertEqual(Markup(u'0<b>0</b> and <b>0</b>'),
                         Markup(tag(0, tag.b(0L), ' and ', tag.b(0.0))))

class FormTokenInjectorTestCase(unittest.TestCase):
    def test_no_form(self):
        html = '<div><img src="trac.png"/></div>'
        injector = FormTokenInjector('123123', StringIO())
        injector.feed(html)
        injector.close()
        self.assertEqual(html, injector.out.getvalue())

    def test_form_get(self):
        html = '<form method="get"><input name="age" value=""/></form>'
        injector = FormTokenInjector('123123', StringIO())
        injector.feed(html)
        injector.close()
        self.assertEqual(html, injector.out.getvalue())

    def test_form_post(self):
        html = '<form method="POST">%s<input name="age" value=""/></form>'
        injector = FormTokenInjector('123123', StringIO())
        injector.feed(html % '')
        injector.close()
        self.assertEqual(
            html % (
            '<input type="hidden" name="__FORM_TOKEN" value="%s"/>' %
                injector.token),
            injector.out.getvalue())


class TracHTMLSanitizerTestCase(unittest.TestCase):
    def sanitize(self, html):
        return unicode(TracHTMLSanitizer().sanitize(html))

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
        html = u'<div style="top:ｅｘｐｒｅｓｓｉｏｎ(alert())">XSS</div>'
        self.assertEqual('<div>XSS</div>', self.sanitize(html))
        # Fullwidth capital letters
        html = u'<div style="top:ＥＸＰＲＥＳＳＩＯＮ(alert())">XSS</div>'
        self.assertEqual('<div>XSS</div>', self.sanitize(html))
        # IPA extensions
        html = u'<div style="top:expʀessɪoɴ(alert())">XSS</div>'
        self.assertEqual('<div>XSS</div>', self.sanitize(html))

    def test_unicode_url(self):
        # IPA extensions
        html = (
            u'<div style="background-image:uʀʟ(javascript:alert())">XSS</div>'
        )
        self.assertEqual('<div>XSS</div>', self.sanitize(html))


if genshi:
    class TracHTMLSanitizerLegacyGenshiTestCase(TracHTMLSanitizerTestCase):
        def sanitize(self, html):
            return unicode(HTML(html, encoding='utf-8') | TracHTMLSanitizer())

    def test_cross_origin(self):
        def test(expected, content):
            html = HTML(content)
            sanitizer = TracHTMLSanitizer(safe_schemes=['http', 'data'])
            self.assertEqual(expected, unicode(html | sanitizer))

        test(u'<div>x</div>',
             u'<div style="background:url(http://example.org/login)">x</div>')
        test(u'<div style="background:url(data:image/png,...)">x</div>',
             u'<div style="background:url(data:image/png,...)">x</div>')
        test(u'<div>x</div>',
             u'<div style="background:url(//example.net/foo.png)">x</div>')
        test(u'<div style="background:url(/path/to/foo.png)">safe</div>',
             u'<div style="background:url(/path/to/foo.png)">safe</div>')
        test(u'<div style="background:url(../../bar.png)">safe</div>',
             u'<div style="background:url(../../bar.png)">safe</div>')
        test(u'<div style="background:url(qux.png)">safe</div>',
             u'<div style="background:url(qux.png)">safe</div>')


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
                      tag.a('Trac', href='http://trac.edgewall.org/'))
        rv = to_fragment(TracError(message))
        self.assertEqual(Fragment, type(rv))
        self.assertEqual('Powered by <a href="http://trac.edgewall.org/">Trac'
                         '</a>', unicode(rv))

    def test_tracerror_with_element(self):
        message = tag.p('Powered by ',
                        tag.a('Trac', href='http://trac.edgewall.org/'))
        rv = to_fragment(TracError(message))
        self.assertEqual(Element, type(rv))
        self.assertEqual('<p>Powered by <a href="http://trac.edgewall.org/">'
                         'Trac</a></p>', unicode(rv))

    def test_tracerror_with_tracerror_with_fragment(self):
        message = tag('Powered by ',
                      tag.a('Trac', href='http://trac.edgewall.org/'))
        rv = to_fragment(TracError(TracError(message)))
        self.assertEqual(Fragment, type(rv))
        self.assertEqual('Powered by <a href="http://trac.edgewall.org/">Trac'
                         '</a>', unicode(rv))

    def test_tracerror_with_tracerror_with_element(self):
        message = tag.p('Powered by ',
                        tag.a('Trac', href='http://trac.edgewall.org/'))
        rv = to_fragment(TracError(TracError(message)))
        self.assertEqual(Element, type(rv))
        self.assertEqual('<p>Powered by <a href="http://trac.edgewall.org/">'
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


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(doctest.DocTestSuite(html))
    suite.addTest(unittest.makeSuite(EscapeFragmentTestCase))
    suite.addTest(unittest.makeSuite(FragmentTestCase))
    suite.addTest(unittest.makeSuite(XMLElementTestCase))
    suite.addTest(unittest.makeSuite(ElementTestCase))
    suite.addTest(unittest.makeSuite(FormTokenInjectorTestCase))
    suite.addTest(unittest.makeSuite(TracHTMLSanitizerTestCase))
    if genshi:
        suite.addTest(unittest.makeSuite(TracHTMLSanitizerLegacyGenshiTestCase))
    suite.addTest(unittest.makeSuite(FindElementTestCase))
    suite.addTest(unittest.makeSuite(ToFragmentTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
