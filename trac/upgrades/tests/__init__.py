# -*- coding: utf-8 -*-
#
# Copyright (C) 2015 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

import unittest

from trac.upgrades.tests import db31, db32, db39, db41


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(db31.test_suite())
    suite.addTest(db32.test_suite())
    suite.addTest(db39.test_suite())
    suite.addTest(db41.test_suite())
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
