# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2004, 2005 Edgewall Software
# Copyright (C) 2004, 2005 Christopher Lenz <cmlenz@gmx.de>
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
# Author: Christopher Lenz <cmlenz@gmx.de>

from trac import perm
from trac.Module import Module
from trac.Ticket import get_custom_fields, Ticket
from trac.web.main import add_link
from trac.WikiFormatter import wiki_to_html
from trac.util import *

import time


def get_tickets_for_milestone(env, db, milestone, field='component'):
    custom = field not in Ticket.std_fields
    cursor = db.cursor()
    sql = "SELECT ticket.id AS id, ticket.status AS status, "
    if custom:
        sql += "ticket_custom.value AS %s " \
               "FROM ticket LEFT OUTER JOIN ticket_custom ON id=ticket " \
               "WHERE name='%s' AND milestone='%s'" % (
               sql_escape(field), sql_escape(field), sql_escape(milestone))
    else:
        sql += "ticket.%s AS %s FROM ticket WHERE milestone='%s'" % (
               field, field, sql_escape(milestone))
    sql += " ORDER BY %s" % field

    cursor.execute(sql)
    tickets = []
    while 1:
        row = cursor.fetchone()
        if not row:
            break
        ticket = {
            'id': int(row['id']),
            'status': row['status'],
            field: row[field]
        }
        tickets.append(ticket)
    return tickets


def get_query_links(env, milestone, grouped_by='component', group=None):
    q = {}
    if not group:
        q['all_tickets'] = env.href.query(milestone=milestone)
        q['active_tickets'] = env.href.query(milestone=milestone,
                                             status=('new', 'assigned', 'reopened'))
        q['closed_tickets'] = env.href.query(milestone=milestone, status='closed')
    else:
        q['all_tickets'] = env.href.query(milestone=milestone, grouped_by=group)
        q['active_tickets'] = env.href.query(milestone=milestone,
                                             grouped_by=group,
                                             status=('new', 'assigned', 'reopened'))
        q['closed_tickets'] = env.href.query(milestone=milestone, grouped_by=group,
                                             status='closed')
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


class Milestone(Module):

    def save_milestone(self, req, id):
        self.perm.assert_permission(perm.MILESTONE_MODIFY)
        if req.args.has_key('save'):
            name = req.args.get('name', '')
            if not name:
                raise TracError('You must provide a name for the milestone.',
                                'Required Field Missing')
            due = 0
            due_str = req.args.get('duedate', '')
            if due_str:
                due = self.parse_date(due_str)
            completed = 0
            if req.args.has_key('completed'):
                completed_str = req.args.get('completeddate', '')
                if completed_str:
                    completed = self.parse_date(completed_str)
            description = req.args.get('description', '')
            if not id:
                self.create_milestone(req, name, due, completed, description)
            else:
                self.update_milestone(req, id, name, due, completed, description)
        elif id:
            req.redirect(self.env.href.milestone(id))
        else:
            req.redirect(self.env.href.roadmap())

    def parse_date(self, datestr):
        seconds = None
        datestr = datestr.strip()
        for format in ['%x %X', '%x, %X', '%X %x', '%X, %x', '%x', '%c',
                       '%b %d, %Y']:
            try:
                date = time.strptime(datestr, format)
                seconds = time.mktime(date)
                break
            except ValueError:
                continue
        if seconds == None:
            raise TracError('%s is not a known date format.' % datestr,
                            'Invalid Date Format')
        return seconds

    def create_milestone(self, req, name, due=0, completed=0, description=''):
        self.perm.assert_permission(perm.MILESTONE_CREATE)
        if not name:
            raise TracError('You must provide a name for the milestone.',
                            'Required Field Missing')
        cursor = self.db.cursor()
        self.log.debug("Creating new milestone '%s'" % name)
        cursor.execute("INSERT INTO milestone (name,due,completed,description) "
                       "VALUES (%s,%s,%s,%s)",
                       (name, due, completed, description))
        self.db.commit()
        req.redirect(self.env.href.milestone(name))

    def delete_milestone(self, req, id):
        self.perm.assert_permission(perm.MILESTONE_DELETE)
        self.get_milestone(req, id) # check whether the milestone exists
        if req.args.has_key('delete'):
            cursor = self.db.cursor()
            if req.args.has_key('retarget'):
                target = req.args.get('target')
                if target:
                    self.log.info('Retargeting milestone field of all '
                                  'tickets associated with milestone %s to '
                                  'milestone %s' % (id, target))
                    cursor.execute("UPDATE ticket SET milestone=%s "
                                   "WHERE milestone=%s", (target, id))
                else:
                    self.log.info('Resetting milestone field of all '
                                  'tickets associated with milestone %s' % id)
                    cursor.execute("UPDATE ticket SET milestone=NULL "
                                   "WHERE milestone=%s", (id,))
            self.log.info('Deleting milestone %s' % id)
            cursor.execute("DELETE FROM milestone WHERE name=%s", (id,))
            self.db.commit()
            req.redirect(self.env.href.roadmap())
        else:
            req.redirect(self.env.href.milestone(id))

    def update_milestone(self, req, id, name, due, completed, description):
        self.perm.assert_permission(perm.MILESTONE_MODIFY)
        cursor = self.db.cursor()
        self.log.info("Updating milestone '%s'" % id)
        if req.args.has_key('save'):
            self.log.info('Updating milestone field of all tickets '
                          'associated with milestone %s' % id)
            cursor.execute("UPDATE ticket SET milestone=%s "
                           "WHERE milestone=%s", (name, id))
            cursor.execute("UPDATE milestone SET name=%s,due=%s,"
                           "completed=%s,description=%s WHERE name=%s",
                           (name, due, completed, description, id))
            self.db.commit()
            req.redirect(self.env.href.milestone(name))
        else:
            req.redirect(self.env.href.milestone(id))

    def get_groups(self, by='component'):
        cursor = self.db.cursor ()
        groups = []
        if by in ['status', 'resolution', 'severity', 'priority']:
            cursor.execute("SELECT name FROM enum WHERE type = %s "
                           "AND COALESCE(name,'')!='' ORDER BY value", (by,))
        elif by in ['component', 'milestone', 'version']:
            cursor.execute("SELECT name FROM %s "
                           "WHERE COALESCE(name,'')!='' ORDER BY name" % (by,))
        elif by == 'owner':
            cursor.execute("SELECT DISTINCT owner AS name FROM ticket "
                           "ORDER BY owner")
        elif by not in Ticket.std_fields:
            fields = get_custom_fields(self.env)
            field = [f for f in fields if f['name'] == by]
            if not field:
                return []
            return [o for o in field[0]['options'] if o]
        while 1:
            row = cursor.fetchone()
            if not row:
                break
            groups.append(row['name'] or '')
        return groups

    def get_milestone(self, req, name):
        cursor = self.db.cursor()
        cursor.execute("SELECT name, due, completed, description "
                       "FROM milestone WHERE name = %s", (name,))
        row = cursor.fetchone()
        cursor.close()
        if not row:
            raise TracError('Milestone %s does not exist.' % name,
                            'Invalid Milestone Number')
        milestone = {'name': row['name']}
        description = row['description']
        if description:
            milestone['description_source'] = description
            milestone['description'] = wiki_to_html(description, req.hdf,
                                                    self.env, self.db)
        due = row['due'] and int(row['due'])
        if due > 0:
            milestone['due'] = due
            milestone['due_date'] = time.strftime('%x', time.localtime(due))
            milestone['due_delta'] = pretty_timedelta(due)
            if due < time.time():
                milestone['late'] = 1
        completed = row['completed'] and int(row['completed'])
        if completed > 0:
            milestone['completed'] = completed
            milestone['completed_date'] = time.strftime('%x %X', time.localtime(completed))
            milestone['completed_delta'] = pretty_timedelta(completed)
        return milestone

    def render(self, req):
        self.perm.assert_permission(perm.MILESTONE_VIEW)

        add_link(req, 'up', self.env.href.roadmap(), 'Roadmap')

        action = req.args.get('action', 'view')
        id = req.args.get('id')

        if action == 'new':
            self.perm.assert_permission(perm.MILESTONE_CREATE)
            self.render_editor(req)
        elif action == 'edit':
            self.perm.assert_permission(perm.MILESTONE_MODIFY)
            self.render_editor(req, id)
        elif action == 'delete':
            self.perm.assert_permission(perm.MILESTONE_DELETE)
            self.render_confirm(req, id)
        elif action == 'commit_changes':
            self.save_milestone(req, id)
        elif action == 'confirm_delete':
            self.delete_milestone(req, id)
        else:
            self.render_view(req, id)
        req.display('milestone.cs')

    def render_confirm(self, req, id):
        milestone = self.get_milestone(req, id)
        req.hdf['title'] = 'Milestone %s' % milestone['name']
        req.hdf['milestone.mode'] = 'delete'
        req.hdf['milestone'] = milestone

        cursor = self.db.cursor()
        cursor.execute("SELECT name FROM milestone "
                       "WHERE name != '' ORDER BY name")
        milestone_no = 0
        while 1:
            row = cursor.fetchone()
            if not row:
                break
            req.hdf['milestones.%d' % milestone_no] = row['name']
            milestone_no += 1
        cursor.close()

    def render_editor(self, req, id=None):
        if not id:
            milestone = { 'name': '', 'date': '', 'description': '' }
            req.hdf['title'] = 'New Milestone'
            req.hdf['milestone.mode'] = 'new'
        else:
            milestone = self.get_milestone(req, id)
            req.hdf['title'] = 'Milestone %s' % milestone['name']
            req.hdf['milestone.mode'] = 'edit'
        req.hdf['milestone'] = milestone
        req.hdf['milestone.date_hint'] = get_date_format_hint()
        req.hdf['milestone.datetime_hint'] = get_datetime_format_hint()
        req.hdf['milestone.datetime_now'] = time.strftime('%x %X',
                                                          time.localtime(time.time()))

    def render_view(self, req, id):
        milestone = self.get_milestone(req, id)
        req.hdf['title'] = 'Milestone %s' % milestone['name']
        req.hdf['milestone.mode'] = 'view'

        # If the milestone name contains slashes, we'll need to include the 'id'
        # parameter in the forms for editing/deleting the milestone. See #806.
        if id.find('/') >= 0:
            req.hdf['milestone.id_param'] = 1

        req.hdf['milestone'] = milestone

        available_groups = map(lambda x: {'name': x, 'label': x.capitalize()},
                               ['component', 'version', 'severity', 'priority',
                                'owner'])
        available_groups.extend([{'name': f['name'], 'label': f['label']}
                                 for f in get_custom_fields(self.env)
                                 if f['type'] == 'select'
                                 or f['type'] == 'radio'])
        req.hdf['milestone.stats.available_groups'] = available_groups

        by = req.args.get('by', 'component')
        req.hdf['milestone.stats.grouped_by'] = by

        tickets = get_tickets_for_milestone(self.env, self.db, id, by)
        stats = calc_ticket_stats(tickets)
        req.hdf['milestone.stats'] = stats
        queries = get_query_links(self.env, milestone['name'])
        req.hdf['milestone.queries'] = queries

        groups = self.get_groups(by)
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
            queries = get_query_links(self.env, milestone['name'], by, group)
            req.hdf['%s.queries' % prefix] = queries
            group_no += 1
        req.hdf['milestone.stats.max_percent_total'] = max_percent_total * 100
