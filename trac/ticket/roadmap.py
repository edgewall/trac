# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2006 Edgewall Software
# Copyright (C) 2004-2005 Christopher Lenz <cmlenz@gmx.de>
# Copyright (C) 2006 Christian Boos <cboos@neuf.fr>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://projects.edgewall.com/trac/.
#
# Author: Christopher Lenz <cmlenz@gmx.de>

import re
from time import localtime, strftime, time

from trac import __version__
from trac.core import *
from trac.perm import IPermissionRequestor
from trac.util.datefmt import format_date, format_datetime, parse_date, \
                               pretty_timedelta
from trac.util.text import shorten_line, CRLF, to_unicode
from trac.util.markup import html, unescape, Markup
from trac.ticket import Milestone, Ticket, TicketSystem
from trac.Timeline import ITimelineEventProvider
from trac.web import IRequestHandler
from trac.web.chrome import add_link, add_stylesheet, INavigationContributor
from trac.wiki import wiki_to_html, wiki_to_oneliner, IWikiSyntaxProvider


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

def get_query_links(req, milestone, grouped_by='component', group=None):
    q = {}
    if not group:
        q['all_tickets'] = req.href.query(milestone=milestone)
        q['active_tickets'] = req.href.query(
            milestone=milestone, status=('new', 'assigned', 'reopened'))
        q['closed_tickets'] = req.href.query(
            milestone=milestone, status='closed')
    else:
        q['all_tickets'] = req.href.query(
            {grouped_by: group}, milestone=milestone)
        q['active_tickets'] = req.href.query(
            {grouped_by: group}, milestone=milestone,
            status=('new', 'assigned', 'reopened'))
        q['closed_tickets'] = req.href.query(
            {grouped_by: group}, milestone=milestone, status='closed')
    return q

def calc_ticket_stats(tickets):
    total_cnt = len(tickets)
    active = [ticket for ticket in tickets if ticket['status'] != 'closed']
    active_cnt = len(active)
    closed_cnt = total_cnt - active_cnt

    percent_active, percent_closed = 0, 0
    if total_cnt > 0:
        percent_active = round(float(active_cnt) / float(total_cnt) * 100)
        percent_closed = round(float(closed_cnt) / float(total_cnt) * 100)
        if percent_active + percent_closed > 100:
            percent_closed -= 1

    return {
        'total_tickets': total_cnt,
        'active_tickets': active_cnt,
        'percent_active': percent_active,
        'closed_tickets': closed_cnt,
        'percent_closed': percent_closed
    }

def milestone_to_hdf(env, db, req, milestone):
    safe_name = None
    if milestone.exists:
        safe_name = milestone.name.replace('/', '%2F')
    hdf = {'name': milestone.name,
           'href': req.href.milestone(safe_name)}
    if milestone.description:
        hdf['description_source'] = milestone.description
        hdf['description'] = wiki_to_html(milestone.description, env, req, db)
    if milestone.due:
        hdf['due'] = milestone.due
        hdf['due_date'] = format_date(milestone.due)
        hdf['due_delta'] = pretty_timedelta(milestone.due + 86400)
        hdf['late'] = milestone.is_late
    if milestone.completed:
        hdf['completed'] = milestone.completed
        hdf['completed_date'] = format_datetime(milestone.completed)
        hdf['completed_delta'] = pretty_timedelta(milestone.completed)
    return hdf

def _get_groups(env, db, by='component'):
    for field in TicketSystem(env).get_ticket_fields():
        if field['name'] == by:
            if field.has_key('options'):
                return field['options']
            else:
                cursor = db.cursor()
                cursor.execute("SELECT DISTINCT %s FROM ticket ORDER BY %s"
                               % (by, by))
                return [row[0] for row in cursor]
    return []


class RoadmapModule(Component):

    implements(INavigationContributor, IPermissionRequestor, IRequestHandler)

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'roadmap'

    def get_navigation_items(self, req):
        if not req.perm.has_permission('ROADMAP_VIEW'):
            return
        yield ('mainnav', 'roadmap',
               html.a('Roadmap', href=req.href.roadmap(), accesskey=3))

    # IPermissionRequestor methods

    def get_permission_actions(self):
        return ['ROADMAP_VIEW']

    # IRequestHandler methods

    def match_request(self, req):
        return re.match(r'/roadmap/?', req.path_info) is not None

    def process_request(self, req):
        req.perm.assert_permission('ROADMAP_VIEW')
        req.hdf['title'] = 'Roadmap'

        showall = req.args.get('show') == 'all'
        req.hdf['roadmap.showall'] = showall

        db = self.env.get_db_cnx()
        milestones = [milestone_to_hdf(self.env, db, req, m)
                      for m in Milestone.select(self.env, showall, db)]
        req.hdf['roadmap.milestones'] = milestones        

        for idx, milestone in enumerate(milestones):
            milestone_name = unescape(milestone['name']) # Kludge
            prefix = 'roadmap.milestones.%d.' % idx
            tickets = get_tickets_for_milestone(self.env, db, milestone_name,
                                                'owner')
            req.hdf[prefix + 'stats'] = calc_ticket_stats(tickets)
            for k, v in get_query_links(req, milestone_name).items():
                req.hdf[prefix + 'queries.' + k] = v
            milestone['tickets'] = tickets # for the iCalendar view

        if req.args.get('format') == 'ics':
            self.render_ics(req, db, milestones)
            return

        add_stylesheet(req, 'common/css/roadmap.css')

        # FIXME should use the 'webcal:' scheme, probably
        username = None
        if req.authname and req.authname != 'anonymous':
            username = req.authname
        icshref = req.href.roadmap(show=req.args.get('show'),
                                        user=username, format='ics')
        add_link(req, 'alternate', icshref, 'iCalendar', 'text/calendar', 'ics')

        return 'roadmap.cs', None

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

        def write_prop(name, value, params={}):
            text = ';'.join([name] + [k + '=' + v for k, v in params.items()]) \
                 + ':' + '\\n'.join(re.split(r'[\r\n]+', value))
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
                write_date('DTSTAMP', localtime(milestone['due']))
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
        if req.perm.has_permission('MILESTONE_VIEW'):
            yield ('milestone', 'Milestones')

    def get_timeline_events(self, req, start, stop, filters):
        if 'milestone' in filters:
            format = req.args.get('format')
            db = self.env.get_db_cnx()
            cursor = db.cursor()
            cursor.execute("SELECT completed,name,description FROM milestone "
                           "WHERE completed>=%s AND completed<=%s",
                           (start, stop,))
            for completed, name, description in cursor:
                title = Markup('Milestone <em>%s</em> completed', name)
                if format == 'rss':
                    href = req.abs_href.milestone(name)
                    message = wiki_to_html(description, self.env, req, db,
                                           absurls=True)
                else:
                    href = req.href.milestone(name)
                    message = wiki_to_oneliner(description, self.env, db,
                                               shorten=True)
                yield 'milestone', href, title, completed, None, message or '--'

    # IRequestHandler methods

    def match_request(self, req):
        import re, urllib
        match = re.match(r'/milestone(?:/(.+))?', req.path_info)
        if match:
            if match.group(1):
                req.args['id'] = match.group(1)
            return True

    def process_request(self, req):
        req.perm.assert_permission('MILESTONE_VIEW')

        add_link(req, 'up', req.href.roadmap(), 'Roadmap')

        db = self.env.get_db_cnx()
        milestone = Milestone(self.env, req.args.get('id'), db)
        action = req.args.get('action', 'view')

        if req.method == 'POST':
            if req.args.has_key('cancel'):
                if milestone.exists:
                    safe_name = milestone.name.replace('/', '%2F')
                    req.redirect(req.href.milestone(safe_name))
                else:
                    req.redirect(req.href.roadmap())
            elif action == 'edit':
                self._do_save(req, db, milestone)
            elif action == 'delete':
                self._do_delete(req, db, milestone)
        elif action in ('new', 'edit'):
            self._render_editor(req, db, milestone)
        elif action == 'delete':
            self._render_confirm(req, db, milestone)
        else:
            self._render_view(req, db, milestone)

        add_stylesheet(req, 'common/css/roadmap.css')
        return 'milestone.cs', None

    # Internal methods

    def _do_delete(self, req, db, milestone):
        req.perm.assert_permission('MILESTONE_DELETE')

        retarget_to = None
        if req.args.has_key('retarget'):
            retarget_to = req.args.get('target')
        milestone.delete(retarget_to, req.authname)
        db.commit()
        req.redirect(req.href.roadmap())

    def _do_save(self, req, db, milestone):
        if milestone.exists:
            req.perm.assert_permission('MILESTONE_MODIFY')
        else:
            req.perm.assert_permission('MILESTONE_CREATE')

        if not req.args.has_key('name'):
            raise TracError('You must provide a name for the milestone.',
                            'Required Field Missing')
        milestone.name = req.args.get('name')

        due = req.args.get('duedate', '')
        try:
            milestone.due = due and parse_date(due) or 0
        except ValueError, e:
            raise TracError(to_unicode(e), 'Invalid Date Format')
        if req.args.has_key('completed'):
            completed = req.args.get('completeddate', '')
            try:
                milestone.completed = completed and parse_date(completed) or 0
            except ValueError, e:
                raise TracError(to_unicode(e), 'Invalid Date Format')
            if milestone.completed > time():
                raise TracError('Completion date may not be in the future',
                                'Invalid Completion Date')
            retarget_to = req.args.get('target')
            if req.args.has_key('retarget'):
                cursor = db.cursor()
                cursor.execute("UPDATE ticket SET milestone=%s WHERE "
                               "milestone=%s and status != 'closed'",
                                (retarget_to, milestone.name))
                self.env.log.info('Tickets associated with milestone %s '
                                  'retargeted to %s' % 
                                  (milestone.name, retarget_to))
        else:
            milestone.completed = 0

        milestone.description = req.args.get('description', '')

        if milestone.exists:
            milestone.update()
        else:
            milestone.insert()
        db.commit()

        safe_name = milestone.name.replace('/', '%2F')
        req.redirect(req.href.milestone(safe_name))

    def _render_confirm(self, req, db, milestone):
        req.perm.assert_permission('MILESTONE_DELETE')

        req.hdf['title'] = 'Milestone %s' % milestone.name
        req.hdf['milestone'] = milestone_to_hdf(self.env, db, req, milestone)
        req.hdf['milestone.mode'] = 'delete'

        for idx,other in enumerate(Milestone.select(self.env, False, db)):
            if other.name == milestone.name:
                continue
            req.hdf['milestones.%d' % idx] = other.name

    def _render_editor(self, req, db, milestone):
        if milestone.exists:
            req.perm.assert_permission('MILESTONE_MODIFY')
            req.hdf['title'] = 'Milestone %s' % milestone.name
            req.hdf['milestone.mode'] = 'edit'
            req.hdf['milestones'] = [m.name for m in
                                     Milestone.select(self.env)
                                     if m.name != milestone.name]
        else:
            req.perm.assert_permission('MILESTONE_CREATE')
            req.hdf['title'] = 'New Milestone'
            req.hdf['milestone.mode'] = 'new'

        from trac.util.datefmt import get_date_format_hint, \
                                       get_datetime_format_hint
        req.hdf['milestone'] = milestone_to_hdf(self.env, db, req, milestone)
        req.hdf['milestone.date_hint'] = get_date_format_hint()
        req.hdf['milestone.datetime_hint'] = get_datetime_format_hint()
        req.hdf['milestone.datetime_now'] = format_datetime()

    def _render_view(self, req, db, milestone):
        req.hdf['title'] = 'Milestone %s' % milestone.name
        req.hdf['milestone.mode'] = 'view'

        req.hdf['milestone'] = milestone_to_hdf(self.env, db, req, milestone)

        available_groups = []
        component_group_available = False
        for field in TicketSystem(self.env).get_ticket_fields():
            if field['type'] == 'select' and field['name'] != 'milestone' \
                    or field['name'] == 'owner':
                available_groups.append({'name': field['name'],
                                         'label': field['label']})
                if field['name'] == 'component':
                    component_group_available = True
        req.hdf['milestone.stats.available_groups'] = available_groups

        if component_group_available:
            by = req.args.get('by', 'component')
        else:
            by = req.args.get('by', available_groups[0]['name'])
        req.hdf['milestone.stats.grouped_by'] = by

        tickets = get_tickets_for_milestone(self.env, db, milestone.name, by)
        stats = calc_ticket_stats(tickets)
        req.hdf['milestone.stats'] = stats
        for key, value in get_query_links(req, milestone.name).items():
            req.hdf['milestone.queries.' + key] = value

        groups = _get_groups(self.env, db, by)
        group_no = 0
        max_percent_total = 0
        for group in groups:
            group_tickets = [t for t in tickets if t[by] == group]
            if not group_tickets:
                continue
            prefix = 'milestone.stats.groups.%s' % group_no
            req.hdf['%s.name' % prefix] = group
            percent_total = 0
            if len(tickets) > 0:
                percent_total = float(len(group_tickets)) / float(len(tickets))
                if percent_total > max_percent_total:
                    max_percent_total = percent_total
            req.hdf['%s.percent_total' % prefix] = percent_total * 100
            stats = calc_ticket_stats(group_tickets)
            req.hdf[prefix] = stats
            for key, value in \
                    get_query_links(req, milestone.name, by, group).items():
                req.hdf['%s.queries.%s' % (prefix, key)] = value
            group_no += 1
        req.hdf['milestone.stats.max_percent_total'] = max_percent_total * 100

    # IWikiSyntaxProvider methods

    def get_wiki_syntax(self):
        return []

    def get_link_resolvers(self):
        yield ('milestone', self._format_link)

    def _format_link(self, formatter, ns, name, label):
        return html.A(label, href=formatter.href.milestone(name),
                      class_='milestone')
