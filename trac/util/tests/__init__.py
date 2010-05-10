# -*- coding: utf-8 -*-
#
# Copyright (C) 2009 Edgewall Software
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
import os.path
import tempfile
import unittest

from trac import util
from trac.util.tests import concurrency, datefmt, presentation, text


class AtomicFileTestCase(unittest.TestCase):
    
    def setUp(self):
        self.path = os.path.join(tempfile.gettempdir(), 'trac-tempfile')
    
    def tearDown(self):
        try:
            os.unlink(self.path)
        except OSError:
            pass
    
    def test_non_existing(self):
        f = util.AtomicFile(self.path)
        try:
            f.write('test content')
        finally:
            f.close()
        self.assertEqual('test content', util.read_file(self.path))
    
    def test_existing(self):
        util.create_file(self.path, 'Some content')
        self.assertEqual('Some content', util.read_file(self.path))
        f = util.AtomicFile(self.path)
        try:
            f.write('Some new content')
        finally:
            f.close()
        self.assertEqual('Some new content', util.read_file(self.path))
    
    if util.can_rename_open_file:
        def test_existing_open_for_reading(self):
            util.create_file(self.path, 'Initial file content')
            self.assertEqual('Initial file content', util.read_file(self.path))
            rf = open(self.path)
            try:
                f = util.AtomicFile(self.path)
                try:
                    f.write('Replaced content')
                finally:
                    f.close()
            finally:
                rf.close()
            self.assertEqual('Replaced content', util.read_file(self.path))
    
    # FIXME: It is currently not possible to make this test pass on all
    # platforms and with all locales. Typically, it will fail on Linux with
    # LC_ALL=C.
    # Python 3 adds sys.setfilesystemencoding(), which could be used here
    # to remove the dependency on the locale. So the test is disabled until
    # we require Python 3.
    def _test_unicode_path(self):
        self.path = os.path.join(tempfile.gettempdir(), u'träc-témpfilè')
        f = util.AtomicFile(self.path)
        try:
            f.write('test content')
        finally:
            f.close()
        self.assertEqual('test content', util.read_file(self.path))


class ContentDispositionTestCase(unittest.TestCase):

    def test_filename(self):
        self.assertEqual('attachment; filename=myfile.txt',
                         util.content_disposition('attachment', 'myfile.txt'))
        self.assertEqual('attachment; filename=a%20file.txt',
                         util.content_disposition('attachment', 'a file.txt'))
    
    def test_no_filename(self):
        self.assertEqual('inline', util.content_disposition('inline'))
        self.assertEqual('attachment', util.content_disposition('attachment'))


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(AtomicFileTestCase, 'test'))
    suite.addTest(unittest.makeSuite(ContentDispositionTestCase, 'test'))
    suite.addTest(concurrency.suite())
    suite.addTest(datefmt.suite())
    suite.addTest(presentation.suite())
    suite.addTest(doctest.DocTestSuite(util))
    suite.addTest(text.suite())
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
