import unittest

from trac.tests import attachment, config, core, env, perm, resource, \
                       wikisyntax, functional

def suite():
    suite = unittest.TestSuite()
    suite.addTest(basicSuite())
    suite.addTest(functionalSuite())
    return suite

def basicSuite():
    suite = unittest.TestSuite()
    suite.addTest(attachment.suite())
    suite.addTest(config.suite())
    suite.addTest(core.suite())
    suite.addTest(env.suite())
    suite.addTest(perm.suite())
    suite.addTest(resource.suite())
    suite.addTest(wikisyntax.suite())
    return suite

def functionalSuite():
    return functional.suite()

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
