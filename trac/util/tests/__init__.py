import doctest
import unittest

from trac import util
from trac.util.tests import presentation, text

def suite():
    suite = unittest.TestSuite()
    suite.addTest(presentation.suite())
    suite.addTest(doctest.DocTestSuite(util))
    suite.addTest(text.suite())
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
