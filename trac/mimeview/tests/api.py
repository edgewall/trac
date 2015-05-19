# -*- coding: utf-8 -*-
#
# Copyright (C)2006-2009 Edgewall Software
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
import sys

from trac.core import *
from trac.test import EnvironmentStub
from trac.mimeview import api
from trac.mimeview.api import get_mimetype, IContentConverter, Mimeview, \
                              _group_lines
from genshi import Stream, Namespace
from genshi.core import Attrs, TEXT, START, END
from genshi.input import HTMLParser


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
        self.assertEqual(Converter0(self.env), conversions[0][-1])
        self.assertEqual(Converter1(self.env), conversions[1][-1])
        self.assertEqual(Converter2(self.env), conversions[2][-1])

class GroupLinesTestCase(unittest.TestCase):

    def test_empty_stream(self):
        # FIXME: this currently fails
        lines = list(_group_lines([]))
        self.assertEqual(len(lines), 0)

    def test_text_only_stream(self):
        input = [(TEXT, "test", (None, -1, -1))]
        lines = list(_group_lines(input))
        self.assertEquals(len(lines), 1)
        self.assertTrue(isinstance(lines[0], Stream))
        self.assertEquals(lines[0].events, input)

    def test_text_only_stream2(self):
        input = [(TEXT, "test\n", (None, -1, -1))]
        lines = list(_group_lines(input))
        self.assertEquals(len(lines), 1)
        self.assertTrue(isinstance(lines[0], Stream))
        self.assertEquals(lines[0].events, [(TEXT, "test", (None, -1, -1))])

    def test_simplespan(self):
        input = HTMLParser(StringIO("<span>test</span>"))
        lines = list(_group_lines(input))
        self.assertEquals(len(lines), 1)
        self.assertTrue(isinstance(lines[0], Stream))
        for (a, b) in zip(lines[0], input):
            self.assertEqual(a, b)

    def test_empty_text_stream(self):
        """
        http://trac.edgewall.org/ticket/4336
        """
        input = [(TEXT, "", (None, -1, -1))]
        lines = list(_group_lines(input))
        self.assertEquals(len(lines), 0)

    def test_newline_stream(self):
        input = [(TEXT, "\n", (None, -1, -1))]
        lines = list(_group_lines(input))
        self.assertEquals(len(lines), 1)

    def test_newline_stream2(self):
        input = [(TEXT, "\n\n\n", (None, -1, -1))]
        lines = list(_group_lines(input))
        self.assertEquals(len(lines), 3)

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
        input = HTMLParser(StringIO('<span class="c">a\nb</span>'))
        expected = ['<span class="c">a</span>',
                    '<span class="c">b</span>',
                   ]
        lines = list(_group_lines(input))
        self.assertEquals(len(lines), len(expected))
        for a, b in zip(lines, expected):
            self.assertEquals(a.render('html'), b)

    def test_newline2(self):
        """
        Same as test_newline above, but make sure it behaves properly wrt
        the trailing \\n, especially given it's inside an element.
        """
        input = HTMLParser(StringIO('<span class="c">a\nb\n</span>'))
        expected = ['<span class="c">a</span>',
                    '<span class="c">b</span>',
                   ]
        lines = list(_group_lines(input))
        self.assertEquals(len(lines), len(expected))
        for a, b in zip(lines, expected):
            self.assertEquals(a.render('html'), b)

    def test_multinewline(self):
        """
        ditto.
        """
        input = HTMLParser(StringIO('<span class="c">\n\n\na</span>'))
        expected = ['<span class="c"></span>',
                    '<span class="c"></span>',
                    '<span class="c"></span>',
                    '<span class="c">a</span>',
                   ]
        lines = list(_group_lines(input))
        self.assertEquals(len(lines), len(expected))
        for a, b in zip(lines, expected):
            self.assertEquals(a.render('html'), b)


def suite():
    suite = unittest.TestSuite()
    suite.addTest(doctest.DocTestSuite(api))
    suite.addTest(unittest.makeSuite(GetMimeTypeTestCase, 'test'))
    suite.addTest(unittest.makeSuite(MimeviewTestCase, 'test'))
    suite.addTest(unittest.makeSuite(GroupLinesTestCase, 'test'))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
