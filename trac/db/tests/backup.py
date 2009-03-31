import os.path
import unittest

try:
    from svn import core, repos
    has_svn = True
except:
    has_svn = False

import trac
from trac.tests.functional.testenv import FunctionalTestEnvironment

class DatabaseBackupTestCase(unittest.TestCase):

    env_class = FunctionalTestEnvironment

    def setUp(self):
        trac_source_tree = os.path.normpath(os.path.join(trac.__file__, '..',
                                                     '..'))
        port = 8000 + os.getpid() % 1000
        dirname = os.path.join(trac_source_tree, "testenv")

        baseurl = "http://127.0.0.1:%s" % port
        self._testenv = self.env_class(dirname, port, baseurl)

    def tearDown(self):
        """leave the test environment for later examination,
        FunctionalTestEnvironment will cleanup on the next run"""

    def test_backup(self):
        """Testing backup"""
        # raises TracError if backup fails
        env = self._testenv.get_trac_environment()
        env.backup()


def suite():
    suite = unittest.TestSuite()
    if has_svn:
        suite.addTest(unittest.makeSuite(DatabaseBackupTestCase,'test'))
    else:
        print "SKIP: db/tests/backup.py (no svn bindings)"
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
