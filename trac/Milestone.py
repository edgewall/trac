# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2004 Edgewall Software
# Copyright (C) 2004 Christopher Lenz <cmlenz@gmx.de>
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

import time

from Module import Module
from util import add_dict_to_hdf, TracError
from WikiFormatter import wiki_to_html
import perm


def get_tickets_for_milestone(db, milestone):
    cursor = db.cursor ()
    cursor.execute("SELECT id, status, component FROM ticket "
                   "WHERE milestone = %s", milestone)
    tickets = []
    while 1:
        row = cursor.fetchone()
        if not row:
            break
        ticket = {
            'id': int(row['id']),
            'status': row['status'],
            'component': row['component']
        }
        tickets.append(ticket)
    return tickets

def calc_ticket_stats(tickets):
    total_cnt = len(tickets)
    active = [ticket for ticket in tickets if ticket['status'] != 'closed']
    active_cnt = len(active)
    closed_cnt = total_cnt - active_cnt

    percent_complete = 0
    if total_cnt > 0:
        percent_complete = float(closed_cnt) / float(total_cnt) * 100

    return {
        'total_tickets': total_cnt,
        'active_tickets': active_cnt,
        'closed_tickets': closed_cnt,
        'percent_complete': percent_complete
    }


class Milestone(Module):
    template_name = 'milestone.cs'

    def save_milestone(self, id):
        self.perm.assert_permission(perm.MILESTONE_MODIFY)
        if self.args.has_key('save'):
            name = self.args.get('name', '')
            if not name:
                raise TracError('You must provide a name for the milestone.',
                                'Required Field Missing')
            datestr = self.args.get('date', '')
            date = 0
            if datestr:
                date = self.parse_date(datestr)
            descr = self.args.get('descr', '')
            if id == -1:
                self.create_milestone(name, date, descr)
            else:
                self.update_milestone(id, name, date, descr)
        elif id != -1:
            self.req.redirect(self.env.href.milestone(id))
        else:
            self.req.redirect(self.env.href.roadmap())

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

    def create_milestone(self, name, date=0, descr=''):
        self.perm.assert_permission(perm.MILESTONE_CREATE)
        if not name:
            raise TracError('You must provide a name for the milestone.',
                            'Required Field Missing')
        cursor = self.db.cursor()
        self.env.log.debug("Creating new milestone '%s'" % name)
        cursor.execute("INSERT INTO milestone (id, name, time, descr) "
                       "VALUES (NULL, %s, %d, %s)", name, date, descr)
        self.db.commit()
        self.req.redirect(self.env.href.milestone(name))

    def delete_milestone(self, id):
        self.perm.assert_permission(perm.MILESTONE_DELETE)
        milestone = self.get_milestone(id)
        if self.args.has_key('delete'):
            cursor = self.db.cursor()
            if self.args.has_key('resettickets'):
                self.env.log.info('Resetting milestone field of all tickets '
                                  'associated with milestone %s' % id)
                cursor.execute ('UPDATE ticket SET milestone = NULL '
                                'WHERE milestone = %s', id)
            self.env.log.debug('Deleting milestone %s' % id)
            cursor.execute("DELETE FROM milestone WHERE name = %s", id)
            self.db.commit()
            self.req.redirect(self.env.href.roadmap())
        else:
            self.req.redirect(self.env.href.milestone(id))

    def update_milestone(self, id, name, date, descr):
        self.perm.assert_permission(perm.MILESTONE_MODIFY)
        cursor = self.db.cursor()
        self.env.log.debug("Updating milestone '%s'" % id)
        if self.args.has_key('save'):
            self.env.log.info('Updating milestone field of all tickets '
                              'associated with milestone %s' % id)
            cursor.execute ('UPDATE ticket SET milestone = %s '
                            'WHERE milestone = %s', name, id)
            cursor.execute("UPDATE milestone SET name = %s, time = %d, "
                           "descr = %s WHERE name = %s",
                           name, date, descr, id)
            self.db.commit()
            self.req.redirect(self.env.href.milestone(name))
        else:
            self.req.redirect(self.env.href.milestone(id))

    def get_components(self):
        cursor = self.db.cursor ()
        cursor.execute("SELECT name, owner FROM component ORDER BY name")
        components = []
        while 1:
            row = cursor.fetchone()
            if not row:
                break
            component = ( row['name'], row['owner'] )
            components.append(component)
        return components

    def get_milestone(self, name):
        cursor = self.db.cursor()
        cursor.execute("SELECT name, time, descr FROM milestone "
                       "WHERE name = %s ORDER BY time, name", name)
        row = cursor.fetchone()
        cursor.close()
        if not row:
            raise TracError('Milestone %s does not exist.' % name,
                            'Invalid Milestone Number')
        milestone = { 'name': row['name'] }
        descr = row['descr']
        if descr:
            milestone['descr_source'] = descr
            milestone['descr'] = wiki_to_html(descr, self.req.hdf, self.env)
        t = row['time'] and int(row['time'])
        if t > 0:
            milestone['date'] = time.strftime('%x', time.localtime(t))
        return milestone

    def render(self):
        action = self.args.get('action', 'view')
        id = self.args.get('id', -1)

        if action == 'new':
            self.perm.assert_permission(perm.MILESTONE_CREATE)
            self.render_editor(-1)
        elif action == 'edit':
            self.perm.assert_permission(perm.MILESTONE_MODIFY)
            self.render_editor(id)
        elif action == 'delete':
            self.perm.assert_permission(perm.MILESTONE_DELETE)
            self.render_confirm(id)
        elif action == 'commit_changes':
            self.save_milestone(id)
        elif action == 'confirm_delete':
            self.delete_milestone(id)
        else:
            self.render_view(id)

    def render_confirm(self, id):
        milestone = self.get_milestone(id)
        self.req.hdf.setValue('title', 'Milestone %s' % milestone['name'])
        self.req.hdf.setValue('milestone.mode', 'delete')
        add_dict_to_hdf(milestone, self.req.hdf, 'milestone')

    def render_editor(self, id):
        if id == -1:
            milestone = { 'name': '', 'date': '', 'descr': '' }
            self.req.hdf.setValue('title', 'New Milestone')
            self.req.hdf.setValue('milestone.mode', 'new')
        else:
            milestone = self.get_milestone(id)
            self.req.hdf.setValue('title', 'Milestone %s' % milestone['name'])
            self.req.hdf.setValue('milestone.mode', 'edit')
        add_dict_to_hdf(milestone, self.req.hdf, 'milestone')

    def render_view(self, id):
        self.perm.assert_permission(perm.MILESTONE_VIEW)

        if self.perm.has_permission(perm.MILESTONE_DELETE):
            self.req.hdf.setValue('milestone.href.delete',
                                   self.env.href.milestone(id, 'delete'))
        if self.perm.has_permission(perm.MILESTONE_MODIFY):
            self.req.hdf.setValue('milestone.href.edit',
                                   self.env.href.milestone(id, 'edit'))

        milestone = self.get_milestone(id)
        self.req.hdf.setValue('title', 'Milestone %s' % milestone['name'])
        add_dict_to_hdf(milestone, self.req.hdf, 'milestone')

        tickets = get_tickets_for_milestone(self.db, id)
        stats = calc_ticket_stats(tickets)
        add_dict_to_hdf(stats, self.req.hdf, 'milestone.stats')

        components = self.get_components()
        comp_no = 0
        for component, owner in components:
            prefix = 'milestone.stats.components.%s' % comp_no
            self.req.hdf.setValue('%s.name' % prefix, component)
            comp_tickets = [t for t in tickets if t['component'] == component]
            percent_total = 0
            if len(tickets) > 0:
                percent_total = float(len(comp_tickets)) / float(len(tickets))
            self.req.hdf.setValue('%s.percent_total' % prefix,
                                  str(percent_total * 100))
            stats = calc_ticket_stats(comp_tickets)
            add_dict_to_hdf(stats, self.req.hdf, prefix)
            comp_no += 1

