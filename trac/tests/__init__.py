import unittest

from trac.tests import attachment, config, core, db, env, perm, util

def suite():
    suite = unittest.TestSuite()
    suite.addTest(attachment.suite())
    suite.addTest(config.suite())
    suite.addTest(core.suite())
    suite.addTest(db.suite())
    suite.addTest(env.suite())
    suite.addTest(perm.suite())
    suite.addTest(util.suite())
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
