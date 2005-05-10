import unittest

from trac.wiki.tests import formatter

def suite():

    suite = unittest.TestSuite()
    suite.addTest(formatter.suite())
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
