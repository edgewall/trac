# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2018 Edgewall Software
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

import trac.wiki.api
import trac.wiki.formatter
import trac.wiki.parser
from trac.wiki.tests import (
    admin, formatter, macros, model, web_api, web_ui, wikisyntax)
from trac.wiki.tests.functional import functionalSuite

def test_suite():

    suite = unittest.TestSuite()
    suite.addTest(admin.test_suite())
    suite.addTest(formatter.test_suite())
    suite.addTest(macros.test_suite())
    suite.addTest(model.test_suite())
    suite.addTest(web_api.test_suite())
    suite.addTest(web_ui.test_suite())
    suite.addTest(wikisyntax.test_suite())
    suite.addTest(doctest.DocTestSuite(trac.wiki.api))
    suite.addTest(doctest.DocTestSuite(trac.wiki.formatter))
    suite.addTest(doctest.DocTestSuite(trac.wiki.parser))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
