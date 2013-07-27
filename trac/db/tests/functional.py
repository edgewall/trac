#!/usr/bin/python

import os
from trac.tests.functional import *


class DatabaseBackupTestCase(FunctionalTestCaseSetup):
    def runTest(self):
        """Testing backup"""
        env = self._testenv.get_trac_environment()
        # raises TracError if backup fails
        backup_file = env.backup()
        self.assertTrue(os.path.exists(backup_file),
                        'Backup file was not created.')
        self.assertNotEqual(os.path.getsize(backup_file), 0,
                            'Backup file is zero length.')


def functionalSuite(suite=None):
    if not suite:
        import trac.tests.functional.testcases
        suite = trac.tests.functional.testcases.functionalSuite()
    suite.addTest(DatabaseBackupTestCase())
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='functionalSuite')

