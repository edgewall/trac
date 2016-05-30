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

from trac.perm import PermissionError, PermissionSystem
from trac.test import EnvironmentStub, MockRequest, locale_en
from trac.timeline.web_ui import TimelineModule
from trac.util.datefmt import (
    datetime_now, format_date, format_datetime, format_time,
    get_date_format_hint, pretty_timedelta, utc,
)
from trac.util.html import plaintext
from trac.web.chrome import Chrome
from trac.web.tests.api import RequestHandlerPermissionsTestCaseBase


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


class TimelinePermissionsTestCase(RequestHandlerPermissionsTestCaseBase):

    authz_policy = """\
[timeline:*]
user1 = TIMELINE_VIEW
user2 =
    """

    def setUp(self):
        super(TimelinePermissionsTestCase, self).setUp(TimelineModule)

    def test_get_navigation_items_with_timeline_view(self):
        req = MockRequest(self.env, authname='user1', path_info='/timeline')
        self.assertEqual('timeline', self.get_navigation_items(req).next()[1])

    def test_get_navigation_items_without_timeline_view(self):
        req = MockRequest(self.env, authname='user2', path_info='/timeline')
        self.assertEqual([], list(self.get_navigation_items(req)))

    def test_process_request_with_timeline_view(self):
        req = MockRequest(self.env, authname='user1', path_info='/timeline')
        self.assertEqual('timeline.html', self.process_request(req)[0])

    def test_process_request_without_timeline_view(self):
        req = MockRequest(self.env, authname='user2', path_info='/timeline')
        self.assertRaises(PermissionError, self.process_request, req)


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

    def test_daysback_from_session(self):
        """Daysback value is retrieved from session attributes."""
        PermissionSystem(self.env).grant_permission('user1', 'TIMELINE_VIEW')
        req = MockRequest(self.env, authname='user1')
        req.session.set('timeline.daysback', '45')

        data = TimelineModule(self.env).process_request(req)[1]

        self.assertEqual(45, data['daysback'])

    def test_no_exception_when_from_year_before_1900(self):
        """Exception not raised when 'from' year before 1900 (#12489)."""
        req = MockRequest(self.env, args={
            'from': '1899-12-23',
            'daysback': 7,
        })

        TimelineModule(self.env).process_request(req)

        self.assertIn('prev', req.chrome['links'])

    def test_daysback_less_than_min(self):
        """Daysback minimum value is 1."""
        req = MockRequest(self.env, args={'daysback': '-1'})

        data = TimelineModule(self.env).process_request(req)[1]

        self.assertEqual(1, data['daysback'])

    def test_daysback_greater_than_max(self):
        """Daysback is limited to [timeline] max_daysback."""
        req = MockRequest(self.env, args={'daysback': '100'})

        data = TimelineModule(self.env).process_request(req)[1]

        self.assertEqual(90, data['daysback'])

    def test_daysback_invalid_default_is_used(self):
        """Daysback request value is invalid: default value is used."""
        req = MockRequest(self.env, args={'daysback': '--'})

        data = TimelineModule(self.env).process_request(req)[1]

        self.assertEqual(30, data['daysback'])

    def test_daysback_invalid_session_value_default_is_used(self):
        """Daysback session value is invalid: default value is used."""
        PermissionSystem(self.env).grant_permission('user1', 'TIMELINE_VIEW')
        req = MockRequest(self.env, authname='user1', args={'daysback': '--'})
        req.session.set('timeline.daysback', '45')

        data = TimelineModule(self.env).process_request(req)[1]

        self.assertEqual(45, data['daysback'])

    def test_daysback_default_is_90_for_rss_format(self):
        """Daysback default is 90 for RSS format request."""
        PermissionSystem(self.env).grant_permission('user1', 'TIMELINE_VIEW')
        req = MockRequest(self.env, authname='user1', args={'format': 'rss'})
        req.session.set('timeline.daysback', '45')

        data = TimelineModule(self.env).process_request(req)[1]

        self.assertEqual(90, data['daysback'])


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(PrettyDateinfoTestCase))
    suite.addTest(unittest.makeSuite(TimelinePermissionsTestCase))
    suite.addTest(unittest.makeSuite(TimelineModuleTestCase))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
