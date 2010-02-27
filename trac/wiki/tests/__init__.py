import doctest
import unittest

import trac.wiki.api
import trac.wiki.formatter
from trac.wiki.tests import formatter, macros, model, wikisyntax
from trac.wiki.tests.functional import functionalSuite

def suite():

    suite = unittest.TestSuite()
    suite.addTest(formatter.suite())
    suite.addTest(macros.suite())
    suite.addTest(model.suite())
    suite.addTest(wikisyntax.suite())
    suite.addTest(doctest.DocTestSuite(trac.wiki.api))
    suite.addTest(doctest.DocTestSuite(trac.wiki.formatter))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
