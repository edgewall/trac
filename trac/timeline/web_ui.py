# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2009 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2004-2005 Christopher Lenz <cmlenz@gmx.de>
# Copyright (C) 2005-2006 Christian Boos <cboos@edgewall.org>
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

import pkg_resources
import re
from datetime import datetime, timedelta

from genshi.builder import tag

from trac.config import IntOption, BoolOption
from trac.core import *
from trac.perm import IPermissionRequestor
from trac.timeline.api import ITimelineEventProvider
from trac.util.datefmt import (datetime_now, format_date, format_datetime,
                               format_time, localtz, parse_date,
                               pretty_timedelta, utc, to_datetime,
                               to_utimestamp, user_time)
from trac.util.text import exception_to_unicode, to_unicode
from trac.util.translation import _, tag_
from trac.web import IRequestHandler, IRequestFilter
from trac.web.chrome import (Chrome, INavigationContributor,
                             ITemplateProvider, add_link, add_stylesheet,
                             add_warning, auth_link, prevnext_nav, web_context)
from trac.wiki.api import IWikiSyntaxProvider
from trac.wiki.formatter import concat_path_query_fragment, \
                                split_url_into_path_query_fragment


class TimelineModule(Component):

    implements(INavigationContributor, IPermissionRequestor, IRequestHandler,
               IRequestFilter, ITemplateProvider, IWikiSyntaxProvider)

    event_providers = ExtensionPoint(ITimelineEventProvider)

    default_daysback = IntOption('timeline', 'default_daysback', 30,
        """Default number of days displayed in the Timeline, in days.
        """)

    max_daysback = IntOption('timeline', 'max_daysback', 90,
        """Maximum number of days (-1 for unlimited) displayable in the
        Timeline.
        """)

    abbreviated_messages = BoolOption('timeline', 'abbreviated_messages',
                                      True,
        """Whether wiki-formatted event messages should be truncated or not.

        This only affects the default rendering, and can be overriden by
        specific event providers, see their own documentation.
        """)

    _authors_pattern = re.compile(r'(-)?(?:"([^"]*)"|\'([^\']*)\'|([^\s]+))')

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'timeline'

    def get_navigation_items(self, req):
        if 'TIMELINE_VIEW' in req.perm('timeline'):
            yield ('mainnav', 'timeline',
                   tag.a(_("Timeline"), href=req.href.timeline(), accesskey=2))

    # IPermissionRequestor methods

    def get_permission_actions(self):
        return ['TIMELINE_VIEW']

    # IRequestHandler methods

    def match_request(self, req):
        return req.path_info == '/timeline'

    def process_request(self, req):
        req.perm('timeline').require('TIMELINE_VIEW')

        format = req.args.getfirst('format')
        maxrows = req.args.getint('max', 50 if format == 'rss' else 0)
        lastvisit = req.session.as_int('timeline.lastvisit', 0)

        # indication of new events is unchanged when form is updated by user
        revisit = any(a in req.args
                      for a in ['update', 'from', 'daysback', 'author'])
        if revisit:
            lastvisit = req.session.as_int('timeline.nextlastvisit',
                                           lastvisit)

        # Parse the from date and adjust the timestamp to the last second of
        # the day
        fromdate = today = datetime_now(req.tz)
        yesterday = to_datetime(today.replace(tzinfo=None) - timedelta(days=1),
                                req.tz)
        precisedate = precision = None
        if 'from' in req.args:
            # Acquire from date only from non-blank input
            reqfromdate = req.args.getfirst('from').strip()
            if reqfromdate:
                try:
                    precisedate = user_time(req, parse_date, reqfromdate)
                except TracError as e:
                    add_warning(req, e)
                else:
                    fromdate = precisedate.astimezone(req.tz)
            precision = req.args.getfirst('precision', '')
            if precision.startswith('second'):
                precision = timedelta(seconds=1)
            elif precision.startswith('minute'):
                precision = timedelta(minutes=1)
            elif precision.startswith('hour'):
                precision = timedelta(hours=1)
            else:
                precision = None
        fromdate = to_datetime(datetime(fromdate.year, fromdate.month,
                                        fromdate.day, 23, 59, 59, 999999),
                               req.tz)

        pref = req.session.as_int('timeline.daysback', self.default_daysback)
        default = 90 if format == 'rss' else pref
        daysback = req.args.as_int('daysback', default,
                                   min=1, max=self.max_daysback)

        authors = req.args.getfirst('authors')
        if authors is None and format != 'rss':
            authors = req.session.get('timeline.authors')
        authors = (authors or '').strip()

        data = {'fromdate': fromdate, 'daysback': daysback,
                'authors': authors,
                'today': user_time(req, format_date, today),
                'yesterday': user_time(req, format_date, yesterday),
                'precisedate': precisedate, 'precision': precision,
                'events': [], 'filters': [],
                'abbreviated_messages': self.abbreviated_messages,
                'lastvisit': lastvisit}

        available_filters = []
        for event_provider in self.event_providers:
            available_filters += event_provider.get_timeline_filters(req) or []

        # check the request or session for enabled filters, or use default
        filters = [f[0] for f in available_filters if f[0] in req.args]
        if not filters and format != 'rss':
            filters = [f[0] for f in available_filters
                            if req.session.as_int('timeline.filter.' + f[0])]
        if not filters:
            filters = [f[0] for f in available_filters if len(f) == 2 or f[2]]

        # save the results of submitting the timeline form to the session
        if 'update' in req.args:
            for filter_ in available_filters:
                key = 'timeline.filter.%s' % filter_[0]
                if filter_[0] in req.args:
                    req.session[key] = '1'
                elif key in req.session:
                    del req.session[key]

        stop = fromdate
        start = to_datetime(stop.replace(tzinfo=None) -
                            timedelta(days=daysback + 1), req.tz)

        # create author include and exclude sets
        include = set()
        exclude = set()
        for match in self._authors_pattern.finditer(authors):
            name = (match.group(2) or match.group(3) or match.group(4)).lower()
            if match.group(1):
                exclude.add(name)
            else:
                include.add(name)

        # gather all events for the given period of time
        events = []
        for provider in self.event_providers:
            try:
                for event in provider.get_timeline_events(req, start, stop,
                                                          filters) or []:
                    author = (event[2] or '').lower()
                    if (not include or author in include) \
                            and author not in exclude:
                        events.append(self._event_data(provider, event))
            except Exception as e:  # cope with a failure of that provider
                self._provider_failure(e, req, provider, filters,
                                       [f[0] for f in available_filters])

        # prepare sorted global list
        events = sorted(events, key=lambda e: e['date'], reverse=True)
        if maxrows:
            events = events[:maxrows]

        data['events'] = events

        if format == 'rss':
            rss_context = web_context(req, absurls=True)
            rss_context.set_hints(wiki_flavor='html', shorten_lines=False)
            data['context'] = rss_context
            return 'timeline.rss', data, 'application/rss+xml'
        else:
            req.session.set('timeline.daysback', daysback,
                            self.default_daysback)
            req.session.set('timeline.authors', authors, '')
            # store lastvisit
            if events and not revisit:
                lastviewed = to_utimestamp(events[0]['date'])
                req.session['timeline.lastvisit'] = max(lastvisit, lastviewed)
                req.session['timeline.nextlastvisit'] = lastvisit
            html_context = web_context(req)
            html_context.set_hints(wiki_flavor='oneliner',
                                   shorten_lines=self.abbreviated_messages)
            data['context'] = html_context

        add_stylesheet(req, 'common/css/timeline.css')
        rss_href = req.href.timeline([(f, 'on') for f in filters],
                                     daysback=90, max=50, authors=authors,
                                     format='rss')
        add_link(req, 'alternate', auth_link(req, rss_href), _('RSS Feed'),
                 'application/rss+xml', 'rss')
        Chrome(self.env).add_jquery_ui(req)

        for filter_ in available_filters:
            data['filters'].append({'name': filter_[0], 'label': filter_[1],
                                    'enabled': filter_[0] in filters})

        # Navigation to the previous/next period of 'daysback' days
        previous_start = fromdate.replace(tzinfo=None) - \
                         timedelta(days=daysback + 1)
        previous_start = format_date(previous_start, format='iso8601',
                                     tzinfo=req.tz)
        add_link(req, 'prev', req.href.timeline(from_=previous_start,
                                                authors=authors,
                                                daysback=daysback),
                 _("Previous Period"))
        if today - fromdate > timedelta(days=0):
            next_start = fromdate.replace(tzinfo=None) + \
                         timedelta(days=daysback + 1)
            next_start = format_date(to_datetime(next_start, req.tz),
                                     format='iso8601', tzinfo=req.tz)
            add_link(req, 'next', req.href.timeline(from_=next_start,
                                                    authors=authors,
                                                    daysback=daysback),
                     _("Next Period"))
        prevnext_nav(req, _("Previous Period"), _("Next Period"))

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
            def pretty_dateinfo(date, format=None, dateonly=False):
                if not date:
                    return ''
                if format == 'date':
                    absolute = user_time(req, format_date, date)
                else:
                    absolute = user_time(req, format_datetime, date)
                now = datetime_now(localtz)
                relative = pretty_timedelta(date, now)
                if not format:
                    format = req.session.get('dateinfo',
                                 Chrome(self.env).default_dateinfo_format)
                if format == 'relative':
                    if date > now:
                        label = _("in %(relative)s", relative=relative) \
                                if not dateonly else relative
                        title = _("on %(date)s at %(time)s",
                                  date=user_time(req, format_date, date),
                                  time=user_time(req, format_time, date))
                        return tag.span(label, title=title)
                    else:
                        label = _("%(relative)s ago", relative=relative) \
                                if not dateonly else relative
                        title = _("See timeline at %(absolutetime)s",
                                  absolutetime=absolute)
                else:
                    if dateonly:
                        label = absolute
                    elif req.lc_time == 'iso8601':
                        label = _("at %(iso8601)s", iso8601=absolute)
                    elif format == 'date':
                        label = _("on %(date)s", date=absolute)
                    else:
                        label = _("on %(date)s at %(time)s",
                                  date=user_time(req, format_date, date),
                                  time=user_time(req, format_time, date))
                    if date > now:
                        title = _("in %(relative)s", relative=relative)
                        return tag.span(label, title=title)
                    title = _("See timeline %(relativetime)s ago",
                              relativetime=relative)
                return self.get_timeline_link(req, date, label,
                                              precision='second', title=title)
            def dateinfo(date):
                return pretty_dateinfo(date, format='relative', dateonly=True)
            data['pretty_dateinfo'] = pretty_dateinfo
            data['dateinfo'] = dateinfo
        return template, data, content_type

    # IWikiSyntaxProvider methods

    def get_wiki_syntax(self):
        return []

    def get_link_resolvers(self):
        def link_resolver(formatter, ns, target, label):
            path, query, fragment = split_url_into_path_query_fragment(target)
            precision = None
            time = path.split("T", 1)
            if len(time) > 1:
                time = time[1].split("Z")[0]
                if len(time) >= 6:
                    precision = 'seconds'
                elif len(time) >= 4:
                    precision = 'minutes'
                elif len(time) >= 2:
                    precision = 'hours'
            try:
                dt = parse_date(path, utc, locale='iso8601', hint='iso8601')
                return self.get_timeline_link(formatter.req, dt, label,
                                              precision, query, fragment)
            except TracError as e:
                return tag.a(label, title=to_unicode(e),
                             class_='timeline missing')
        yield 'timeline', link_resolver

    # Public methods

    def get_timeline_link(self, req, date, label=None, precision='hours',
                          query=None, fragment=None, title=None):
        iso_date = format_datetime(date, 'iso8601', req.tz)
        href = req.href.timeline(from_=iso_date, precision=precision)
        return tag.a(label or iso_date, class_='timeline',
                     title=title or _("See timeline at %(absolutetime)s",
                                      absolutetime=iso_date),
                     href=concat_path_query_fragment(href, query, fragment))

    # Internal methods

    def _event_data(self, provider, event):
        """Compose the timeline event date from the event tuple and prepared
        provider methods"""
        if len(event) == 5:  # with special provider
            kind, date, author, data, provider = event
        else:
            kind, date, author, data = event
        render = lambda field, context: \
                 provider.render_timeline_event(context, field, event)
        dateuid = to_utimestamp(date)
        return {'kind': kind, 'author': author, 'date': date,
                'dateuid': dateuid, 'render': render, 'event': event,
                'data': data, 'provider': provider}

    def _provider_failure(self, exc, req, ep, current_filters, all_filters):
        """Raise a TracError exception explaining the failure of a provider.

        At the same time, the message will contain a link to the timeline
        without the filters corresponding to the guilty event provider `ep`.
        """
        self.log.error("Timeline event provider failed: %s",
                       exception_to_unicode(exc, traceback=True))

        ep_kinds = dict((f[0], f[1])
                        for f in ep.get_timeline_filters(req) or [])
        ep_filters = set(ep_kinds.keys())
        current_filters = set(current_filters)
        other_filters = set(current_filters) - ep_filters
        if not other_filters:
            other_filters = set(all_filters) - ep_filters
        args = [(a, req.args.get(a))
                for a in ('from', 'format', 'max', 'daysback')]
        href = req.href.timeline(args + [(f, 'on') for f in other_filters])
        # TRANSLATOR: ...want to see the 'other kinds of events' from... (link)
        other_events = tag.a(_('other kinds of events'), href=href)
        raise TracError(tag(
            tag.p(tag_("Event provider %(name)s failed for filters "
                       "%(kinds)s: ",
                       name=tag.code(ep.__class__.__name__),
                       kinds=', '.join('"%s"' % ep_kinds[f] for f in
                                       current_filters & ep_filters)),
                  tag.strong(exception_to_unicode(exc)), class_='message'),
            tag.p(tag_("You may want to see the %(other_events)s from the "
                       "Timeline or notify your Trac administrator about the "
                       "error (detailed information was written to the log).",
                       other_events=other_events))))
