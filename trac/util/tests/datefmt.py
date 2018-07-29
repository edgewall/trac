# -*- coding: utf-8 -*-
#
# Copyright (C) 2007-2018 Edgewall Software
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
import locale
import os
import time
import unittest

import trac.tests.compat
from trac.core import TracError
from trac.test import locale_en
from trac.util import datefmt

try:
    from babel import Locale
except ImportError:
    Locale = None

if datefmt.pytz is None:
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
            self.assertTrue(isinstance(tz, datefmt.FixedOffset))

            tz = datefmt.get_timezone('Etc/GMT+12')
            self.assertEqual(datetime.timedelta(hours=-12),
                             tz.utcoffset(None))
            self.assertEqual('GMT -12:00', tz.zone)
            self.assertTrue(isinstance(tz, datefmt.FixedOffset))

            tz = datefmt.get_timezone('Etc/GMT-14')
            self.assertEqual(datetime.timedelta(hours=14),
                             tz.utcoffset(None))
            self.assertEqual('GMT +14:00', tz.zone)
            self.assertTrue(isinstance(tz, datefmt.FixedOffset))

        def test_unicode_input(self):
            tz = datefmt.get_timezone(u'Etc/GMT-4')
            self.assertEqual(datetime.timedelta(hours=4),
                             tz.utcoffset(None))
            self.assertEqual('GMT +4:00', tz.zone)

        def test_parse_date(self):
            tz = datefmt.get_timezone('Europe/Zurich')
            t_utc = datetime.datetime(2009, 12, 1, 11, 0, 0, 0, datefmt.utc)
            self.assertEqual(t_utc,
                    datefmt.parse_date('2009-12-01T12:00:00', tz))
            self.assertEqual(t_utc,
                    datefmt.parse_date('2009-12-01 12:00:00', tz))

        def test_parse_date_dst(self):
            tz = datefmt.get_timezone('Europe/Zurich')
            t_utc = datetime.datetime(2009, 8, 1, 10, 0, 0, 0, datefmt.utc)
            self.assertEqual(t_utc,
                    datefmt.parse_date('2009-08-01T12:00:00', tz))
            self.assertEqual(t_utc,
                    datefmt.parse_date('2009-08-01 12:00:00', tz))

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
            # i18n datetime
            if Locale:
                t = datefmt.parse_date('Mar 31, 2002 02:30', tz, locale_en)
                self.assertEqual(expected, t.strftime(format))

        def test_to_datetime_pytz_normalize(self):
            tz = datefmt.get_timezone('Europe/Zurich')
            date = datefmt.to_datetime(datetime.date(2002, 3, 31), tz)
            format = '%Y-%m-%d %H:%M:%S %Z%z'
            expected = '2002-03-31 00:00:00 CET+0100'
            self.assertEqual(expected, date.strftime(format))

        def test_to_datetime_normalized(self):
            tz = datefmt.get_timezone('Europe/Paris')
            t = datetime.datetime(2012, 3, 25, 2, 15)
            dt = datefmt.to_datetime(t, tz)
            self.assertEqual(datetime.timedelta(0, 7200), dt.utcoffset())

        def test_to_datetime_astimezone(self):
            tz = datefmt.get_timezone('Europe/Paris')
            t = datetime.datetime(2012, 3, 25, 2, 15, tzinfo=datefmt.utc)
            dt = datefmt.to_datetime(t, tz)
            self.assertEqual(datetime.timedelta(0, 7200), dt.utcoffset())

        def test_to_datetime_tz_from_naive_datetime_is_localtz(self):
            t = datetime.datetime(2012, 3, 25, 2, 15)
            dt = datefmt.to_datetime(t)
            self.assertIsInstance(dt.tzinfo, datefmt.LocalTimezone)

        def test_to_datetime_tz_from_now_is_localtz(self):
            dt = datefmt.to_datetime(None)
            self.assertIsInstance(dt.tzinfo, datefmt.LocalTimezone)


class ParseISO8601TestCase(unittest.TestCase):

    def test_iso8601_microsecond(self):
        parse = datefmt.parse_date
        t = datetime.datetime(2012, 10, 11, 2, 40, 57, 987543, datefmt.utc)
        self.assertEqual(t, parse('2012-10-11T02:40:57.987543Z'))
        self.assertEqual(t, parse('2012-10-10T14:40:57.987543-12:00'))
        self.assertEqual(t, parse('2012-10-11T02:40:57.987543+00:00'))
        self.assertEqual(t, parse('2012-10-11T02:40:57.987543-00:00'))
        self.assertEqual(t, parse('2012-10-11T08:25:57.987543+05:45'))
        self.assertEqual(t, parse('2012-10-11T16:40:57.987543+14:00'))
        self.assertEqual(t, parse('20121011T024057.987543Z'))
        self.assertEqual(t, parse('20121010T144057.987543-1200'))
        self.assertEqual(t, parse('20121011T024057.987543+0000'))
        self.assertEqual(t, parse('20121011T024057.987543-0000'))
        self.assertEqual(t, parse('20121011T082557.987543+0545'))
        self.assertEqual(t, parse('20121011T164057.987543+1400'))

        self.assertEqual(datetime.datetime(2012, 10, 11, 2, 40, 57, 100000,
                                           datefmt.utc),
                         parse('2012-10-11T02:40:57.1Z'))
        self.assertEqual(datetime.datetime(2012, 10, 11, 2, 40, 57, 120000,
                                           datefmt.utc),
                         parse('2012-10-11T02:40:57.12Z'))
        self.assertEqual(datetime.datetime(2012, 10, 11, 2, 40, 57, 123000,
                                           datefmt.utc),
                         parse('2012-10-11T02:40:57.123Z'))
        self.assertEqual(datetime.datetime(2012, 10, 11, 2, 40, 57, 123400,
                                           datefmt.utc),
                         parse('2012-10-11T02:40:57.1234Z'))
        self.assertEqual(datetime.datetime(2012, 10, 11, 2, 40, 57, 123450,
                                           datefmt.utc),
                         parse('2012-10-11T02:40:57.12345Z'))

        self.assertRaises(TracError, parse, '2012-10-11T02:40:57.1234567Z')

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

    def test_iso8601_invalid_tz(self):
        def try_parse(text):
            self.assertRaises(TracError, datefmt.parse_date, text)

        try_parse('2012-10-11T02:40:5703:45')    # no sign of timezone offset
        try_parse('2012-10-11T02:40:570345')
        try_parse('2012-10-11T02:40:57Z+01:15')  # Z and timezone offset
        try_parse('2012-10-11T02:40:57Z-02:30')
        try_parse('2012-10-11T02:40:57Z03:45')
        try_parse('2012-10-11T02:40:57Z+0115')
        try_parse('2012-10-11T02:40:57Z-0230')
        try_parse('2012-10-11T02:40:57Z0345')
        try_parse('2012-10-11T02:40:57Z+01')
        try_parse('2012-10-11T02:40:57Z-02')
        try_parse('2012-10-11T02:40:57Z03')

    def test_iso8601_tz_invalid_range(self):
        def try_parse(text):
            self.assertRaises(TracError, datefmt.parse_date, text)

        try_parse('2012-10-11T02:40:57+00:60')
        try_parse('2012-10-11T02:40:57+00:99')
        try_parse('2012-10-11T02:40:57+23:60')
        try_parse('2012-10-11T02:40:57-23:60')
        try_parse('2012-10-11T02:40:57+24:00')
        try_parse('2012-10-11T02:40:57-24:00')
        try_parse('2012-10-11T02:40:57+99:00')
        try_parse('2012-10-11T02:40:57-99:00')

    def test_iso8601_tz_zone(self):
        def test_tzinfo_zone(expected, text):
            dt = datefmt.parse_date(text)
            self.assertEqual(datefmt.FixedOffset, type(dt.tzinfo))
            self.assertEqual(expected, dt.tzinfo.zone)

        test_tzinfo_zone('+23:59', '2012-10-11T02:40:57+23:59')
        test_tzinfo_zone('+12:00', '2012-10-11T02:40:57+12:00')
        test_tzinfo_zone('+12:00', '2012-10-11T02:40:57+12')
        test_tzinfo_zone('+11:30', '2012-10-11T02:40:57+11:30')
        test_tzinfo_zone('+00:30', '2012-10-11T02:40:57+00:30')
        test_tzinfo_zone('UTC',    '2012-10-11T02:40:57+00:00')
        test_tzinfo_zone('UTC',    '2012-10-11T02:40:57+00')
        test_tzinfo_zone('UTC',    '2012-10-11T02:40:57-00')
        test_tzinfo_zone('UTC',    '2012-10-11T02:40:57-00:00')
        test_tzinfo_zone('-00:30', '2012-10-11T02:40:57-00:30')
        test_tzinfo_zone('-13:30', '2012-10-11T02:40:57-13:30')
        test_tzinfo_zone('-14:00', '2012-10-11T02:40:57-14:00')
        test_tzinfo_zone('-14:00', '2012-10-11T02:40:57-14')
        test_tzinfo_zone('-23:59', '2012-10-11T02:40:57-23:59')

    def test_iso8601_naive_tz_is_localtz(self):
        t = datetime.datetime(2012, 10, 11, 2, 40, 57, 0, datefmt.localtz)
        dt = datefmt.parse_date('2012-10-11T02:40:57')
        self.assertEqual(t, dt)
        self.assertIsInstance(dt.tzinfo, datefmt.LocalTimezone)

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

    if datefmt.pytz:
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

    def _test_hint_iso8601(self, locale=None):
        try:
            datefmt.parse_date('2001-0a-01', locale=locale, hint='iso8601')
            raise self.failureException('TracError not raised')
        except TracError as e:
            self.assertIn(u'Try "YYYY-MM-DDThh:mm:ss±hh:mm" instead.',
                          unicode(e))

    def test_hint_iso8601_locale_none(self):
        self._test_hint_iso8601()

    def test_hint_iso8601_locale_iso8601(self):
        self._test_hint_iso8601('iso8601')

    def test_hint_iso8601_locale_en(self):
        self._test_hint_iso8601(locale_en)


class ParseDateWithoutBabelTestCase(unittest.TestCase):

    if os.name != 'nt':
        locales = {}
    else:
        # LCID: http://msdn.microsoft.com/en-us/goglobal/bb964664.aspx
        # NLS: http://msdn.microsoft.com/en-us/goglobal/bb896001.aspx
        ref_time = time.gmtime(123456)
        locales = {
            'en_US.UTF8': ('English_United States', '1/2/1970 10:17:36 AM'),
            'en_GB.UTF8': ('English_United Kingdom', '02/01/1970 10:17:36'),
            'fr_FR.UTF8': ('French_France', '02/01/1970 10:17:36'),
            'ja_JP.UTF8': ('Japanese_Japan', '1970/01/02 10:17:36'),
            'zh_CN.UTF8': ("Chinese_People's Republic of China",
                           '1970/1/2 10:17:36')
        }

    def setUp(self):
        rv = locale.getlocale(locale.LC_TIME)
        self._orig_locale = rv if rv[0] else 'C'

    def tearDown(self):
        locale.setlocale(locale.LC_ALL, self._orig_locale)

    def _setlocale(self, id):
        try:
            mapped, ref_strftime = self.locales.get(id, (id, None))
            locale.setlocale(locale.LC_ALL, mapped)
            return (ref_strftime is None or
                    ref_strftime == time.strftime('%x %X', self.ref_time))
        except locale.Error:
            return False

    def test_parse_date_libc(self):
        tz = datefmt.timezone('GMT +2:00')
        expected = datetime.datetime(2010, 8, 28, 13, 45, 56, 0, tz)
        expected_minute = datetime.datetime(2010, 8, 28, 13, 45, 0, 0, tz)
        expected_date = datetime.datetime(2010, 8, 28, 0, 0, 0, 0, tz)

        self.assertTrue(self._setlocale('C'))
        self.assertEqual(expected,
                         datefmt.parse_date('08/28/10 13:45:56', tz))
        self.assertEqual(expected_minute,
                         datefmt.parse_date('08/28/10 13:45', tz))
        self.assertEqual(expected_date, datefmt.parse_date('08/28/10', tz))
        self.assertEqual(expected_minute,
                         datefmt.parse_date('28 Aug 2010 1:45 pm', tz))

        if self._setlocale('en_US.UTF8'):
            self.assertEqual(expected,
                             datefmt.parse_date('Aug 28, 2010 1:45:56 PM', tz))
            self.assertEqual(expected,
                             datefmt.parse_date('8 28, 2010 1:45:56 PM', tz))
            self.assertEqual(expected,
                             datefmt.parse_date('28 Aug 2010 1:45:56 PM', tz))
            self.assertEqual(expected,
                             datefmt.parse_date('28 Aug 2010 PM 1:45:56', tz))
            self.assertEqual(expected,
                             datefmt.parse_date('28 Aug 2010 13:45:56', tz))
            self.assertEqual(expected_minute,
                             datefmt.parse_date('28 Aug 2010 PM 1:45', tz))
            self.assertEqual(expected_date,
                             datefmt.parse_date('28 Aug 2010', tz))

        if self._setlocale('en_GB.UTF8'):
            self.assertEqual(expected,
                             datefmt.parse_date('28 Aug 2010 13:45:56', tz))
            self.assertEqual(expected_minute,
                             datefmt.parse_date('28 Aug 2010 PM 1:45', tz))
            self.assertEqual(expected_date,
                             datefmt.parse_date('28 Aug 2010', tz))

        if self._setlocale('fr_FR.UTF8'):
            self.assertEqual(expected,
                             datefmt.parse_date(u'28 août 2010 13:45:56', tz))
            self.assertEqual(expected,
                             datefmt.parse_date(u'août 28 2010 13:45:56', tz))
            self.assertEqual(expected_minute,
                             datefmt.parse_date(u'août 28 2010 13:45', tz))
            self.assertEqual(expected_date,
                             datefmt.parse_date(u'août 28 2010', tz))
            self.assertEqual(expected_minute,
                             datefmt.parse_date('Aug 28 2010 1:45 pm', tz))

        if self._setlocale('ja_JP.UTF8'):
            self.assertEqual(expected,
                             datefmt.parse_date('2010/08/28 13:45:56', tz))
            self.assertEqual(expected_minute,
                             datefmt.parse_date('2010/08/28 13:45', tz))
            self.assertEqual(expected_date,
                             datefmt.parse_date('2010/08/28', tz))
            self.assertEqual(expected_minute,
                             datefmt.parse_date('2010/Aug/28 1:45 pm', tz))

        if self._setlocale('zh_CN.UTF8'):
            self.assertEqual(expected,
                             datefmt.parse_date(u'2010-8-28 下午01:45:56', tz))
            self.assertEqual(expected,
                             datefmt.parse_date(u'2010-8-28 01:45:56下午', tz))
            self.assertEqual(expected_minute,
                             datefmt.parse_date(u'2010-8-28 下午01:45', tz))
            self.assertEqual(expected_minute,
                             datefmt.parse_date(u'2010-8-28 01:45下午', tz))
            self.assertEqual(expected_date,
                             datefmt.parse_date('2010-8-28', tz))
            self.assertEqual(expected_minute,
                             datefmt.parse_date('2010-Aug-28 01:45 pm', tz))


class ParseRelativeDateTestCase(unittest.TestCase):

    def test_time_interval_seconds(self):
        tz = datefmt.timezone('GMT +1:00')
        now = datetime.datetime(2012, 3, 25, 3, 15, 21, 987654, tzinfo=tz)
        in_53s = datetime.datetime(2012, 3, 25, 3, 16, 14, 987654, tzinfo=tz)
        past_42s = datetime.datetime(2012, 3, 25, 3, 14, 39, 987654, tzinfo=tz)

        self.assertEqual(
            in_53s,
            datefmt._parse_relative_time('in53second', tz, now))
        self.assertEqual(
            in_53s,
            datefmt._parse_relative_time('+ 53second', tz, now))
        self.assertEqual(
            None,
            datefmt._parse_relative_time('+53s', tz, now))
        self.assertEqual(
            None,
            datefmt._parse_relative_time('+ 53second ago', tz, now))

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
            past_42s,
            datefmt._parse_relative_time('-42seconds', tz, now))
        self.assertEqual(
            past_42s,
            datefmt._parse_relative_time('- 42second ago', tz, now))
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
            datetime.datetime(2012, 3, 25, 3, 57, 21, 987654, tzinfo=tz),
            datefmt._parse_relative_time('+42minute', tz, now))
        self.assertEqual(
            datetime.datetime(2012, 3, 25, 3, 57, 51, 987654, tzinfo=tz),
            datefmt._parse_relative_time('in 42.50 minutes', tz, now))

        self.assertEqual(
            datetime.datetime(2012, 3, 25, 2, 54, 21, 987654, tzinfo=tz),
            datefmt._parse_relative_time('21minute', tz, now))
        self.assertEqual(
            datetime.datetime(2012, 3, 25, 2, 54, 6, 987654, tzinfo=tz),
            datefmt._parse_relative_time('21.25 minutes', tz, now))
        self.assertEqual(
            datetime.datetime(2012, 3, 25, 2, 53, 36, 987654, tzinfo=tz),
            datefmt._parse_relative_time('- 21.75 minutes', tz, now))

    def test_time_interval_hours(self):
        tz = datefmt.timezone('GMT +1:00')
        now = datetime.datetime(2012, 3, 25, 3, 15, 21, 987654, tzinfo=tz)
        in_31h = datetime.datetime(2012, 3, 26, 10, 15, 21, 987654, tzinfo=tz)
        past_42h = datetime.datetime(2012, 3, 23, 9, 15, 21, 987654, tzinfo=tz)

        self.assertEqual(
            in_31h,
            datefmt._parse_relative_time('in 31 hours', tz, now))
        self.assertEqual(
            in_31h,
            datefmt._parse_relative_time('+31. hours', tz, now))
        self.assertEqual(
            in_31h,
            datefmt._parse_relative_time('in31h', tz, now))
        self.assertEqual(
            past_42h,
            datefmt._parse_relative_time('42 hours', tz, now))
        self.assertEqual(
            past_42h,
            datefmt._parse_relative_time('42h ago', tz, now))
        self.assertEqual(
            past_42h,
            datefmt._parse_relative_time('-42h ago', tz, now))

    def test_time_interval_days(self):
        tz = datefmt.timezone('GMT +1:00')
        now = datetime.datetime(2012, 3, 25, 3, 15, 21, 987654, tzinfo=tz)
        in_35d = datetime.datetime(2012, 4, 29, 3, 15, 21, 987654, tzinfo=tz)
        past_24d = datetime.datetime(2012, 3, 1, 3, 15, 21, 987654, tzinfo=tz)

        self.assertEqual(
            in_35d,
            datefmt._parse_relative_time('+35day', tz, now))
        self.assertEqual(
            in_35d,
            datefmt._parse_relative_time('in35ds', tz, now))
        self.assertEqual(
            past_24d,
            datefmt._parse_relative_time('24day', tz, now))
        self.assertEqual(
            past_24d,
            datefmt._parse_relative_time('24ds', tz, now))
        self.assertEqual(
            past_24d,
            datefmt._parse_relative_time('- 24ds', tz, now))

    def test_time_interval_weeks(self):
        tz = datefmt.timezone('GMT +1:00')
        now = datetime.datetime(2012, 3, 25, 3, 15, 21, 987654, tzinfo=tz)
        in_4w = datetime.datetime(2012, 4, 22, 3, 15, 21, 987654, tzinfo=tz)
        past_3w = datetime.datetime(2012, 3, 4, 3, 15, 21, 987654, tzinfo=tz)

        self.assertEqual(in_4w,
                         datefmt._parse_relative_time('in 4 weeks', tz, now))
        self.assertEqual(in_4w,
                         datefmt._parse_relative_time('+4w', tz, now))
        self.assertEqual(past_3w,
                         datefmt._parse_relative_time('3 weeks', tz, now))
        self.assertEqual(past_3w,
                         datefmt._parse_relative_time('3w', tz, now))
        self.assertEqual(past_3w,
                         datefmt._parse_relative_time('-3w', tz, now))

    def test_time_interval_months(self):
        tz = datefmt.timezone('GMT +1:00')
        now = datetime.datetime(2012, 1, 1, 3, 15, 21, 987654, tzinfo=tz)
        in_18m = datetime.datetime(2013, 6, 24, 3, 15, 21, 987654, tzinfo=tz)
        past_12m = datetime.datetime(2011, 1, 6, 3, 15, 21, 987654, tzinfo=tz)

        self.assertEqual(
            in_18m,
            datefmt._parse_relative_time('in 18 months', tz, now))
        self.assertEqual(
            in_18m,
            datefmt._parse_relative_time('+18 ms', tz, now))
        self.assertEqual(
            past_12m,
            datefmt._parse_relative_time('12 months', tz, now))
        self.assertEqual(
            past_12m,
            datefmt._parse_relative_time('12 ms ago', tz, now))
        self.assertEqual(
            past_12m,
            datefmt._parse_relative_time('- 12 ms ago', tz, now))

    def test_time_interval_years(self):
        tz = datefmt.timezone('GMT +1:00')
        now = datetime.datetime(2012, 3, 25, 3, 15, 21, 987654, tzinfo=tz)
        in_5y = datetime.datetime(2017, 3, 24, 3, 15, 21, 987654, tzinfo=tz)
        past_2y = datetime.datetime(2010, 3, 26, 3, 15, 21, 987654, tzinfo=tz)

        self.assertEqual(in_5y,
                         datefmt._parse_relative_time('in 5 years', tz, now))
        self.assertEqual(in_5y, datefmt._parse_relative_time('+5y', tz, now))
        self.assertEqual(past_2y,
                         datefmt._parse_relative_time('2 years', tz, now))
        self.assertEqual(past_2y, datefmt._parse_relative_time('2y', tz, now))
        self.assertEqual(past_2y, datefmt._parse_relative_time('-2y', tz, now))

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

    def test_time_start_tomorrow(self):
        tz = datefmt.timezone('GMT +1:00')
        now = datetime.datetime(2012, 3, 25, 3, 15, 21, 987654, tzinfo=tz)
        tomorrow = datefmt.to_datetime(datetime.datetime(2012, 3, 26), tz)
        self.assertEqual(tomorrow,
                         datefmt._parse_relative_time('tomorrow', tz, now))
        self.assertEqual(tomorrow,
                         datefmt._parse_relative_time('next day', tz, now))

    def test_time_start_year(self):
        tz = datefmt.timezone('GMT +1:00')

        now = datetime.datetime(2012, 3, 25, 3, 15, 21, 987654, tzinfo=tz)
        self.assertEqual(datetime.datetime(2012, 1, 1, tzinfo=tz),
                         datefmt._parse_relative_time('this year', tz, now))
        self.assertEqual(datetime.datetime(2011, 1, 1, tzinfo=tz),
                         datefmt._parse_relative_time('last year', tz, now))
        self.assertEqual(datetime.datetime(2013, 1, 1, tzinfo=tz),
                         datefmt._parse_relative_time('next year', tz, now))

        now = datetime.datetime(2009, 3, 25, 3, 15, 21, 987654, tzinfo=tz)
        self.assertEqual(datetime.datetime(2009, 1, 1, tzinfo=tz),
                         datefmt._parse_relative_time('this year', tz, now))
        self.assertEqual(datetime.datetime(2008, 1, 1, tzinfo=tz),
                         datefmt._parse_relative_time('last year', tz, now))
        self.assertEqual(datetime.datetime(2010, 1, 1, tzinfo=tz),
                         datefmt._parse_relative_time('next year', tz, now))

    def test_time_start_month(self):
        tz = datefmt.timezone('GMT +1:00')
        now = datetime.datetime(2012, 1, 23, 3, 15, 42, 987654, tzinfo=tz)
        self.assertEqual(datetime.datetime(2012, 1, 1, tzinfo=tz),
                         datefmt._parse_relative_time('this month', tz, now))
        self.assertEqual(datetime.datetime(2011, 12, 1, tzinfo=tz),
                         datefmt._parse_relative_time('last month', tz, now))
        self.assertEqual(datetime.datetime(2012, 2, 1, tzinfo=tz),
                         datefmt._parse_relative_time('next month', tz, now))

    def test_time_start_week(self):
        tz = datefmt.timezone('GMT +1:00')
        now = datetime.datetime(2012, 3, 25, 3, 15, 21, 987654, tzinfo=tz)
        self.assertEqual(datetime.datetime(2012, 3, 19, tzinfo=tz),
                         datefmt._parse_relative_time('this week', tz, now))
        self.assertEqual(datetime.datetime(2012, 3, 12, tzinfo=tz),
                         datefmt._parse_relative_time('last week', tz, now))
        self.assertEqual(datetime.datetime(2012, 3, 26, tzinfo=tz),
                         datefmt._parse_relative_time('next week', tz, now))

    def test_time_start_day(self):
        tz = datefmt.timezone('GMT +1:00')
        now = datetime.datetime(2012, 3, 1, 3, 15, 21, 987654, tzinfo=tz)
        self.assertEqual(datetime.datetime(2012, 3, 1, tzinfo=tz),
                         datefmt._parse_relative_time('this day', tz, now))
        self.assertEqual(datetime.datetime(2012, 2, 29, tzinfo=tz),
                         datefmt._parse_relative_time('last day', tz, now))
        self.assertEqual(datetime.datetime(2012, 3, 2, tzinfo=tz),
                         datefmt._parse_relative_time('next day', tz, now))

    def test_time_start_hour(self):
        tz = datefmt.timezone('GMT +1:00')
        now = datetime.datetime(2012, 3, 25, 0, 15, 21, 987654, tzinfo=tz)
        self.assertEqual(datetime.datetime(2012, 3, 25, 0, tzinfo=tz),
                         datefmt._parse_relative_time('this hour', tz, now))
        self.assertEqual(datetime.datetime(2012, 3, 24, 23, tzinfo=tz),
                         datefmt._parse_relative_time('last hour', tz, now))
        self.assertEqual(datetime.datetime(2012, 3, 25, 1, tzinfo=tz),
                         datefmt._parse_relative_time('next hour', tz, now))

    def test_time_start_minute(self):
        tz = datefmt.timezone('GMT +1:00')
        now = datetime.datetime(2012, 3, 25, 3, 0, 21, 987654, tzinfo=tz)
        self.assertEqual(datetime.datetime(2012, 3, 25, 3, 0, tzinfo=tz),
                         datefmt._parse_relative_time('this minute', tz, now))
        self.assertEqual(datetime.datetime(2012, 3, 25, 2, 59, tzinfo=tz),
                         datefmt._parse_relative_time('last minute', tz, now))
        self.assertEqual(datetime.datetime(2012, 3, 25, 3, 1, tzinfo=tz),
                         datefmt._parse_relative_time('next minute', tz, now))

    def test_time_start_second(self):
        tz = datefmt.timezone('GMT +1:00')
        now = datetime.datetime(2012, 3, 25, 3, 15, 0, 987654, tzinfo=tz)
        self.assertEqual(datetime.datetime(2012, 3, 25, 3, 15, 0, tzinfo=tz),
                         datefmt._parse_relative_time('this second', tz, now))
        self.assertEqual(datetime.datetime(2012, 3, 25, 3, 14, 59, tzinfo=tz),
                         datefmt._parse_relative_time('last second', tz, now))
        self.assertEqual(datetime.datetime(2012, 3, 25, 3, 15, 1, tzinfo=tz),
                         datefmt._parse_relative_time('next second', tz, now))

    if datefmt.pytz:
        def test_time_past_interval_across_dst(self):
            tz = datefmt.timezone('Europe/Paris')
            now = datefmt.to_datetime(datetime.datetime(2012, 3, 25, 3, 0, 41),
                                      tz)
            dt = datefmt._parse_relative_time('41 seconds', tz, now)
            self.assertEqual('2012-03-25T03:00:00+02:00', dt.isoformat())
            dt = datefmt._parse_relative_time('42 seconds', tz, now)
            self.assertEqual('2012-03-25T01:59:59+01:00', dt.isoformat())

        def test_time_future_interval_across_dst(self):
            tz = datefmt.timezone('Europe/Paris')
            now = datefmt.to_datetime(
                datetime.datetime(2012, 3, 25, 1, 59, 39), tz)

            actual = datefmt._parse_relative_time('+20 seconds', tz, now)
            self.assertEqual('2012-03-25T01:59:59+01:00', actual.isoformat())
            actual = datefmt._parse_relative_time('+21 seconds', tz, now)
            self.assertEqual('2012-03-25T03:00:00+02:00', actual.isoformat())

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

        def test_next_time_start_across_dst(self):
            tz = datefmt.timezone('Europe/Paris')
            now = datefmt.to_datetime(
                datetime.datetime(2012, 3, 25, 1, 15, 42, 123456), tz)
            dt = datefmt._parse_relative_time('next hour', tz, now)
            self.assertEqual('2012-03-25T03:00:00+02:00', dt.isoformat())
            dt = datefmt._parse_relative_time('tomorrow', tz, now)
            self.assertEqual('2012-03-26T00:00:00+02:00', dt.isoformat())
            dt = datefmt._parse_relative_time('next day', tz, now)
            self.assertEqual('2012-03-26T00:00:00+02:00', dt.isoformat())


class ParseDateValidRangeTestCase(unittest.TestCase):

    def test_max_timestamp(self):
        # At least all platforms support maximal signed 32 bits integer,
        # 2**31 - 1, INT32_MAX.
        datefmt.parse_date('2038-01-19T03:14:07Z')
        try:
            datefmt.parse_date('9999-12-31T23:59:59-12:00')
            raise self.failureException('TracError not raised')
        except TracError as e:
            self.assertIn('is outside valid range', unicode(e))

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
            raise self.failureException('TracError not raised')
        except TracError as e:
            self.assertIn('is outside valid range', unicode(e))

    def test_large_integer_in_date_part(self):
        def try_parse(text):
            try:
                # using libc's format
                rv = datefmt.parse_date(text, datefmt.utc)
                self.fail('TracError not raised: %r' % rv)
            except TracError as e:
                self.assertIn('is an invalid date', unicode(e))

            if locale_en:
                try:
                    # using Babel's format
                    rv = datefmt.parse_date(text, datefmt.utc, locale_en)
                    self.fail('TracError not raised: %r' % rv)
                except TracError as e:
                    self.assertIn('is an invalid date', unicode(e))

        try_parse('Jan 2147483647, 2016')
        try_parse('Jan 2147483648, 2016')
        try_parse('Jan 9223372036854775808, 2016')
        try_parse('Jan 18446744073709551616, 2016')
        try_parse('2147483647 02, 2016')
        try_parse('2147483648 02, 2016')
        try_parse('9223372036854775808 02, 2016')
        try_parse('18446744073709551616 02, 2016')
        try_parse('Jan 02, 2147483647')
        try_parse('Jan 02, 2147483648')
        try_parse('Jan 02, 9223372036854775808')
        try_parse('Jan 02, 18446744073709551616')

    def test_large_integer_in_time_part(self):
        def try_parse(expected, text):
            # using libc's format
            self.assertEqual(expected, datefmt.parse_date(text, datefmt.utc))
            if locale_en:
                # using Babel's format
                self.assertEqual(expected,
                                 datefmt.parse_date(text, datefmt.utc,
                                                    locale_en))

        expected = datetime.datetime(2016, 1, 2, 0, 0, 0, 0, datefmt.utc)
        try_parse(expected, 'Jan 02, 2016 24:34:56')
        try_parse(expected, 'Jan 02, 2016 2147483647:34:56')
        try_parse(expected, 'Jan 02, 2016 2147483648:34:56')
        try_parse(expected, 'Jan 02, 2016 9223372036854775808:34:56')
        try_parse(expected, 'Jan 02, 2016 18446744073709551616:34:56')
        try_parse(expected, 'Jan 02, 2016 12:60:56')
        try_parse(expected, 'Jan 02, 2016 12:2147483647:56')
        try_parse(expected, 'Jan 02, 2016 12:2147483648:56')
        try_parse(expected, 'Jan 02, 2016 12:9223372036854775808:56')
        try_parse(expected, 'Jan 02, 2016 12:18446744073709551616:56')
        try_parse(expected, 'Jan 02, 2016 12:34:60')
        try_parse(expected, 'Jan 02, 2016 12:34:2147483647')
        try_parse(expected, 'Jan 02, 2016 12:34:2147483648')
        try_parse(expected, 'Jan 02, 2016 12:34:9223372036854775808')
        try_parse(expected, 'Jan 02, 2016 12:34:18446744073709551616')

    def test_iso8601_out_of_range(self):
        self.assertRaises(TracError, datefmt.parse_date,
                          '0000-01-02T12:34:56.987654Z')
        self.assertRaises(TracError, datefmt.parse_date,
                          '10000-01-02T12:34:56.987654Z')
        self.assertRaises(TracError, datefmt.parse_date,
                          '10001-01-02T12:34:56.987654Z')
        self.assertRaises(TracError, datefmt.parse_date,
                          '2016-00-02T12:34:56.987654Z')
        self.assertRaises(TracError, datefmt.parse_date,
                          '2016-13-02T12:34:56.987654Z')
        self.assertRaises(TracError, datefmt.parse_date,
                          '2016-01-00T12:34:56.987654Z')
        self.assertRaises(TracError, datefmt.parse_date,
                          '2016-01-32T12:34:56.987654Z')
        self.assertRaises(TracError, datefmt.parse_date,
                          '2016-01-02T24:34:56.987654Z')
        self.assertRaises(TracError, datefmt.parse_date,
                          '2016-01-02T12:60:56.987654Z')
        self.assertRaises(TracError, datefmt.parse_date,
                          '2016-01-02T12:34:60.987654Z')


class DateFormatTestCase(unittest.TestCase):

    def test_time_now(self):
        now = time.time()
        actual = datefmt.time_now()
        self.assertEqual(float, type(actual))
        self.assertTrue(now - 1.0 < actual < now + 1.0,
                        'now %r, actual %r' % (now, actual))

    def test_datetime_now(self):
        self.assertEqual(datetime.datetime.now().tzinfo,
                         datefmt.datetime_now().tzinfo)
        self.assertEqual(datetime.datetime.now(datefmt.utc).tzinfo,
                         datefmt.datetime_now(datefmt.utc).tzinfo)
        gmt01 = datefmt.timezone('GMT +1:00')
        self.assertEqual(datetime.datetime.now(gmt01).tzinfo,
                         datefmt.datetime_now(gmt01).tzinfo)
        now = datetime.datetime.now(gmt01)
        actual = datefmt.datetime_now(gmt01)
        delta = datetime.timedelta(seconds=1)
        self.assertTrue(now - delta < actual < now + delta,
                        'now %s, actual %s' %
                        (now.isoformat(), actual.isoformat()))

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

    def test_to_datetime_typeerror(self):
        self.assertRaises(TypeError, datefmt.to_datetime, 'blah')
        self.assertRaises(TypeError, datefmt.to_datetime, u'bl\xe1h')

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
        self.assertEqual(datefmt.format_date(t, 'iso8601', datefmt.utc),
                         expected.split('T')[0])
        self.assertEqual(datefmt.format_time(t, 'iso8601', datefmt.utc),
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
        self.assertEqual(datefmt.format_date(t, 'iso8601', gmt01),
                         expected.split('T')[0])
        self.assertEqual(datefmt.format_time(t, 'iso8601', gmt01),
                         expected.split('T')[1])

    def test_format_iso8601_before_1900(self):
        t = datetime.datetime(1899, 12, 30, 23, 58, 59, 123456, datefmt.utc)
        self.assertEqual('1899-12-30T23:58:59Z',
                         datefmt.format_datetime(t, 'iso8601', datefmt.utc))
        self.assertEqual('1899-12-30',
                         datefmt.format_datetime(t, 'iso8601date',
                                                 datefmt.utc))
        self.assertEqual('1899-12-30',
                         datefmt.format_date(t, 'iso8601', datefmt.utc))
        self.assertEqual('23:58:59Z',
                         datefmt.format_datetime(t, 'iso8601time',
                                                 datefmt.utc))
        self.assertEqual('23:58:59Z',
                         datefmt.format_time(t, 'iso8601', datefmt.utc))

    def test_format_date_accepts_date_instances(self):
        a_date = datetime.date(2009, 8, 20)
        self.assertEqual('2009-08-20',
                         datefmt.format_date(a_date, format='%Y-%m-%d'))

    def test_format_compatibility(self):
        tz = datefmt.timezone('GMT +2:00')
        t = datetime.datetime(2010, 8, 28, 11, 45, 56, 123456, datefmt.utc)
        tz_t = datetime.datetime(2010, 8, 28, 13, 45, 56, 123456, tz)

        # Converting babel's format to strftime format
        self.assertEqual(tz_t.strftime('%x %H:%M').decode('utf-8'),
                         datefmt.format_datetime(t, 'short', tz))
        self.assertEqual(tz_t.strftime('%x').decode('utf-8'),
                         datefmt.format_date(t, 'short', tz))
        self.assertEqual(tz_t.strftime('%H:%M').decode('utf-8'),
                         datefmt.format_time(t, 'short', tz))
        for f in ('medium', 'long', 'full'):
            self.assertEqual(tz_t.strftime('%x %X').decode('utf-8'),
                             datefmt.format_datetime(t, f, tz))
            self.assertEqual(tz_t.strftime('%x').decode('utf-8'),
                             datefmt.format_date(t, f, tz))
            self.assertEqual(tz_t.strftime('%X').decode('utf-8'),
                             datefmt.format_time(t, f, tz))


class UTimestampTestCase(unittest.TestCase):

    def test_sub_second(self):
        t = datetime.datetime(2001, 2, 3, 4, 5, 6, 123456, datefmt.utc)
        ts = datefmt.to_utimestamp(t)
        self.assertEqual(981173106123456L, ts)
        self.assertEqual(t, datefmt.from_utimestamp(ts))


class ISO8601TestCase(unittest.TestCase):
    def test_default(self):
        tz = datefmt.timezone('GMT +2:00')
        t = datetime.datetime(2010, 8, 28, 11, 45, 56, 123456, tz)
        self.assertEqual('2010-08-28',
                         datefmt.format_date(t, tzinfo=tz, locale='iso8601'))
        self.assertEqual('11:45:56+02:00',
                         datefmt.format_time(t, tzinfo=tz, locale='iso8601'))
        self.assertEqual('2010-08-28T11:45:56+02:00',
                         datefmt.format_datetime(t, tzinfo=tz,
                                                 locale='iso8601'))

    def test_with_iso8601(self):
        tz = datefmt.timezone('GMT +2:00')
        t = datetime.datetime(2010, 8, 28, 11, 45, 56, 123456, tz)
        self.assertEqual('2010-08-28',
                         datefmt.format_date(t, 'iso8601', tz, 'iso8601'))
        self.assertEqual('11:45:56+02:00',
                         datefmt.format_time(t, 'iso8601', tz, 'iso8601'))
        self.assertEqual('2010-08-28T11:45:56+02:00',
                         datefmt.format_datetime(t, 'iso8601', tz, 'iso8601'))

    def test_parse_date_offset(self):
        t_utc = datetime.datetime(2009, 12, 1, 11, 0, 0, 0, datefmt.utc)
        self.assertEqual(t_utc,
                         datefmt.parse_date('2009-12-01T11:00:00Z'))
        self.assertEqual(t_utc,
                         datefmt.parse_date('2009-12-01T11:00:00+00:00'))
        self.assertEqual(t_utc,
                         datefmt.parse_date('2009-12-01T11:00:00-00:00'))
        self.assertEqual(t_utc,
                         datefmt.parse_date('2009-12-01T09:00:00-02:00'))
        self.assertEqual(t_utc,
                         datefmt.parse_date('2009-12-01T11:30:00+00:30'))

    def test_parse_date_usec(self):
        tz = datefmt.get_timezone('GMT +1:00')
        t_utc = datetime.datetime(2009, 12, 1, 11, 0, 0, 98765, datefmt.utc)
        self.assertEqual(t_utc,
                         datefmt.parse_date('2009-12-01T12:00:00.098765', tz))
        self.assertEqual(t_utc,
                         datefmt.parse_date('2009-12-01T12:00:00,098765', tz))
        self.assertEqual(datetime.datetime(2009, 12, 1, 11, 0, 0, 98700,
                                           datefmt.utc),
                         datefmt.parse_date('2009-12-01T12:00:00.0987', tz))
        self.assertEqual(datetime.datetime(2009, 12, 1, 11, 0, 0, 90000,
                                           datefmt.utc),
                         datefmt.parse_date('2009-12-01T12:00:00.09', tz))
        self.assertEqual(datetime.datetime(2009, 12, 1, 11, 0, 0, 0,
                                           datefmt.utc),
                         datefmt.parse_date('2009-12-01T12:00:00.0', tz))

    def test_with_babel_format(self):
        tz = datefmt.timezone('GMT +2:00')
        t = datetime.datetime(2010, 8, 28, 11, 45, 56, 123456, tz)
        for f in ('short', 'medium', 'long', 'full'):
            self.assertEqual('2010-08-28',
                             datefmt.format_date(t, f, tz, 'iso8601'))
        self.assertEqual('11:45',
                         datefmt.format_time(t, 'short', tz, 'iso8601'))
        self.assertEqual('2010-08-28T11:45',
                         datefmt.format_datetime(t, 'short', tz, 'iso8601'))
        self.assertEqual('11:45:56',
                         datefmt.format_time(t, 'medium', tz, 'iso8601'))
        self.assertEqual('2010-08-28T11:45:56',
                         datefmt.format_datetime(t, 'medium', tz, 'iso8601'))
        self.assertEqual('11:45:56+02:00',
                         datefmt.format_time(t, 'long', tz, 'iso8601'))
        self.assertEqual('2010-08-28T11:45:56+02:00',
                         datefmt.format_datetime(t, 'long', tz, 'iso8601'))
        self.assertEqual('11:45:56.123456+02:00',
                         datefmt.format_time(t, 'full', tz, 'iso8601'))
        self.assertEqual('2010-08-28T11:45:56.123456+02:00',
                         datefmt.format_datetime(t, 'full', tz, 'iso8601'))

    def test_with_babel_format_before_1900(self):
        tz = datefmt.timezone('GMT +2:00')
        t = datetime.datetime(1899, 8, 28, 11, 45, 56, 123456, tz)
        for f in ('short', 'medium', 'long', 'full'):
            self.assertEqual('1899-08-28',
                             datefmt.format_date(t, f, tz, 'iso8601'))
        self.assertEqual('11:45',
                         datefmt.format_time(t, 'short', tz, 'iso8601'))
        self.assertEqual('1899-08-28T11:45',
                         datefmt.format_datetime(t, 'short', tz, 'iso8601'))
        self.assertEqual('11:45:56',
                         datefmt.format_time(t, 'medium', tz, 'iso8601'))
        self.assertEqual('1899-08-28T11:45:56',
                         datefmt.format_datetime(t, 'medium', tz, 'iso8601'))
        self.assertEqual('11:45:56+02:00',
                         datefmt.format_time(t, 'long', tz, 'iso8601'))
        self.assertEqual('1899-08-28T11:45:56+02:00',
                         datefmt.format_datetime(t, 'long', tz, 'iso8601'))
        self.assertEqual('11:45:56.123456+02:00',
                         datefmt.format_time(t, 'full', tz, 'iso8601'))
        self.assertEqual('1899-08-28T11:45:56.123456+02:00',
                         datefmt.format_datetime(t, 'full', tz, 'iso8601'))

    def test_hint_date(self):
        try:
            datefmt.parse_date('***', locale='iso8601', hint='date')
            raise self.failureException('TracError not raised')
        except TracError as e:
            self.assertIn('Try "YYYY-MM-DD" instead.', unicode(e))

    def test_hint_datetime(self):
        try:
            datefmt.parse_date('***', locale='iso8601', hint='datetime')
            raise self.failureException('TracError not raised')
        except TracError as e:
            self.assertIn(u'Try "YYYY-MM-DDThh:mm:ss±hh:mm" instead.',
                          unicode(e))

    def test_hint_foobar(self):
        try:
            datefmt.parse_date('***', locale='iso8601', hint='foobar')
            raise self.failureException('TracError not raised')
        except TracError as e:
            self.assertIn(u'Try "foobar" or "YYYY-MM-DDThh:mm:ss±hh:mm" '
                          u'instead.', unicode(e))


if Locale is None:
    I18nDateFormatTestCase = None
else:
    class I18nDateFormatTestCase(unittest.TestCase):

        def test_i18n_format_datetime(self):
            tz = datefmt.timezone('GMT +2:00')
            t = datetime.datetime(2010, 8, 28, 11, 45, 56, 123456, datefmt.utc)
            self.assertIn(datefmt.format_datetime(t, tzinfo=tz,
                                                  locale=locale_en),
                          ('Aug 28, 2010 1:45:56 PM',
                           'Aug 28, 2010, 1:45:56 PM'))  # CLDR 23
            en_GB = Locale.parse('en_GB')
            self.assertIn(datefmt.format_datetime(t, tzinfo=tz, locale=en_GB),
                          ('28 Aug 2010 13:45:56', '28 Aug 2010, 13:45:56'))
            fr = Locale.parse('fr')
            self.assertIn(datefmt.format_datetime(t, tzinfo=tz, locale=fr),
                          (u'28 août 2010 13:45:56',
                           u'28 ao\xfbt 2010 \xe0 13:45:56'))
            ja = Locale.parse('ja')
            self.assertEqual(u'2010/08/28 13:45:56',
                             datefmt.format_datetime(t, tzinfo=tz, locale=ja))
            vi = Locale.parse('vi')
            self.assertIn(datefmt.format_datetime(t, tzinfo=tz, locale=vi),
                          ('13:45:56 28-08-2010', '13:45:56, 28 thg 8, 2010'))
            zh_CN = Locale.parse('zh_CN')
            self.assertIn(datefmt.format_datetime(t, tzinfo=tz, locale=zh_CN),
                          (u'2010-8-28 下午01:45:56',
                           u'2010年8月28日 下午1:45:56'))

        def test_i18n_format_date(self):
            tz = datefmt.timezone('GMT +2:00')
            t = datetime.datetime(2010, 8, 7, 11, 45, 56, 123456, datefmt.utc)
            self.assertEqual('Aug 7, 2010',
                             datefmt.format_date(t, tzinfo=tz,
                                                 locale=locale_en))
            en_GB = Locale.parse('en_GB')
            self.assertEqual('7 Aug 2010',
                             datefmt.format_date(t, tzinfo=tz, locale=en_GB))
            fr = Locale.parse('fr')
            self.assertEqual(u'7 août 2010',
                             datefmt.format_date(t, tzinfo=tz, locale=fr))
            ja = Locale.parse('ja')
            self.assertEqual(u'2010/08/07',
                             datefmt.format_date(t, tzinfo=tz, locale=ja))
            vi = Locale.parse('vi')
            self.assertIn(datefmt.format_date(t, tzinfo=tz, locale=vi),
                          ('07-08-2010', '7 thg 8, 2010'))
            zh_CN = Locale.parse('zh_CN')
            self.assertIn(datefmt.format_date(t, tzinfo=tz, locale=zh_CN),
                          (u'2010-8-7', u'2010年8月7日'))

        def test_i18n_format_time(self):
            tz = datefmt.timezone('GMT +2:00')
            t = datetime.datetime(2010, 8, 28, 11, 45, 56, 123456, datefmt.utc)
            en_GB = Locale.parse('en_GB')
            fr = Locale.parse('fr')
            ja = Locale.parse('ja')
            vi = Locale.parse('vi')
            zh_CN = Locale.parse('zh_CN')

            self.assertEqual('1:45:56 PM',
                             datefmt.format_time(t, tzinfo=tz,
                                                 locale=locale_en))
            self.assertEqual('13:45:56',
                             datefmt.format_time(t, tzinfo=tz, locale=en_GB))
            self.assertEqual('13:45:56',
                             datefmt.format_time(t, tzinfo=tz, locale=fr))
            self.assertEqual('13:45:56',
                             datefmt.format_time(t, tzinfo=tz, locale=ja))
            self.assertEqual('13:45:56',
                             datefmt.format_time(t, tzinfo=tz, locale=vi))
            self.assertIn(datefmt.format_time(t, tzinfo=tz, locale=zh_CN),
                          (u'下午01:45:56', u'下午1:45:56'))

        def test_i18n_datetime_hint(self):
            en_GB = Locale.parse('en_GB')
            fr = Locale.parse('fr')
            ja = Locale.parse('ja')
            vi = Locale.parse('vi')
            zh_CN = Locale.parse('zh_CN')

            self.assertIn(datefmt.get_datetime_format_hint(locale_en),
                          ('MMM d, yyyy h:mm:ss a', 'MMM d, y h:mm:ss a',
                           'MMM d, y, h:mm:ss a'))
            self.assertIn(datefmt.get_datetime_format_hint(en_GB),
                          ('d MMM yyyy HH:mm:ss', 'd MMM y HH:mm:ss',
                           'd MMM y, HH:mm:ss'))
            self.assertIn(datefmt.get_datetime_format_hint(fr),
                          ('d MMM yyyy HH:mm:ss', 'd MMM y HH:mm:ss',
                           u"d MMM y '\xe0' HH:mm:ss"))
            self.assertIn(datefmt.get_datetime_format_hint(ja),
                          ('yyyy/MM/dd H:mm:ss', 'y/MM/dd H:mm:ss'))
            self.assertIn(datefmt.get_datetime_format_hint(vi),
                          ('HH:mm:ss dd-MM-yyyy', 'HH:mm:ss dd-MM-y',
                           'HH:mm:ss, d MMM, y'))
            self.assertIn(datefmt.get_datetime_format_hint(zh_CN),
                          ('yyyy-M-d ahh:mm:ss', u'y年M月d日 ah:mm:ss'))

        def test_i18n_date_hint(self):
            en_GB = Locale.parse('en_GB')
            fr = Locale.parse('fr')
            ja = Locale.parse('ja')
            vi = Locale.parse('vi')
            zh_CN = Locale.parse('zh_CN')

            self.assertIn(datefmt.get_date_format_hint(locale_en),
                          ('MMM d, yyyy', 'MMM d, y'))
            self.assertIn(datefmt.get_date_format_hint(en_GB),
                          ('d MMM yyyy', 'd MMM y'))
            self.assertIn(datefmt.get_date_format_hint(fr),
                          ('d MMM yyyy', 'd MMM y'))
            self.assertIn(datefmt.get_date_format_hint(ja),
                          ('yyyy/MM/dd', 'y/MM/dd'))
            self.assertIn(datefmt.get_date_format_hint(vi),
                          ('dd-MM-yyyy', 'dd-MM-y', 'd MMM, y'))
            self.assertIn(datefmt.get_date_format_hint(zh_CN),
                          ('yyyy-M-d', u'y年M月d日'))

        def test_i18n_parse_date_iso8609(self):
            tz = datefmt.timezone('GMT +2:00')
            dt = datetime.datetime(2010, 8, 28, 13, 45, 56, 0, tz)
            d = datetime.datetime(2010, 8, 28, 0, 0, 0, 0, tz)
            vi = Locale.parse('vi')

            def iso8601(expected, text, tz, locale):
                self.assertEqual(expected,
                                 datefmt.parse_date(text, tz, locale))

            iso8601(dt, '2010-08-28T15:45:56+0400', tz, locale_en)
            iso8601(dt, '2010-08-28T11:45:56+0000', tz, vi)
            iso8601(dt, '2010-08-28T11:45:56Z', tz, vi)
            iso8601(dt, '20100828T144556+0300', tz, locale_en)
            iso8601(dt, '20100828T114556Z', tz, vi)

            iso8601(d, '2010-08-28+0200', tz, locale_en)
            # iso8601(d, '2010-08-28+0000', tz, vi)
            # iso8601(d, '2010-08-28Z', tz, en_US)
            iso8601(d, '2010-08-28', tz, vi)
            iso8601(d, '20100828+0200', tz, locale_en)
            # iso8601(d, '20100828Z', tz, vi)

        def test_i18n_parse_date_datetime(self):
            tz = datefmt.timezone('GMT +2:00')
            expected = datetime.datetime(2010, 8, 28, 13, 45, 56, 0, tz)
            expected_minute = datetime.datetime(2010, 8, 28, 13, 45, 0, 0, tz)
            en_GB = Locale.parse('en_GB')
            fr = Locale.parse('fr')
            ja = Locale.parse('ja')
            vi = Locale.parse('vi')
            zh_CN = Locale.parse('zh_CN')

            self.assertEqual(expected,
                             datefmt.parse_date('Aug 28, 2010 1:45:56 PM', tz,
                                                locale_en))
            self.assertEqual(expected,
                             datefmt.parse_date('8 28, 2010 1:45:56 PM', tz,
                                                locale_en))
            self.assertEqual(expected,
                             datefmt.parse_date('28 Aug 2010 1:45:56 PM', tz,
                                                locale_en))
            self.assertEqual(expected,
                             datefmt.parse_date('28 Aug 2010 PM 1:45:56', tz,
                                                locale_en))
            self.assertEqual(expected,
                             datefmt.parse_date('28 Aug 2010 13:45:56', tz,
                                                locale_en))
            self.assertEqual(expected_minute,
                             datefmt.parse_date('28 Aug 2010 PM 1:45', tz,
                                                locale_en))

            self.assertEqual(expected,
                             datefmt.parse_date('28 Aug 2010 13:45:56', tz,
                                                en_GB))

            self.assertEqual(expected,
                             datefmt.parse_date(u'28 août 2010 13:45:56', tz,
                                                fr))
            self.assertEqual(expected,
                             datefmt.parse_date(u'août 28 2010 13:45:56', tz,
                                                fr))
            self.assertEqual(expected_minute,
                             datefmt.parse_date(u'août 28 2010 13:45', tz,
                                                fr))
            self.assertEqual(expected_minute,
                             datefmt.parse_date('Aug 28 2010 1:45 PM', tz, fr))

            self.assertEqual(expected,
                             datefmt.parse_date('2010/08/28 13:45:56', tz, ja))
            self.assertEqual(expected_minute,
                             datefmt.parse_date('2010/08/28 13:45', tz, ja))
            self.assertEqual(expected_minute,
                             datefmt.parse_date('2010/Aug/28 1:45 PM', tz, ja))

            self.assertEqual(expected,
                             datefmt.parse_date('13:45:56 28-08-2010', tz, vi))
            self.assertEqual(expected_minute,
                             datefmt.parse_date('13:45 28-08-2010', tz, vi))
            self.assertEqual(expected_minute,
                             datefmt.parse_date('1:45PM 28-Aug-2010', tz, vi))

            self.assertEqual(expected,
                             datefmt.parse_date(u'2010-8-28 下午01:45:56',
                                                tz, zh_CN))
            self.assertEqual(expected,
                             datefmt.parse_date(u'2010-8-28 01:45:56下午',
                                                tz, zh_CN))
            self.assertEqual(expected_minute,
                             datefmt.parse_date(u'2010-8-28 下午01:45', tz,
                                                zh_CN))
            self.assertEqual(expected_minute,
                             datefmt.parse_date(u'2010-8-28 01:45下午', tz,
                                                zh_CN))
            self.assertEqual(expected_minute,
                             datefmt.parse_date('2010-Aug-28 01:45PM', tz,
                                                zh_CN))

        def test_i18n_parse_date_datetime_meridiem(self):
            tz = datefmt.timezone('GMT +2:00')
            expected_am = datetime.datetime(2011, 2, 22, 0, 45, 56, 0, tz)
            expected_pm = datetime.datetime(2011, 2, 22, 12, 45, 56, 0, tz)
            zh_CN = Locale.parse('zh_CN')

            self.assertEqual(expected_am,
                             datefmt.parse_date('Feb 22, 2011 0:45:56 AM', tz,
                                                locale_en))
            self.assertEqual(expected_am,
                             datefmt.parse_date('Feb 22, 2011 12:45:56 AM', tz,
                                                locale_en))
            self.assertEqual(expected_am,
                             datefmt.parse_date(u'2011-2-22 上午0:45:56', tz,
                                                zh_CN))
            self.assertEqual(expected_am,
                             datefmt.parse_date(u'2011-2-22 上午12:45:56', tz,
                                                zh_CN))

            self.assertEqual(expected_pm,
                             datefmt.parse_date('Feb 22, 2011 0:45:56 PM', tz,
                                                locale_en))
            self.assertEqual(expected_pm,
                             datefmt.parse_date('Feb 22, 2011 12:45:56 PM', tz,
                                                locale_en))
            self.assertEqual(expected_pm,
                             datefmt.parse_date(u'2011-2-22 下午0:45:56', tz,
                                                zh_CN))
            self.assertEqual(expected_pm,
                             datefmt.parse_date(u'2011-2-22 下午12:45:56', tz,
                                                zh_CN))

        def test_i18n_parse_date_date(self):
            tz = datefmt.timezone('GMT +2:00')
            expected = datetime.datetime(2010, 8, 28, 0, 0, 0, 0, tz)
            en_GB = Locale.parse('en_GB')
            fr = Locale.parse('fr')
            ja = Locale.parse('ja')
            vi = Locale.parse('vi')
            zh_CN = Locale.parse('zh_CN')

            self.assertEqual(expected,
                             datefmt.parse_date('Aug 28, 2010', tz,
                                                locale_en))
            self.assertEqual(expected,
                             datefmt.parse_date('28 Aug 2010', tz, en_GB))
            self.assertEqual(expected,
                             datefmt.parse_date(u'28 août 2010', tz, fr))
            self.assertEqual(expected,
                             datefmt.parse_date('2010/08/28', tz, ja))
            self.assertEqual(expected,
                             datefmt.parse_date('28-08-2010', tz, vi))
            self.assertEqual(expected,
                             datefmt.parse_date(u'2010-8-28', tz, zh_CN))

        def test_i18n_parse_date_roundtrip(self):
            from pkg_resources import resource_listdir
            locales = sorted(dirname
                             for dirname in resource_listdir('trac', 'locale')
                             if '.' not in dirname)

            tz = datefmt.timezone('GMT +2:00')
            t = datetime.datetime(2010, 8, 28, 11, 45, 56, 123456, datefmt.utc)
            tz_t = datetime.datetime(2010, 8, 28, 13, 45, 56, 0, tz)

            for locale in locales:
                locale = Locale.parse(locale)
                formatted = datefmt.format_datetime(t, tzinfo=tz,
                                                    locale=locale)

                actual = datefmt.parse_date(formatted, tz, locale)
                self.assertEqual(tz_t, actual,
                                 '%r != %r (%r %r)' % (tz_t, actual, formatted,
                                                       locale))
                self.assertEqual(tz_t.isoformat(), actual.isoformat())

                actual = datefmt.format_datetime(tz_t, tzinfo=tz,
                                                 locale=locale)
                self.assertEqual(formatted, actual,
                                 '%r != %r (%r)' % (formatted, actual, locale))

        def test_format_compatibility(self):
            tz = datefmt.timezone('GMT +2:00')
            t = datetime.datetime(2010, 8, 28, 11, 45, 56, 123456, datefmt.utc)

            # Converting default format to babel's format
            self.assertIn(datefmt.format_datetime(t, '%x %X', tz, locale_en),
                          ('Aug 28, 2010 1:45:56 PM',
                           'Aug 28, 2010, 1:45:56 PM'))  # CLDR 23
            self.assertEqual('Aug 28, 2010',
                             datefmt.format_datetime(t, '%x', tz, locale_en))
            self.assertEqual('1:45:56 PM',
                             datefmt.format_datetime(t, '%X', tz, locale_en))
            self.assertEqual('Aug 28, 2010',
                             datefmt.format_date(t, '%x', tz, locale_en))
            self.assertEqual('1:45:56 PM',
                             datefmt.format_time(t, '%X', tz, locale_en))

        def test_parse_invalid_date(self):
            tz = datefmt.timezone('GMT +2:00')

            self.assertRaises(TracError, datefmt.parse_date,
                              '',
                              tzinfo=tz, locale=locale_en, hint='date')
            self.assertRaises(TracError, datefmt.parse_date,
                              '2011 Apr Mar',
                              tzinfo=tz, locale=locale_en, hint='date')
            self.assertRaises(TracError, datefmt.parse_date,
                              '29 Feb',
                              tzinfo=tz, locale=locale_en, hint='date')
            self.assertRaises(TracError, datefmt.parse_date,
                              'Feb 2011',
                              tzinfo=tz, locale=locale_en, hint='date')
            self.assertRaises(TracError, datefmt.parse_date,
                              '29 Feb 2010',
                              tzinfo=tz, locale=locale_en, hint='date')
            self.assertRaises(TracError, datefmt.parse_date,
                              '29 Xxx 2012',
                              tzinfo=tz, locale=locale_en, hint='date')
            self.assertRaises(TracError, datefmt.parse_date,
                              '29 Xxx 2012 4:00:00 AM',
                              tzinfo=tz, locale=locale_en, hint='datetime')
            self.assertRaises(TracError, datefmt.parse_date,
                              '29 2012 4:01:02 AM Feb',
                              tzinfo=tz, locale=locale_en, hint='datetime')
            self.assertRaises(TracError, datefmt.parse_date,
                              '29 2012 4:00 Feb',
                              tzinfo=tz, locale=locale_en, hint='datetime')

        def test_hint_date(self):
            try:
                datefmt.parse_date('***', locale=locale_en, hint='date')
                raise self.failureException('TracError not raised')
            except TracError as e:
                self.assertIn('Try "%s" or "YYYY-MM-DD" instead.'
                              % datefmt.get_date_format_hint(locale_en),
                              unicode(e))

        def test_hint_datetime(self):
            try:
                datefmt.parse_date('***', locale=locale_en, hint='datetime')
                raise self.failureException('TracError not raised')
            except TracError as e:
                self.assertIn(u'Try "%s" or "YYYY-MM-DDThh:mm:ss\xb1hh:mm" '
                              u'instead.'
                              % datefmt.get_datetime_format_hint(locale_en),
                              unicode(e))

        def test_hint_foobar(self):
            try:
                datefmt.parse_date('***', locale=locale_en, hint='foobar')
                raise self.failureException('TracError not raised')
            except TracError as e:
                self.assertIn(u'Try "foobar" or "YYYY-MM-DDThh:mm:ss±hh:mm" '
                              u'instead.', unicode(e))


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

    def test_utcoffset_non_whole_number_of_minutes(self):
        self._tzset('Europe/Dublin')
        dt = datetime.datetime(1910, 12, 13, 20, 20, 31)
        self.assertEqual(datetime.timedelta(days=-1, seconds=84900),
                         datefmt.localtz.utcoffset(dt))

    def test_utcoffset_overflow_error_on_osx(self):
        self._tzset('Europe/Dublin')
        tt = (1901, 12, 13, 20, 20, 30)
        try:
            time.mktime(tt + (-1, 0, 0))
        except OverflowError:  # OSX
            dt = datetime.datetime(*tt)
            self.assertEqual(datetime.timedelta(),
                             datefmt.localtz.utcoffset(dt))
        else:  # Linux
            dt = datetime.datetime(*tt)
            self.assertEqual(datetime.timedelta(days=-1, seconds=84900),
                             datefmt.localtz.utcoffset(dt))

    def test_localized_non_existent_time(self):
        self._tzset('Europe/Paris')
        dt = datetime.datetime(2012, 3, 25, 2, 15, 42, 123456)
        self.assertEqual('2012-03-25T02:15:42.123456+01:00',
                         datefmt.localtz.localize(dt).isoformat())
        try:
            datefmt.localtz.localize(dt, is_dst=None)
            raise AssertionError('ValueError not raised')
        except ValueError as e:
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
        except ValueError as e:
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

    def test_london_between_1968_and_1971(self):
        self._tzset('Europe/London')
        # -1:00 (DST end) at 1967-10-29 03:00
        ts = datefmt.to_timestamp(datetime.datetime(1967, 10, 30,
                                                    tzinfo=datefmt.utc))
        self.assertEqual('1967-10-30T00:00:00+00:00',
                         datefmt.to_datetime(ts, datefmt.localtz).isoformat())
        # +1:00 (DST start) at 1968-02-18 02:00
        ts = datefmt.to_timestamp(datetime.datetime(1968, 2, 19,
                                                    tzinfo=datefmt.utc))
        self.assertEqual('1968-02-19T01:00:00+01:00',
                         datefmt.to_datetime(ts, datefmt.localtz).isoformat())
        # No DST between 1968-02-18 02:00 and 1971-10-31 03:00
        ts = datefmt.to_timestamp(datetime.datetime(1970, 1, 1, 0, 0, 23,
                                                    tzinfo=datefmt.utc))
        self.assertEqual('1970-01-01T01:00:23+01:00',
                         datefmt.to_datetime(ts, datefmt.localtz).isoformat())
        # -1:00 (TZ change) at 1971-10-31 03:00
        t = datefmt.to_datetime(datetime.datetime(1971, 10, 31, 1, 30),
                                datefmt.localtz)
        delta = datetime.timedelta(hours=1)
        self.assertEqual('1971-10-31T01:30:00+01:00', t.isoformat())
        t = datefmt.to_datetime(t + delta, datefmt.localtz)
        self.assertEqual('1971-10-31T02:30:00+01:00', t.isoformat())
        t = datefmt.to_datetime(t + delta, datefmt.localtz)
        self.assertEqual('1971-10-31T02:30:00+00:00', t.isoformat())
        t = datefmt.to_datetime(t + delta, datefmt.localtz)
        self.assertEqual('1971-10-31T03:30:00+00:00', t.isoformat())

        ts = datefmt.to_timestamp(datetime.datetime(1971, 11, 1,
                                                    tzinfo=datefmt.utc))
        self.assertEqual('1971-11-01T00:00:00+00:00',
                         datefmt.to_datetime(ts, datefmt.localtz).isoformat())

    def test_guatemala_dst_in_2006(self):
        self._tzset('America/Guatemala')
        # No DST before 2006-04-30 00:00
        ts = datefmt.to_timestamp(datetime.datetime(2006, 4, 29,
                                                    tzinfo=datefmt.utc))
        self.assertEqual('2006-04-28T18:00:00-06:00',
                         datefmt.to_datetime(ts, datefmt.localtz).isoformat())
        # +1:00 (DST start) at 2006-04-30 00:00
        ts = datefmt.to_timestamp(datetime.datetime(2006, 8, 1,
                                                    tzinfo=datefmt.utc))
        self.assertEqual('2006-07-31T19:00:00-05:00',
                         datefmt.to_datetime(ts, datefmt.localtz).isoformat())
        # -1:00 (DST end) at 2006-10-01 00:00
        ts = datefmt.to_timestamp(datetime.datetime(2006, 10, 2,
                                                    tzinfo=datefmt.utc))
        self.assertEqual('2006-10-01T18:00:00-06:00',
                         datefmt.to_datetime(ts, datefmt.localtz).isoformat())
        # No DST after 2006-10-01 00:00

    def test_venezuela_in_2007(self):
        self._tzset('America/Caracas')
        ts = datefmt.to_timestamp(datetime.datetime(2007, 12, 8,
                                                    tzinfo=datefmt.utc))
        self.assertEqual('2007-12-07T20:00:00-04:00',
                         datefmt.to_datetime(ts, datefmt.localtz).isoformat())
        # -0:30 (TZ change) at 2007-12-09 03:00
        ts = datefmt.to_timestamp(datetime.datetime(2007, 12, 10,
                                                    tzinfo=datefmt.utc))
        self.assertEqual('2007-12-09T19:30:00-04:30',
                         datefmt.to_datetime(ts, datefmt.localtz).isoformat())

    def test_lord_howe_island_in_198x(self):
        self._tzset('Australia/Lord_Howe')
        ts = datefmt.to_timestamp(datetime.datetime(1985, 3, 1,
                                                    tzinfo=datefmt.utc))
        self.assertEqual('1985-03-01T11:30:00+11:30',
                         datefmt.to_datetime(ts, datefmt.localtz).isoformat())
        # -1:00 (DST end) at 1985-03-03 02:00
        ts = datefmt.to_timestamp(datetime.datetime(1985, 8, 1,
                                                    tzinfo=datefmt.utc))
        self.assertEqual('1985-08-01T10:30:00+10:30',
                         datefmt.to_datetime(ts, datefmt.localtz).isoformat())
        ts = datefmt.to_timestamp(datetime.datetime(1985, 11, 1,
                                                    tzinfo=datefmt.utc))
        # +0:30 (DST start) at 1985-10-27 02:00
        self.assertEqual('1985-11-01T11:00:00+11:00',
                         datefmt.to_datetime(ts, datefmt.localtz).isoformat())

    def _compare_pytz_arithmetic(self, tz, dt_naive):
        """Compare arithmetic timezone-aware datetime between localtz and
        pytz's timezone"""
        localtz = datefmt.localtz
        delta = datetime.timedelta(minutes=20)
        n = datetime.timedelta(hours=3).seconds / delta.seconds
        # create timezone-aware datetime instances
        dt_localtz = datefmt.to_datetime(dt_naive - delta * n, localtz)
        dt_tz = datefmt.to_datetime(dt_naive - delta * n, tz)
        # compare datetime instances between -3 hours and +3 hours
        for i in xrange(n * 2 + 1):
            self.assertEqual(dt_tz, dt_localtz)
            self.assertEqual(dt_tz.isoformat(), dt_localtz.isoformat())
            dt_localtz = datefmt.to_datetime(dt_localtz + delta, localtz)
            dt_tz = datefmt.to_datetime(dt_tz + delta, tz)

    def _compare_pytz_localize_and_normalize(self, tz, dt_naive):
        """Compare localize() and normalize() of LocalTimezone and pytz's
        timezone"""
        localtz = datefmt.localtz
        delta = datetime.timedelta(minutes=20)
        n = datetime.timedelta(hours=3).seconds / delta.seconds
        dt_naive -= delta * n
        # compare localize and normalize with naive datetime
        # between -3 hours and +3 hours
        for i in xrange(n * 2 + 1):
            dt_localtz = localtz.localize(dt_naive)
            dt_tz = tz.localize(dt_naive)
            self.assertEqual(dt_tz, dt_localtz,
                             '%r != %r (%r)' % (dt_tz, dt_localtz, dt_naive))
            self.assertEqual(dt_tz.isoformat(), dt_localtz.isoformat(),
                             '%r != %r (%r)' % (dt_tz.isoformat(),
                                                dt_localtz.isoformat(),
                                                dt_naive))
            dt_localtz = localtz.normalize(localtz.localize(dt_naive))
            dt_tz = tz.normalize(tz.localize(dt_naive))
            self.assertEqual(dt_tz, dt_localtz,
                             '%r != %r (%r)' % (dt_tz, dt_localtz, dt_naive))
            self.assertEqual(dt_tz.isoformat(), dt_localtz.isoformat(),
                             '%r != %r (%r)' % (dt_tz.isoformat(),
                                                dt_localtz.isoformat(),
                                                dt_naive))
            dt_naive += delta

    def _compare_pytz(self, tz, value, localize=True):
        if isinstance(value, basestring):
            value = datefmt.parse_date(value + 'Z', datefmt.utc)
        dt_naive = value.replace(tzinfo=None)
        self._compare_pytz_arithmetic(tz, dt_naive)
        # `localize()` differs one of pytz's timezone when backward timezone
        # change
        if localize:
            self._compare_pytz_localize_and_normalize(tz, dt_naive)

    if datefmt.pytz:
        def test_pytz_choibalsan(self):
            tz = datefmt.timezone('Asia/Choibalsan')
            self._tzset('Asia/Choibalsan')
            self._compare_pytz(tz, '1977-01-01T00:00')  # No DST
            self._compare_pytz(tz, '1978-01-01T01:00')  # +1:00 (TZ change)
            self._compare_pytz(tz, '1978-01-01T02:00')  #       (TZ change)
            self._compare_pytz(tz, '1982-04-01T00:00')  # No DST
            self._compare_pytz(tz, '1983-04-01T00:00')  # +2:00 (TZ change)
            self._compare_pytz(tz, '1983-04-01T02:00')  #       (TZ change)
            self._compare_pytz(tz, '1983-10-01T00:00',  # -1:00 (DST end)
                               localize=False)
            self._compare_pytz(tz, '2006-03-25T02:00')  # +1:00 (DST start)
            self._compare_pytz(tz, '2006-09-30T02:00',  # -1:00 (DST end)
                               localize=False)
            self._compare_pytz(tz, '2007-07-01T00:00')  # No DST in 2007
            self._compare_pytz(tz, '2008-03-30T23:00',  #       (TZ change)
                               localize=False)
            self._compare_pytz(tz, '2008-03-31T00:00',  # -1:00 (TZ change)
                               localize=False)
            self._compare_pytz(tz, '2009-07-01T00:00')  # No DST

        def test_pytz_guatemala(self):
            tz = datefmt.timezone('America/Guatemala')
            self._tzset('America/Guatemala')
            self._compare_pytz(tz, '2005-07-01T00:00')  # No DST
            self._compare_pytz(tz, '2006-04-30T00:00')  # +1:00 (DST start)
            self._compare_pytz(tz, '2006-10-01T00:00')  # -1:00 (DST end)
            self._compare_pytz(tz, '2007-07-01T00:00')  # No DST

        def test_pytz_london(self):
            tz = datefmt.timezone('Europe/London')
            self._tzset('Europe/London')
            self._compare_pytz(tz, '1968-02-18T02:00')  # +1:00 (DST start)
            self._compare_pytz(tz, '1971-10-31T02:00',  #       (TZ change)
                               localize=False)
            self._compare_pytz(tz, '1971-10-31T03:00',  # -1:00 (TZ change)
                               localize=False)
            self._compare_pytz(tz, '1972-03-19T02:00')  # +1:00 (DST start)
            self._compare_pytz(tz, '1972-10-29T03:00')  # -1:00 (DST end)

        def test_pytz_lord_howe_island(self):
            tz = datefmt.timezone('Australia/Lord_Howe')
            self._tzset('Australia/Lord_Howe')
            self._compare_pytz(tz, '1980-07-01T00:00')  # No DST
            self._compare_pytz(tz, '1981-03-01T00:00')  # +0:30 (TZ change)
            self._compare_pytz(tz, '1981-03-01T00:30')  #       (TZ change)
            self._compare_pytz(tz, '1981-10-25T02:00')  # +1:00 (DST start)
            self._compare_pytz(tz, '1985-03-03T02:00')  # -1:00 (DST end)
            self._compare_pytz(tz, '1985-10-27T02:00')  # +0:30 (DST start)
            self._compare_pytz(tz, '1986-03-16T02:00')  # -0:30 (DST end)

        def test_pytz_moscow(self):
            tz = datefmt.timezone('Europe/Moscow')
            self._tzset('Europe/Moscow')
            self._compare_pytz(tz, '1991-09-29T03:00')  # -1:00 (DST end)
            self._compare_pytz(tz, '1992-01-19T02:00')  # +1:00 (TZ change)
            self._compare_pytz(tz, '1992-01-19T03:00')  #       (TZ change)
            self._compare_pytz(tz, '1993-03-28T02:00')  # +1:00 (DST start)
            self._compare_pytz(tz, '1993-09-26T03:00')  # -1:00 (DST end)
            self._compare_pytz(tz, '2010-03-28T02:00')  # +1:00 (DST start)
            self._compare_pytz(tz, '2010-10-31T03:00')  # -1:00 (DST end)
            self._compare_pytz(tz, '2011-03-27T02:00')  # +1:00 (TZ change)
            self._compare_pytz(tz, '2011-03-27T03:00')  #       (TZ change)
            self._compare_pytz(tz, '2011-10-31T03:00')  # No DST

        def test_pytz_paris(self):
            tz = datefmt.timezone('Europe/Paris')
            self._tzset('Europe/Paris')
            self._compare_pytz(tz, '1975-07-01T01:00')  # No DST
            self._compare_pytz(tz, '1976-03-28T01:00')  # +1:00 (DST start)
            self._compare_pytz(tz, '1976-09-26T01:00')  # -1:00 (DST end)
            self._compare_pytz(tz, '2009-03-29T02:00')  # +1:00 (DST start)
            self._compare_pytz(tz, '2009-10-25T03:00')  # -1:00 (DST end)

        def test_pytz_venezuela(self):
            tz = datefmt.timezone('America/Caracas')
            self._tzset('America/Caracas')
            self._compare_pytz(tz, '2006-07-01T00:00')  # No DST
            self._compare_pytz(tz, '2007-12-09T02:30',  #       (TZ change)
                               localize=False)
            self._compare_pytz(tz, '2007-12-09T03:00',  # -0:30 (TZ change)
                               localize=False)
            self._compare_pytz(tz, '2008-07-01T00:00')  # No DST


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


def test_suite():
    suite = unittest.TestSuite()
    if PytzTestCase:
        suite.addTest(unittest.makeSuite(PytzTestCase))
    else:
        print("SKIP: utils/tests/datefmt.py (no pytz installed)")
    suite.addTest(unittest.makeSuite(DateFormatTestCase))
    suite.addTest(unittest.makeSuite(UTimestampTestCase))
    suite.addTest(unittest.makeSuite(ISO8601TestCase))
    if I18nDateFormatTestCase:
        suite.addTest(unittest.makeSuite(I18nDateFormatTestCase))
    else:
        print("SKIP: utils/tests/datefmt.py (no babel installed)")
    suite.addTest(unittest.makeSuite(ParseISO8601TestCase))
    suite.addTest(unittest.makeSuite(ParseDateWithoutBabelTestCase))
    suite.addTest(unittest.makeSuite(ParseRelativeDateTestCase))
    suite.addTest(unittest.makeSuite(ParseDateValidRangeTestCase))
    suite.addTest(unittest.makeSuite(HttpDateTestCase))
    if hasattr(time, 'tzset'):
        suite.addTest(unittest.makeSuite(LocalTimezoneTestCase))
    suite.addTest(unittest.makeSuite(LocalTimezoneStrTestCase))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
