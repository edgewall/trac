import unittest

from trac.versioncontrol.tests import cache, diff, svn_authz

def suite():

    suite = unittest.TestSuite()
    suite.addTest(cache.suite())
    suite.addTest(diff.suite())
    suite.addTest(svn_authz.suite())
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
