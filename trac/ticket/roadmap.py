# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2007 Edgewall Software
# Copyright (C) 2004-2005 Christopher Lenz <cmlenz@gmx.de>
# Copyright (C) 2006-2007 Christian Boos <cboos@neuf.fr>
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
# Author: Christopher Lenz <cmlenz@gmx.de>

from datetime import datetime
import re
from time import localtime, strftime, time

from genshi.builder import tag

from trac import __version__
from trac.context import Context
from trac.core import *
from trac.perm import IPermissionRequestor
from trac.util import sorted
from trac.util.datefmt import parse_date, utc, to_timestamp, \
                              get_date_format_hint, get_datetime_format_hint
from trac.util.text import shorten_line, CRLF, to_unicode
from trac.ticket import Milestone, Ticket, TicketSystem
from trac.ticket.query import Query
from trac.timeline.api import ITimelineEventProvider, TimelineEvent
from trac.web import IRequestHandler
from trac.web.chrome import add_link, add_stylesheet, INavigationContributor
from trac.wiki.api import IWikiSyntaxProvider
from trac.config import ExtensionOption

class ITicketGroupStatsProvider(Interface):
    def get_ticket_group_stats(self, ticket_ids):
        """ Gather statistics on a group of tickets.

        This method returns a valid TicketGroupStats object.
        """

class TicketGroupStats(object):
    """Encapsulates statistics on a group of tickets."""

    def __init__(self, title, unit):
        """Creates a new TicketGroupStats object.
        
        `title` is the display name of this group of stats (e.g.
          'ticket status').
        `unit` is the display name of the units for these stats (e.g. 'hour').
        """
        self.title = title
        self.unit = unit
        self.count = 0
        self.qry_args = {}
        self.intervals = []
        self.done_percent = 0
        self.done_count = 0

    def add_interval(self, title, count, qry_args, css_class, countsToProg=0):
        """Adds a division to this stats' group's progress bar.

        `title` is the display name (eg 'closed', 'spent effort') of this
        interval that will be displayed in front of the unit name.
        `count` is the number of units in the interval.
        `qry_args` is a dict of extra params that will yield the subset of
          tickets in this interval on a query.
        `css_class` is the css class that will be used to display the division.
        `countsToProg` can be set to true to make this interval count towards
          overall completion of this group of tickets.
        """
        self.intervals.append({
            'title': title,
            'count': count,
            'qry_args': qry_args,
            'css_class': css_class,
            'percent': None,
            'countsToProg': countsToProg
        })
        self.count = self.count + count

    def refresh_calcs(self):
        if self.count < 1:
            return
        total_percent = 0
        self.done_percent = 0
        self.done_count = 0
        for interval in self.intervals:
            interval['percent'] = round(float(interval['count'] / 
                                        float(self.count) * 100))
            total_percent = total_percent + interval['percent']
            if interval['countsToProg']:
                self.done_percent += interval['percent']
                self.done_count += interval['count']

        if self.done_count and total_percent != 100:
            fudge_int = [i for i in self.intervals if i['countsToProg']][0]
            fudge_amt = 100 - total_percent
            fudge_int['percent'] += fudge_amt
            self.done_percent += fudge_amt

class DefaultTicketGroupStatsProvider(Component):
    implements(ITicketGroupStatsProvider)

    def get_ticket_group_stats(self, ticket_ids):
        total_cnt = len(ticket_ids)
        if total_cnt:
            cursor = self.env.get_db_cnx().cursor()
            str_ids = [str(x) for x in sorted(ticket_ids)]
            active_cnt = cursor.execute("SELECT count(1) FROM ticket "
                                        "WHERE status <> 'closed' AND id IN "
                                        "(%s)" % ",".join(str_ids))
            active_cnt = 0
            for cnt, in cursor:
                active_cnt = cnt
        else:
            active_cnt = 0

        closed_cnt = total_cnt - active_cnt

        stat = TicketGroupStats('ticket status', 'ticket')
        stat.add_interval('closed', closed_cnt,
                          {'status': 'closed', 'group': 'resolution'},
                          'closed', True)
        stat.add_interval('active', active_cnt,
                          {'status': ['new', 'assigned', 'reopened']},
                          'open', False)
        stat.refresh_calcs()
        return stat


def get_ticket_stats(provider, tickets):
    return provider.get_ticket_group_stats([t['id'] for t in tickets])

def get_tickets_for_milestone(env, db, milestone, field='component'):
    cursor = db.cursor()
    fields = TicketSystem(env).get_ticket_fields()
    if field in [f['name'] for f in fields if not f.get('custom')]:
        cursor.execute("SELECT id,status,%s FROM ticket WHERE milestone=%%s "
                       "ORDER BY %s" % (field, field), (milestone,))
    else:
        cursor.execute("SELECT id,status,value FROM ticket LEFT OUTER "
                       "JOIN ticket_custom ON (id=ticket AND name=%s) "
                       "WHERE milestone=%s ORDER BY value", (field, milestone))
    tickets = []
    for tkt_id, status, fieldval in cursor:
        tickets.append({'id': tkt_id, 'status': status, field: fieldval})
    return tickets

def milestone_stats_data(req, stat, name, grouped_by='component', group=None):
    def query_href(extra_args):
        args = {'milestone': name, grouped_by: group, 'group': 'status'}
        args.update(extra_args)
        return req.href.query(args)
    return {'stats': stat,
            'stats_href': query_href(stat.qry_args),
            'interval_hrefs': [query_href(interval['qry_args'])
                               for interval in stat.intervals]}



class RoadmapModule(Component):

    implements(INavigationContributor, IPermissionRequestor, IRequestHandler)
    stats_provider = ExtensionOption('roadmap', 'stats_provider',
                                     ITicketGroupStatsProvider,
                                     'DefaultTicketGroupStatsProvider',
        """Name of the component implementing `ITicketGroupStatsProvider`, 
        which is used to collect statistics on groups of tickets for display
        in the roadmap views.""")

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'roadmap'

    def get_navigation_items(self, req):
        if 'ROADMAP_VIEW' in req.perm:
            yield ('mainnav', 'roadmap',
                   tag.a('Roadmap', href=req.href.roadmap(), accesskey=3))

    # IPermissionRequestor methods

    def get_permission_actions(self):
        return ['ROADMAP_VIEW']

    # IRequestHandler methods

    def match_request(self, req):
        return re.match(r'/roadmap/?', req.path_info) is not None

    def process_request(self, req):
        req.perm.require('ROADMAP_VIEW')

        showall = req.args.get('show') == 'all'

        db = self.env.get_db_cnx()
        milestones = list(Milestone.select(self.env, showall, db))
        stats = []
        queries = []

        for milestone in milestones:
            tickets = get_tickets_for_milestone(self.env, db, milestone.name,
                                                'owner')
            stat = get_ticket_stats(self.stats_provider, tickets)
            stats.append(milestone_stats_data(req, stat, milestone.name))
            #milestone['tickets'] = tickets # for the iCalendar view

        if req.args.get('format') == 'ics':
            self.render_ics(req, db, milestones)
            return

        # FIXME should use the 'webcal:' scheme, probably
        username = None
        if req.authname and req.authname != 'anonymous':
            username = req.authname
        icshref = req.href.roadmap(show=req.args.get('show'), user=username,
                                   format='ics')
        add_link(req, 'alternate', icshref, 'iCalendar', 'text/calendar', 'ics')

        data = {
            'context': Context(self.env, req),
            'milestones': milestones,
            'milestone_stats': stats,
            'queries': queries,
            'showall': showall,
        }
        return 'roadmap.html', data, None

    # Internal methods

    def render_ics(self, req, db, milestones):
        req.send_response(200)
        req.send_header('Content-Type', 'text/calendar;charset=utf-8')
        req.end_headers()

        from trac.ticket import Priority
        priorities = {}
        for priority in Priority.select(self.env):
            priorities[priority.name] = float(priority.value)
        def get_priority(ticket):
            value = priorities.get(ticket['priority'])
            if value:
                return int(value * 9 / len(priorities))

        def get_status(ticket):
            status = ticket['status']
            if status == 'new' or status == 'reopened' and not ticket['owner']:
                return 'NEEDS-ACTION'
            elif status == 'assigned' or status == 'reopened':
                return 'IN-PROCESS'
            elif status == 'closed':
                if ticket['resolution'] == 'fixed': return 'COMPLETED'
                else: return 'CANCELLED'
            else: return ''

        def escape_value(text): 
            s = ''.join(map(lambda c: (c in ';,\\') and '\\' + c or c, text))
            return '\\n'.join(re.split(r'[\r\n]+', s))

        def write_prop(name, value, params={}):
            text = ';'.join([name] + [k + '=' + v for k, v in params.items()]) \
                 + ':' + escape_value(value)
            firstline = 1
            while text:
                if not firstline: text = ' ' + text
                else: firstline = 0
                req.write(text[:75] + CRLF)
                text = text[75:]

        def write_date(name, value, params={}):
            params['VALUE'] = 'DATE'
            write_prop(name, strftime('%Y%m%d', value), params)

        def write_utctime(name, value, params={}):
            write_prop(name, strftime('%Y%m%dT%H%M%SZ', value), params)

        host = req.base_url[req.base_url.find('://') + 3:]
        user = req.args.get('user', 'anonymous')

        write_prop('BEGIN', 'VCALENDAR')
        write_prop('VERSION', '2.0')
        write_prop('PRODID', '-//Edgewall Software//NONSGML Trac %s//EN'
                   % __version__)
        write_prop('METHOD', 'PUBLISH')
        write_prop('X-WR-CALNAME',
                   self.config.get('project', 'name') + ' - Roadmap')
        for milestone in milestones:
            uid = '<%s/milestone/%s@%s>' % (req.base_path, milestone['name'],
                                            host)
            if milestone.has_key('due'):
                write_prop('BEGIN', 'VEVENT')
                write_prop('UID', uid)
                write_utctime('DTSTAMP', localtime(milestone['due']))
                write_date('DTSTART', localtime(milestone['due']))
                write_prop('SUMMARY', 'Milestone %s' % milestone['name'])
                write_prop('URL', req.base_url + '/milestone/' +
                           milestone['name'])
                if milestone.has_key('description_source'):
                    write_prop('DESCRIPTION', milestone['description_source'])
                write_prop('END', 'VEVENT')
            for tkt_id in [ticket['id'] for ticket in milestone['tickets']
                           if ticket['owner'] == user]:
                ticket = Ticket(self.env, tkt_id)
                write_prop('BEGIN', 'VTODO')
                write_prop('UID', '<%s/ticket/%s@%s>' % (req.base_path,
                                                         tkt_id, host))
                if milestone.has_key('due'):
                    write_prop('RELATED-TO', uid)
                    write_date('DUE', localtime(milestone['due']))
                write_prop('SUMMARY', 'Ticket #%i: %s' % (ticket.id,
                                                          ticket['summary']))
                write_prop('URL', req.abs_href.ticket(ticket.id))
                write_prop('DESCRIPTION', ticket['description'])
                priority = get_priority(ticket)
                if priority:
                    write_prop('PRIORITY', unicode(priority))
                write_prop('STATUS', get_status(ticket))
                if ticket['status'] == 'closed':
                    cursor = db.cursor()
                    cursor.execute("SELECT time FROM ticket_change "
                                   "WHERE ticket=%s AND field='status' "
                                   "ORDER BY time desc LIMIT 1",
                                   (ticket.id,))
                    row = cursor.fetchone()
                    if row:
                        write_utctime('COMPLETED', localtime(row[0]))
                write_prop('END', 'VTODO')
        write_prop('END', 'VCALENDAR')


class MilestoneModule(Component):

    implements(INavigationContributor, IPermissionRequestor, IRequestHandler,
               ITimelineEventProvider, IWikiSyntaxProvider)
 
    stats_provider = ExtensionOption('milestone', 'stats_provider',
                                     ITicketGroupStatsProvider,
                                     'DefaultTicketGroupStatsProvider',
        """Name of the component implementing `ITicketGroupStatsProvider`, 
        which is used to collect statistics on groups of tickets for display
        in the milestone views.""")
    

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'roadmap'

    def get_navigation_items(self, req):
        return []

    # IPermissionRequestor methods

    def get_permission_actions(self):
        actions = ['MILESTONE_CREATE', 'MILESTONE_DELETE', 'MILESTONE_MODIFY',
                   'MILESTONE_VIEW']
        return actions + [('MILESTONE_ADMIN', actions),
                          ('ROADMAP_ADMIN', actions)]

    # ITimelineEventProvider methods

    def get_timeline_filters(self, req):
        if 'MILESTONE_VIEW' in req.perm:
            yield ('milestone', 'Milestones')

    def get_timeline_events(self, req, start, stop, filters):
        if 'milestone' in filters:
            context = Context(self.env, req)
            cursor = context.db.cursor()
            # TODO: creation and (later) modifications should also be reported
            cursor.execute("SELECT completed,name,description FROM milestone "
                           "WHERE completed>=%s AND completed<=%s",
                           (to_timestamp(start), to_timestamp(stop)))
            for ts, name, description in cursor:
                completed = datetime.fromtimestamp(ts, utc)
                title = tag('Milestone ', tag.em(name), ' completed')
                event = TimelineEvent('milestone', title,
                                      req.href.milestone(name))
                event.set_changeinfo(completed, '') # FIXME: store the author
                event.set_context(context('milestone', name), description)
                yield event

    # IRequestHandler methods

    def match_request(self, req):
        import re, urllib
        match = re.match(r'/milestone(?:/(.+))?', req.path_info)
        if match:
            if match.group(1):
                req.args['id'] = match.group(1)
            return True

    def process_request(self, req):
        req.perm.require('MILESTONE_VIEW')
        milestone_id = req.args.get('id')

        add_link(req, 'up', req.href.roadmap(), 'Roadmap')

        db = self.env.get_db_cnx()
        milestone = Milestone(self.env, milestone_id, db)
        action = req.args.get('action', 'view')

        if req.method == 'POST':
            if req.args.has_key('cancel'):
                if milestone.exists:
                    req.redirect(req.href.milestone(milestone.name))
                else:
                    req.redirect(req.href.roadmap())
            elif action == 'edit':
                return self._do_save(req, db, milestone)
            elif action == 'delete':
                self._do_delete(req, db, milestone)
        elif action in ('new', 'edit'):
            return self._render_editor(req, db, milestone)
        elif action == 'delete':
            return self._render_confirm(req, db, milestone)

        if not milestone_id:
            req.redirect(req.href.roadmap())

        return self._render_view(req, db, milestone)

    # Internal methods

    def _do_delete(self, req, db, milestone):
        req.perm.require('MILESTONE_DELETE')

        retarget_to = None
        if req.args.has_key('retarget'):
            retarget_to = req.args.get('target')
        milestone.delete(retarget_to, req.authname)
        db.commit()
        req.redirect(req.href.roadmap())

    def _do_save(self, req, db, milestone):
        if milestone.exists:
            req.perm.require('MILESTONE_MODIFY')
        else:
            req.perm.require('MILESTONE_CREATE')

        old_name = milestone.name

        milestone.name = req.args.get('name')
        milestone.description = req.args.get('description', '')

        due = req.args.get('duedate', '')
        milestone.due = due and parse_date(due, tzinfo=req.tz) or 0

        completed = req.args.get('completeddate', '')
        retarget_to = req.args.get('target')

        # Instead of raising one single error, check all the constraints and
        # let the user fix them by going back to edit mode showing the warnings
        warnings = []
        def warn(msg):
            req.warning(msg)
            warnings.append(msg)

        # -- check the name
        if milestone.name:
            # check that the milestone doesn't already exists
            # FIXME: the whole .exists business needs to be clarified (#4130)
            try:
                test_milestone = Milestone(self.env, milestone.name, db)
                if not milestone.exists:
                    # then an exception should have been raised
                    warn('Milestone "%s" already exists, '
                         'please choose another name' % milestone.name)
            except TracError:
                pass
        else:
            warn('You must provide a name for the milestone.')

        # -- check completed date
        if 'completed' in req.args:
            milestone.completed = completed and parse_date(completed) or \
                                  None
            if milestone.completed and milestone.completed > datetime.now(utc):
                warn('Completion date may not be in the future')
        else:
            milestone.completed = None

        if warnings:
            if not milestone.exists:
                milestone.name = None
            return self._render_editor(req, db, milestone)
        
        # -- actually save changes
        if milestone.exists:
            milestone.update()
            # eventually retarget opened tickets associated with the milestone
            if 'retarget' in req.args:
                cursor = db.cursor()
                cursor.execute("UPDATE ticket SET milestone=%s WHERE "
                               "milestone=%s and status != 'closed'",
                                (retarget_to, old_name))
                self.env.log.info('Tickets associated with milestone %s '
                                  'retargeted to %s' % (old_name, retarget_to))
        else:
            milestone.insert()
        db.commit()

        req.redirect(req.href.milestone(milestone.name))

    def _render_confirm(self, req, db, milestone):
        req.perm.require('MILESTONE_DELETE')

        data = {
            'milestone': milestone,
            'context': Context(self.env, req, 'milestone', milestone.name,
                               db=db),
            'milestones': Milestone.select(self.env, False, db)
        }
        return 'milestone_delete.html', data, None

    def _render_editor(self, req, db, milestone):
        data = {
            'milestone': milestone,
            'context': Context(self.env, req, 'milestone', milestone.name,
                               db=db),
            'date_hint': get_date_format_hint(),
            'datetime_hint': get_datetime_format_hint(),
            'milestones': [],
        }

        if milestone.exists:
            req.perm.require('MILESTONE_MODIFY')
            data['milestones'] = [m for m in
                                  Milestone.select(self.env, False, db)
                                  if m.name != milestone.name]
        else:
            req.perm.require('MILESTONE_CREATE')

        return 'milestone_edit.html', data, None

    def _render_view(self, req, db, milestone):
        milestone_groups = []
        available_groups = []
        component_group_available = False
        ticket_fields = TicketSystem(self.env).get_ticket_fields()

        # collect fields that can be used for grouping
        for field in ticket_fields:
            if field['type'] == 'select' and field['name'] != 'milestone' \
                    or field['name'] in ('owner', 'reporter'):
                available_groups.append({'name': field['name'],
                                         'label': field['label']})
                if field['name'] == 'component':
                    component_group_available = True

        # determine the field currently used for grouping
        by = None
        if component_group_available:
            by = 'component'
        elif available_groups:
            by = available_groups[0]['name']
        by = req.args.get('by', by)

        tickets = get_tickets_for_milestone(self.env, db, milestone.name, by)
        stat = get_ticket_stats(self.stats_provider, tickets)

        data = {'milestone': milestone,
                'context': Context(self.env, req, 'milestone', milestone.name,
                                   db=db),
                'available_groups': available_groups, 
                'grouped_by': by,
                'groups': milestone_groups}
        data.update(milestone_stats_data(req, stat, milestone.name))

        if by:
            groups = []
            for field in ticket_fields:
                if field['name'] == by:
                    if field.has_key('options'):
                        groups = field['options']
                    else:
                        cursor = db.cursor()
                        cursor.execute("SELECT DISTINCT %s FROM ticket "
                                       "ORDER BY %s" % (by, by))
                        groups = [row[0] for row in cursor]

            max_count = 0
            group_stats = []

            for group in groups:
                group_tickets = [t for t in tickets if t[by] == group]
                if not group_tickets:
                    continue

                gstat = get_ticket_stats(self.stats_provider, group_tickets)
                if gstat.count > max_count:
                    max_count = gstat.count

                group_stats.append(gstat) 

                gs_dict = {'name': group}
                gs_dict.update(milestone_stats_data(req, gstat, milestone.name,
                                                    by, group))
                milestone_groups.append(gs_dict)

            for idx, gstat in enumerate(group_stats):
                gs_dict = milestone_groups[idx]
                gs_dict['percent_of_max_total'] = (float(gstat.count) /
                                                   float(max_count) * 100)

        return 'milestone_view.html', data, None

    # IWikiSyntaxProvider methods

    def get_wiki_syntax(self):
        return []

    def get_link_resolvers(self):
        yield ('milestone', self._format_link)

    def _format_link(self, formatter, ns, name, label):
        name, query, fragment = formatter.split_link(name)
        href = formatter.href.milestone(name) + query + fragment
        try:
            milestone = Milestone(self.env, name, formatter.db)
        except TracError:
            milestone = Milestone(self.env)
        # Note: this should really not be needed, exists should simply be false
        # if the milestone doesn't exist in the db
        if milestone.exists:
            closed = milestone.completed and 'closed ' or ''
            return tag.a(label, class_='%smilestone' % closed, href=href)
        else: 
            return tag.a(label, class_='missing milestone', href=href,
                         rel="nofollow")
