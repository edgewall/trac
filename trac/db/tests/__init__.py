# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2014 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import unittest

from trac.db.tests import api, mysql_test, postgres_test, sqlite_test, util
from trac.db.tests.functional import functionalSuite


def suite():
    suite = unittest.TestSuite()
    suite.addTest(api.suite())
    suite.addTest(mysql_test.suite())
    suite.addTest(postgres_test.suite())
    suite.addTest(sqlite_test.suite())
    suite.addTest(util.suite())
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
