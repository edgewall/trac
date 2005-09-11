import unittest

from trac.ticket.tests import api, model, query

def suite():
    suite = unittest.TestSuite()
    suite.addTest(api.suite())
    suite.addTest(model.suite())
    suite.addTest(query.suite())
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
