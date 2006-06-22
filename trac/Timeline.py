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
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For exact contribution history, see the revision
# history and logs, available at http://projects.edgewall.com/trac/.
#
# Author: Jonas Borgström <jonas@edgewall.com>
#         Christopher Lenz <cmlenz@gmx.de>

import re
import time

from trac.config import IntOption
from trac.core import *
from trac.perm import IPermissionRequestor
from trac.util.datefmt import format_date, format_time, http_date
from trac.util.text import to_unicode
from trac.util.markup import html, Markup
from trac.web import IRequestHandler
from trac.web.chrome import add_link, add_stylesheet, INavigationContributor


class ITimelineEventProvider(Interface):
    """Extension point interface for adding sources for timed events to the
    timeline.
    """

    def get_timeline_filters(self, req):
        """Return a list of filters that this event provider supports.
        
        Each filter must be a (name, label) tuple, where `name` is the internal
        name, and `label` is a human-readable name for display.

        Optionally, the tuple can contain a third element, `checked`.
        If `checked` is omitted or True, the filter is active by default,
        otherwise it will be inactive.
        """

    def get_timeline_events(self, req, start, stop, filters):
        """Return a list of events in the time range given by the `start` and
        `stop` parameters.
        
        The `filters` parameters is a list of the enabled filters, each item
        being the name of the tuples returned by `get_timeline_filters`.

        The events returned by this function must be tuples of the form
        (kind, href, title, date, author, message).
        """


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
        if not req.perm.has_permission('TIMELINE_VIEW'):
            return
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

        format = req.args.get('format')
        maxrows = int(req.args.get('max', 0))

        # Parse the from date and adjust the timestamp to the last second of
        # the day
        t = time.localtime()
        if req.args.has_key('from'):
            try:
                t = time.strptime(req.args.get('from'), '%x')
            except:
                pass

        fromdate = time.mktime((t[0], t[1], t[2], 23, 59, 59, t[6], t[7], t[8]))
        try:
            daysback = max(0, int(req.args.get('daysback', '')))
        except ValueError:
            daysback = self.default_daysback
        req.hdf['timeline.from'] = format_date(fromdate)
        req.hdf['timeline.daysback'] = daysback

        available_filters = []
        for event_provider in self.event_providers:
            available_filters += event_provider.get_timeline_filters(req)

        filters = []
        # check the request or session for enabled filters, or use default
        for test in (lambda f: req.args.has_key(f[0]),
                     lambda f: req.session.get('timeline.filter.%s' % f[0], '')\
                               == '1',
                     lambda f: len(f) == 2 or f[2]):
            if filters:
                break
            filters = [f[0] for f in available_filters if test(f)]

        # save the results of submitting the timeline form to the session
        if req.args.has_key('update'):
            for filter in available_filters:
                key = 'timeline.filter.%s' % filter[0]
                if req.args.has_key(filter[0]):
                    req.session[key] = '1'
                elif req.session.has_key(key):
                    del req.session[key]

        stop = fromdate
        start = stop - (daysback + 1) * 86400

        events = []
        for event_provider in self.event_providers:
            try:
                events += event_provider.get_timeline_events(req, start, stop,
                                                             filters)
            except Exception, e: # cope with a failure of that provider
                self._provider_failure(e, req, event_provider, filters,
                                       [f[0] for f in available_filters])

        events.sort(lambda x,y: cmp(y[3], x[3]))
        if maxrows and len(events) > maxrows:
            del events[maxrows:]

        req.hdf['title'] = 'Timeline'

        # Get the email addresses of all known users
        email_map = {}
        for username, name, email in self.env.get_known_users():
            if email:
                email_map[username] = email

        idx = 0
        for kind, href, title, date, author, message in events:
            event = {'kind': kind, 'title': title, 'href': href,
                     'author': author or 'anonymous',
                     'date': format_date(date),
                     'time': format_time(date, '%H:%M'),
                     'message': message}

            if format == 'rss':
                # Strip/escape HTML markup
                if isinstance(title, Markup):
                    title = title.plaintext(keeplinebreaks=False)
                event['title'] = title
                event['message'] = to_unicode(message)

                if author:
                    # For RSS, author must be an email address
                    if author.find('@') != -1:
                        event['author.email'] = author
                    elif email_map.has_key(author):
                        event['author.email'] = email_map[author]
                event['date'] = http_date(date)

            req.hdf['timeline.events.%s' % idx] = event
            idx += 1

        if format == 'rss':
            return 'timeline_rss.cs', 'application/rss+xml'

        add_stylesheet(req, 'common/css/timeline.css')
        rss_href = req.href.timeline([(f, 'on') for f in filters],
                                     daysback=90, max=50, format='rss')
        add_link(req, 'alternate', rss_href, 'RSS Feed', 'application/rss+xml',
                 'rss')
        for idx,fltr in enumerate(available_filters):
            req.hdf['timeline.filters.%d' % idx] = {'name': fltr[0],
                'label': fltr[1], 'enabled': int(fltr[0] in filters)}

        return 'timeline.cs', None

    def _provider_failure(self, exc, req, ep, current_filters, all_filters):
        """Raise a TracError exception explaining the failure of a provider.

        At the same time, the message will contain a link to the timeline
        without the filters corresponding to the guilty event provider `ep`.
        """
        ep_name, exc_name = [i.__class__.__name__ for i in (ep, exc)]
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
