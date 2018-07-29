# -*- coding: utf-8 -*-
#
# Copyright (C) 2006-2018 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import os
import socket
import unittest
from StringIO import StringIO

import trac.tests.compat
from trac.util.text import (
    _get_default_ambiwidth, empty, expandtabs, fix_eol, javascript_quote,
    levenshtein_distance, normalize_whitespace, print_table,
    quote_query_string, shorten_line, strip_line_ws, stripws, sub_vars,
    text_width, to_js_string, to_unicode, to_utf8, unicode_from_base64,
    unicode_quote, unicode_quote_plus, unicode_to_base64, unicode_unquote,
    unicode_urlencode, wrap)


class ToUnicodeTestCase(unittest.TestCase):
    def test_explicit_charset(self):
        uc = to_unicode('\xc3\xa7', 'utf-8')
        self.assertIsInstance(uc, unicode)
        self.assertEqual(u'\xe7', uc)

    def test_explicit_charset_with_replace(self):
        uc = to_unicode('\xc3', 'utf-8')
        self.assertIsInstance(uc, unicode)
        self.assertEqual(u'\xc3', uc)

    def test_implicit_charset(self):
        uc = to_unicode('\xc3\xa7')
        self.assertIsInstance(uc, unicode)
        self.assertEqual(u'\xe7', uc)

    def test_from_exception_using_unicode_args(self):
        u = u'\uB144'
        try:
            raise ValueError, '%s is not a number.' % u
        except ValueError as e:
            self.assertEqual(u'\uB144 is not a number.', to_unicode(e))

    def test_from_exception_using_str_args(self):
        u = u'Das Ger\xe4t oder die Ressource ist belegt'
        try:
            raise ValueError, u.encode('utf-8')
        except ValueError as e:
            self.assertEqual(u, to_unicode(e))

    def test_from_windows_error(self):
        try:
            os.stat('non/existent/file.txt')
        except OSError as e:
            uc = to_unicode(e)
            self.assertIsInstance(uc, unicode, uc)
            self.assertTrue(uc.startswith('[Error '), uc)
            self.assertIn(e.strerror.decode('mbcs'), uc)

    def test_from_socket_error(self):
        for res in socket.getaddrinfo('127.0.0.1', 65536, 0,
                                      socket.SOCK_STREAM):
            af, socktype, proto, canonname, sa = res
            s = socket.socket(af, socktype, proto)
            try:
                s.connect(sa)
            except socket.error as e:
                uc = to_unicode(e)
                self.assertIsInstance(uc, unicode, uc)
                if hasattr(e, 'strerror'):
                    self.assertIn(e.strerror.decode('mbcs'), uc)

    if os.name != 'nt':
        del test_from_windows_error
        del test_from_socket_error


class ExpandtabsTestCase(unittest.TestCase):
    def test_empty(self):
        x = expandtabs('', ignoring='\0')
        self.assertEqual('', x)
    def test_ingoring(self):
        x = expandtabs('\0\t', ignoring='\0')
        self.assertEqual('\0        ', x)
    def test_tabstops(self):
        self.assertEqual('        ', expandtabs('       \t'))
        self.assertEqual('                ', expandtabs('\t\t'))


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
        self.assertEqual(r'\u2028\u2029',
                         javascript_quote(u'\u2028\u2029'))


class ToJsStringTestCase(unittest.TestCase):
    def test_(self):
        self.assertEqual(r'"Quote \" in text"',
                         to_js_string('Quote " in text'))
        self.assertEqual(r'''"\\\"\b\f\n\r\t'"''',
                         to_js_string('\\"\b\f\n\r\t\''))
        self.assertEqual(r'"\u0002\u001e"',
                         to_js_string('\x02\x1e'))
        self.assertEqual(r'"\u0026\u003c\u003e"',
                         to_js_string('&<>'))
        self.assertEqual('""',
                         to_js_string(''))
        self.assertEqual('""',
                         to_js_string(None))
        self.assertEqual(r'"\u2028\u2029"',
                         to_js_string(u'\u2028\u2029'))


class UnicodeQuoteTestCase(unittest.TestCase):
    def test_unicode_quote(self):
        self.assertEqual(u'the%20%C3%9C%20thing',
                         unicode_quote(u'the Ü thing'))
        self.assertEqual(u'%2520%C3%9C%20%2520',
                         unicode_quote(u'%20Ü %20'))

    def test_unicode_quote_plus(self):
        self.assertEqual(u'the+%C3%9C+thing',
                         unicode_quote_plus(u'the Ü thing'))
        self.assertEqual(u'%2520%C3%9C+%2520',
                         unicode_quote_plus(u'%20Ü %20'))

    def test_unicode_unquote(self):
        u = u'the Ü thing'
        up = u'%20Ü %20'
        self.assertEqual(u, unicode_unquote(unicode_quote(u)))
        self.assertEqual(up, unicode_unquote(unicode_quote(up)))

    def test_unicode_urlencode(self):
        self.assertEqual('thing=%C3%9C&%C3%9C=thing&%C3%9Cthing',
                         unicode_urlencode({u'Ü': 'thing',
                                            'thing': u'Ü',
                                            u'Üthing': empty}))


class QuoteQueryStringTestCase(unittest.TestCase):
    def test_quote(self):
        text = u'type=the Ü thing&component=comp\x7fonent'
        self.assertEqual('type=the+%C3%9C+thing&component=comp%7Fonent',
                         quote_query_string(text))


class ToUtf8TestCase(unittest.TestCase):
    def test_unicode(self):
        self.assertEqual('à', to_utf8('à'))
        self.assertEqual('ç', to_utf8('ç'))

    def test_boolean(self):
        self.assertEqual('True', to_utf8(True))
        self.assertEqual('False', to_utf8(False))

    def test_int(self):
        self.assertEqual('-1', to_utf8(-1))
        self.assertEqual('0', to_utf8(0))
        self.assertEqual('1', to_utf8(1))

    def test_utf8(self):
        self.assertEqual('à', to_utf8(u'à'))
        self.assertEqual('ç', to_utf8(u'ç'))

    def test_exception_with_utf8_message(self):
        self.assertEqual('thė mèssägē', to_utf8(Exception('thė mèssägē')))

    def test_exception_with_unicode_message(self):
        self.assertEqual('thė mèssägē', to_utf8(Exception(u'thė mèssägē')))


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


class PrintTableTestCase(unittest.TestCase):
    def test_single_bytes(self):
        data = (
            ('Trac 0.12', '2010-06-13', 'Babel'),
            ('Trac 0.11', '2008-06-22', 'Genshi'),
            ('Trac 0.10', '2006-09-28', 'Zengia'),
            ('Trac 0.9',  '2005-10-31', 'Vodun'),
            ('Trac 0.8',  '2004-11-15', 'Qualia'),
            ('Trac 0.7',  '2004-05-18', 'Fulci'),
            ('Trac 0.6',  '2004-03-23', 'Solanum'),
            ('Trac 0.5',  '2004-02-23', 'Incognito'),
        )
        headers = ('Version', 'Date', 'Name')
        expected = """\

Version     Date         Name
----------------------------------
Trac 0.12 | 2010-06-13 | Babel
Trac 0.11 | 2008-06-22 | Genshi
Trac 0.10 | 2006-09-28 | Zengia
Trac 0.9  | 2005-10-31 | Vodun
Trac 0.8  | 2004-11-15 | Qualia
Trac 0.7  | 2004-05-18 | Fulci
Trac 0.6  | 2004-03-23 | Solanum
Trac 0.5  | 2004-02-23 | Incognito

"""
        self._validate_print_table(expected, data, headers=headers, sep=' | ',
                                   ambiwidth=1)

    def test_various_types(self):
        data = (
            ('NoneType', 'None',  None),
            ('bool',     'True',  True),
            ('bool',     'False', False),
            ('int',      '0',     0),
            ('float',    '0.0',   0.0),
        )
        expected = u"""\

NoneType | None  |
bool     | True  | True
bool     | False | False
int      | 0     | 0
float    | 0.0   | 0.0

"""
        self._validate_print_table(expected, data, sep=' | ', ambiwidth=1)

    def test_ambiwidth_1(self):
        data = (
            ('foo@localhost', 'foo@localhost'),
            (u'bar@….com', 'bar@example.com'),
        )
        headers = ('Obfuscated', 'Email')
        expected = u"""\

Obfuscated      Email
-------------------------------
foo@localhost | foo@localhost
bar@….com     | bar@example.com

"""
        self._validate_print_table(expected, data, headers=headers, sep=' | ',
                                   ambiwidth=1)

    def test_ambiwidth_2(self):
        data = (
            ('foo@localhost', 'foo@localhost'),
            (u'bar@….com', 'bar@example.com'),
        )
        headers = ('Obfuscated', 'Email')
        expected = u"""\

Obfuscated      Email
-------------------------------
foo@localhost | foo@localhost
bar@….com    | bar@example.com

"""
        self._validate_print_table(expected, data, headers=headers, sep=' | ',
                                   ambiwidth=2)

    def test_multilines_in_cell(self):
        data = (
            (41, 'Trac', 'Trac-Hacks'),
            (42, 'blah', 'foo\r\nbar\r\n'),
            (43, 'alfa\r\nbravo\r\n', 'zero\r\none\r\ntwo'),
        )
        headers = ('Id', 'Column 1', 'Column 2')
        expected = u"""\

Id   Column 1   Column 2
--------------------------
41 | Trac     | Trac-Hacks
42 | blah     | foo
   |          | bar
43 | alfa     | zero
   | bravo    | one
   |          | two

"""
        self._validate_print_table(expected, data, headers=headers, sep=' | ')

    def _validate_print_table(self, expected, data, **kwargs):
        out = StringIO()
        kwargs['out'] = out
        print_table(data, **kwargs)
        self.assertEqual(expected.encode('utf-8'),
                         strip_line_ws(out.getvalue(), leading=False))


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


class FixEolTestCase(unittest.TestCase):
    def test_mixed_eol(self):
        text = u'\nLine 2\rLine 3\r\nLine 4\n\r'
        self.assertEqual(u'\nLine 2\nLine 3\nLine 4\n\n',
                         fix_eol(text, '\n'))
        self.assertEqual(u'\rLine 2\rLine 3\rLine 4\r\r',
                         fix_eol(text, '\r'))
        self.assertEqual(u'\r\nLine 2\r\nLine 3\r\nLine 4\r\n\r\n',
                         fix_eol(text, '\r\n'))


class UnicodeBase64TestCase(unittest.TestCase):
    def test_to_and_from_base64_unicode(self):
        text = u'Trac は ØÆÅ'
        text_base64 = unicode_to_base64(text)
        self.assertEqual('VHJhYyDjga8gw5jDhsOF', text_base64)
        self.assertEqual(text, unicode_from_base64(text_base64))

    def test_to_and_from_base64_whitespace(self):
        # test that removing whitespace does not affect conversion
        text = 'a space: '
        text_base64 = unicode_to_base64(text)
        self.assertEqual('YSBzcGFjZTog', text_base64)
        self.assertEqual(text, unicode_from_base64(text_base64))
        text = 'two newlines: \n\n'
        text_base64 = unicode_to_base64(text)
        self.assertEqual('dHdvIG5ld2xpbmVzOiAKCg==', text_base64)
        self.assertEqual(text, unicode_from_base64(text_base64))
        text = 'a test string ' * 10000
        text_base64_strip = unicode_to_base64(text)
        text_base64_no_strip = unicode_to_base64(text, strip_newlines=False)
        self.assertNotEqual(text_base64_strip, text_base64_no_strip)
        self.assertEqual(text, unicode_from_base64(text_base64_strip))
        self.assertEqual(text, unicode_from_base64(text_base64_no_strip))


class StripwsTestCase(unittest.TestCase):
    def test_stripws(self):
        self.assertEqual(u'stripws',
                         stripws(u' \u200b\t\u3000stripws \u200b\t\u2008'))
        self.assertEqual(u'stripws \u3000\t',
                         stripws(u'\u200b\t\u2008 stripws \u3000\t',
                                 trailing=False))
        self.assertEqual(u' \t\u3000stripws',
                         stripws(u' \t\u3000stripws \u200b\t\u2008',
                                 leading=False))
        self.assertEqual(u' \t\u3000stripws \u200b\t\u2008',
                         stripws(u' \t\u3000stripws \u200b\t\u2008',
                                 leading=False, trailing=False))


class LevenshteinDistanceTestCase(unittest.TestCase):
    def test_distance(self):
        self.assertEqual(5, levenshtein_distance('kitten', 'sitting'))
        self.assertEqual(1, levenshtein_distance('wii', 'wiki'))
        self.assertEqual(2, levenshtein_distance('comfig', 'config'))
        self.assertEqual(5, levenshtein_distance('update', 'upgrade'))
        self.assertEqual(0, levenshtein_distance('milestone', 'milestone'))


class SubVarsTestCase(unittest.TestCase):
    def test_sub_vars(self):
        subtext = sub_vars("$USER's tickets for '$COMPONENT', $MILESTONE",
                           {'USER': 'user1', 'COMPONENT': 'component1'})
        self.assertEqual("user1's tickets for 'component1', $MILESTONE",
                         subtext)


class ShortenLineTestCase(unittest.TestCase):

    def test_less_than_maxlen(self):
        text = '123456789'
        self.assertEqual(text, shorten_line(text, 10))

    def test_equalto_maxlen(self):
        text = '1234567890'
        self.assertEqual(text, shorten_line(text, 10))

    def test_greater_than_maxlen(self):
        text = 'word word word word'
        self.assertEqual('word word ...', shorten_line(text, 15))
        text = 'abcdefghij'
        self.assertEqual('abcde ...', shorten_line(text, 9))


class DefaultAmbiwidthTestCase(unittest.TestCase):

    def setUp(self):
        self.environ = os.environ.copy()

    def tearDown(self):
        for name in set(os.environ) - set(self.environ):
            del os.environ[name]
        os.environ.update(self.environ)

    def _unset_locale_envs(self):
        for name in ('LANGUAGE', 'LC_ALL', 'LC_MESSAGES', 'LANG'):
            if name in os.environ:
                del os.environ[name]

    def _test_ambiwidth(self, expected, envs):
        self._unset_locale_envs()
        os.environ.update(envs)
        self.assertEqual(expected, _get_default_ambiwidth())

    def test_no_locale_envs(self):
        self._unset_locale_envs()
        self.assertEqual(1, _get_default_ambiwidth())

    def test_language(self):
        self._test_ambiwidth(1, {'LANGUAGE': 'C'})
        self._test_ambiwidth(1, {'LANGUAGE': 'POSIX'})
        self._test_ambiwidth(1, {'LANGUAGE': 'de_DE'})
        self._test_ambiwidth(2, {'LANGUAGE': 'ko'})
        self._test_ambiwidth(2, {'LANGUAGE': 'ko_KR'})
        self._test_ambiwidth(2, {'LANGUAGE': 'ja'})
        self._test_ambiwidth(2, {'LANGUAGE': 'ja_JP'})
        self._test_ambiwidth(2, {'LANGUAGE': 'zh_CN'})
        self._test_ambiwidth(2, {'LANGUAGE': 'zh_TW'})
        self._test_ambiwidth(1, {'LANGUAGE': 'en_US:ja:zh_TW'})
        self._test_ambiwidth(2, {'LANGUAGE': 'zh_CN:en:ko'})
        self._test_ambiwidth(1, {'LANGUAGE': '*****'})

    def test_simple_locale_env(self):
        for name in ('LC_ALL', 'LC_MESSAGES', 'LANG'):
            self._test_ambiwidth(1, {name: 'C'})
            self._test_ambiwidth(1, {name: 'POSIX'})
            self._test_ambiwidth(1, {name: 'en_US.UTF8'})
            self._test_ambiwidth(1, {name: 'de_DE.UTF8'})
            self._test_ambiwidth(2, {name: 'ko_KR.UTF8'})
            self._test_ambiwidth(2, {name: 'ja_JP.UTF8'})
            self._test_ambiwidth(2, {name: 'zh_CN.UTF8'})
            self._test_ambiwidth(2, {name: 'zh_TW.UTF8'})
            self._test_ambiwidth(1, {name: '*****'})

    def test_combined_locale_envs(self):
        os.environ.update({'LANGUAGE': 'en_US',
                           'LC_ALL': 'zh_TW.UTF8', 'LC_MESSAGES': 'de_DE.UTF8',
                           'LANG': 'ko_KR.UTF8'})
        self.assertEqual(1, _get_default_ambiwidth())
        del os.environ['LANGUAGE']
        self.assertEqual(2, _get_default_ambiwidth())
        del os.environ['LC_ALL']
        self.assertEqual(1, _get_default_ambiwidth())
        del os.environ['LC_MESSAGES']
        self.assertEqual(2, _get_default_ambiwidth())
        del os.environ['LANG']
        self.assertEqual(1, _get_default_ambiwidth())


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(ToUnicodeTestCase))
    suite.addTest(unittest.makeSuite(ExpandtabsTestCase))
    suite.addTest(unittest.makeSuite(UnicodeQuoteTestCase))
    suite.addTest(unittest.makeSuite(JavascriptQuoteTestCase))
    suite.addTest(unittest.makeSuite(ToJsStringTestCase))
    suite.addTest(unittest.makeSuite(QuoteQueryStringTestCase))
    suite.addTest(unittest.makeSuite(ToUtf8TestCase))
    suite.addTest(unittest.makeSuite(WhitespaceTestCase))
    suite.addTest(unittest.makeSuite(TextWidthTestCase))
    suite.addTest(unittest.makeSuite(PrintTableTestCase))
    suite.addTest(unittest.makeSuite(WrapTestCase))
    suite.addTest(unittest.makeSuite(FixEolTestCase))
    suite.addTest(unittest.makeSuite(UnicodeBase64TestCase))
    suite.addTest(unittest.makeSuite(StripwsTestCase))
    suite.addTest(unittest.makeSuite(LevenshteinDistanceTestCase))
    suite.addTest(unittest.makeSuite(SubVarsTestCase))
    suite.addTest(unittest.makeSuite(ShortenLineTestCase))
    if os.name != 'nt':
        suite.addTest(unittest.makeSuite(DefaultAmbiwidthTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
