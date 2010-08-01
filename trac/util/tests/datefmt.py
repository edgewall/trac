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


try:
    from babel import Locale
except:
    I18nDateFormatTestCase = None
else:
    class I18nDateFormatTestCase(unittest.TestCase):
        def test_i18n_format_datetime(self):
            tz = datefmt.timezone('GMT +2:00')
            t = datetime.datetime(2010, 8, 28, 11, 45, 56, 123456, datefmt.utc)
            en_US = Locale.parse('en_US')
            self.assertEqual('Aug 28, 2010 1:45:56 PM',
                             datefmt.i18n_format_datetime(t, tzinfo=tz,
                                                          locale=en_US))
            en_GB = Locale.parse('en_GB')
            self.assertEqual('28 Aug 2010 13:45:56',
                             datefmt.i18n_format_datetime(t, tzinfo=tz,
                                                          locale=en_GB))
            fr = Locale.parse('fr')
            self.assertEqual(u'28 août 2010 13:45:56',
                             datefmt.i18n_format_datetime(t, tzinfo=tz,
                                                          locale=fr))
            ja = Locale.parse('ja')
            self.assertEqual(u'2010/08/28 13:45:56',
                             datefmt.i18n_format_datetime(t, tzinfo=tz,
                                                          locale=ja))
            vi = Locale.parse('vi')
            self.assertEqual(u'13:45:56 28-08-2010',
                             datefmt.i18n_format_datetime(t, tzinfo=tz,
                                                          locale=vi))
            zh_CN = Locale.parse('zh_CN')
            self.assertEqual(u'2010-8-28 下午01:45:56',
                             datefmt.i18n_format_datetime(t, tzinfo=tz,
                                                          locale=zh_CN))

        def test_i18n_format_date(self):
            tz = datefmt.timezone('GMT +2:00')
            t = datetime.datetime(2010, 8, 7, 11, 45, 56, 123456, datefmt.utc)
            en_US = Locale.parse('en_US')
            self.assertEqual('Aug 7, 2010',
                             datefmt.i18n_format_date(t, tzinfo=tz,
                                                      locale=en_US))
            en_GB = Locale.parse('en_GB')
            self.assertEqual('7 Aug 2010',
                             datefmt.i18n_format_date(t, tzinfo=tz,
                                                      locale=en_GB))
            fr = Locale.parse('fr')
            self.assertEqual(u'7 août 2010',
                             datefmt.i18n_format_date(t, tzinfo=tz,
                                                      locale=fr))
            ja = Locale.parse('ja')
            self.assertEqual(u'2010/08/07',
                             datefmt.i18n_format_date(t, tzinfo=tz,
                                                      locale=ja))
            vi = Locale.parse('vi')
            self.assertEqual(u'07-08-2010',
                             datefmt.i18n_format_date(t, tzinfo=tz,
                                                      locale=vi))
            zh_CN = Locale.parse('zh_CN')
            self.assertEqual(u'2010-8-7',
                             datefmt.i18n_format_date(t, tzinfo=tz,
                                                      locale=zh_CN))

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
                             datefmt.i18n_format_time(t, tzinfo=tz,
                                                      locale=en_US))
            self.assertEqual('13:45:56',
                             datefmt.i18n_format_time(t, tzinfo=tz,
                                                      locale=en_GB))
            self.assertEqual('13:45:56',
                             datefmt.i18n_format_time(t, tzinfo=tz,
                                                      locale=fr))
            self.assertEqual('13:45:56',
                             datefmt.i18n_format_time(t, tzinfo=tz,
                                                      locale=ja))
            self.assertEqual('13:45:56',
                             datefmt.i18n_format_time(t, tzinfo=tz,
                                                      locale=vi))
            self.assertEqual(u'下午01:45:56',
                             datefmt.i18n_format_time(t, tzinfo=tz,
                                                      locale=zh_CN))

        def test_i18n_datetime_hint(self):
            en_US = Locale.parse('en_US')
            en_GB = Locale.parse('en_GB')
            fr = Locale.parse('fr')
            ja = Locale.parse('ja')
            vi = Locale.parse('vi')
            zh_CN = Locale.parse('zh_CN')

            self.assertEqual('MMM d, yyyy h:mm:ss a',
                             datefmt.i18n_get_datetime_format_hint(en_US))
            self.assertEqual('d MMM yyyy HH:mm:ss',
                             datefmt.i18n_get_datetime_format_hint(en_GB))
            self.assertEqual('d MMM yyyy HH:mm:ss',
                             datefmt.i18n_get_datetime_format_hint(fr))
            self.assertEqual('yyyy/MM/dd H:mm:ss',
                             datefmt.i18n_get_datetime_format_hint(ja))
            self.assertEqual('HH:mm:ss dd-MM-yyyy',
                             datefmt.i18n_get_datetime_format_hint(vi))
            self.assertEqual('yyyy-M-d ahh:mm:ss',
                             datefmt.i18n_get_datetime_format_hint(zh_CN))

        def test_i18n_date_hint(self):
            en_US = Locale.parse('en_US')
            en_GB = Locale.parse('en_GB')
            fr = Locale.parse('fr')
            ja = Locale.parse('ja')
            vi = Locale.parse('vi')
            zh_CN = Locale.parse('zh_CN')

            self.assertEqual('MMM d, yyyy',
                             datefmt.i18n_get_date_format_hint(en_US))
            self.assertEqual('d MMM yyyy',
                             datefmt.i18n_get_date_format_hint(en_GB))
            self.assertEqual('d MMM yyyy',
                             datefmt.i18n_get_date_format_hint(fr))
            self.assertEqual('yyyy/MM/dd',
                             datefmt.i18n_get_date_format_hint(ja))
            self.assertEqual('dd-MM-yyyy',
                             datefmt.i18n_get_date_format_hint(vi))
            self.assertEqual('yyyy-M-d',
                             datefmt.i18n_get_date_format_hint(zh_CN))

        def test_i18n_parse_date_iso8609(self):
            tz = datefmt.timezone('GMT +2:00')
            dt = datetime.datetime(2010, 8, 28, 13, 45, 56, 0, tz)
            d = datetime.datetime(2010, 8, 28, 0, 0, 0, 0, tz)
            en_US = Locale.parse('en_US')
            vi = Locale.parse('vi')

            def iso8601(expected, text, tz, locale):
                self.assertEqual(expected,
                                 datefmt.i18n_parse_date(text, tzinfo=tz,
                                                         locale=locale))

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
                             datefmt.i18n_parse_date('Aug 28, 2010 1:45:56 PM',
                                                     tzinfo=tz, locale=en_US))
            self.assertEqual(expected,
                             datefmt.i18n_parse_date('8 28, 2010 1:45:56 PM',
                                                     tzinfo=tz, locale=en_US))
            self.assertEqual(expected,
                             datefmt.i18n_parse_date('28 Aug 2010 1:45:56 PM',
                                                     tzinfo=tz, locale=en_US))
            self.assertEqual(expected,
                             datefmt.i18n_parse_date('28 Aug 2010 PM 1:45:56',
                                                     tzinfo=tz, locale=en_US))
            self.assertEqual(expected,
                             datefmt.i18n_parse_date('28 Aug 2010 13:45:56',
                                                     tzinfo=tz, locale=en_US))
            self.assertEqual(expected_minute,
                             datefmt.i18n_parse_date('28 Aug 2010 PM 1:45',
                                                     tzinfo=tz, locale=en_US))

            self.assertEqual(expected,
                             datefmt.i18n_parse_date('28 Aug 2010 13:45:56',
                                                     tzinfo=tz, locale=en_GB))

            self.assertEqual(expected,
                             datefmt.i18n_parse_date(u'28 août 2010 13:45:56',
                                                     tzinfo=tz, locale=fr))
            self.assertEqual(expected,
                             datefmt.i18n_parse_date(u'août 28 2010 13:45:56',
                                                     tzinfo=tz, locale=fr))
            self.assertEqual(expected_minute,
                             datefmt.i18n_parse_date(u'août 28 2010 13:45',
                                                     tzinfo=tz, locale=fr))

            self.assertEqual(expected,
                             datefmt.i18n_parse_date('2010/08/28 13:45:56',
                                                     tzinfo=tz, locale=ja))
            self.assertEqual(expected_minute,
                             datefmt.i18n_parse_date('2010/08/28 13:45',
                                                     tzinfo=tz, locale=ja))

            self.assertEqual(expected,
                             datefmt.i18n_parse_date('13:45:56 28-08-2010',
                                                     tzinfo=tz, locale=vi))
            self.assertEqual(expected_minute,
                             datefmt.i18n_parse_date('13:45 28-08-2010',
                                                     tzinfo=tz, locale=vi))

            self.assertEqual(expected,
                             datefmt.i18n_parse_date(u'2010-8-28 下午01:45:56',
                                                     tzinfo=tz, locale=zh_CN))
            self.assertEqual(expected,
                             datefmt.i18n_parse_date(u'2010-8-28 01:45:56下午',
                                                     tzinfo=tz, locale=zh_CN))
            self.assertEqual(expected_minute,
                             datefmt.i18n_parse_date(u'2010-8-28 下午01:45',
                                                     tzinfo=tz, locale=zh_CN))
            self.assertEqual(expected_minute,
                             datefmt.i18n_parse_date(u'2010-8-28 01:45下午',
                                                     tzinfo=tz, locale=zh_CN))

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
                             datefmt.i18n_parse_date('Aug 28, 2010',
                                                     tzinfo=tz, locale=en_US))
            self.assertEqual(expected,
                             datefmt.i18n_parse_date('28 Aug 2010',
                                                     tzinfo=tz, locale=en_GB))
            self.assertEqual(expected,
                             datefmt.i18n_parse_date(u'28 août 2010',
                                                     tzinfo=tz, locale=fr))
            self.assertEqual(expected,
                             datefmt.i18n_parse_date('2010/08/28',
                                                     tzinfo=tz, locale=ja))
            self.assertEqual(expected,
                             datefmt.i18n_parse_date('28-08-2010',
                                                     tzinfo=tz, locale=vi))
            self.assertEqual(expected,
                             datefmt.i18n_parse_date(u'2010-8-28',
                                                     tzinfo=tz, locale=zh_CN))

        def test_i18n_parse_date_roundtrip(self):
            tz = datefmt.timezone('GMT +2:00')
            t = datetime.datetime(2010, 8, 28, 11, 45, 56, 123456, datefmt.utc)
            expected = datetime.datetime(2010, 8, 28, 13, 45, 56, 0, tz)

            def roundtrip(locale):
                locale = Locale.parse(locale)
                formatted = datefmt.i18n_format_datetime(t, tzinfo=tz,
                                                         locale=locale)
                self.assertEqual(expected,
                                 datefmt.i18n_parse_date(formatted, tzinfo=tz,
                                                         locale=locale))
                self.assertEqual(formatted,
                                 datefmt.i18n_format_datetime(expected,
                                                              tzinfo=tz,
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


def suite():
    suite = unittest.TestSuite()
    if PytzTestCase:
        suite.addTest(unittest.makeSuite(PytzTestCase, 'test'))
    else:
        print "SKIP: utils/tests/datefmt.py (no pytz installed)"
    suite.addTest(unittest.makeSuite(DateFormatTestCase))
    suite.addTest(unittest.makeSuite(UTimestampTestCase))
    if I18nDateFormatTestCase:
        suite.addTest(unittest.makeSuite(I18nDateFormatTestCase, 'test'))
    else:
        print "SKIP: utils/tests/datefmt.py (no babel installed)"
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
