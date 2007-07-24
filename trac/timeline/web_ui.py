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
import pkg_resources
import re
import time
from urlparse import urlparse

from genshi.builder import tag

from trac.config import IntOption, BoolOption
from trac.context import Context
from trac.core import *
from trac.perm import IPermissionRequestor
from trac.timeline.api import ITimelineEventProvider, TimelineEvent
from trac.util.compat import sorted
from trac.util.datefmt import format_date, format_datetime, parse_date, \
                              to_timestamp, utc, pretty_timedelta
from trac.util.text import to_unicode
from trac.util.translation import _
from trac.web import IRequestHandler, IRequestFilter
from trac.web.chrome import add_link, add_stylesheet, Chrome, \
                            INavigationContributor, ITemplateProvider
                            
from trac.wiki.api import IWikiSyntaxProvider


class TimelineModule(Component):

    implements(INavigationContributor, IPermissionRequestor, IRequestHandler,
               IRequestFilter, ITemplateProvider, IWikiSyntaxProvider)

    event_providers = ExtensionPoint(ITimelineEventProvider)

    default_daysback = IntOption('timeline', 'default_daysback', 30,
        """Default number of days displayed in the Timeline, in days.
        (''since 0.9.'')""")

    abbreviated_messages = BoolOption('timeline', 'abbreviated_messages',
                                      'true',
        """Whether wiki-formatted event messages should be truncated or not.

        This only affects the default rendering, and can be overriden by
        specific event providers, see their own documentation.
        (''Since 0.11'')""")

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'timeline'

    def get_navigation_items(self, req):
        if 'TIMELINE_VIEW' in req.perm:
            yield ('mainnav', 'timeline',
                   tag.a(_('Timeline'), href=req.href.timeline(), accesskey=2))

    # IPermissionRequestor methods

    def get_permission_actions(self):
        return ['TIMELINE_VIEW']

    # IRequestHandler methods

    def match_request(self, req):
        return re.match(r'/timeline/?', req.path_info) is not None

    def process_request(self, req):
        req.perm.assert_permission('TIMELINE_VIEW')

        format = req.args.get('format')
        maxrows = int(req.args.get('max', 0))

        # Parse the from date and adjust the timestamp to the last second of
        # the day
        fromdate = today = datetime.now(req.tz)
        precisedate = precision = None
        if 'from' in req.args:
            precisedate = parse_date(req.args.get('from'), req.tz)
            fromdate = precisedate
            precision = req.args.get('precision', '')
            if precision.startswith('second'):
                precision = timedelta(seconds=1)
            elif precision.startswith('minutes'):
                precision = timedelta(minutes=1)
            elif precision.startswith('hours'):
                precision = timedelta(hours=1)
            else:
                precision = None
        fromdate = fromdate.replace(hour=23, minute=59, second=59)
        try:
            daysback = max(0, int(req.args.get('daysback', '')))
        except ValueError:
            daysback = self.default_daysback

        data = {'fromdate': fromdate, 'daysback': daysback,
                'today': format_date(today),
                'yesterday': format_date(today - timedelta(days=1)),
                'precisedate': precisedate, 'precision': precision,
                'events': [], 'filters': [],
                'abbreviated_messages': self.abbreviated_messages}

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
        for provider in self.event_providers:
            try:
                for event in provider.get_timeline_events(req, start, stop,
                                                          filters):
                    # compatibility with 0.10 providers
                    if isinstance(event, tuple):
                        event = self._event_from_tuple(req, event)
                    events.append(event)
            except Exception, e: # cope with a failure of that provider
                self._provider_failure(e, req, provider, filters,
                                       [f[0] for f in available_filters])

        events = sorted(events, key=lambda e: e.date, reverse=True)

        # prepare sorted global list
        if maxrows:
            data['events'] = events[:maxrows]
        else:
            data['events'] = events

        if format == 'rss':
            # Get the email addresses of all known users
            email_map = {}
            if Chrome(self.env).show_email_addresses:
                for username, name, email in self.env.get_known_users():
                    if email:
                        email_map[username] = email
            data['email_map'] = email_map
            return 'timeline.rss', data, 'application/rss+xml'

        add_stylesheet(req, 'common/css/timeline.css')
        rss_href = req.href.timeline([(f, 'on') for f in filters],
                                     daysback=90, max=50, format='rss')
        add_link(req, 'alternate', rss_href, _('RSS Feed'),
                 'application/rss+xml', 'rss')

        for filter_ in available_filters:
            data['filters'].append({'name': filter_[0], 'label': filter_[1],
                                    'enabled': filter_[0] in filters})

        # Navigation to the previous/next period of 'daysback' days
        previous_start = format_date(fromdate - timedelta(days=daysback+1),
                                     format='%Y-%m-%d', tzinfo=req.tz)
        add_link(req, 'prev', req.href.timeline(from_=previous_start,
                                                daysback=daysback),
                 _('Previous period'))
        if today - fromdate > timedelta(days=0):
            next_start = format_date(fromdate + timedelta(days=daysback+1),
                                     format='%Y-%m-%d', tzinfo=req.tz)
            add_link(req, 'next', req.href.timeline(from_=next_start,
                                                    daysback=daysback),
                     _('Next period'))
        
        return 'timeline.html', data, None

    # ITemplateProvider methods

    def get_htdocs_dirs(self):
        return []

    def get_templates_dirs(self):
        return [pkg_resources.resource_filename('trac.timeline', 'templates')]

    # IRequestFilter methods

    def pre_process_request(self, req, handler):
        return handler
    
    def post_process_request(self, req, template, data, content_type):
        if data:
            def dateinfo(date):
                return self.get_timeline_link(req, date,
                                              pretty_timedelta(date),
                                              precision='second')
            data['dateinfo'] = dateinfo
        return template, data, content_type

    # IWikiSyntaxProvider methods

    def get_wiki_syntax(self):
        return []

    def get_link_resolvers(self):
        def link_resolver(formatter, ns, target, label):
            precision = None
            time = target.split("T", 1)
            if len(time) > 1:
                time = time[1].split("Z")[0]
                if len(time) >= 6:
                    precision = 'seconds'
                elif len(time) >= 4:
                    precision = 'minutes'
                elif len(time) >= 2:
                    precision = 'hours'
            try:
                return self.get_timeline_link(formatter.req,
                                              parse_date(target, utc),
                                              label, precision)
            except TracError, e:
                return tag.a(label, title=to_unicode(e.message),
                             class_='timeline missing')
        yield ('timeline', link_resolver)

    # Public methods

    def get_timeline_link(self, req, date, label=None, precision='hours'):
        iso_date = display_date = format_datetime(date, 'iso8601', req.tz)
        fmt = req.session.get('datefmt')
        if fmt and fmt != 'iso8601':
            display_date = format_datetime(date, fmt, req.tz)
        return tag.a(label or utc_date, class_='timeline',
                     title=_("%(date)s in Timeline", date=display_date),
                     href=req.href.timeline(from_=iso_date,
                                            precision=precision))

    # Internal methods

    def _event_from_tuple(self, req, event):
        """Build a TimelineEvent from a pre-0.11 ITimelineEventProvider tuple
        """
        kind, href, title, date, author, markup = event
        if not isinstance(date, datetime):
            date = datetime.fromtimestamp(date, utc)
        if href and href.startswith(req.abs_href.base):
            href = urlparse(href)[2]
        event = TimelineEvent(kind, title, href, markup)
        event.set_changeinfo(date, author)
        event.set_context(Context(self.env, None), '')
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
        raise TracError(tag(
            tag.p(', '.join(guilty_kinds),
                  ' event provider (', tag.tt(ep_name), ') failed:', tag.br(),
                  exc_name, ': ', to_unicode(exc), class_='message'),
            tag.p('You may want to see the other kind of events from the ',
                  tag.a('Timeline', href=href))))
