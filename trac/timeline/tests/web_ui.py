# -*- coding: utf-8 -*-
#
# Copyright (C) 2014 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import unittest
from datetime import datetime, timedelta

from trac.test import EnvironmentStub, MockRequest, locale_en
from trac.timeline.web_ui import TimelineModule
from trac.util.datefmt import (
    datetime_now, format_date, format_datetime, format_time,
    get_date_format_hint, pretty_timedelta, utc,
)
from trac.util.html import plaintext
from trac.web.chrome import Chrome


class PrettyDateinfoTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.env.config.set('trac', 'base_url', 'http://example.org/')
        self.req = MockRequest(self.env)

    def tearDown(self):
        self.env.reset_db()

    def _format_chrome(self, d, format, dateonly):
        data = Chrome(self.env).populate_data(self.req, {})
        return plaintext(data['pretty_dateinfo'](d, format=format,
                                                 dateonly=dateonly))

    def _format_timeline(self, d, format, dateonly):
        data = Chrome(self.env).populate_data(self.req, {})
        TimelineModule(self.env) \
            .post_process_request(self.req, 'timeline.html', data, None)
        return plaintext(data['pretty_dateinfo'](d, format=format,
                                                 dateonly=dateonly))

    def test_relative(self):
        t = datetime_now(utc) - timedelta(days=1)
        label = '%s ago' % pretty_timedelta(t)
        self.assertEqual(label, self._format_chrome(t, 'relative', False))
        self.assertEqual(label, self._format_timeline(t, 'relative', False))

    def test_relative_dateonly(self):
        t = datetime_now(utc) - timedelta(days=1)
        label = pretty_timedelta(t)
        self.assertEqual(label, self._format_chrome(t, 'relative', True))
        self.assertEqual(label, self._format_timeline(t, 'relative', True))

    def test_absolute(self):
        t = datetime_now(utc) - timedelta(days=1)
        label = 'on %s at %s' % \
                (format_date(t, locale=locale_en, tzinfo=utc),
                 format_time(t, locale=locale_en, tzinfo=utc))
        self.assertEqual(label, self._format_chrome(t, 'absolute', False))
        self.assertEqual(label, self._format_timeline(t, 'absolute', False))

    def test_absolute_dateonly(self):
        t = datetime_now(utc) - timedelta(days=1)
        label = format_datetime(t, locale=locale_en, tzinfo=utc)
        self.assertEqual(label, self._format_chrome(t, 'absolute', True))
        self.assertEqual(label, self._format_timeline(t, 'absolute', True))

    def test_absolute_iso8601(self):
        t = datetime(2014, 1, 28, 2, 30, 44, 0, utc)
        label = 'at 2014-01-28T02:30:44Z'
        self.req.lc_time = 'iso8601'
        self.assertEqual(label, self._format_chrome(t, 'absolute', False))
        self.assertEqual(label, self._format_timeline(t, 'absolute', False))

    def test_absolute_iso8601_dateonly(self):
        t = datetime(2014, 1, 28, 2, 30, 44, 0, utc)
        label = '2014-01-28T02:30:44Z'
        self.req.lc_time = 'iso8601'
        self.assertEqual(label, self._format_chrome(t, 'absolute', True))
        self.assertEqual(label, self._format_timeline(t, 'absolute', True))


class TimelineModuleTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()

    def tearDown(self):
        self.env.reset_db()

    def test_invalid_date_format_add_warning(self):
        """Warning is added when date format is invalid."""
        req = MockRequest(self.env, args={
            'from': '2011-02-02T11:38:50 01:00',
        })

        TimelineModule(self.env).process_request(req)

        self.assertIn(u'"2011-02-02T11:38:50 01:00" is an invalid date, '
                      u'or the date format is not known. Try "%s" or "%s" '
                      u'instead.' % (get_date_format_hint(locale_en),
                                     get_date_format_hint('iso8601')),
                      req.chrome['warnings'])

    def test_no_exception_when_from_year_before_1900(self):
        """Exception not raised when 'from' year before 1900 (#12489)."""
        req = MockRequest(self.env, args={
            'from': '1899-12-23',
            'daysback': 7,
        })

        TimelineModule(self.env).process_request(req)

        self.assertIn('prev', req.chrome['links'])


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(PrettyDateinfoTestCase))
    suite.addTest(unittest.makeSuite(TimelineModuleTestCase))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
