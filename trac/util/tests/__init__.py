import unittest

from trac.util.tests import html, text

def suite():
    suite = unittest.TestSuite()
    suite.addTest(html.suite())
    suite.addTest(text.suite())
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
