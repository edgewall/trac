# -*- coding: utf-8 -*-
#
# Copyright (C) 2006-2018 Edgewall Software
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

from trac.mimeview.tests import api, patch, pygments, rst, txtl
from trac.mimeview.tests.functional import functionalSuite


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(api.test_suite())
    suite.addTest(patch.test_suite())
    suite.addTest(pygments.test_suite())
    suite.addTest(rst.test_suite())
    suite.addTest(txtl.test_suite())
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
