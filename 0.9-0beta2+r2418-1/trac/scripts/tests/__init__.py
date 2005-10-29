import unittest

from trac.scripts.tests import admin

def suite():

    suite = unittest.TestSuite()
    suite.addTest(admin.suite())
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
