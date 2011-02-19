# -*- coding: utf-8 -*-

import unittest

from trac.util.text import expandtabs, javascript_quote, \
                           normalize_whitespace, to_unicode, \
                           text_width, wrap


class ToUnicodeTestCase(unittest.TestCase):

    def test_explicit_charset(self):
        uc = to_unicode('\xc3\xa7', 'utf-8')
        assert isinstance(uc, unicode)
        self.assertEquals(u'\xe7', uc)

    def test_explicit_charset_with_replace(self):
        uc = to_unicode('\xc3', 'utf-8')
        assert isinstance(uc, unicode)
        self.assertEquals(u'\xc3', uc)

    def test_implicit_charset(self):
        uc = to_unicode('\xc3\xa7')
        assert isinstance(uc, unicode)
        self.assertEquals(u'\xe7', uc)

    def test_from_exception_using_unicode_args(self):
        u = u'\uB144'
        try:
            raise ValueError, '%s is not a number.' % u
        except ValueError, e:
            self.assertEquals(u'\uB144 is not a number.', to_unicode(e))

    def test_from_exception_using_str_args(self):
        u = u'Das Ger\xe4t oder die Ressource ist belegt'
        try:
            raise ValueError, u.encode('utf-8')
        except ValueError, e:
            self.assertEquals(u, to_unicode(e))


class ExpandtabsTestCase(unittest.TestCase):
    def test_empty(self):
        x = expandtabs('', ignoring='\0')
        self.assertEquals('', x)
    def test_ingoring(self):
        x = expandtabs('\0\t', ignoring='\0')
        self.assertEquals('\0        ', x)
    def test_tabstops(self):
        self.assertEquals('        ', expandtabs('       \t'))
        self.assertEquals('                ', expandtabs('\t\t'))


class JavascriptQuoteTestCase(unittest.TestCase):
    def test_quoting(self):
        self.assertEqual(r'Quote \" in text',
                         javascript_quote('Quote " in text'))
        self.assertEqual(r'\\\"\b\f\n\r\t\'',
                         javascript_quote('\\"\b\f\n\r\t\''))
        self.assertEqual(r'\u0002\u001e',
                         javascript_quote('\x02\x1e'))
        self.assertEqual(r'\u0026\u003c\u003e',
                         javascript_quote('&<>'))


class WhitespaceTestCase(unittest.TestCase):
    def test_default(self):
        self.assertEqual(u'This is text ',
            normalize_whitespace(u'Th\u200bis\u00a0is te\u200bxt\u00a0'))
        self.assertEqual(u'Some other text',
            normalize_whitespace(u'Some\tother\ntext\r', to_space='\t\n',
                                 remove='\r'))


class TextWidthTestCase(unittest.TestCase):
    def test_single(self):
        def tw1(text):
            return text_width(text, ambiwidth=1)
        self.assertEqual(8, tw1(u'Alphabet'))
        self.assertEqual(16, tw1('east asian width'))
        self.assertEqual(16, tw1(u'ひらがなカタカナ'))
        self.assertEqual(21, tw1(u'色は匂えど…酔ひもせず'))

    def test_double(self):
        def tw2(text):
            return text_width(text, ambiwidth=2)
        self.assertEqual(8, tw2(u'Alphabet'))
        self.assertEqual(16, tw2('east asian width'))
        self.assertEqual(16, tw2(u'ひらがなカタカナ'))
        self.assertEqual(22, tw2(u'色は匂えど…酔ひもせず'))


class WrapTestCase(unittest.TestCase):
    def test_wrap_ambiwidth_single(self):
        text = u'Lorem ipsum dolor sit amet, consectetur adipisicing ' + \
               u'elit, sed do eiusmod tempor incididunt ut labore et ' + \
               u'dolore magna aliqua. Ut enim ad minim veniam, quis ' + \
               u'nostrud exercitation ullamco laboris nisi ut aliquip ex ' + \
               u'ea commodo consequat. Duis aute irure dolor in ' + \
               u'reprehenderit in voluptate velit esse cillum dolore eu ' + \
               u'fugiat nulla pariatur. Excepteur sint occaecat ' + \
               u'cupidatat non proident, sunt in culpa qui officia ' + \
               u'deserunt mollit anim id est laborum.'
        wrapped = u"""\
> Lorem ipsum dolor sit amet, consectetur adipisicing elit,
| sed do eiusmod tempor incididunt ut labore et dolore
| magna aliqua. Ut enim ad minim veniam, quis nostrud
| exercitation ullamco laboris nisi ut aliquip ex ea
| commodo consequat. Duis aute irure dolor in reprehenderit
| in voluptate velit esse cillum dolore eu fugiat nulla
| pariatur. Excepteur sint occaecat cupidatat non proident,
| sunt in culpa qui officia deserunt mollit anim id est
| laborum."""
        self.assertEqual(wrapped, wrap(text, 59, '> ', '| ', '\n'))

    def test_wrap_ambiwidth_double(self):
        text = u'Trac は BSD ライセンスのもとで配布されて' + \
               u'います。[1:]このライセンスの全文は、𠀋' + \
               u'配布ファイルに含まれている[3:CОPYING]ファ' + \
               u'イルと同じものが[2:オンライン]で参照でき' \
               u'ます。'
        wrapped = u"""\
> Trac は BSD ライセンスのもとで配布されています。[1:]この
| ライセンスの全文は、𠀋配布ファイルに含まれている
| [3:CОPYING]ファイルと同じものが[2:オンライン]で参照でき
| ます。"""
        self.assertEqual(wrapped, wrap(text, 59, '> ', '| ', '\n',
                                       ambiwidth=2))


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(ToUnicodeTestCase, 'test'))
    suite.addTest(unittest.makeSuite(ExpandtabsTestCase, 'test'))
    suite.addTest(unittest.makeSuite(JavascriptQuoteTestCase, 'test'))
    suite.addTest(unittest.makeSuite(WhitespaceTestCase, 'test'))
    suite.addTest(unittest.makeSuite(TextWidthTestCase, 'test'))
    suite.addTest(unittest.makeSuite(WrapTestCase, 'test'))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
