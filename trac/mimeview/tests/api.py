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
import io
import unittest

from six.moves import range

from trac.core import Component, implements
from trac.test import EnvironmentStub, MockRequest
from trac.mimeview import api
from trac.mimeview.api import (IContentConverter, Mimeview, RenderingContext,
                               get_mimetype)
from trac.resource import Resource
from trac.web.api import RequestDone


class GetMimeTypeTestCase(unittest.TestCase):

    def test_from_suffix_using_MIME_MAP(self):
        self.assertEqual('text/plain', get_mimetype('README', None))
        self.assertEqual('text/plain', get_mimetype('README.txt', None))

    def test_from_suffix_using_mimetypes(self):
        accepted = ('image/png', 'image/x-png')
        self.assertIn(get_mimetype('doc/trac_logo.png', None), accepted)

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


class TestMimeviewConverter(Component):

    implements(IContentConverter)

    in_mimetype = __module__ + '.' + __name__

    def get_supported_conversions(self):
        yield ('text', self.__module__, 'txt', self.in_mimetype, 'text/plain',
               8)

    def convert_content(self, req, mimetype, content, key):
        if content == 'iterable-bytes':
            def fn_bytes():
                for idx in range(256):
                    yield 'b' * 256
            return fn_bytes(), 'text/plain'
        if content == 'iterable-unicode':
            def fn_unicode():
                for idx in range(0x10000):
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


class MimeviewRenderTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()

    def test_plain_text_content(self):
        """Render simple plain text content."""
        mimeview = Mimeview(self.env)
        req = MockRequest(self.env)
        context = RenderingContext(Resource('wiki', 'readme.txt'))
        context.req = req
        content = io.BytesIO("""\
Some text.
""")

        rendered = mimeview.render(context, 'text/plain', content)

        self.assertEqual('<div class="code"><pre>Some text.\n</pre></div>',
                         str(rendered))



def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(doctest.DocTestSuite(api))
    suite.addTest(unittest.makeSuite(GetMimeTypeTestCase))
    suite.addTest(unittest.makeSuite(MimeviewTestCase))
    suite.addTest(unittest.makeSuite(MimeviewConverterTestCase))
    suite.addTest(unittest.makeSuite(MimeviewRenderTestCase))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
