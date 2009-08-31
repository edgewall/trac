# -*- coding: utf-8 -*-
#
# Copyright (C) 2007-2009 Edgewall Software
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

from trac.util import datefmt

try:
    import pytz
except ImportError:
    PytzTestCase = None
else:
    class PytzTestCase(unittest.TestCase):
        def test_pytz_conversion(self):
            tz = datefmt.get_timezone('GMT +3:00')
            self.assertEqual(datetime.timedelta(hours=3),
                             tz.utcoffset(None))

        def test_posix_conversion(self):
            tz = datefmt.get_timezone('Etc/GMT-4')
            self.assertEqual(datetime.timedelta(hours=4),
                             tz.utcoffset(None))
            self.assertEqual('GMT +4:00', tz.zone)

        def test_unicode_input(self):
            tz = datefmt.get_timezone(u'Etc/GMT-4')
            self.assertEqual(datetime.timedelta(hours=4),
                             tz.utcoffset(None))
            self.assertEqual('GMT +4:00', tz.zone)

class DateFormatTestCase(unittest.TestCase):

    def test_to_datetime(self):
        expected = datetime.datetime.fromtimestamp(23, datefmt.localtz)
        self.assertEqual(datefmt.to_datetime(23), expected)
        self.assertEqual(datefmt.to_datetime(23L), expected)
        self.assertEqual(datefmt.to_datetime(23.0), expected)
    
    def test_to_datetime_can_convert_dates(self):
        expected = datetime.datetime(2009, 5, 2, tzinfo=datefmt.localtz)
        self.assertEqual(datefmt.to_datetime(expected.date()), expected)

    def test_to_datetime_tz(self):
        tz = datefmt.timezone('GMT +1:00')
        expected = datetime.datetime(1970,1,1,1,0,23,0,tz)
        self.assertEqual(datefmt.to_datetime(23, tz), expected)
        self.assertEqual(datefmt.to_datetime(23L, tz), expected)
        self.assertEqual(datefmt.to_datetime(23.0, tz), expected)

    def test_format_datetime_gmt01(self):
        t = datetime.datetime(1970,1,1,1,0,23,0,datefmt.utc)
        expected = '1970-01-01T01:00:23Z'
        self.assertEqual(datefmt.format_datetime(t, '%Y-%m-%dT%H:%M:%SZ',
                                                 datefmt.utc), expected)
        self.assertEqual(datefmt.format_datetime(t, 'iso8601',
                                                 datefmt.utc), expected)
        self.assertEqual(datefmt.format_datetime(t, 'iso8601date',
                                                 datefmt.utc), 
                                                 expected.split('T')[0])
        self.assertEqual(datefmt.format_datetime(t, 'iso8601time',
                                                 datefmt.utc), 
                                                 expected.split('T')[1])

    def test_format_datetime_utc(self):
        gmt01 = datefmt.FixedOffset(60, 'GMT +1:00')
        t = datetime.datetime(1970,1,1,1,0,23,0,gmt01)
        expected = '1970-01-01T01:00:23+0100'
        self.assertEqual(datefmt.format_datetime(t, '%Y-%m-%dT%H:%M:%S%z',
                                                 gmt01), expected)
        self.assertEqual(datefmt.format_datetime(t, 'iso8601',
                                                 gmt01), expected)
        self.assertEqual(datefmt.format_datetime(t, 'iso8601date', gmt01),
                                                 expected.split('T')[0])
        self.assertEqual(datefmt.format_datetime(t, 'iso8601time', gmt01),
                                                 expected.split('T')[1])
    
    def test_format_date_accepts_date_instances(self):
        a_date = datetime.date(2009, 8, 20)
        self.assertEqual('2009-08-20', 
                         datefmt.format_date(a_date, format='%Y-%m-%d'))

def suite():
    suite = unittest.TestSuite()
    if PytzTestCase:
        suite.addTest(unittest.makeSuite(PytzTestCase, 'test'))
    else:
        print "SKIP: utils/tests/datefmt.py (no pytz installed)"
    suite.addTest(unittest.makeSuite(DateFormatTestCase))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
