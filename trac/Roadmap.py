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

import perm
import Milestone
from util import add_to_hdf, TracError
from Module import Module
from Wiki import wiki_to_html


class Roadmap(Module):
    template_name = 'roadmap.cs'

    def render (self):
        self.perm.assert_permission(perm.ROADMAP_VIEW)
        self.req.hdf.setValue('title', 'Roadmap')

        if self.perm.has_permission(perm.MILESTONE_CREATE):
            self.req.hdf.setValue('roadmap.href.newmilestone',
                                   self.env.href.milestone(None, 'new'))

        cursor = self.db.cursor()
        cursor.execute("SELECT name, time, descr FROM milestone "
                       "WHERE name != '' "
                       "AND (time IS NULL OR time = 0 OR time > %d) "
                       "ORDER BY time DESC, name" % time.time())
        milestones = []
        while 1:
            row = cursor.fetchone()
            if not row:
                break
            milestone = {
                'name': row['name'],
                'href': self.env.href.milestone(row['name']),
            }
            descr = row['descr']
            if descr:
                milestone['descr'] = wiki_to_html(descr, self.req.hdf, self.env,self.db)
            t = row['time'] and int(row['time'])
            if t > 0:
                milestone['date'] = time.strftime('%x', time.localtime(t))
                milestones.insert(0, milestone)
            else:
                milestones.append(milestone)
        cursor.close()
        add_to_hdf(milestones, self.req.hdf, 'roadmap.milestones')

        milestone_no = 0
        for milestone in milestones:
            tickets = Milestone.get_tickets_for_milestone(self.env, self.db,
                                                          milestone['name'])
            stats = Milestone.calc_ticket_stats(tickets)
            add_to_hdf(stats, self.req.hdf,
                       'roadmap.milestones.%d.stats' % int(milestone_no))
            queries = Milestone.get_query_links(self.env, milestone['name'])
            add_to_hdf(queries, self.req.hdf,
                       'roadmap.milestones.%d.queries' % int(milestone_no))
            milestone_no += 1
