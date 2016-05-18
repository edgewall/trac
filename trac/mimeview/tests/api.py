# -*- coding: utf-8 -*-
#
# Copyright (C) 2006-2013 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import doctest
import unittest
from StringIO import StringIO

from genshi import Stream, Namespace
from genshi.core import Attrs, TEXT, START, END
from genshi.input import HTMLParser

import trac.tests.compat
from trac.core import Component, implements
from trac.test import EnvironmentStub, MockRequest
from trac.mimeview import api
from trac.mimeview.api import get_mimetype, IContentConverter, Mimeview, \
                              _group_lines
from trac.web.api import RequestDone


class GetMimeTypeTestCase(unittest.TestCase):

    def test_from_suffix_using_MIME_MAP(self):
        self.assertEqual('text/plain', get_mimetype('README', None))
        self.assertEqual('text/plain', get_mimetype('README.txt', None))

    def test_from_suffix_using_mimetypes(self):
        accepted = ('image/png', 'image/x-png')
        self.assertTrue(get_mimetype('doc/trac_logo.png', None) in accepted)

    def test_from_content_using_CONTENT_RE(self):
        self.assertEqual('text/x-python',
                         get_mimetype('xxx', """
#!/usr/bin/python
# This is a python script
"""))
        self.assertEqual('text/x-python',
                         get_mimetype('xxx', """
#!/usr/bin/env python
# This is a python script
"""))
        self.assertEqual('text/x-ksh',
                         get_mimetype('xxx', """
#!/bin/ksh
# This is a shell script
"""))
        self.assertEqual('text/x-python',
                         get_mimetype('xxx', """
# -*- Python -*-
# This is a python script
"""))
        self.assertEqual('text/x-ruby',
                         get_mimetype('xxx', """
# -*- mode: ruby -*-
# This is a ruby script
"""))
        self.assertEqual('text/x-python',
                         get_mimetype('xxx', ' ' * 2000 + '# vim: ft=python'))

    def test_from_content_using_is_binary(self):
        self.assertEqual('application/octet-stream',
                         get_mimetype('xxx', "abc\0xyz"))


class MimeviewTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=False,
            enable=['%s.%s' % (self.__module__, c)
                    for c in ['Converter0', 'Converter1', 'Converter2']])

    def tearDown(self):
        pass

    def test_get_supported_conversions(self):
        class Converter0(Component):
            implements(IContentConverter)
            def get_supported_conversions(self):
                yield 'key0', 'Format 0', 'c0', 'text/x-sample', 'text/html', 8

        class Converter2(Component):
            implements(IContentConverter)
            def get_supported_conversions(self):
                yield 'key2', 'Format 2', 'c2', 'text/x-sample', 'text/html', 2

        class Converter1(Component):
            implements(IContentConverter)
            def get_supported_conversions(self):
                yield 'key1', 'Format 1', 'c1', 'text/x-sample', 'text/html', 4

        mimeview = Mimeview(self.env)
        conversions = mimeview.get_supported_conversions('text/x-sample')
        self.assertEqual(Converter0(self.env), conversions[0].converter)
        self.assertEqual(Converter1(self.env), conversions[1].converter)
        self.assertEqual(Converter2(self.env), conversions[2].converter)

class GroupLinesTestCase(unittest.TestCase):

    def test_empty_stream(self):
        # FIXME: this currently fails
        lines = list(_group_lines([]))
        self.assertEqual(len(lines), 0)

    def test_text_only_stream(self):
        input = [(TEXT, "test", (None, -1, -1))]
        lines = list(_group_lines(input))
        self.assertEqual(len(lines), 1)
        self.assertIsInstance(lines[0], Stream)
        self.assertEqual(lines[0].events, input)

    def test_text_only_stream2(self):
        input = [(TEXT, "test\n", (None, -1, -1))]
        lines = list(_group_lines(input))
        self.assertEqual(len(lines), 1)
        self.assertIsInstance(lines[0], Stream)
        self.assertEqual(lines[0].events, [(TEXT, "test", (None, -1, -1))])

    def test_simplespan(self):
        input = HTMLParser(StringIO(u"<span>test</span>"), encoding=None)
        lines = list(_group_lines(input))
        self.assertEqual(len(lines), 1)
        self.assertIsInstance(lines[0], Stream)
        for (a, b) in zip(lines[0], input):
            self.assertEqual(a, b)

    def test_empty_text_stream(self):
        """
        http://trac.edgewall.org/ticket/4336
        """
        input = [(TEXT, "", (None, -1, -1))]
        lines = list(_group_lines(input))
        self.assertEqual(len(lines), 0)

    def test_newline_stream(self):
        input = [(TEXT, "\n", (None, -1, -1))]
        lines = list(_group_lines(input))
        self.assertEqual(len(lines), 1)

    def test_newline_stream2(self):
        input = [(TEXT, "\n\n\n", (None, -1, -1))]
        lines = list(_group_lines(input))
        self.assertEqual(len(lines), 3)

    def test_empty_text_in_span(self):
        """
        http://trac.edgewall.org/ticket/4336
        """
        ns = Namespace('http://www.w3.org/1999/xhtml')
        input = [(START, (ns.span, Attrs([])), (None, -1, -1)),
                 (TEXT, "", (None, -1, -1)),
                 (END, ns.span, (None, -1, -1)),
                ]
        lines = list(_group_lines(input))
        self.assertEqual(len(lines), 0)

    def test_newline(self):
        """
        If the text element does not end with a newline, it's not properly
        closed.
        """
        input = HTMLParser(StringIO(u'<span class="c">a\nb</span>'),
            encoding=None)
        expected = ['<span class="c">a</span>',
                    '<span class="c">b</span>',
                   ]
        lines = list(_group_lines(input))
        self.assertEqual(len(lines), len(expected))
        for a, b in zip(lines, expected):
            self.assertEqual(a.render('html'), b)

    def test_newline2(self):
        """
        Same as test_newline above, but make sure it behaves properly wrt
        the trailing \\n, especially given it's inside an element.
        """
        input = HTMLParser(StringIO(u'<span class="c">a\nb\n</span>'),
            encoding=None)
        expected = ['<span class="c">a</span>',
                    '<span class="c">b</span>',
                   ]
        lines = list(_group_lines(input))
        self.assertEqual(len(lines), len(expected))
        for a, b in zip(lines, expected):
            self.assertEqual(a.render('html'), b)

    def test_multinewline(self):
        """
        ditto.
        """
        input = HTMLParser(StringIO(u'<span class="c">\n\n\na</span>'),
            encoding=None)
        expected = ['<span class="c"></span>',
                    '<span class="c"></span>',
                    '<span class="c"></span>',
                    '<span class="c">a</span>',
                   ]
        lines = list(_group_lines(input))
        self.assertEqual(len(lines), len(expected))
        for a, b in zip(lines, expected):
            self.assertEqual(a.render('html'), b)


class TestMimeviewConverter(Component):

    implements(IContentConverter)

    in_mimetype = __module__ + '.' + __name__

    def get_supported_conversions(self):
        yield ('text', self.__module__, 'txt', self.in_mimetype, 'text/plain',
               8)

    def convert_content(self, req, mimetype, content, key):
        if content == 'iterable-bytes':
            def fn_bytes():
                for idx in xrange(256):
                    yield 'b' * 256
            return fn_bytes(), 'text/plain'
        if content == 'iterable-unicode':
            def fn_unicode():
                for idx in xrange(0x10000):
                    yield u'ü'
            return fn_unicode(), 'text/plain'
        if content == 'bytes':
            return 'a' * 0x10000, 'text/plain'
        if content == 'unicode':
            return u'Ü' * 0x10000, 'text/plain'


class MimeviewConverterTestCase(unittest.TestCase):

    in_mimetype = TestMimeviewConverter.in_mimetype

    def setUp(self):
        self.env = EnvironmentStub(enable=['trac.*', TestMimeviewConverter])

    def tearDown(self):
        pass

    def _test_convert_content(self, expected, content, iterable):
        mimeview = Mimeview(self.env)
        output = mimeview.convert_content(MockRequest(self.env),
                                          self.in_mimetype,
                                          content, 'text', iterable=iterable)
        if iterable:
            self.assertNotIn(type(output[0]), (str, unicode))
            self.assertEqual(expected, ''.join(output[0]))
        else:
            self.assertEqual(type(expected), type(output[0]))
            self.assertEqual(expected, output[0])
        self.assertEqual('text/plain', output[1])
        self.assertEqual('txt', output[2])

    def test_convert_content_iterable_bytes(self):
        self._test_convert_content('b' * 0x10000, 'iterable-bytes', False)

    def test_convert_content_iterable_unicode(self):
        self._test_convert_content(u'ü' * 0x10000, 'iterable-unicode', False)

    def test_convert_content_bytes(self):
        self._test_convert_content('a' * 0x10000, 'bytes', False)

    def test_convert_content_unicode(self):
        self._test_convert_content(u'Ü' * 0x10000, 'unicode', False)

    def test_convert_content_iterable_bytes_iterable(self):
        self._test_convert_content('b' * 0x10000, 'iterable-bytes', True)

    def test_convert_content_iterable_unicode_iterable(self):
        self._test_convert_content(u'ü' * 0x10000, 'iterable-unicode', True)

    def test_convert_content_bytes_iterable(self):
        self._test_convert_content('a' * 0x10000, 'bytes', True)

    def test_convert_content_unicode_iterable(self):
        self._test_convert_content(u'Ü' * 0x10000, 'unicode', True)

    def _test_send_converted(self, expected, content, use_chunked_encoding):
        self.env.config.set('trac', 'use_chunked_encoding',
                            'true' if use_chunked_encoding else 'false')
        mimeview = Mimeview(self.env)
        req = MockRequest(self.env)
        self.assertRaises(RequestDone, mimeview.send_converted, req,
                          self.in_mimetype, content, 'text')
        result = req.response_sent.getvalue()
        if use_chunked_encoding:
            self.assertNotIn('Content-Length', req.headers_sent)
        else:
            self.assertIn('Content-Length', req.headers_sent)
            self.assertEqual(str(len(expected)),
                             req.headers_sent['Content-Length'])
        self.assertEqual('text/plain', req.headers_sent['Content-Type'])
        self.assertEqual(set(expected), set(result))
        self.assertEqual(expected, result)

    def test_send_converted_iterable_bytes(self):
        self._test_send_converted('b' * 0x10000, 'iterable-bytes', False)

    def test_send_converted_iterable_unicode(self):
        self._test_send_converted('ü' * 0x10000, 'iterable-unicode', False)

    def test_send_converted_bytes(self):
        self._test_send_converted('a' * 0x10000, 'bytes', False)

    def test_send_converted_unicode(self):
        self._test_send_converted('Ü' * 0x10000, 'unicode', False)

    def test_send_converted_iterable_bytes_chunked(self):
        self._test_send_converted('b' * 0x10000, 'iterable-bytes', True)

    def test_send_converted_iterable_unicode_chunked(self):
        self._test_send_converted('ü' * 0x10000, 'iterable-unicode', True)

    def test_send_converted_bytes_chunked(self):
        self._test_send_converted('a' * 0x10000, 'bytes', True)

    def test_send_converted_unicode_chunked(self):
        self._test_send_converted('Ü' * 0x10000, 'unicode', True)


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(doctest.DocTestSuite(api))
    suite.addTest(unittest.makeSuite(GetMimeTypeTestCase))
    suite.addTest(unittest.makeSuite(MimeviewTestCase))
    suite.addTest(unittest.makeSuite(GroupLinesTestCase))
    suite.addTest(unittest.makeSuite(MimeviewConverterTestCase))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
