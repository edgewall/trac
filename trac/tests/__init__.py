import unittest

from trac.tests import config, core, db, env, milestone, perm, query, ticket, \
                       wiki

def suite():

    suite = unittest.TestSuite()
    suite.addTest(config.suite())
    suite.addTest(core.suite())
    suite.addTest(db.suite())
    suite.addTest(env.suite())
    suite.addTest(milestone.suite())
    suite.addTest(perm.suite())
    suite.addTest(query.suite())
    suite.addTest(ticket.suite())
    suite.addTest(wiki.suite())
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
