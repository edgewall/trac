# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2003, 2004, 2005 Edgewall Software
# Copyright (C) 2003, 2004, 2005 Jonas Borgström <jonas@edgewall.com>
#
# Trac is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version.
#
# Trac is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#
# Author: Jonas Borgström <jonas@edgewall.com>

from trac import perm
from trac.core import *
from trac.util import enum, escape, http_date, shorten_line
from trac.versioncontrol.svn_authz import SubversionAuthorizer
from trac.web.chrome import add_link, INavigationContributor
from trac.web.main import IRequestHandler
from trac.WikiFormatter import wiki_to_oneliner, wiki_to_html

import re
import time


class ITimelineEventProvider(Interface):
    """
    Extension point interface for adding sources for timed events to the
    timeline.
    """

    def get_timeline_filters(self, req):
        """
        Return a list of filters that this event provider supports. Each
        filter must be a (name, label) tuple, where `name` is the internal
        name, and `label` is a human-readable name for display.
        """

    def get_timeline_events(self, req, start, stop, filters):
        """
        Return a list of events in the time range given by the `start` and
        `stop` parameters. The `filters` parameters is a list of the enabled
        filters, each item being the name of the tuples returned by
        `get_timeline_events`.

        The events returned by this function must be tuples of the form
        (kind, href, title, date, author, message).
        """


class TimelineModule(Component):

    implements(INavigationContributor, IRequestHandler)

    event_providers = ExtensionPoint(ITimelineEventProvider)

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'timeline'

    def get_navigation_items(self, req):
        if not req.perm.has_permission(perm.TIMELINE_VIEW):
            return
        yield 'mainnav', 'timeline', '<a href="%s" accesskey="2">Timeline</a>' \
                                     % self.env.href.timeline()

    # IRequestHandler methods

    def match_request(self, req):
        return req.path_info == '/timeline'

    def process_request(self, req):
        req.perm.assert_permission(perm.TIMELINE_VIEW)

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
            daysback = 30
        req.hdf['timeline.from'] = time.strftime('%x', time.localtime(fromdate))
        req.hdf['timeline.daysback'] = daysback

        available_filters = []
        for event_provider in self.event_providers:
            available_filters += event_provider.get_timeline_filters(req)
        filters = [f[0] for f in available_filters if f[0] in req.args.keys()]
        if not filters:
            filters = [f[0] for f in available_filters]

        stop = fromdate
        start = stop - (daysback + 1) * 86400

        events = []
        for event_provider in self.event_providers:
            events += event_provider.get_timeline_events(req, start, stop,
                                                         filters)
        events.sort(lambda x,y: cmp(y[3], x[3]))
        if maxrows and len(events) > maxrows:
            del events[maxrows:]

        req.hdf['title'] = 'Timeline'

        # Get the email addresses of all known users
        email_map = {}
        for username,name,email in self.env.get_known_users():
            if email:
                email_map[username] = email

        idx = 0
        for kind,href,title,date,author,message in events:
            t = time.localtime(date)
            event = {'kind': kind, 'title': title,
                     'author': author or 'anonymous', 'href': href,
                     'date': time.strftime('%x', t),
                     'time': time.strftime('%H:%M', t), 'message': message}

            if format == 'rss':
                # Strip/escape HTML markup
                event['title'] = re.sub(r'</?\w+(?: .*?)?>', '', title)
                event['message'] = escape(message)

                if author:
                    # For RSS, author must be an email address
                    if author.find('@') != -1:
                        event['author.email'] = author
                    elif author in email_map.keys():
                        event['author.email'] = email_map[author]
                event['date'] = http_date(time.mktime(t))

            req.hdf['timeline.events.%s' % idx] = event
            idx += 1

        if format == 'rss':
            return 'timeline_rss.cs', 'application/rss+xml'

        rss_href = self.env.href.timeline([(f, 'on') for f in filters],
                                          daysback=90, max=50, format='rss')
        add_link(req, 'alternate', rss_href, 'RSS Feed', 'application/rss+xml',
                 'rss')
        for idx,fltr in enum(available_filters):
            req.hdf['timeline.filters.%d' % idx] = {'name': fltr[0],
                'label': fltr[1], 'enabled': int(fltr[0] in filters)}

        return 'timeline.cs', None
