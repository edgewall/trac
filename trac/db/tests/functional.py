#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2009-2013 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import os
import unittest

from trac.tests.functional import FunctionalTestCaseSetup


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
        import trac.tests.functional
        suite = trac.tests.functional.functionalSuite()
    suite.addTest(DatabaseBackupTestCase())
    return suite


test_suite = functionalSuite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
