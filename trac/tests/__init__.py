import unittest

from trac.tests import attachment, config, core, env, perm, notification

def suite():
    suite = unittest.TestSuite()
    suite.addTest(attachment.suite())
    suite.addTest(config.suite())
    suite.addTest(core.suite())
    suite.addTest(env.suite())
    suite.addTest(perm.suite())
    suite.addTest(notification.suite())
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
