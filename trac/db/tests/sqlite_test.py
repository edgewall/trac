# -*- coding: utf-8 -*-
#
# Copyright (C) 2015 Edgewall Software
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
import tempfile
import unittest

from trac.config import ConfigurationError
from trac.env import Environment
from trac.tests.compat import rmtree


class DatabaseFileTestCase(unittest.TestCase):

    def setUp(self):
        self.env_path = tempfile.mkdtemp(prefix='trac-tempenv-')
        self.db_path = os.path.join(self.env_path, 'db', 'trac.db')

    def tearDown(self):
        rmtree(self.env_path)

    def _create_env(self):
        env = Environment(self.env_path, create=True)
        env.shutdown()

    def _db_query(self, env):
        env.db_query("SELECT name FROM system")

    def test_missing_tracdb(self):
        self._create_env()
        os.remove(self.db_path)
        env = Environment(self.env_path)
        try:
            self._db_query(env)
            self.fail('ConfigurationError not raised')
        except ConfigurationError, e:
            self.assertIn('Database "', unicode(e))
            self.assertIn('" not found.', unicode(e))

    def test_no_permissions(self):
        self._create_env()
        os.chmod(self.db_path, 0444)
        env = Environment(self.env_path)
        try:
            self._db_query(env)
            self.fail('ConfigurationError not raised')
        except ConfigurationError, e:
            self.assertIn('requires read _and_ write permissions', unicode(e))


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(DatabaseFileTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
