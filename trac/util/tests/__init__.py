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
import unittest

from trac import util
from trac.util.tests import datefmt, presentation, text


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
    suite.addTest(unittest.makeSuite(ContentDispositionTestCase, 'test'))
    suite.addTest(datefmt.suite())
    suite.addTest(presentation.suite())
    suite.addTest(doctest.DocTestSuite(util))
    suite.addTest(text.suite())
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
