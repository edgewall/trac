import unittest

from trac.db.tests import api

def suite():

    suite = unittest.TestSuite()
    suite.addTest(api.suite())
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')

