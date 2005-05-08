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

from trac import Milestone, perm, __version__
from trac.core import *
from trac.util import enum, escape, pretty_timedelta, CRLF
from trac.Ticket import Ticket
from trac.web.chrome import add_link, INavigationContributor
from trac.web.main import IRequestHandler
from trac.WikiFormatter import wiki_to_html

import re
from time import localtime, strftime, time


class RoadmapModule(Component):

    implements(INavigationContributor, IRequestHandler)

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'roadmap'

    def get_navigation_items(self, req):
        if not req.perm.has_permission(perm.ROADMAP_VIEW):
            return
        yield 'mainnav', 'roadmap', '<a href="%s" accesskey="3">Roadmap</a>' \
                                    % self.env.href.roadmap()

    # IRequestHandler methods

    def match_request(self, req):
        return req.path_info == '/roadmap'

    def process_request(self, req):
        req.perm.assert_permission(perm.ROADMAP_VIEW)
        req.hdf['title'] = 'Roadmap'

        showall = req.args.get('show') == 'all'
        req.hdf['roadmap.showall'] = showall

        db = self.env.get_db_cnx()
        milestones = []
        for idx,milestone in enum(Milestone.Milestone.select(self.env, showall)):
            hdf = Milestone.milestone_to_hdf(self.env, db, req, milestone)
            milestones.append(hdf)
        req.hdf['roadmap.milestones'] = milestones

        for idx,milestone in enum(milestones):
            tickets = Milestone.get_tickets_for_milestone(self.env, db,
                                                          milestone['name'],
                                                          'owner')
            stats = Milestone.calc_ticket_stats(tickets)
            req.hdf['roadmap.milestones.%s.stats' % idx] = stats
            queries = Milestone.get_query_links(self.env, milestone['name'])
            req.hdf['roadmap.milestones.%s.queries' % idx] = queries
            milestone['tickets'] = tickets # for the iCalendar view

        if req.args.get('format') == 'ics':
            self.render_ics(req, db, milestones)
            return

        # FIXME should use the 'webcal:' scheme, probably
        username = None
        if req.authname and req.authname != 'anonymous':
            username = req.authname
        icshref = self.env.href.roadmap(show=req.args.get('show'),
                                        user=username, format='ics')
        add_link(req, 'alternate', icshref, 'iCalendar', 'text/calendar', 'ics')

        return 'roadmap.cs', None

    # Internal methods

    def render_ics(self, req, db, milestones):
        req.send_response(200)
        req.send_header('Content-Type', 'text/plain;charset=utf-8')
        req.end_headers()

        priority_mapping = {'highest': '1', 'high': '3', 'normal': '5',
                            'low': '7', 'lowest': '9'}

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
        write_prop('X-WR-CALNAME',
                   self.config.get('project', 'name') + ' - Roadmap')
        for milestone in milestones:
            uid = '<%s/milestone/%s@%s>' % (req.cgi_location,
                                            milestone['name'], host)
            if milestone.has_key('due'):
                write_prop('BEGIN', 'VEVENT')
                write_prop('UID', uid)
                write_date('DTSTART', localtime(milestone['due']))
                write_prop('SUMMARY', 'Milestone %s' % milestone['name'])
                write_prop('URL', req.base_url + '/milestone/' + milestone['name'])
                if milestone.has_key('description'):
                    write_prop('DESCRIPTION', milestone['description_text'])
                write_prop('END', 'VEVENT')
            for ticket in [ticket for ticket in milestone['tickets']
                          if ticket['owner'] == user]:
                ticket = Ticket(db, ticket['id'])
                write_prop('BEGIN', 'VTODO')
                if milestone.has_key('date'):
                    write_prop('RELATED-TO', uid)
                    write_date('DUE', localtime(milestone['due']))
                write_prop('SUMMARY', 'Ticket #%i: %s' % (ticket['id'],
                                                          ticket['summary']))
                write_prop('URL', req.base_url + '/ticket/' + str(ticket['id']))
                write_prop('DESCRIPTION', ticket['description'])
                write_prop('PRIORITY', priority_mapping[ticket['priority']])
                write_prop('STATUS', get_status(ticket))
                if ticket['status'] == 'closed':
                    cursor = db.cursor()
                    cursor.execute("SELECT time FROM ticket_change "
                                   "WHERE ticket=%s AND field='status' "
                                   "ORDER BY time desc LIMIT 1", (ticket['id'],))
                    row = cursor.fetchone()
                    if row: write_utctime('COMPLETED', localtime(row['time']))
                write_prop('END', 'VTODO')
        write_prop('END', 'VCALENDAR')
