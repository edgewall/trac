import unittest

from trac.tests import attachment, config, core, env, perm, wikisyntax

def suite():
    suite = unittest.TestSuite()
    suite.addTest(attachment.suite())
    suite.addTest(config.suite())
    suite.addTest(core.suite())
    suite.addTest(env.suite())
    suite.addTest(perm.suite())
    suite.addTest(wikisyntax.suite())
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
