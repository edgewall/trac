import unittest

from trac.util.tests import html

def suite():
    suite = unittest.TestSuite()
    suite.addTest(html.suite())
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
