import unittest

from trac.versioncontrol.tests import cache, diff

def suite():

    suite = unittest.TestSuite()
    suite.addTest(cache.suite())
    suite.addTest(diff.suite())
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
