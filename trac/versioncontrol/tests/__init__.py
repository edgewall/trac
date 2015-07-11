# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2013 Edgewall Software
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

def suite():

    suite = unittest.TestSuite()
    suite.addTest(admin.suite())
    suite.addTest(cache.suite())
    suite.addTest(diff.suite())
    suite.addTest(svn_authz.suite())
    suite.addTest(api.suite())
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
