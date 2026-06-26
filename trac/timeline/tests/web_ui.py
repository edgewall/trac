# -*- coding: utf-8 -*-
#
# Copyright (C) 2014-2026 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.
import itertools
import textwrap
import unittest
from datetime import datetime, timedelta
from xml.dom import minidom

from trac.core import Component, ComponentMeta, implements
from trac.perm import PermissionError, PermissionSystem
from trac.test import EnvironmentStub, Mock, MockRequest, locale_en, makeSuite
from trac.timeline.api import ITimelineEventProvider
from trac.timeline.web_ui import TimelineModule
from trac.util.datefmt import (
    datetime_now, format_date, format_datetime, format_time,
    get_date_format_hint, get_timezone, pretty_timedelta, pytz, utc,
)
from trac.util.html import plaintext, tag
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
        data = Chrome(self.env).populate_data(self.req)
        return plaintext(data['pretty_dateinfo'](d, format=format,
                                                 dateonly=dateonly))

    def _format_timeline(self, d, format, dateonly):
        data = Chrome(self.env).populate_data(self.req)
        TimelineModule(self.env).post_process_request(
            self.req, 'timeline.html', data, {})
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

    authz_policy = textwrap.dedent("""\
        [timeline:*]
        user1 = TIMELINE_VIEW
        user2 =
        """)

    def setUp(self):
        super().setUp(TimelineModule)

    def test_get_navigation_items_with_timeline_view(self):
        req = MockRequest(self.env, authname='user1', path_info='/timeline')
        self.assertEqual('timeline', next(self.get_navigation_items(req))[1])

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

        self.assertIn('"2011-02-02T11:38:50 01:00" is an invalid date, '
                      'or the date format is not known. Try "%s" or "%s" '
                      'instead.' % (get_date_format_hint(locale_en),
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

        self.assertEqual(0, data['daysback'])

    def test_daysback_greater_than_max(self):
        """Daysback is limited to [timeline] max_daysback."""
        req = MockRequest(self.env, args={'daysback': '100'})

        data = TimelineModule(self.env).process_request(req)[1]

        self.assertEqual(90, data['daysback'])

    def test_max_daysback_unlimited(self):
        """Daysback is unlimited if [timeline] max_daysback set to -1."""
        self.env.config.set('timeline', 'max_daysback', '-1')
        req = MockRequest(self.env, args={'daysback': '365'})
        data = TimelineModule(self.env).process_request(req)[1]
        self.assertEqual(365, data['daysback'])

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


class TimelineEventProviderTestCase(unittest.TestCase):

    timeline_event_providers = None

    @classmethod
    def setUpClass(cls):

        class TimelineEventProvider(Component):
            implements(ITimelineEventProvider)

            def __init__(self):
                self._events = ()

            def get_timeline_filters(self, req):
                yield ('test', 'Test')

            def get_timeline_events(self, req, start, stop, filters):
                for event in self._events:
                    if start <= event[1] <= stop:
                        yield event

            def render_timeline_event(self, context, field, event):
                return event[3].render(context, field, event)

        cls.timeline_event_providers = {
            'normal': TimelineEventProvider,
        }

    @classmethod
    def tearDownClass(cls):
        for c in (cls.timeline_event_providers or {}).values():
            ComponentMeta.deregister(c)

    def setUp(self):
        self.env = EnvironmentStub()
        self.env.config.set('trac', 'use_chunked_encoding', False)

    def tearDown(self):
        self.env.reset_db()

    def test_rss(self):
        def render(context, field, event):
            if event[0] == 'test&1':
                if field == 'url':
                    return 'http://example.org/path?foo=bar&baz=1'
                if field == 'summary':
                    return 'summary 1: <b>&</b>'
                if field == 'description':
                    return tag(tag.h1('Title 1st'), tag.p('body & < >'))
            if event[0] == 'test&2':
                if field == 'url':
                    return 'http://example.org/path?baz=2&foo=bar'
                if field == 'summary':
                    return tag('summary 2: ', tag.b('&'))
                if field == 'description':
                    return tag(tag.h1('Title 2nd'), tag.p('body & < >'))

        self._set_events([
            ('test&1', datetime(2018, 4, 27, 12, 34, 56, 123456, utc),
             'jo&hn', Mock(render=render)),
            ('test&2', datetime(2018, 3, 19, 23, 56, 12, 987654, utc),
             'Joe <joe@example.org>', Mock(render=render)),
        ])
        req = MockRequest(self.env, path_info='/timeline', tz=utc,
                          args={'format': 'rss', 'daysback': '90',
                                'from': '2018-04-30T00:00:00Z'})
        rv = self._process_request(req)
        self.assertEqual('timeline.rss', rv[0])
        self.assertEqual({'content_type': 'application/rss+xml'}, rv[2])
        output = str(self._render_template(req, *rv), 'utf-8')

        self.assertIn('<title>summary 1: &lt;b&gt;&amp;&lt;/b&gt;</title>',
                      output)
        self.assertIn('<dc:creator>jo&amp;hn</dc:creator>', output)
        self.assertIn('<pubDate>Fri, 27 Apr 2018 12:34:56 GMT</pubDate>',
                      output)
        self.assertIn('<link>http://example.org/path?foo=bar&amp;baz=1'
                      '</link>', output)
        self.assertIn('<guid isPermaLink="false">http://example.org/path?'
                      'foo=bar&amp;baz=1/1524832496123456</guid>', output)
        self.assertIn('<description>&lt;h1&gt;Title 1st&lt;/h1&gt;'
                      '&lt;p&gt;body &amp;amp; &amp;lt; &amp;gt;&lt;/p&gt;'
                      '</description>', output)
        self.assertIn('<category>test&amp;1</category>', output)

        self.assertIn('<title>summary 2: &amp;</title>', output)
        self.assertIn('<author>Joe &lt;joe@example.org&gt;</author>', output)
        self.assertIn('<pubDate>Mon, 19 Mar 2018 23:56:12 GMT</pubDate>',
                      output)
        self.assertIn('<link>http://example.org/path?baz=2&amp;foo=bar'
                      '</link>', output)
        self.assertIn('<guid isPermaLink="false">http://example.org/path?'
                      'baz=2&amp;foo=bar/1521503772987654</guid>', output)
        self.assertIn('<description>&lt;h1&gt;Title 2nd&lt;/h1&gt;'
                      '&lt;p&gt;body &amp;amp; &amp;lt; &amp;gt;&lt;/p&gt;'
                      '</description>', output)
        self.assertIn('<category>test&amp;2</category>', output)

        self.assertEqual('<?xml version="1.0"?>', output[:21])
        minidom.parseString(output)  # verify valid xml

    def test_daysback(self):
        base_datetime = datetime(2025, 2, 20, 12, tzinfo=utc)
        self._set_events([
            ('test', base_datetime - timedelta(days=days), 'trac', None)
            for days in range(-30, 120)
        ])

        def render_and_get_events(daysback):
            req = MockRequest(self.env, path_info='/timeline', tz=utc,
                              args={'from': '2025-02-19T12:34:56.012345Z',
                                    'daysback': daysback})
            rv = self._process_request(req)
            data = rv[1]
            return data['events']

        def get_datetimes(events):
            return [event['datetime'] for event in events]

        events = render_and_get_events('0')
        self.assertEqual([datetime(2025, 2, 19, 12, tzinfo=utc)],
                         get_datetimes(events))

        events = render_and_get_events('1')
        self.assertEqual([datetime(2025, 2, 19, 12, tzinfo=utc),
                          datetime(2025, 2, 18, 12, tzinfo=utc)],
                         get_datetimes(events))

        events = render_and_get_events('90')
        self.assertEqual(datetime(2024, 11, 21, 12, tzinfo=utc),
                         get_datetimes(events)[-1])
        self.assertEqual(91, len(events))

        events = render_and_get_events('91')
        self.assertEqual(datetime(2024, 11, 21, 12, tzinfo=utc),
                         get_datetimes(events)[-1])
        self.assertEqual(91, len(events))

    @unittest.skipUnless(pytz, 'pytz unavailable')
    def test_forward_across_dst(self):
        tz = get_timezone('Europe/Berlin')  # DST start at 2025-03-30 02:00
        base = datetime(2025, 3, 30, 12, 30, tzinfo=utc)
        self._set_events([
            ('test', base - timedelta(hours=hours), 'trac', None)
            for hours in range(-48, 48)
        ])
        req = MockRequest(self.env, path_info='/timeline', tz=tz,
                          args={'from': '2025-03-31T12:34:56Z',
                                'daysback': '2'})
        rv = self._process_request(req)
        events = rv[1]['events']
        grouped_events = {
            str(key): list(map(str, sorted(e['datetime'] for e in g)))
            for key, g in itertools.groupby(events, key=lambda e: e['date'])
        }
        self.assertEqual(
            ['2025-03-30 00:30:00+01:00', '2025-03-30 01:30:00+01:00',
             '2025-03-30 03:30:00+02:00', '2025-03-30 04:30:00+02:00',
             '2025-03-30 05:30:00+02:00', '2025-03-30 06:30:00+02:00',
             '2025-03-30 07:30:00+02:00', '2025-03-30 08:30:00+02:00',
             '2025-03-30 09:30:00+02:00', '2025-03-30 10:30:00+02:00',
             '2025-03-30 11:30:00+02:00', '2025-03-30 12:30:00+02:00',
             '2025-03-30 13:30:00+02:00', '2025-03-30 14:30:00+02:00',
             '2025-03-30 15:30:00+02:00', '2025-03-30 16:30:00+02:00',
             '2025-03-30 17:30:00+02:00', '2025-03-30 18:30:00+02:00',
             '2025-03-30 19:30:00+02:00', '2025-03-30 20:30:00+02:00',
             '2025-03-30 21:30:00+02:00', '2025-03-30 22:30:00+02:00',
             '2025-03-30 23:30:00+02:00'],
            grouped_events['2025-03-30 00:00:00+01:00'])
        self.assertEqual(
            ['2025-03-29 00:00:00+01:00', '2025-03-30 00:00:00+01:00',
             '2025-03-31 00:00:00+02:00'], sorted(grouped_events))
        self.assertEqual(24, len(grouped_events['2025-03-29 00:00:00+01:00']))
        self.assertEqual(23, len(grouped_events['2025-03-30 00:00:00+01:00']))
        self.assertEqual(24, len(grouped_events['2025-03-31 00:00:00+02:00']))

    @unittest.skipUnless(pytz, 'pytz unavailable')
    def test_back_across_dst(self):
        tz = get_timezone('Europe/Berlin')  # DST end at 2024-10-27 03:00
        base = datetime(2024, 10, 27, 12, 30, tzinfo=utc)
        self._set_events([
            ('test', base - timedelta(hours=hours), 'trac', None)
            for hours in range(-48, 48)
        ])
        req = MockRequest(self.env, path_info='/timeline', tz=tz,
                          args={'from': '2024-10-28T12:34:56Z',
                                'daysback': '2'})
        rv = self._process_request(req)
        events = rv[1]['events']
        grouped_events = {
            str(key): list(map(str, sorted(e['datetime'] for e in g)))
            for key, g in itertools.groupby(events, key=lambda e: e['date'])
        }
        self.assertEqual(
            ['2024-10-27 00:30:00+02:00', '2024-10-27 01:30:00+02:00',
             '2024-10-27 02:30:00+02:00', '2024-10-27 02:30:00+01:00',
             '2024-10-27 03:30:00+01:00', '2024-10-27 04:30:00+01:00',
             '2024-10-27 05:30:00+01:00', '2024-10-27 06:30:00+01:00',
             '2024-10-27 07:30:00+01:00', '2024-10-27 08:30:00+01:00',
             '2024-10-27 09:30:00+01:00', '2024-10-27 10:30:00+01:00',
             '2024-10-27 11:30:00+01:00', '2024-10-27 12:30:00+01:00',
             '2024-10-27 13:30:00+01:00', '2024-10-27 14:30:00+01:00',
             '2024-10-27 15:30:00+01:00', '2024-10-27 16:30:00+01:00',
             '2024-10-27 17:30:00+01:00', '2024-10-27 18:30:00+01:00',
             '2024-10-27 19:30:00+01:00', '2024-10-27 20:30:00+01:00',
             '2024-10-27 21:30:00+01:00', '2024-10-27 22:30:00+01:00',
             '2024-10-27 23:30:00+01:00'],
            grouped_events['2024-10-27 00:00:00+02:00'])
        self.assertEqual(
            ['2024-10-26 00:00:00+02:00', '2024-10-27 00:00:00+02:00',
             '2024-10-28 00:00:00+01:00'], sorted(grouped_events))
        self.assertEqual(24, len(grouped_events['2024-10-26 00:00:00+02:00']))
        self.assertEqual(25, len(grouped_events['2024-10-27 00:00:00+02:00']))
        self.assertEqual(24, len(grouped_events['2024-10-28 00:00:00+01:00']))

    def _set_events(self, events):
        provider = self.timeline_event_providers['normal'](self.env)
        provider._events = tuple(events)

    def _process_request(self, req):
        mod = TimelineModule(self.env)
        self.assertTrue(mod.match_request(req))
        return mod.process_request(req)

    def _render_template(self, *args, **kwargs):
        return Chrome(self.env).render_template(*args, **kwargs)


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(makeSuite(PrettyDateinfoTestCase))
    suite.addTest(makeSuite(TimelinePermissionsTestCase))
    suite.addTest(makeSuite(TimelineModuleTestCase))
    suite.addTest(makeSuite(TimelineEventProviderTestCase))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
