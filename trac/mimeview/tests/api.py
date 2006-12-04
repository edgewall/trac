# -*- coding: utf-8 -*-
#
# Copyright (C) 2006 Edgewall Software
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

from trac.core import *
from trac.test import EnvironmentStub
from trac.mimeview.api import get_mimetype, IContentConverter, Mimeview


class GetMimeTypeTestCase(unittest.TestCase):

    def test_from_suffix_using_MIME_MAP(self):
        self.assertEqual('text/plain', get_mimetype('README', None))
        self.assertEqual('text/plain', get_mimetype('README.txt', None))
        
    def test_from_suffix_using_mimetypes(self):
        self.assertEqual('application/x-python-code',
                         get_mimetype('test.pyc', None))
        
    def test_from_content_using_CONTENT_RE(self):
        self.assertEqual('text/x-python',
                         get_mimetype('xxx', """
#!/usr/bin/python
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

    def test_from_content_using_is_binary(self):
        self.assertEqual('application/octet-stream',
                         get_mimetype('xxx', "abc\0xyz"))


class MimeviewTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True)

        # Make sure we have no external components hanging around in the
        # component registry
        from trac.core import ComponentMeta
        self.old_registry = ComponentMeta._registry
        ComponentMeta._registry = {}

    def tearDown(self):
        # Restore the original component registry
        from trac.core import ComponentMeta
        ComponentMeta._registry = self.old_registry

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


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(GetMimeTypeTestCase, 'test'))
    suite.addTest(unittest.makeSuite(MimeviewTestCase, 'test'))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
