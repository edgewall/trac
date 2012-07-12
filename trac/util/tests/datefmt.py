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

from trac.core import TracError
from trac.util import datefmt

try:
    import pytz
except ImportError:
    pytz = None
try:
    from babel import Locale
except ImportError:
    Locale = None

if pytz is None:
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
                en_US = Locale.parse('en_US')
                t = datefmt.parse_date('Mar 31, 2002 02:30', tz, en_US)
                self.assertEqual(expected, t.strftime(format))

        def test_to_datetime_pytz_normalize(self):
            tz = datefmt.get_timezone('Europe/Zurich')
            date = datefmt.to_datetime(datetime.date(2002, 3, 31), tz)
            format = '%Y-%m-%d %H:%M:%S %Z%z'
            expected = '2002-03-31 00:00:00 CET+0100'
            self.assertEqual(expected, date.strftime(format))


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
        for f in ('long', 'full'):
            self.assertEqual('11:45:56+02:00',
                             datefmt.format_time(t, f, tz, 'iso8601'))
            self.assertEqual('2010-08-28T11:45:56+02:00',
                             datefmt.format_datetime(t, f, tz, 'iso8601'))

    def test_hint(self):
        try:
            datefmt.parse_date('***', locale='iso8601', hint='date')
        except TracError, e:
            self.assert_('"YYYY-MM-DD"' in unicode(e))
        try:
            datefmt.parse_date('***', locale='iso8601', hint='datetime')
        except TracError, e:
            self.assert_(u'"YYYY-MM-DDThh:mm:ss±hh:mm"' in unicode(e))
        try:
            datefmt.parse_date('***', locale='iso8601', hint='foobar')
        except TracError, e:
            self.assert_('"foobar"' in unicode(e))


if Locale is None:
    I18nDateFormatTestCase = None
else:
    class I18nDateFormatTestCase(unittest.TestCase):
        def test_i18n_format_datetime(self):
            tz = datefmt.timezone('GMT +2:00')
            t = datetime.datetime(2010, 8, 28, 11, 45, 56, 123456, datefmt.utc)
            en_US = Locale.parse('en_US')
            self.assertEqual('Aug 28, 2010 1:45:56 PM',
                             datefmt.format_datetime(t, tzinfo=tz,
                                                     locale=en_US))
            en_GB = Locale.parse('en_GB')
            self.assertEqual('28 Aug 2010 13:45:56',
                             datefmt.format_datetime(t, tzinfo=tz,
                                                     locale=en_GB))
            fr = Locale.parse('fr')
            self.assertEqual(u'28 août 2010 13:45:56',
                             datefmt.format_datetime(t, tzinfo=tz, locale=fr))
            ja = Locale.parse('ja')
            self.assertEqual(u'2010/08/28 13:45:56',
                             datefmt.format_datetime(t, tzinfo=tz, locale=ja))
            vi = Locale.parse('vi')
            self.assertEqual(u'13:45:56 28-08-2010',
                             datefmt.format_datetime(t, tzinfo=tz, locale=vi))
            zh_CN = Locale.parse('zh_CN')
            self.assertEqual(u'2010-8-28 下午01:45:56',
                             datefmt.format_datetime(t, tzinfo=tz,
                                                     locale=zh_CN))

        def test_i18n_format_date(self):
            tz = datefmt.timezone('GMT +2:00')
            t = datetime.datetime(2010, 8, 7, 11, 45, 56, 123456, datefmt.utc)
            en_US = Locale.parse('en_US')
            self.assertEqual('Aug 7, 2010',
                             datefmt.format_date(t, tzinfo=tz, locale=en_US))
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
            self.assertEqual(u'07-08-2010',
                             datefmt.format_date(t, tzinfo=tz, locale=vi))
            zh_CN = Locale.parse('zh_CN')
            self.assertEqual(u'2010-8-7',
                             datefmt.format_date(t, tzinfo=tz, locale=zh_CN))

        def test_i18n_format_time(self):
            tz = datefmt.timezone('GMT +2:00')
            t = datetime.datetime(2010, 8, 28, 11, 45, 56, 123456, datefmt.utc)
            en_US = Locale.parse('en_US')
            en_GB = Locale.parse('en_GB')
            fr = Locale.parse('fr')
            ja = Locale.parse('ja')
            vi = Locale.parse('vi')
            zh_CN = Locale.parse('zh_CN')

            self.assertEqual('1:45:56 PM',
                             datefmt.format_time(t, tzinfo=tz, locale=en_US))
            self.assertEqual('13:45:56',
                             datefmt.format_time(t, tzinfo=tz, locale=en_GB))
            self.assertEqual('13:45:56',
                             datefmt.format_time(t, tzinfo=tz, locale=fr))
            self.assertEqual('13:45:56',
                             datefmt.format_time(t, tzinfo=tz, locale=ja))
            self.assertEqual('13:45:56',
                             datefmt.format_time(t, tzinfo=tz, locale=vi))
            self.assertEqual(u'下午01:45:56',
                             datefmt.format_time(t, tzinfo=tz, locale=zh_CN))

        def test_i18n_datetime_hint(self):
            en_US = Locale.parse('en_US')
            en_GB = Locale.parse('en_GB')
            fr = Locale.parse('fr')
            ja = Locale.parse('ja')
            vi = Locale.parse('vi')
            zh_CN = Locale.parse('zh_CN')

            self.assert_(datefmt.get_datetime_format_hint(en_US)
                         in ('MMM d, yyyy h:mm:ss a', 'MMM d, y h:mm:ss a'))
            self.assert_(datefmt.get_datetime_format_hint(en_GB)
                         in ('d MMM yyyy HH:mm:ss', 'd MMM y HH:mm:ss'))
            self.assert_(datefmt.get_datetime_format_hint(fr)
                         in ('d MMM yyyy HH:mm:ss', 'd MMM y HH:mm:ss'))
            self.assertEqual('yyyy/MM/dd H:mm:ss',
                             datefmt.get_datetime_format_hint(ja))
            self.assertEqual('HH:mm:ss dd-MM-yyyy',
                             datefmt.get_datetime_format_hint(vi))
            self.assertEqual('yyyy-M-d ahh:mm:ss',
                             datefmt.get_datetime_format_hint(zh_CN))

        def test_i18n_date_hint(self):
            en_US = Locale.parse('en_US')
            en_GB = Locale.parse('en_GB')
            fr = Locale.parse('fr')
            ja = Locale.parse('ja')
            vi = Locale.parse('vi')
            zh_CN = Locale.parse('zh_CN')

            self.assert_(datefmt.get_date_format_hint(en_US)
                         in ('MMM d, yyyy', 'MMM d, y'))
            self.assert_(datefmt.get_date_format_hint(en_GB)
                         in ('d MMM yyyy', 'd MMM y'))
            self.assert_(datefmt.get_date_format_hint(fr)
                         in ('d MMM yyyy', 'd MMM y'))
            self.assertEqual('yyyy/MM/dd',
                             datefmt.get_date_format_hint(ja))
            self.assertEqual('dd-MM-yyyy',
                             datefmt.get_date_format_hint(vi))
            self.assertEqual('yyyy-M-d',
                             datefmt.get_date_format_hint(zh_CN))

        def test_i18n_parse_date_iso8609(self):
            tz = datefmt.timezone('GMT +2:00')
            dt = datetime.datetime(2010, 8, 28, 13, 45, 56, 0, tz)
            d = datetime.datetime(2010, 8, 28, 0, 0, 0, 0, tz)
            en_US = Locale.parse('en_US')
            vi = Locale.parse('vi')

            def iso8601(expected, text, tz, locale):
                self.assertEqual(expected,
                                 datefmt.parse_date(text, tz, locale))

            iso8601(dt, '2010-08-28T15:45:56+0400', tz, en_US)
            iso8601(dt, '2010-08-28T11:45:56+0000', tz, vi)
            iso8601(dt, '2010-08-28T11:45:56Z', tz, vi)
            iso8601(dt, '20100828T144556+0300', tz, en_US)
            iso8601(dt, '20100828T114556Z', tz, vi)

            iso8601(d, '2010-08-28+0200', tz, en_US)
            # iso8601(d, '2010-08-28+0000', tz, vi)
            # iso8601(d, '2010-08-28Z', tz, en_US)
            iso8601(d, '2010-08-28', tz, vi)
            iso8601(d, '20100828+0200', tz, en_US)
            # iso8601(d, '20100828Z', tz, vi)

        def test_i18n_parse_date_datetime(self):
            tz = datefmt.timezone('GMT +2:00')
            expected = datetime.datetime(2010, 8, 28, 13, 45, 56, 0, tz)
            expected_minute = datetime.datetime(2010, 8, 28, 13, 45, 0, 0, tz)
            en_US = Locale.parse('en_US')
            en_GB = Locale.parse('en_GB')
            fr = Locale.parse('fr')
            ja = Locale.parse('ja')
            vi = Locale.parse('vi')
            zh_CN = Locale.parse('zh_CN')

            self.assertEqual(expected,
                             datefmt.parse_date('Aug 28, 2010 1:45:56 PM', tz,
                                                en_US))
            self.assertEqual(expected,
                             datefmt.parse_date('8 28, 2010 1:45:56 PM', tz,
                                                en_US))
            self.assertEqual(expected,
                             datefmt.parse_date('28 Aug 2010 1:45:56 PM', tz,
                                                en_US))
            self.assertEqual(expected,
                             datefmt.parse_date('28 Aug 2010 PM 1:45:56', tz,
                                                en_US))
            self.assertEqual(expected,
                             datefmt.parse_date('28 Aug 2010 13:45:56', tz,
                                                en_US))
            self.assertEqual(expected_minute,
                             datefmt.parse_date('28 Aug 2010 PM 1:45', tz,
                                                en_US))

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

            self.assertEqual(expected,
                             datefmt.parse_date('2010/08/28 13:45:56', tz, ja))
            self.assertEqual(expected_minute,
                             datefmt.parse_date('2010/08/28 13:45', tz, ja))

            self.assertEqual(expected,
                             datefmt.parse_date('13:45:56 28-08-2010', tz, vi))
            self.assertEqual(expected_minute,
                             datefmt.parse_date('13:45 28-08-2010', tz, vi))

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

        def test_i18n_parse_date_datetime_meridiem(self):
            tz = datefmt.timezone('GMT +2:00')
            expected_am = datetime.datetime(2011, 2, 22, 0, 45, 56, 0, tz)
            expected_pm = datetime.datetime(2011, 2, 22, 12, 45, 56, 0, tz)
            en_US = Locale.parse('en_US')
            zh_CN = Locale.parse('zh_CN')

            self.assertEqual(expected_am,
                             datefmt.parse_date('Feb 22, 2011 0:45:56 AM', tz,
                                                en_US))
            self.assertEqual(expected_am,
                             datefmt.parse_date('Feb 22, 2011 12:45:56 AM', tz,
                                                en_US))
            self.assertEqual(expected_am,
                             datefmt.parse_date(u'2011-2-22 上午0:45:56', tz,
                                                zh_CN))
            self.assertEqual(expected_am,
                             datefmt.parse_date(u'2011-2-22 上午12:45:56', tz,
                                                zh_CN))

            self.assertEqual(expected_pm,
                             datefmt.parse_date('Feb 22, 2011 0:45:56 PM', tz,
                                                en_US))
            self.assertEqual(expected_pm,
                             datefmt.parse_date('Feb 22, 2011 12:45:56 PM', tz,
                                                en_US))
            self.assertEqual(expected_pm,
                             datefmt.parse_date(u'2011-2-22 下午0:45:56', tz,
                                                zh_CN))
            self.assertEqual(expected_pm,
                             datefmt.parse_date(u'2011-2-22 下午12:45:56', tz,
                                                zh_CN))

        def test_i18n_parse_date_date(self):
            tz = datefmt.timezone('GMT +2:00')
            expected = datetime.datetime(2010, 8, 28, 0, 0, 0, 0, tz)
            en_US = Locale.parse('en_US')
            en_GB = Locale.parse('en_GB')
            fr = Locale.parse('fr')
            ja = Locale.parse('ja')
            vi = Locale.parse('vi')
            zh_CN = Locale.parse('zh_CN')

            self.assertEqual(expected,
                             datefmt.parse_date('Aug 28, 2010', tz, en_US))
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
            tz = datefmt.timezone('GMT +2:00')
            t = datetime.datetime(2010, 8, 28, 11, 45, 56, 123456, datefmt.utc)
            expected = datetime.datetime(2010, 8, 28, 13, 45, 56, 0, tz)

            def roundtrip(locale):
                locale = Locale.parse(locale)
                formatted = datefmt.format_datetime(t, tzinfo=tz,
                                                    locale=locale)
                self.assertEqual(expected,
                                 datefmt.parse_date(formatted, tz, locale))
                self.assertEqual(formatted,
                                 datefmt.format_datetime(expected, tzinfo=tz,
                                                         locale=locale))

            roundtrip('ca')
            roundtrip('cs')
            roundtrip('de')
            roundtrip('el')
            roundtrip('en_GB')
            roundtrip('en_US')
            roundtrip('eo')
            roundtrip('es')
            roundtrip('es_AR')
            roundtrip('fa')
            roundtrip('fi')
            roundtrip('fr')
            roundtrip('gl')
            roundtrip('he')
            roundtrip('hu')
            roundtrip('hy')
            roundtrip('it')
            roundtrip('ja')
            roundtrip('ko')
            roundtrip('nb')
            roundtrip('nl')
            roundtrip('pl')
            roundtrip('pt')
            roundtrip('pt_BR')
            roundtrip('ro')
            roundtrip('ru')
            roundtrip('sl')
            roundtrip('sv')
            roundtrip('tr')
            roundtrip('vi')
            roundtrip('zh_CN')
            roundtrip('zh_TW')

        def test_format_compatibility(self):
            tz = datefmt.timezone('GMT +2:00')
            t = datetime.datetime(2010, 8, 28, 11, 45, 56, 123456, datefmt.utc)
            tz_t = datetime.datetime(2010, 8, 28, 13, 45, 56, 123456, tz)
            en_US = Locale.parse('en_US')

            # Converting default format to babel's format
            self.assertEqual('Aug 28, 2010 1:45:56 PM',
                             datefmt.format_datetime(t, '%x %X', tz, en_US))
            self.assertEqual('Aug 28, 2010',
                             datefmt.format_datetime(t, '%x', tz, en_US))
            self.assertEqual('1:45:56 PM',
                             datefmt.format_datetime(t, '%X', tz, en_US))
            self.assertEqual('Aug 28, 2010',
                             datefmt.format_date(t, '%x', tz, en_US))
            self.assertEqual('1:45:56 PM',
                             datefmt.format_time(t, '%X', tz, en_US))

        def test_parse_invalid_date(self):
            tz = datefmt.timezone('GMT +2:00')
            en_US = Locale.parse('en_US')

            self.assertRaises(TracError, datefmt.parse_date,
                              '',
                              tzinfo=tz, locale=en_US, hint='date')
            self.assertRaises(TracError, datefmt.parse_date,
                              '2011 Apr Mar',
                              tzinfo=tz, locale=en_US, hint='date')
            self.assertRaises(TracError, datefmt.parse_date,
                              '29 Feb',
                              tzinfo=tz, locale=en_US, hint='date')
            self.assertRaises(TracError, datefmt.parse_date,
                              'Feb 2011',
                              tzinfo=tz, locale=en_US, hint='date')
            self.assertRaises(TracError, datefmt.parse_date,
                              '29 Feb 2010',
                              tzinfo=tz, locale=en_US, hint='date')
            self.assertRaises(TracError, datefmt.parse_date,
                              '29 Xxx 2012',
                              tzinfo=tz, locale=en_US, hint='date')
            self.assertRaises(TracError, datefmt.parse_date,
                              '29 Xxx 2012 4:00:00 AM',
                              tzinfo=tz, locale=en_US, hint='datetime')
            self.assertRaises(TracError, datefmt.parse_date,
                              '29 2012 4:01:02 AM Feb',
                              tzinfo=tz, locale=en_US, hint='datetime')
            self.assertRaises(TracError, datefmt.parse_date,
                              '29 2012 4:00 Feb',
                              tzinfo=tz, locale=en_US, hint='datetime')


def suite():
    suite = unittest.TestSuite()
    if PytzTestCase:
        suite.addTest(unittest.makeSuite(PytzTestCase, 'test'))
    else:
        print "SKIP: utils/tests/datefmt.py (no pytz installed)"
    suite.addTest(unittest.makeSuite(DateFormatTestCase))
    suite.addTest(unittest.makeSuite(UTimestampTestCase))
    suite.addTest(unittest.makeSuite(ISO8601TestCase))
    if I18nDateFormatTestCase:
        suite.addTest(unittest.makeSuite(I18nDateFormatTestCase, 'test'))
    else:
        print "SKIP: utils/tests/datefmt.py (no babel installed)"
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
