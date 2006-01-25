from trac.mimeview.tests import api

import unittest

def suite():
    suite = unittest.TestSuite()
    suite.addTest(api.suite())
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
