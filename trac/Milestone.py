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

from util import *
from Module import Module
import perm

import time

def get_tickets_for_milestone(db, milestone):
    cursor = db.cursor ()
    cursor.execute("SELECT id, status, component FROM ticket "
                   "WHERE milestone = '%s'" % milestone)
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
        cursor.execute("SELECT name, time FROM milestone "
                       "WHERE name = '%s' ORDER BY time, name" % name)
        row = cursor.fetchone()
        cursor.close()
        if not row:
            raise TracError('Milestone %s does not exist.' % id,
                            'Invalid Milestone Number')
        milestone = { 'name': row['name'] }
        t = int(row['time'])
        if t > 0:
            milestone['date'] = time.strftime('%x', time.localtime(t))
        return milestone

    def render(self):
        action = self.args.get('action', 'view')

        if not self.args.has_key('id'):
            self.req.redirect(self.env.href.roadmap())
        id = self.args.get('id')

        self.perm.assert_permission(perm.MILESTONE_VIEW)

        milestone = self.get_milestone(id)
        self.req.hdf.setValue('title', '%s (milestone)' % milestone['name'])
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

