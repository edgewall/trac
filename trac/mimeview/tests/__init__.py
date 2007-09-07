from trac.mimeview.tests import api, patch, php, pygments

import unittest

def suite():
    suite = unittest.TestSuite()
    suite.addTest(api.suite())
    suite.addTest(patch.suite())
    suite.addTest(php.suite())
    suite.addTest(pygments.suite())
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
