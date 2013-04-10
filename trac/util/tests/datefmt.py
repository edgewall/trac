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
import time
import unittest

from trac.core import TracError
from trac.util import datefmt

try:
    import pytz
except ImportError:
    pytz = None
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

        def test_to_datetime_normalized(self):
            tz = datefmt.get_timezone('Europe/Paris')
            t = datetime.datetime(2012, 3, 25, 2, 15)
            dt = datefmt.to_datetime(t, tz)
            self.assertEqual(datetime.timedelta(0, 7200), dt.utcoffset())

        def test_parse_date_across_dst_boundary(self):
            tz = datefmt.get_timezone('Europe/Zurich')
            # DST start - 31 March, 02:00
            format = '%Y-%m-%d %H:%M:%S %Z%z'
            expected = '2002-03-31 03:30:00 CEST+0200'
            # iso8601
            t = datefmt.parse_date('2002-03-31T02:30:00', tz)
            self.assertEqual(expected, t.strftime(format))
            # strptime
            t = datetime.datetime(2002, 3, 31, 2, 30)
            t = datefmt.parse_date(t.strftime('%x %X'), tz)
            self.assertEqual(expected, t.strftime(format))

        def test_to_datetime_astimezone(self):
            tz = datefmt.get_timezone('Europe/Paris')
            t = datetime.datetime(2012, 3, 25, 2, 15, tzinfo=datefmt.utc)
            dt = datefmt.to_datetime(t, tz)
            self.assertEqual(datetime.timedelta(0, 7200), dt.utcoffset())

        def test_to_datetime_tz_from_naive_datetime_is_localtz(self):
            t = datetime.datetime(2012, 3, 25, 2, 15)
            dt = datefmt.to_datetime(t)
            self.assert_(isinstance(dt.tzinfo, datefmt.LocalTimezone))

        def test_to_datetime_tz_from_now_is_localtz(self):
            dt = datefmt.to_datetime(None)
            self.assert_(isinstance(dt.tzinfo, datefmt.LocalTimezone))


class ParseISO8601TestCase(unittest.TestCase):

    def test_iso8601_second(self):
        t = datetime.datetime(2012, 10, 11, 2, 40, 57, 0, datefmt.utc)
        self.assertEqual(t, datefmt.parse_date('2012-10-11T02:40:57Z'))
        self.assertEqual(t, datefmt.parse_date('2012-10-10T14:40:57-12:00'))
        self.assertEqual(t, datefmt.parse_date('2012-10-11T02:40:57+00:00'))
        self.assertEqual(t, datefmt.parse_date('2012-10-11T02:40:57-00:00'))
        self.assertEqual(t, datefmt.parse_date('2012-10-11T08:25:57+05:45'))
        self.assertEqual(t, datefmt.parse_date('2012-10-11T16:40:57+14:00'))
        self.assertEqual(t, datefmt.parse_date('20121011T024057Z'))
        self.assertEqual(t, datefmt.parse_date('20121010T144057-1200'))
        self.assertEqual(t, datefmt.parse_date('20121011T024057+0000'))
        self.assertEqual(t, datefmt.parse_date('20121011T024057-0000'))
        self.assertEqual(t, datefmt.parse_date('20121011T082557+0545'))
        self.assertEqual(t, datefmt.parse_date('20121011T164057+1400'))

    def test_iso8601_minute(self):
        t = datetime.datetime(2012, 10, 11, 2, 40, 0, 0, datefmt.utc)
        self.assertEqual(t, datefmt.parse_date('2012-10-11T02:40Z'))
        self.assertEqual(t, datefmt.parse_date('2012-10-10T14:40-12:00'))
        self.assertEqual(t, datefmt.parse_date('2012-10-11T16:40+14:00'))
        self.assertEqual(t, datefmt.parse_date('20121011T0240Z'))
        self.assertEqual(t, datefmt.parse_date('20121010T1440-1200'))
        self.assertEqual(t, datefmt.parse_date('20121011T1640+1400'))

    def test_iso8601_hour(self):
        t = datetime.datetime(2012, 10, 11, 2, 0, 0, 0, datefmt.utc)
        self.assertEqual(t, datefmt.parse_date('2012-10-11T02Z'))
        self.assertEqual(t, datefmt.parse_date('2012-10-10T14-12'))
        self.assertEqual(t, datefmt.parse_date('2012-10-10T14-12:00'))
        self.assertEqual(t, datefmt.parse_date('2012-10-11T16+14'))
        self.assertEqual(t, datefmt.parse_date('2012-10-11T16+14:00'))
        self.assertEqual(t, datefmt.parse_date('20121011T02Z'))
        self.assertEqual(t, datefmt.parse_date('20121010T14-12'))
        self.assertEqual(t, datefmt.parse_date('20121010T14-1200'))
        self.assertEqual(t, datefmt.parse_date('20121011T16+1400'))
        self.assertEqual(t, datefmt.parse_date('20121011T16+14'))

    def test_iso8601_day(self):
        t = datetime.datetime(2012, 10, 11, 0, 0, 0, 0, datefmt.localtz)
        self.assertEqual(t, datefmt.parse_date('2012-10-11'))
        self.assertEqual(t, datefmt.parse_date('20121011'))

    def test_iso8601_month(self):
        t = datetime.datetime(2012, 10, 1, 0, 0, 0, 0, datefmt.localtz)
        self.assertEqual(t, datefmt.parse_date('2012-10'))
        self.assertEqual(t, datefmt.parse_date('201210'))

    def test_iso8601_year(self):
        t = datetime.datetime(2012, 1, 1, 0, 0, 0, 0, datefmt.localtz)
        self.assertEqual(t, datefmt.parse_date('2012'))

    def test_iso8601_tz(self):
        self.assertEqual(
            datetime.timedelta(),
            datefmt.parse_date('2012-10-11T02:40:57Z').utcoffset())
        self.assertEqual(
            datetime.timedelta(hours=-12),
            datefmt.parse_date('2012-10-10T14:40:57-12').utcoffset())
        self.assertEqual(
            datetime.timedelta(hours=-9, minutes=-30),
            datefmt.parse_date('2012-10-10T17:10:57-09:30').utcoffset())
        self.assertEqual(
            datetime.timedelta(),
            datefmt.parse_date('2012-10-11T02:40:57+00:00').utcoffset())
        self.assertEqual(
            datetime.timedelta(),
            datefmt.parse_date('2012-10-11T02:40:57-00:00').utcoffset())
        self.assertEqual(
            datetime.timedelta(hours=5, minutes=45),
            datefmt.parse_date('2012-10-11T08:25:57+05:45').utcoffset())

    def test_iso8601_naive_tz_is_localtz(self):
        t = datetime.datetime(2012, 10, 11, 2, 40, 57, 0, datefmt.localtz)
        dt = datefmt.parse_date('2012-10-11T02:40:57')
        self.assertEqual(t, dt)
        self.assert_(isinstance(dt.tzinfo, datefmt.LocalTimezone))

    def test_iso8601_naive_tz_used_tzinfo_arg(self):
        tz = datefmt.timezone('GMT +1:00')
        t = datetime.datetime(2012, 10, 11, 2, 40, 57, 0, tz)
        dt = datefmt.parse_date('2012-10-11T02:40:57', tz)
        self.assertEqual(t, dt)
        self.assertEqual(tz, dt.tzinfo)
        self.assertEqual(datetime.timedelta(hours=1), dt.utcoffset())

    def test_iso8601_tz_not_used_tzinfo_arg(self):
        tz = datefmt.timezone('GMT +1:00')
        dt = datefmt.parse_date('2012-10-10T17:10:57-09:30', tz)
        self.assertEqual(datetime.timedelta(hours=-9, minutes=-30),
                         dt.utcoffset())

    if pytz:
        def test_iso8601_naive_tz_normalize_non_existent_time(self):
            t = datetime.datetime(2012, 3, 25, 1, 15, 57, 0, datefmt.utc)
            tz = datefmt.timezone('Europe/Paris')
            dt = datefmt.parse_date('2012-03-25T02:15:57', tz)
            self.assertEqual(t, dt)
            self.assertEqual(3, dt.hour)
            self.assertEqual(datetime.timedelta(hours=2), dt.utcoffset())

        def test_iso8601_naive_tz_normalize_ambiguous_time(self):
            t = datetime.datetime(2011, 10, 31, 1, 15, 57, 0, datefmt.utc)
            tz = datefmt.timezone('Europe/Paris')
            dt = datefmt.parse_date('2011-10-31T02:15:57', tz)
            self.assertEqual(t, dt)
            self.assertEqual(2, dt.hour)
            self.assertEqual(datetime.timedelta(hours=1), dt.utcoffset())


class ParseRelativeDateTestCase(unittest.TestCase):

    def test_time_interval_seconds(self):
        tz = datefmt.timezone('GMT +1:00')
        now = datetime.datetime(2012, 3, 25, 3, 15, 21, 987654, tzinfo=tz)
        past_42s = datetime.datetime(2012, 3, 25, 3, 14, 39, 987654, tzinfo=tz)

        self.assertEqual(
            past_42s,
            datefmt._parse_relative_time('42second ago', tz, now))
        self.assertEqual(
            past_42s,
            datefmt._parse_relative_time('42 secondsago', tz, now))
        self.assertEqual(
            past_42s,
            datefmt._parse_relative_time('42 second', tz, now))
        self.assertEqual(
            past_42s,
            datefmt._parse_relative_time('42seconds', tz, now))
        self.assertEqual(
            None,
            datefmt._parse_relative_time('42s ago', tz, now))
        self.assertEqual(
            None,
            datefmt._parse_relative_time('42s', tz, now))

    def test_time_interval_minutes(self):
        tz = datefmt.timezone('GMT +1:00')
        now = datetime.datetime(2012, 3, 25, 3, 15, 21, 987654, tzinfo=tz)

        self.assertEqual(
            datetime.datetime(2012, 3, 25, 2, 54, 21, 987654, tzinfo=tz),
            datefmt._parse_relative_time('21minute', tz, now))
        self.assertEqual(
            datetime.datetime(2012, 3, 25, 2, 54, 6, 987654, tzinfo=tz),
            datefmt._parse_relative_time('21.25 minutes', tz, now))

    def test_time_interval_hours(self):
        tz = datefmt.timezone('GMT +1:00')
        now = datetime.datetime(2012, 3, 25, 3, 15, 21, 987654, tzinfo=tz)
        past_42h = datetime.datetime(2012, 3, 23, 9, 15, 21, 987654, tzinfo=tz)

        self.assertEqual(
            past_42h,
            datefmt._parse_relative_time('42 hours', tz, now))
        self.assertEqual(
            past_42h,
            datefmt._parse_relative_time('42h ago', tz, now))

    def test_time_interval_days(self):
        tz = datefmt.timezone('GMT +1:00')
        now = datetime.datetime(2012, 3, 25, 3, 15, 21, 987654, tzinfo=tz)
        past_24d = datetime.datetime(2012, 3, 1, 3, 15, 21, 987654, tzinfo=tz)

        self.assertEqual(
            past_24d,
            datefmt._parse_relative_time('24day', tz, now))
        self.assertEqual(
            past_24d,
            datefmt._parse_relative_time('24ds', tz, now))

    def test_time_interval_weeks(self):
        tz = datefmt.timezone('GMT +1:00')
        now = datetime.datetime(2012, 3, 25, 3, 15, 21, 987654, tzinfo=tz)
        past_3w = datetime.datetime(2012, 3, 4, 3, 15, 21, 987654, tzinfo=tz)

        self.assertEqual(past_3w,
                         datefmt._parse_relative_time('3 weeks', tz, now))
        self.assertEqual(past_3w,
                         datefmt._parse_relative_time('3w', tz, now))

    def test_time_interval_months(self):
        tz = datefmt.timezone('GMT +1:00')
        now = datetime.datetime(2012, 1, 1, 3, 15, 21, 987654, tzinfo=tz)
        past_12m = datetime.datetime(2011, 1, 6, 3, 15, 21, 987654, tzinfo=tz)

        self.assertEqual(
            past_12m,
            datefmt._parse_relative_time('12 months', tz, now))
        self.assertEqual(
            past_12m,
            datefmt._parse_relative_time('12 ms ago', tz, now))

    def test_time_interval_years(self):
        tz = datefmt.timezone('GMT +1:00')
        now = datetime.datetime(2012, 3, 25, 3, 15, 21, 987654, tzinfo=tz)
        past_2y = datetime.datetime(2010, 3, 26, 3, 15, 21, 987654, tzinfo=tz)

        self.assertEqual(past_2y,
                         datefmt._parse_relative_time('2 years', tz, now))
        self.assertEqual(past_2y, datefmt._parse_relative_time('2y', tz, now))

    def test_time_start_now(self):
        tz = datefmt.timezone('GMT +1:00')
        now = datetime.datetime(2012, 3, 25, 3, 15, 21, 987654, tzinfo=tz)
        self.assertEqual(now, datefmt._parse_relative_time('now', tz, now))

    def test_time_start_today(self):
        tz = datefmt.timezone('GMT +1:00')
        now = datetime.datetime(2012, 3, 25, 3, 15, 21, 987654, tzinfo=tz)
        today = datefmt.to_datetime(datetime.datetime(2012, 3, 25), tzinfo=tz)
        self.assertEqual(today,
                         datefmt._parse_relative_time('today', tz, now))
        self.assertEqual(today,
                         datefmt._parse_relative_time('this day', tz, now))

    def test_time_start_yesterday(self):
        tz = datefmt.timezone('GMT +1:00')
        now = datetime.datetime(2012, 3, 25, 3, 15, 21, 987654, tzinfo=tz)
        yesterday = datefmt.to_datetime(datetime.datetime(2012, 3, 24), tz)
        self.assertEqual(yesterday,
                         datefmt._parse_relative_time('yesterday', tz, now))
        self.assertEqual(yesterday,
                         datefmt._parse_relative_time('last day', tz, now))

    def test_time_start_year(self):
        tz = datefmt.timezone('GMT +1:00')

        now = datetime.datetime(2012, 3, 25, 3, 15, 21, 987654, tzinfo=tz)
        self.assertEqual(datetime.datetime(2012, 1, 1, tzinfo=tz),
                         datefmt._parse_relative_time('this year', tz, now))
        self.assertEqual(datetime.datetime(2011, 1, 1, tzinfo=tz),
                         datefmt._parse_relative_time('last year', tz, now))

        now = datetime.datetime(2009, 3, 25, 3, 15, 21, 987654, tzinfo=tz)
        self.assertEqual(datetime.datetime(2009, 1, 1, tzinfo=tz),
                         datefmt._parse_relative_time('this year', tz, now))
        self.assertEqual(datetime.datetime(2008, 1, 1, tzinfo=tz),
                         datefmt._parse_relative_time('last year', tz, now))

    def test_time_start_month(self):
        tz = datefmt.timezone('GMT +1:00')
        now = datetime.datetime(2012, 1, 23, 3, 15, 42, 987654, tzinfo=tz)
        self.assertEqual(datetime.datetime(2012, 1, 1, tzinfo=tz),
                         datefmt._parse_relative_time('this month', tz, now))
        self.assertEqual(datetime.datetime(2011, 12, 1, tzinfo=tz),
                         datefmt._parse_relative_time('last month', tz, now))

    def test_time_start_week(self):
        tz = datefmt.timezone('GMT +1:00')
        now = datetime.datetime(2012, 3, 25, 3, 15, 21, 987654, tzinfo=tz)
        self.assertEqual(datetime.datetime(2012, 3, 19, tzinfo=tz),
                         datefmt._parse_relative_time('this week', tz, now))
        self.assertEqual(datetime.datetime(2012, 3, 12, tzinfo=tz),
                         datefmt._parse_relative_time('last week', tz, now))

    def test_time_start_day(self):
        tz = datefmt.timezone('GMT +1:00')
        now = datetime.datetime(2012, 3, 1, 3, 15, 21, 987654, tzinfo=tz)
        self.assertEqual(datetime.datetime(2012, 3, 1, tzinfo=tz),
                         datefmt._parse_relative_time('this day', tz, now))
        self.assertEqual(datetime.datetime(2012, 2, 29, tzinfo=tz),
                         datefmt._parse_relative_time('last day', tz, now))

    def test_time_start_hour(self):
        tz = datefmt.timezone('GMT +1:00')
        now = datetime.datetime(2012, 3, 25, 0, 15, 21, 987654, tzinfo=tz)
        self.assertEqual(datetime.datetime(2012, 3, 25, 0, tzinfo=tz),
                         datefmt._parse_relative_time('this hour', tz, now))
        self.assertEqual(datetime.datetime(2012, 3, 24, 23, tzinfo=tz),
                         datefmt._parse_relative_time('last hour', tz, now))

    def test_time_start_minute(self):
        tz = datefmt.timezone('GMT +1:00')
        now = datetime.datetime(2012, 3, 25, 3, 0, 21, 987654, tzinfo=tz)
        self.assertEqual(datetime.datetime(2012, 3, 25, 3, 0, tzinfo=tz),
                         datefmt._parse_relative_time('this minute', tz, now))
        self.assertEqual(datetime.datetime(2012, 3, 25, 2, 59, tzinfo=tz),
                         datefmt._parse_relative_time('last minute', tz, now))

    def test_time_start_second(self):
        tz = datefmt.timezone('GMT +1:00')
        now = datetime.datetime(2012, 3, 25, 3, 15, 0, 987654, tzinfo=tz)
        self.assertEqual(datetime.datetime(2012, 3, 25, 3, 15, 0, tzinfo=tz),
                         datefmt._parse_relative_time('this second', tz, now))
        self.assertEqual(datetime.datetime(2012, 3, 25, 3, 14, 59, tzinfo=tz),
                         datefmt._parse_relative_time('last second', tz, now))

    if pytz:
        def test_time_interval_across_dst(self):
            tz = datefmt.timezone('Europe/Paris')
            now = datefmt.to_datetime(datetime.datetime(2012, 3, 25, 3, 0, 41),
                                      tz)
            dt = datefmt._parse_relative_time('41 seconds', tz, now)
            self.assertEqual('2012-03-25T03:00:00+02:00', dt.isoformat())
            dt = datefmt._parse_relative_time('42 seconds', tz, now)
            self.assertEqual('2012-03-25T01:59:59+01:00', dt.isoformat())

        def test_this_time_start_across_dst(self):
            tz = datefmt.timezone('Europe/Paris')
            now = datefmt.to_datetime(
                datetime.datetime(2012, 3, 25, 3, 15, 21, 987654), tz)
            dt = datefmt._parse_relative_time('this hour', tz, now)
            self.assertEqual('2012-03-25T03:00:00+02:00', dt.isoformat())
            dt = datefmt._parse_relative_time('today', tz, now)
            self.assertEqual('2012-03-25T00:00:00+01:00', dt.isoformat())
            dt = datefmt._parse_relative_time('this day', tz, now)
            self.assertEqual('2012-03-25T00:00:00+01:00', dt.isoformat())

        def test_last_time_start_across_dst(self):
            tz = datefmt.timezone('Europe/Paris')
            now = datefmt.to_datetime(datetime.datetime(2012, 3, 26, 3, 0, 41),
                                      tz)
            dt = datefmt._parse_relative_time('this day', tz, now)
            self.assertEqual('2012-03-26T00:00:00+02:00', dt.isoformat())
            dt = datefmt._parse_relative_time('yesterday', tz, now)
            self.assertEqual('2012-03-25T00:00:00+01:00', dt.isoformat())
            dt = datefmt._parse_relative_time('last day', tz, now)
            self.assertEqual('2012-03-25T00:00:00+01:00', dt.isoformat())


class ParseDateValidRangeTestCase(unittest.TestCase):

    def test_max_timestamp(self):
        # At least all platforms support maximal signed 32 bits integer,
        # 2**31 - 1, INT32_MAX.
        datefmt.parse_date('2038-01-19T03:14:07Z')
        try:
            datefmt.parse_date('9999-12-31T23:59:59-12:00')
            raise AssertionError('TracError not raised')
        except TracError, e:
            self.assert_('is outside valid range' in unicode(e))

    def test_min_timestamp(self):
        if os.name != 'nt':
            # At least all Unix support minimal signed 32 bits integer,
            # -(2**31), INT32_MIN
            datefmt.parse_date('1901-12-13T20:45:52Z')
        else:
            # At least All VC run-times support 0 as time_t
            datefmt.parse_date('1970-01-01T00:00:00Z')
        try:
            datefmt.parse_date('0001-01-01T00:00:00+14:00')
            raise AssertionError('TracError not raised')
        except TracError, e:
            self.assert_('is outside valid range' in unicode(e))


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


class HttpDateTestCase(unittest.TestCase):

    def test_http_date(self):
        t = datetime.datetime(2001, 2, 3, 4, 5, 6, 123456, datefmt.utc)
        self.assertEqual('Sat, 03 Feb 2001 04:05:06 GMT', datefmt.http_date(t))


class LocalTimezoneTestCase(unittest.TestCase):

    def setUp(self):
        self.env_tz = os.environ.get('TZ')

    def tearDown(self):
        self._tzset(self.env_tz)

    def _tzset(self, tz):
        if tz is not None:
            os.environ['TZ'] = tz
        elif 'TZ' in os.environ:
            del os.environ['TZ']
        time.tzset()
        datefmt.LocalTimezone._initialize()

    def test_gmt01(self):
        self._tzset('GMT-1')
        self.assertEqual(datetime.timedelta(hours=1),
                         datefmt.LocalTimezone._std_offset)
        self.assertEqual(datetime.timedelta(hours=1),
                         datefmt.LocalTimezone._dst_offset)
        self.assertEqual(datetime.timedelta(0),
                         datefmt.LocalTimezone._dst_diff)

    def test_europe_paris(self):
        self._tzset('Europe/Paris')
        self.assertEqual(datetime.timedelta(hours=1),
                         datefmt.LocalTimezone._std_offset)
        self.assertEqual(datetime.timedelta(hours=2),
                         datefmt.LocalTimezone._dst_offset)
        self.assertEqual(datetime.timedelta(hours=1),
                         datefmt.LocalTimezone._dst_diff)

    def test_utcoffset_not_localized(self):
        self._tzset('Europe/Paris')
        self.assertEqual(datetime.timedelta(hours=1),
                         datetime.datetime(2012, 3, 25, 1, 15, 42, 123456,
                                           datefmt.localtz).utcoffset())
        self.assertEqual(datetime.timedelta(hours=2),
                         datetime.datetime(2012, 3, 25, 3, 15, 42, 123456,
                                           datefmt.localtz).utcoffset())
        # non existent time
        self.assertEqual(datetime.timedelta(hours=1),
                         datetime.datetime(2012, 3, 25, 2, 15, 42, 123456,
                                           datefmt.localtz).utcoffset())
        # ambiguous time
        self.assertEqual(datetime.timedelta(hours=1),
                         datetime.datetime(2011, 10, 30, 2, 45, 42, 123456,
                                           datefmt.localtz).utcoffset())

    def test_localized_non_existent_time(self):
        self._tzset('Europe/Paris')
        dt = datetime.datetime(2012, 3, 25, 2, 15, 42, 123456)
        self.assertEqual('2012-03-25T02:15:42.123456+01:00',
                         datefmt.localtz.localize(dt).isoformat())
        try:
            datefmt.localtz.localize(dt, is_dst=None)
            raise AssertionError('ValueError not raised')
        except ValueError, e:
            self.assertEqual('Non existent time "2012-03-25 02:15:42.123456"',
                             unicode(e))

    def test_localized_ambiguous_time(self):
        self._tzset('Europe/Paris')
        dt = datetime.datetime(2011, 10, 30, 2, 45, 42, 123456)
        self.assertEqual('2011-10-30T02:45:42.123456+01:00',
                         datefmt.localtz.localize(dt).isoformat())
        try:
            datefmt.localtz.localize(dt, is_dst=None)
            raise AssertionError('ValueError not raised')
        except ValueError, e:
            self.assertEqual('Ambiguous time "2011-10-30 02:45:42.123456"',
                             unicode(e))

    def test_normalized_non_existent_time(self):
        self._tzset('Europe/Paris')
        dt = datetime.datetime(2012, 3, 25, 2, 15, 42, 123456)
        dt = datefmt.localtz.normalize(datefmt.localtz.localize(dt))
        self.assertEqual('2012-03-25T03:15:42.123456+02:00', dt.isoformat())

    def test_normalized_ambiguous_time(self):
        self._tzset('Europe/Paris')
        dt = datetime.datetime(2011, 10, 30, 2, 45, 42, 123456)
        dt = datefmt.localtz.normalize(datefmt.localtz.localize(dt))
        self.assertEqual('2011-10-30T02:45:42.123456+01:00', dt.isoformat())

    def test_normalized_not_localized_non_existent_time(self):
        self._tzset('Europe/Paris')
        dt = datetime.datetime(2012, 3, 25, 2, 15, 42, 123456, datefmt.localtz)
        self.assertEqual('2012-03-25T02:15:42.123456+01:00', dt.isoformat())
        dt = datefmt.localtz.normalize(dt)
        self.assertEqual(datefmt.localtz, dt.tzinfo)
        self.assertEqual('2012-03-25T02:15:42.123456+01:00', dt.isoformat())

    def test_normalized_not_localized_ambiguous_time(self):
        self._tzset('Europe/Paris')
        dt = datetime.datetime(2011, 10, 30, 2, 45, 42, 123456, datefmt.localtz)
        self.assertEqual('2011-10-30T02:45:42.123456+01:00', dt.isoformat())
        dt = datefmt.localtz.normalize(dt)
        self.assertEqual(datefmt.localtz, dt.tzinfo)
        self.assertEqual('2011-10-30T02:45:42.123456+01:00', dt.isoformat())

    def test_astimezone_utc(self):
        self._tzset('Europe/Paris')
        dt = datetime.datetime(2012, 1, 23, 23, 32, 42, 123456, datefmt.utc)
        self.assertEqual('2012-01-24T00:32:42.123456+01:00',
                         dt.astimezone(datefmt.localtz).isoformat())
        dt = datetime.datetime(2011, 7, 15, 23, 57, 42, 123456, datefmt.utc)
        self.assertEqual('2011-07-16T01:57:42.123456+02:00',
                         dt.astimezone(datefmt.localtz).isoformat())

    def test_astimezone_non_utc(self):
        self._tzset('Europe/Paris')
        dt = datetime.datetime(2012, 1, 23, 16, 32, 42, 123456,
                               datefmt.timezone('GMT -7:00'))
        self.assertEqual('2012-01-24T00:32:42.123456+01:00',
                         dt.astimezone(datefmt.localtz).isoformat())
        dt = datetime.datetime(2011, 7, 16, 10, 57, 42, 123456,
                               datefmt.timezone('GMT +11:00'))
        self.assertEqual('2011-07-16T01:57:42.123456+02:00',
                         dt.astimezone(datefmt.localtz).isoformat())

    def test_astimezone_non_existent_time(self):
        self._tzset('Europe/Paris')
        dt = datetime.datetime(2012, 3, 25, 0, 15, 42, 123456, datefmt.utc)
        self.assertEqual('2012-03-25T01:15:42.123456+01:00',
                         dt.astimezone(datefmt.localtz).isoformat())
        dt = datetime.datetime(2012, 3, 25, 1, 15, 42, 123456, datefmt.utc)
        self.assertEqual('2012-03-25T03:15:42.123456+02:00',
                         dt.astimezone(datefmt.localtz).isoformat())

    def test_astimezone_ambiguous_time(self):
        self._tzset('Europe/Paris')
        dt = datetime.datetime(2011, 10, 30, 0, 45, 42, 123456, datefmt.utc)
        self.assertEqual('2011-10-30T02:45:42.123456+02:00',
                         dt.astimezone(datefmt.localtz).isoformat())
        dt = datetime.datetime(2011, 10, 30, 1, 45, 42, 123456, datefmt.utc)
        self.assertEqual('2011-10-30T02:45:42.123456+01:00',
                         dt.astimezone(datefmt.localtz).isoformat())

    def test_astimezone_invalid_range_on_gmt01(self):
        self._tzset('GMT-1')

        # 1899-12-30T23:59:58+00:00 is -0x83ac4e92 for time_t, out of range
        # for 32-bit signed integer
        dt = datetime.datetime(1899, 12, 30, 23, 59, 58, 123456, datefmt.utc)
        self.assertEqual('1899-12-31T00:59:58.123456+01:00',
                         dt.astimezone(datefmt.localtz).isoformat())
        dt = datetime.datetime(1899, 12, 30, 23, 59, 58, 123456,
                               datefmt.localtz)
        self.assertEqual('1899-12-30T22:59:58.123456+00:00',
                         dt.astimezone(datefmt.utc).isoformat())

        # 2040-12-31T23:59:58+00:00 is 0x858c84ee for time_t, out of range for
        # 32-bit signed integer
        dt = datetime.datetime(2040, 12, 31, 23, 59, 58, 123456, datefmt.utc)
        self.assertEqual('2041-01-01T00:59:58.123456+01:00',
                         dt.astimezone(datefmt.localtz).isoformat())
        dt = datetime.datetime(2040, 12, 31, 23, 59, 58, 123456,
                               datefmt.localtz)
        self.assertEqual('2040-12-31T22:59:58.123456+00:00',
                         dt.astimezone(datefmt.utc).isoformat())

    def test_arithmetic_localized_non_existent_time(self):
        self._tzset('Europe/Paris')
        t = datetime.datetime(2012, 3, 25, 1, 15, 42, 123456)
        t_utc = t.replace(tzinfo=datefmt.utc)
        t1 = datefmt.localtz.localize(t)
        self.assertEqual('2012-03-25T01:15:42.123456+01:00', t1.isoformat())
        t2 = t1 + datetime.timedelta(hours=1)
        self.assertEqual('2012-03-25T02:15:42.123456+01:00', t2.isoformat())
        t3 = t1 + datetime.timedelta(hours=2)
        self.assertEqual('2012-03-25T03:15:42.123456+01:00', t3.isoformat())
        self.assertEqual(datetime.timedelta(hours=1),
                         (t2 - t_utc) - (t1 - t_utc))
        self.assertEqual(datetime.timedelta(hours=2),
                         (t3 - t_utc) - (t1 - t_utc))

    def test_arithmetic_localized_ambiguous_time(self):
        self._tzset('Europe/Paris')
        t = datetime.datetime(2011, 10, 30, 1, 45, 42, 123456)
        t_utc = t.replace(tzinfo=datefmt.utc)
        t1 = datefmt.localtz.localize(t)
        self.assertEqual('2011-10-30T01:45:42.123456+02:00', t1.isoformat())
        t2 = t1 + datetime.timedelta(hours=1)
        self.assertEqual('2011-10-30T02:45:42.123456+02:00', t2.isoformat())
        t3 = t1 + datetime.timedelta(hours=2)
        self.assertEqual('2011-10-30T03:45:42.123456+02:00', t3.isoformat())
        self.assertEqual(datetime.timedelta(hours=1),
                         (t2 - t_utc) - (t1 - t_utc))
        self.assertEqual(datetime.timedelta(hours=1),
                         (t3 - t_utc) - (t2 - t_utc))

    def test_arithmetic_normalized_non_existent_time(self):
        self._tzset('Europe/Paris')
        t = datetime.datetime(2012, 3, 25, 1, 15, 42, 123456)
        t_utc = t.replace(tzinfo=datefmt.utc)
        t1 = datefmt.localtz.normalize(datefmt.localtz.localize(t))
        self.assertEqual('2012-03-25T01:15:42.123456+01:00', t1.isoformat())
        t2 = datefmt.localtz.normalize(t1 + datetime.timedelta(hours=1))
        self.assertEqual('2012-03-25T03:15:42.123456+02:00', t2.isoformat())
        t3 = datefmt.localtz.normalize(t1 + datetime.timedelta(hours=2))
        self.assertEqual('2012-03-25T04:15:42.123456+02:00', t3.isoformat())

        self.assertEqual(datetime.timedelta(hours=1),
                         (t2 - t_utc) - (t1 - t_utc))
        self.assertEqual(datetime.timedelta(hours=1),
                         (t3 - t_utc) - (t2 - t_utc))

    def test_arithmetic_normalized_ambiguous_time(self):
        self._tzset('Europe/Paris')
        t = datetime.datetime(2011, 10, 30, 1, 45, 42, 123456)
        t_utc = t.replace(tzinfo=datefmt.utc)
        t1 = datefmt.localtz.normalize(datefmt.localtz.localize(t))
        self.assertEqual('2011-10-30T01:45:42.123456+02:00', t1.isoformat())
        t2 = datefmt.localtz.normalize(t1 + datetime.timedelta(hours=1))
        self.assertEqual('2011-10-30T02:45:42.123456+02:00', t2.isoformat())
        t3 = datefmt.localtz.normalize(t1 + datetime.timedelta(hours=2))
        self.assertEqual('2011-10-30T02:45:42.123456+01:00', t3.isoformat())
        t4 = datefmt.localtz.normalize(t1 + datetime.timedelta(hours=3))
        self.assertEqual('2011-10-30T03:45:42.123456+01:00', t4.isoformat())

        self.assertEqual(datetime.timedelta(hours=1),
                         (t2 - t_utc) - (t1 - t_utc))
        self.assertEqual(datetime.timedelta(hours=1),
                         (t3 - t_utc) - (t2 - t_utc))
        self.assertEqual(datetime.timedelta(hours=1),
                         (t4 - t_utc) - (t3 - t_utc))

    def test_arithmetic_not_localized_normalized_non_existent_time(self):
        self._tzset('Europe/Paris')
        t = datetime.datetime(2012, 3, 25, 1, 15, 42, 123456, datefmt.localtz)
        t_utc = t.replace(tzinfo=datefmt.utc)
        t1 = t
        self.assertEqual('2012-03-25T01:15:42.123456+01:00', t1.isoformat())
        t2 = datefmt.localtz.normalize(t1 + datetime.timedelta(hours=1))
        self.assertEqual('2012-03-25T02:15:42.123456+01:00', t2.isoformat())
        t3 = datefmt.localtz.normalize(t1 + datetime.timedelta(hours=2))
        self.assertEqual('2012-03-25T03:15:42.123456+02:00', t3.isoformat())

        self.assertEqual(datetime.timedelta(hours=1), t2 - t1)
        self.assertEqual(datetime.timedelta(hours=1), t3 - t2)

    def test_arithmetic_not_localized_normalized_ambiguous_time(self):
        self._tzset('Europe/Paris')
        t = datetime.datetime(2011, 10, 30, 1, 45, 42, 123456, datefmt.localtz)
        t_utc = t.replace(tzinfo=datefmt.utc)
        t1 = t
        self.assertEqual('2011-10-30T01:45:42.123456+02:00', t1.isoformat())
        t2 = datefmt.localtz.normalize(t1 + datetime.timedelta(hours=1))
        self.assertEqual('2011-10-30T02:45:42.123456+01:00', t2.isoformat())
        t3 = datefmt.localtz.normalize(t1 + datetime.timedelta(hours=2))
        self.assertEqual('2011-10-30T03:45:42.123456+01:00', t3.isoformat())
        t4 = datefmt.localtz.normalize(t1 + datetime.timedelta(hours=3))
        self.assertEqual('2011-10-30T04:45:42.123456+01:00', t4.isoformat())

        self.assertEqual(datetime.timedelta(hours=1), t2 - t1)
        self.assertEqual(datetime.timedelta(hours=1), t3 - t2)
        self.assertEqual(datetime.timedelta(hours=1), t4 - t3)


class LocalTimezoneStrTestCase(unittest.TestCase):

    def test_localtz_str(self):
        class FixedLocalTz(datefmt.LocalTimezone):
            def __init__(self, hours, minutes):
                self._offset = datetime.timedelta(hours=hours,
                                                  seconds=minutes * 60)
            def utcoffset(self, dt):
                return self._offset

        self.assertEqual("UTC+02:03", str(FixedLocalTz(02, 03)))
        self.assertEqual("UTC+01:00", str(FixedLocalTz(01, 00)))
        self.assertEqual("UTC+00:23", str(FixedLocalTz(00, 23)))
        self.assertEqual("UTC+00:00", str(FixedLocalTz(00, 00)))
        self.assertEqual("UTC-00:23", str(FixedLocalTz(-00, -23)))
        self.assertEqual("UTC-01:00", str(FixedLocalTz(-01, -00)))
        self.assertEqual("UTC-02:03", str(FixedLocalTz(-02, -03)))


def suite():
    suite = unittest.TestSuite()
    if PytzTestCase:
        suite.addTest(unittest.makeSuite(PytzTestCase, 'test'))
    else:
        print "SKIP: utils/tests/datefmt.py (no pytz installed)"
    suite.addTest(unittest.makeSuite(DateFormatTestCase))
    suite.addTest(unittest.makeSuite(UTimestampTestCase))
    suite.addTest(unittest.makeSuite(ParseISO8601TestCase))
    suite.addTest(unittest.makeSuite(ParseRelativeDateTestCase))
    suite.addTest(unittest.makeSuite(ParseDateValidRangeTestCase))
    suite.addTest(unittest.makeSuite(HttpDateTestCase))
    if hasattr(time, 'tzset'):
        suite.addTest(unittest.makeSuite(LocalTimezoneTestCase))
    suite.addTest(unittest.makeSuite(LocalTimezoneStrTestCase))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
