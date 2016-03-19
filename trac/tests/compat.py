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

import os
import shutil
import sys
import time
import unittest


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


def rmtree(path):
    import errno
    def onerror(function, path, excinfo, retry=1):
        # `os.remove` fails for a readonly file on Windows.
        # Then, it attempts to be writable and remove.
        if function != os.remove:
            raise
        e = excinfo[1]
        if isinstance(e, OSError) and e.errno == errno.EACCES:
            mode = os.stat(path).st_mode
            os.chmod(path, mode | 0666)
            try:
                function(path)
            except Exception:
                # print "%d: %s %o" % (retry, path, os.stat(path).st_mode)
                if retry > 10:
                    raise
                time.sleep(0.1)
                onerror(function, path, excinfo, retry + 1)
        else:
            raise
    if os.name == 'nt' and isinstance(path, str):
        # Use unicode characters in order to allow non-ansi characters
        # on Windows.
        path = unicode(path, sys.getfilesystemencoding())
    shutil.rmtree(path, onerror=onerror)
