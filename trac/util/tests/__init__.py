import unittest

from trac.util.tests import markup, text

def suite():
    suite = unittest.TestSuite()
    suite.addTest(markup.suite())
    suite.addTest(text.suite())
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
