# -*- coding: utf-8 -*-
#
# Copyright (C) 2013 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

"""Some test functions since Python 2.7 to provide backwards-compatibility
with previous versions of Python from 2.5 onward.
"""

import unittest

from trac.test import rmtree  # for backward compatibility


if not hasattr(unittest.TestCase, 'assertIs'):
    def assertIs(self, expr1, expr2, msg=None):
        if expr1 is not expr2:
            raise self.failureException(msg or '%r is not %r'
                                               % (expr1, expr2))
    unittest.TestCase.assertIs = assertIs


if not hasattr(unittest.TestCase, 'assertIsNot'):
    def assertIsNot(self, expr1, expr2, msg=None):
        if expr1 is expr2:
            raise self.failureException(msg or '%r is %r' % (expr1, expr2))
    unittest.TestCase.assertIsNot = assertIsNot


if not hasattr(unittest.TestCase, 'assertIsNone'):
    def assertIsNone(self, obj, msg=None):
        self.assertIs(obj, None, msg)
    unittest.TestCase.assertIsNone = assertIsNone


if not hasattr(unittest.TestCase, 'assertIsNotNone'):
    def assertIsNotNone(self, obj, msg=None):
        self.assertIsNot(obj, None, msg)
    unittest.TestCase.assertIsNotNone = assertIsNotNone


if not hasattr(unittest.TestCase, 'assertIn'):
    def assertIn(self, member, container, msg=None):
        if member not in container:
            raise self.failureException(msg or '%r not in %r' %
                                               (member, container))
    unittest.TestCase.assertIn = assertIn


if not hasattr(unittest.TestCase, 'assertNotIn'):
    def assertNotIn(self, member, container, msg=None):
        if member in container:
            raise self.failureException(msg or '%r in %r' %
                                               (member, container))
    unittest.TestCase.assertNotIn = assertNotIn


if not hasattr(unittest.TestCase, 'assertIsInstance'):
    def assertIsInstance(self, obj, cls, msg=None):
        if not isinstance(obj, cls):
            raise self.failureException(msg or '%r is not an instance of %r' %
                                               (obj, cls))
    unittest.TestCase.assertIsInstance = assertIsInstance


if not hasattr(unittest.TestCase, 'assertNotIsInstance'):
    def assertNotIsInstance(self, obj, cls, msg=None):
        if isinstance(obj, cls):
            raise self.failureException(msg or '%r is an instance of %r' %
                                               (obj, cls))
    unittest.TestCase.assertNotIsInstance = assertNotIsInstance
