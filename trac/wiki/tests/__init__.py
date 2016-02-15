# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2013 Edgewall Software
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
    formatter, macros, model, web_api, web_ui, wikisyntax)
from trac.wiki.tests.functional import functionalSuite

def suite():

    suite = unittest.TestSuite()
    suite.addTest(formatter.suite())
    suite.addTest(macros.suite())
    suite.addTest(model.suite())
    suite.addTest(web_api.suite())
    suite.addTest(web_ui.suite())
    suite.addTest(wikisyntax.suite())
    suite.addTest(doctest.DocTestSuite(trac.wiki.api))
    suite.addTest(doctest.DocTestSuite(trac.wiki.formatter))
    suite.addTest(doctest.DocTestSuite(trac.wiki.parser))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
