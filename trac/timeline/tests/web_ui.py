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

from trac.test import EnvironmentStub, Mock, MockPerm, locale_en
from trac.timeline.web_ui import TimelineModule
from trac.util.datefmt import (
    format_date, format_datetime, format_time, pretty_timedelta, utc,
)
from trac.util.html import plaintext
from trac.web.chrome import Chrome
from trac.web.href import Href


class PrettyDateinfoTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.req = Mock(href=Href('/'), abs_href=Href('http://example.org/'),
                        authname='anonymous', tz=utc, locale=locale_en,
                        lc_time=locale_en, chrome={}, perm=MockPerm(),
                        session={})

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
        t = datetime.now(utc) - timedelta(days=1)
        label = '%s ago' % pretty_timedelta(t)
        self.assertEqual(label, self._format_chrome(t, 'relative', False))
        self.assertEqual(label, self._format_timeline(t, 'relative', False))

    def test_relative_dateonly(self):
        t = datetime.now(utc) - timedelta(days=1)
        label = pretty_timedelta(t)
        self.assertEqual(label, self._format_chrome(t, 'relative', True))
        self.assertEqual(label, self._format_timeline(t, 'relative', True))

    def test_absolute(self):
        t = datetime.now(utc) - timedelta(days=1)
        label = 'on %s at %s' % \
                (format_date(t, locale=locale_en, tzinfo=utc),
                 format_time(t, locale=locale_en, tzinfo=utc))
        self.assertEqual(label, self._format_chrome(t, 'absolute', False))
        self.assertEqual(label, self._format_timeline(t, 'absolute', False))

    def test_absolute_dateonly(self):
        t = datetime.now(utc) - timedelta(days=1)
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


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(PrettyDateinfoTestCase))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
