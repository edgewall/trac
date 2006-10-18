# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2006 Edgewall Software
# Copyright (C) 2004-2005 Christopher Lenz <cmlenz@gmx.de>
# Copyright (C) 2006 Christian Boos <cboos@neuf.fr>
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

from trac import __version__
from trac.core import *
from trac.perm import IPermissionRequestor
from trac.util.datefmt import parse_date, utc, to_timestamp
from trac.util.html import html, unescape, Markup
from trac.util.text import shorten_line, CRLF, to_unicode
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
    hdf = {'name': milestone.name, 'exists': milestone.exists,
           'href': req.href.milestone(safe_name),
           'due':  milestone.due, 'completed': milestone.completed
           } # FIXME: pass the full milestone object
    if milestone.description:
        hdf['description_source'] = milestone.description
        hdf['description'] = wiki_to_html(milestone.description, env, req, db)
    if milestone.due:
        hdf['late'] = milestone.is_late
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
        data = {}

        showall = req.args.get('show') == 'all'
        data['showall'] = showall

        db = self.env.get_db_cnx()
        milestones = [milestone_to_hdf(self.env, db, req, m)
                      for m in Milestone.select(self.env, showall, db)]
        data['milestones'] = milestones

        for idx, milestone in enumerate(milestones):
            milestone_name = unescape(milestone['name']) # Kludge
            tickets = get_tickets_for_milestone(self.env, db, milestone_name,
                                                'owner')
            milestone['stats'] = calc_ticket_stats(tickets)
            milestone['queries'] = get_query_links(req, milestone_name)
            milestone['tickets'] = tickets # for the iCalendar view

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
                           (to_timestamp(start), to_timestamp(stop)))
            for ts, name, description in cursor:
                completed = datetime.fromtimestamp(ts, utc)
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
            return self._render_editor(req, db, milestone)
        elif action == 'delete':
            return self._render_confirm(req, db, milestone)

        return self._render_view(req, db, milestone)

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

        due = req.args.get('duedate', '')
        try:
            milestone.due = due and parse_date(due, tzinfo=req.tz) or 0
        except ValueError, e:
            raise TracError(to_unicode(e), 'Invalid Date Format')
        if req.args.has_key('completed'):
            completed = req.args.get('completeddate', '')
            try:
                milestone.completed = completed and parse_date(completed) or None
            except ValueError, e:
                raise TracError(to_unicode(e), 'Invalid Date Format')
            if milestone.completed > datetime.now(utc):
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

        # don't update the milestone name until after retargetting open tickets
        milestone.name = req.args.get('name')
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

        data = {'milestone': milestone_to_hdf(self.env, db, req, milestone),
                'milestones': [m.name for m in
                               Milestone.select(self.env, False, db)
                               if m.name != milestone.name]}

        return 'milestone_delete.html', data, None

    def _render_editor(self, req, db, milestone):
        from trac.util.datefmt import get_date_format_hint, \
                                       get_datetime_format_hint
        data = {'date_hint': get_date_format_hint(),
                'datetime_hint': get_datetime_format_hint()}

        if milestone.exists:
            req.perm.assert_permission('MILESTONE_MODIFY')
            data['milestones'] = [m.name for m in
                                  Milestone.select(self.env, False, db)
                                  if m.name != milestone.name]
        else:
            req.perm.assert_permission('MILESTONE_CREATE')

        data['milestone'] = milestone_to_hdf(self.env, db, req, milestone)

        return 'milestone_edit.html', data, None

    def _render_view(self, req, db, milestone):
        data = {'milestone': milestone_to_hdf(self.env, db, req, milestone)}

        available_groups = []
        component_group_available = False
        for field in TicketSystem(self.env).get_ticket_fields():
            if field['type'] == 'select' and field['name'] != 'milestone' \
                    or field['name'] == 'owner':
                available_groups.append({'name': field['name'],
                                         'label': field['label']})
                if field['name'] == 'component':
                    component_group_available = True
        if component_group_available:
            by = req.args.get('by', 'component')
        else:
            by = req.args.get('by', available_groups[0]['name'])

        tickets = get_tickets_for_milestone(self.env, db, milestone.name, by)
        data['stats'] = calc_ticket_stats(tickets)
        data['stats']['available_groups'] = available_groups
        data['stats']['grouped_by'] = by
        data['queries'] = get_query_links(req, milestone.name)

        data['stats']['groups'] = []
        groups = _get_groups(self.env, db, by)
        max_percent_total = 0
        for group in groups:
            group_tickets = [t for t in tickets if t[by] == group]
            if not group_tickets:
                continue
            data['stats']['groups'].append({'name': group})
            percent_total = 0
            if len(tickets) > 0:
                percent_total = float(len(group_tickets)) / float(len(tickets))
                if percent_total > max_percent_total:
                    max_percent_total = percent_total
            data['stats']['groups'][-1]['percent_total'] = percent_total * 100
            data['stats']['groups'][-1]['stats'] = calc_ticket_stats(group_tickets)
            data['stats']['groups'][-1]['queries'] = get_query_links(req, milestone.name, by, group)
        data['stats']['max_percent_total'] = max_percent_total * 100

        return 'milestone_view.html', data, None

    # IWikiSyntaxProvider methods

    def get_wiki_syntax(self):
        return []

    def get_link_resolvers(self):
        yield ('milestone', self._format_link)

    def _format_link(self, formatter, ns, name, label):
        return html.A(label, href=formatter.href.milestone(name),
                      class_='milestone')
