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
import os
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

        def test_parse_date(self):
            tz = datefmt.get_timezone('Europe/Zurich')
            t = datefmt.parse_date('2009-12-01T12:00:00', tz)
            t_utc = datetime.datetime(2009, 12, 1, 11, 0, 0, 0, datefmt.utc)
            self.assertEqual(t_utc, t)

        def test_parse_date_dst(self):
            tz = datefmt.get_timezone('Europe/Zurich')
            t = datefmt.parse_date('2009-08-01T12:00:00', tz)
            t_utc = datetime.datetime(2009, 8, 1, 10, 0, 0, 0, datefmt.utc)
            self.assertEqual(t_utc, t)


class DateFormatTestCase(unittest.TestCase):

    def test_to_datetime(self):
        expected = datetime.datetime.fromtimestamp(23, datefmt.localtz)
        self.assertEqual(datefmt.to_datetime(23), expected)
        self.assertEqual(datefmt.to_datetime(23L), expected)
        self.assertEqual(datefmt.to_datetime(23.0), expected)

    def test_to_datetime_microsecond_timestamps(self):
        expected = datetime.datetime.fromtimestamp(2345.678912,
                                                   datefmt.localtz)
        self.assertEqual(datefmt.to_datetime(2345678912), expected)
        self.assertEqual(datefmt.to_datetime(2345678912L), expected)
        self.assertEqual(datefmt.to_datetime(2345678912.0), expected)

    def test_to_datetime_microsecond_negative_timestamps(self):
        # Work around issue1646728 in Python 2.4
        expected = datetime.datetime.fromtimestamp(-2345, datefmt.localtz) \
                   - datetime.timedelta(seconds=.678912)

        self.assertEqual(datefmt.to_datetime(-2345678912).microsecond,
                         321088) # 1000000 - 678912
        self.assertEqual(datefmt.to_datetime(-2345678912), expected)
        self.assertEqual(datefmt.to_datetime(-2345678912L), expected)
        self.assertEqual(datefmt.to_datetime(-2345678912.0), expected)
    if os.name == 'nt':
        del test_to_datetime_microsecond_negative_timestamps
        # negative timestamps not supported on Windows:
        # ValueError: timestamp out of range for platform localtime()/gmtime()
    
    def test_to_datetime_can_convert_dates(self):
        expected = datetime.datetime(2009, 5, 2, tzinfo=datefmt.localtz)
        self.assertEqual(datefmt.to_datetime(expected.date()), expected)

    def test_to_datetime_tz(self):
        tz = datefmt.timezone('GMT +1:00')
        expected = datetime.datetime(1970, 1, 1, 1, 0, 23, 0, tz)
        self.assertEqual(datefmt.to_datetime(23, tz), expected)
        self.assertEqual(datefmt.to_datetime(23L, tz), expected)
        self.assertEqual(datefmt.to_datetime(23.0, tz), expected)
        tz = datefmt.timezone('GMT +4:00')
        expected = datetime.datetime(1970, 1, 1, 4, 0, 23, 0, tz)
        self.assertEqual(datefmt.to_datetime(23, tz), expected)
        self.assertEqual(datefmt.to_datetime(23L, tz), expected)
        self.assertEqual(datefmt.to_datetime(23.0, tz), expected)

    def test_format_datetime_utc(self):
        t = datetime.datetime(1970, 1, 1, 1, 0, 23, 0, datefmt.utc)
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

    def test_format_datetime_gmt01(self):
        gmt01 = datefmt.FixedOffset(60, 'GMT +1:00')
        t = datetime.datetime(1970, 1, 1, 1, 0, 23, 0, gmt01)
        self.assertEqual('1970-01-01T01:00:23+0100',
                         datefmt.format_datetime(t, '%Y-%m-%dT%H:%M:%S%z',
                                                 gmt01))
        expected = '1970-01-01T01:00:23+01:00'
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


class UTimestampTestCase(unittest.TestCase):
    
    def test_sub_second(self):
        t = datetime.datetime(2001, 2, 3, 4, 5, 6, 123456, datefmt.utc)
        ts = datefmt.to_utimestamp(t)
        self.assertEqual(981173106123456L, ts)
        self.assertEqual(t, datefmt.from_utimestamp(ts))


def suite():
    suite = unittest.TestSuite()
    if PytzTestCase:
        suite.addTest(unittest.makeSuite(PytzTestCase, 'test'))
    else:
        print "SKIP: utils/tests/datefmt.py (no pytz installed)"
    suite.addTest(unittest.makeSuite(DateFormatTestCase))
    suite.addTest(unittest.makeSuite(UTimestampTestCase))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
