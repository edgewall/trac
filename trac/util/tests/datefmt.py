# -*- coding: utf-8 -*-
#
# Copyright (C) 2007 Edgewall Software
# Copyright (C) 2007 Matt Good <trac@matt-good.net>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.
#
# Author: Matt Good <trac@matt-good.net>

import datetime
import unittest

from trac.util.datefmt import get_timezone

try:
    import pytz
except ImportError:
    PytzTestCase = None
else:
    class PytzTestCase(unittest.TestCase):
        def test_pytz_conversion(self):
            tz = get_timezone('GMT +3:00')
            self.assertEqual(datetime.timedelta(hours=3),
                             tz.utcoffset(None))

        def test_posix_conversion(self):
            tz = get_timezone('Etc/GMT-4')
            self.assertEqual(datetime.timedelta(hours=4),
                             tz.utcoffset(None))
            self.assertEqual('GMT +4:00', tz.zone)


def suite():
    suite = unittest.TestSuite()
    if PytzTestCase:
        suite.addTest(unittest.makeSuite(PytzTestCase, 'test'))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
