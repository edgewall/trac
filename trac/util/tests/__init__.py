import unittest

from trac.util.tests import markup

def suite():
    suite = unittest.TestSuite()
    suite.addTest(markup.suite())
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
