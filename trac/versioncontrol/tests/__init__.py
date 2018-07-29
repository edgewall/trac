# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2018 Edgewall Software
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

from trac.versioncontrol.tests import admin, cache, diff, svn_authz, api
from trac.versioncontrol.tests.functional import functionalSuite

def test_suite():

    suite = unittest.TestSuite()
    suite.addTest(admin.test_suite())
    suite.addTest(cache.test_suite())
    suite.addTest(diff.test_suite())
    suite.addTest(svn_authz.test_suite())
    suite.addTest(api.test_suite())
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
