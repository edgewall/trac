# -*- coding: utf-8 -*-

import unittest
from genshi.input import HTML

from trac.util.html import TracHTMLSanitizer


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


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TracHTMLSanitizerTestCase, 'test'))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
