# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2006 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2004-2005 Christopher Lenz <cmlenz@gmx.de>
# Copyright (C) 2005-2006 Christian Boos <cboos@neuf.fr>
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
# Author: Jonas Borgström <jonas@edgewall.com>
#         Christopher Lenz <cmlenz@gmx.de>

from datetime import datetime, timedelta
from heapq import heappush, heappop
import re
import time

from trac.config import IntOption
from trac.core import *
from trac.perm import IPermissionRequestor
from trac.timeline.api import ITimelineEventProvider, TimelineEvent
from trac.util.datefmt import format_date, parse_date, to_timestamp, utc
from trac.util.html import html, Markup
from trac.util.text import to_unicode
from trac.web import IRequestHandler
from trac.web.chrome import add_link, add_stylesheet, INavigationContributor



class TimelineModule(Component):

    implements(INavigationContributor, IPermissionRequestor, IRequestHandler)

    event_providers = ExtensionPoint(ITimelineEventProvider)

    default_daysback = IntOption('timeline', 'default_daysback', 30,
        """Default number of days displayed in the Timeline, in days.
        (''since 0.9.'')""")

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'timeline'

    def get_navigation_items(self, req):
        if 'TIMELINE_VIEW' in req.perm:
            yield ('mainnav', 'timeline',
                   html.A('Timeline', href=req.href.timeline(), accesskey=2))

    # IPermissionRequestor methods

    def get_permission_actions(self):
        return ['TIMELINE_VIEW']

    # IRequestHandler methods

    def match_request(self, req):
        return re.match(r'/timeline/?', req.path_info) is not None

    def process_request(self, req):
        req.perm.assert_permission('TIMELINE_VIEW')
        data = {}

        format = req.args.get('format')
        maxrows = int(req.args.get('max', 0))

        # Parse the from date and adjust the timestamp to the last second of
        # the day
        t = datetime.now(utc)
        if 'from' in req.args:
            try:
                t =  parse_date(req.args.get('from'), req.tz)
            except:
                pass
        fromdate = t.replace(hour=23, minute=59, second=59)
        try:
            daysback = max(0, int(req.args.get('daysback', '')))
        except ValueError:
            daysback = self.default_daysback

        data = {'fromdate': fromdate, 'daysback': daysback,
                'events': [], 'filters': []}

        available_filters = []
        for event_provider in self.event_providers:
            available_filters += event_provider.get_timeline_filters(req)

        filters = []
        # check the request or session for enabled filters, or use default
        for test in (lambda f: f[0] in req.args,
                     lambda f: req.session.get('timeline.filter.%s' % f[0], '')\
                               == '1',
                     lambda f: len(f) == 2 or f[2]):
            if filters:
                break
            filters = [f[0] for f in available_filters if test(f)]

        # save the results of submitting the timeline form to the session
        if 'update' in req.args:
            for filter in available_filters:
                key = 'timeline.filter.%s' % filter[0]
                if filter[0] in req.args:
                    req.session[key] = '1'
                elif key in req.session:
                    del req.session[key]

        stop = fromdate
        start = stop - timedelta(days=daysback + 1)

        # gather all events for the given period of time
        events = []
        for event_provider in self.event_providers:
            try:
                for event in event_provider.get_timeline_events(req, start,
                                                                stop, filters):
                    # compatibility with 0.10 providers
                    if isinstance(event, tuple):
                        event = self._event_from_tuple(req, event)
                    heappush(events, (-to_timestamp(event.date), event))
            except Exception, e: # cope with a failure of that provider
                self._provider_failure(e, req, event_provider, filters,
                                       [f[0] for f in available_filters])
        # prepare sorted global list
        data_events = data['events']
        while events:
            _, event = heappop(events)
            day = format_date(event.date, tzinfo=req.tz),
            data_events.append((day, event))
            if maxrows and len(data_events) > maxrows:
                break

        if format == 'rss':
            # Get the email addresses of all known users
            email_map = {}
            for username, name, email in self.env.get_known_users():
                if email:
                    email_map[username] = email
            data['email_map'] = email_map
            return 'timeline.rss', data, 'application/rss+xml'

        add_stylesheet(req, 'common/css/timeline.css')
        rss_href = req.href.timeline([(f, 'on') for f in filters],
                                     daysback=90, max=50, format='rss')
        add_link(req, 'alternate', rss_href, 'RSS Feed', 'application/rss+xml',
                 'rss')

        for filter_ in available_filters:
            data['filters'].append({'name': filter_[0], 'label': filter_[1],
                                    'enabled': filter_[0] in filters})

        return 'timeline.html', data, None

    def _event_from_tuple(self, req, event):
        """Build a TimelineEvent from a pre-0.11 ITimelineEventProvider tuple
        """
        kind, href, title, date, author, markup = event
        if not isinstance(date, datetime):
            date = datetime.fromtimestamp(date, utc)
        base = req.abs_href.base[:-len(req.href.base)]
        if href and href.startswith(base):
            href = href[len(base):]
        event = TimelineEvent(kind, title, href, markup)
        event.set_changeinfo(date, author)
        return event

    def _provider_failure(self, exc, req, ep, current_filters, all_filters):
        """Raise a TracError exception explaining the failure of a provider.

        At the same time, the message will contain a link to the timeline
        without the filters corresponding to the guilty event provider `ep`.
        """
        ep_name, exc_name = [i.__class__.__name__ for i in (ep, exc)]
        self.log.exception('Timeline event provider %s failed', ep_name)

        guilty_filters = [f[0] for f in ep.get_timeline_filters(req)]
        guilty_kinds = [f[1] for f in ep.get_timeline_filters(req)]
        other_filters = [f for f in current_filters if not f in guilty_filters]
        if not other_filters:
            other_filters = [f for f in all_filters if not f in guilty_filters]
        args = [(a, req.args.get(a)) for a in ('from', 'format', 'max',
                                               'daysback')]
        href = req.href.timeline(args+[(f, 'on') for f in other_filters])
        raise TracError(Markup(
            '%s  event provider (<tt>%s</tt>) failed:<br /><br />'
            '%s: %s'
            '<p>You may want to see the other kind of events from the '
            '<a href="%s">Timeline</a></p>', 
            ", ".join(guilty_kinds), ep_name, exc_name, to_unicode(exc), href))
