import unittest

from trac.tests import env, perm, query, ticket, wiki

def suite():

    suite = unittest.TestSuite()
    suite.addTest(env.suite())
    suite.addTest(perm.suite())
    suite.addTest(query.suite())
    suite.addTest(ticket.suite())
    suite.addTest(wiki.suite())
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
