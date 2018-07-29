# -*- coding: utf-8 -*-
#
# Copyright (C) 2007-2018 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import unittest
from genshi.builder import Element, Fragment, tag
from genshi.input import HTML

import trac.tests.compat
from trac.core import TracError
from trac.util.html import TracHTMLSanitizer, find_element, is_safe_origin, \
                           to_fragment
from trac.util.translation import gettext, tgettext


class TracHTMLSanitizerTestCase(unittest.TestCase):
    def test_expression(self):
        html = HTML('<div style="top:expression(alert())">XSS</div>',
                    encoding='utf-8')
        self.assertEqual('<div>XSS</div>', unicode(html | TracHTMLSanitizer()))

    def test_capital_expression(self):
        html = HTML('<div style="top:EXPRESSION(alert())">XSS</div>',
                    encoding='utf-8')
        self.assertEqual('<div>XSS</div>', unicode(html | TracHTMLSanitizer()))

    def test_expression_with_comments(self):
        html = HTML(r'<div style="top:exp/**/ression(alert())">XSS</div>',
                    encoding='utf-8')
        self.assertEqual('<div style="top:exp ression(alert())">XSS</div>',
                         unicode(html | TracHTMLSanitizer()))
        html = HTML(r'<div style="top:exp//**/**/ression(alert())">XSS</div>',
                    encoding='utf-8')
        self.assertEqual(
            '<div style="top:exp/ **/ression(alert())">XSS</div>',
            unicode(html | TracHTMLSanitizer()))
        html = HTML(r'<div style="top:ex/*p*/ression(alert())">XSS</div>',
                    encoding='utf-8')
        self.assertEqual('<div style="top:ex ression(alert())">XSS</div>',
                         unicode(html | TracHTMLSanitizer()))

    def test_url_with_javascript(self):
        html = HTML('<div style="background-image:url(javascript:alert())">'
                    'XSS</div>', encoding='utf-8')
        self.assertEqual('<div>XSS</div>', unicode(html | TracHTMLSanitizer()))

    def test_capital_url_with_javascript(self):
        html = HTML('<div style="background-image:URL(javascript:alert())">'
                    'XSS</div>', encoding='utf-8')
        self.assertEqual('<div>XSS</div>', unicode(html | TracHTMLSanitizer()))

    def test_unicode_escapes(self):
        html = HTML(r'<div style="top:exp\72 ess\000069 on(alert())">'
                    r'XSS</div>', encoding='utf-8')
        self.assertEqual('<div>XSS</div>', unicode(html | TracHTMLSanitizer()))
        # escaped backslash
        html = HTML(r'<div style="top:exp\5c ression(alert())">XSS</div>',
                    encoding='utf-8')
        self.assertEqual(r'<div style="top:exp\\ression(alert())">XSS</div>',
                         unicode(html | TracHTMLSanitizer()))
        html = HTML(r'<div style="top:exp\5c 72 ession(alert())">XSS</div>',
                    encoding='utf-8')
        self.assertEqual(r'<div style="top:exp\\72 ession(alert())">XSS</div>',
                         unicode(html | TracHTMLSanitizer()))
        # escaped control characters
        html = HTML(r'<div style="top:exp\000000res\1f sion(alert())">'
                    r'XSS</div>', encoding='utf-8')
        self.assertEqual('<div style="top:exp res sion(alert())">XSS</div>',
                         unicode(html | TracHTMLSanitizer()))

    def test_backslash_without_hex(self):
        html = HTML(r'<div style="top:e\xp\ression(alert())">XSS</div>',
                    encoding='utf-8')
        self.assertEqual('<div>XSS</div>', unicode(html | TracHTMLSanitizer()))
        html = HTML(r'<div style="top:e\\xp\\ression(alert())">XSS</div>',
                    encoding='utf-8')
        self.assertEqual(r'<div style="top:e\\xp\\ression(alert())">'
                         'XSS</div>',
                         unicode(html | TracHTMLSanitizer()))

    def test_unsafe_props(self):
        html = HTML('<div style="POSITION:RELATIVE">XSS</div>',
                    encoding='utf-8')
        self.assertEqual('<div>XSS</div>', unicode(html | TracHTMLSanitizer()))
        html = HTML('<div style="position:STATIC">safe</div>',
                    encoding='utf-8')
        self.assertEqual('<div style="position:STATIC">safe</div>',
                         unicode(html | TracHTMLSanitizer()))

        html = HTML('<div style="behavior:url(test.htc)">XSS</div>',
                    encoding='utf-8')
        self.assertEqual('<div>XSS</div>', unicode(html | TracHTMLSanitizer()))

        html = HTML('<div style="-ms-behavior:url(test.htc) url(#obj)">'
                    'XSS</div>', encoding='utf-8')
        self.assertEqual('<div>XSS</div>', unicode(html | TracHTMLSanitizer()))

        html = HTML("""<div style="-o-link:'javascript:alert(1)';"""
                    """-o-link-source:current">XSS</div>""", encoding='utf-8')
        self.assertEqual('<div>XSS</div>', unicode(html | TracHTMLSanitizer()))

        html = HTML("""<div style="-moz-binding:url(xss.xbl)">XSS</div>""",
                    encoding='utf-8')
        self.assertEqual('<div>XSS</div>', unicode(html | TracHTMLSanitizer()))

    def test_nagative_margin(self):
        html = HTML('<div style="margin-top:-9999px">XSS</div>',
                    encoding='utf-8')
        self.assertEqual('<div>XSS</div>', unicode(html | TracHTMLSanitizer()))
        html = HTML('<div style="margin:0 -9999px">XSS</div>',
                    encoding='utf-8')
        self.assertEqual('<div>XSS</div>', unicode(html | TracHTMLSanitizer()))

    def test_css_hack(self):
        html = HTML('<div style="*position:static">XSS</div>',
                    encoding='utf-8')
        self.assertEqual('<div>XSS</div>', unicode(html | TracHTMLSanitizer()))

        html = HTML('<div style="_margin:-10px">XSS</div>', encoding='utf-8')
        self.assertEqual('<div>XSS</div>', unicode(html | TracHTMLSanitizer()))

    def test_property_name(self):
        html = HTML('<div style="display:none;border-left-color:red;'
                    'user_defined:1;-moz-user-selct:-moz-all">prop</div>',
                    encoding='utf-8')
        self.assertEqual('<div style="display:none; border-left-color:red'
                         '">prop</div>',
                         unicode(html | TracHTMLSanitizer()))

    def test_unicode_expression(self):
        # Fullwidth small letters
        html = HTML(u'<div style="top:ｅｘｐｒｅｓｓｉｏｎ(alert())">'
                    u'XSS</div>')
        self.assertEqual('<div>XSS</div>', unicode(html | TracHTMLSanitizer()))
        # Fullwidth capital letters
        html = HTML(u'<div style="top:ＥＸＰＲＥＳＳＩＯＮ(alert())">'
                    u'XSS</div>')
        self.assertEqual('<div>XSS</div>', unicode(html | TracHTMLSanitizer()))
        # IPA extensions
        html = HTML(u'<div style="top:expʀessɪoɴ(alert())">'
                    u'XSS</div>')
        self.assertEqual('<div>XSS</div>', unicode(html | TracHTMLSanitizer()))

    def test_unicode_url(self):
        # IPA extensions
        html = HTML(u'<div style="background-image:uʀʟ(javascript:alert())">'
                    u'XSS</div>')
        self.assertEqual('<div>XSS</div>', unicode(html | TracHTMLSanitizer()))

    def test_cross_origin(self):
        def test(expected, content):
            html = HTML(content)
            sanitizer = TracHTMLSanitizer(
                safe_schemes=['http', 'data'],
                safe_origins=['data:', 'http://example.net',
                              'https://example.org/'])
            self.assertEqual(expected, unicode(html | sanitizer))

        test(u'<img src="data:image/png,...."/>',
             u'<img src="data:image/png,...."/>')
        test(u'<img src="http://example.org/login" crossorigin="anonymous"/>',
             u'<img src="http://example.org/login"/>')
        test(u'<img src="http://example.org/login" crossorigin="anonymous"/>',
             u'<img src="http://example.org/login"'
             u' crossorigin="use-credentials"/>')
        test(u'<img src="http://example.net/bar.png"/>',
             u'<img src="http://example.net/bar.png"/>')
        test(u'<img src="http://example.net:443/qux.png"'
             u' crossorigin="anonymous"/>',
             u'<img src="http://example.net:443/qux.png"/>')
        test(u'<img src="/path/foo.png"/>', u'<img src="/path/foo.png"/>')
        test(u'<img src="../../bar.png"/>', u'<img src="../../bar.png"/>')
        test(u'<img src="qux.png"/>', u'<img src="qux.png"/>')

        test(u'<div>x</div>',
             u'<div style="background:url(http://example.org/login)">x</div>')
        test(u'<div style="background:url(http://example.net/1.png)">x</div>',
             u'<div style="background:url(http://example.net/1.png)">x</div>')
        test(u'<div>x</div>',
             u'<div style="background:url(http://example.net:443/1.png)">'
             u'x</div>')
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

    def _ioerror(self, filename):
        try:
            open(filename)
        except IOError as e:
            return e
        else:
            self.fail('IOError not raised')

    def test_ioerror(self):
        rv = to_fragment(self._ioerror('./notfound'))
        self.assertEqual(Fragment, type(rv))
        self.assertEqual("[Errno 2] No such file or directory: './notfound'",
                         unicode(rv))

    def test_error_with_ioerror(self):
        e = self._ioerror('./notfound')
        rv = to_fragment(ValueError(e))
        self.assertEqual(Fragment, type(rv))
        self.assertEqual("[Errno 2] No such file or directory: './notfound'",
                         unicode(rv))


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TracHTMLSanitizerTestCase))
    suite.addTest(unittest.makeSuite(FindElementTestCase))
    suite.addTest(unittest.makeSuite(IsSafeOriginTestCase))
    suite.addTest(unittest.makeSuite(ToFragmentTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
