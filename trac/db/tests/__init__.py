import unittest

from trac.db.tests import api, mysql_test, postgres_test, util

from trac.db.tests.functional import functionalSuite

def suite():

    suite = unittest.TestSuite()
    suite.addTest(api.suite())
    suite.addTest(mysql_test.suite())
    suite.addTest(postgres_test.suite())
    #suite.addTest(util.suite())
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')

