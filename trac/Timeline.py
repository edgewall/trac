# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2003, 2004 Edgewall Software
# Copyright (C) 2003, 2004 Jonas Borgström <jonas@edgewall.com>
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

from util import *
from Module import Module
from Wiki import wiki_to_oneliner
import perm

import time
import string

class Timeline (Module):
    template_name = 'timeline.cs'
    template_rss_name = 'timeline_rss.cs'

    def get_info (self, start, stop, maxrows, tickets,
                  changeset, wiki, milestone):
        cursor = self.db.cursor ()

        if tickets == changeset == wiki == 0:
            return []

        CHANGESET = 1
        NEW_TICKET = 2
        CLOSED_TICKET = 3
        REOPENED_TICKET = 4
        WIKI = 5
        MILESTONE = 6
        
        q = []
        if changeset:
            q.append("SELECT time, rev AS idata, '' AS tdata, 1 AS type, message, author "
                        "FROM revision WHERE time>=%s AND time<=%s" %
                     (start, stop))
        if tickets:
            q.append("SELECT time, id AS idata, '' AS tdata, 2 AS type, "
                     "summary AS message, reporter AS author "
                     "FROM ticket WHERE time>=%s AND time<=%s" %
                     (start, stop))
            q.append("SELECT time, ticket AS idata, '' AS tdata, 3 AS type, "
                        "'' AS message, author "
                        "FROM ticket_change WHERE field='status' "
                        "AND newvalue='closed' AND time>=%s AND time<=%s" %
                     (start, stop))
            q.append("SELECT time, ticket AS idata, '' AS tdata, 4 AS type, "
                     "'' AS message, author "
                     "FROM ticket_change WHERE field='status' "
                     "AND newvalue='reopened' AND time>=%s AND time<=%s" %
                     (start, stop))
        if wiki:
            q.append("SELECT time, -1 AS idata, name AS tdata, 5 AS type, "
                     "'' AS message, author "
                        "FROM wiki WHERE time>=%s AND time<=%s" %
                     (start, stop))
            pass

	if milestone:
	    q.append("SELECT time, -1 AS idata, name AS tdata, 6 AS type, "
	             "'' AS message, '' AS author " 
		     "FROM milestone WHERE time>=%s AND time<=%s" %
		     (start, stop))

        q_str = string.join(q, ' UNION ALL ')
        q_str += ' ORDER BY time DESC'
        if maxrows:
            q_str += ' LIMIT %d' % maxrows

        cursor.execute(q_str)

        # Make the data more HDF-friendly
        info = []
        while 1:
            row = cursor.fetchone()
            if not row:
                break
            t = time.localtime(int(row['time']))
            gmt = time.gmtime(int(row['time']))
            item = {'time': time.strftime('%X', t),
                    'date': time.strftime('%x', t),
                    'datetime': time.strftime('%a, %d %b %Y %H:%M:%S GMT', gmt),
                    'idata': int(row['idata']),
                    'tdata': row['tdata'],
                    'type': int(row['type']),
                    'message': row['message'],
                    'author': row['author']}

            if item['type'] == CHANGESET:
                self.env.log.debug ('type: %s' % item['type'])
                item['changeset_href'] = self.env.href.changeset(item['idata'])
                item['shortmsg'] = wiki_to_oneliner(shorten_line(item['message']),
                                                    self.req.hdf, self.env)
                item['message'] = wiki_to_oneliner(item['message'],
                                                   self.req.hdf, self.env)
            elif item['type'] == WIKI:
		item['wiki_href'] = self.env.href.wiki(row['tdata'])
	    elif item['type'] == MILESTONE:
		item['shortmsg'] = ''
	    else:
		item['ticket_href'] = self.env.href.ticket(item['idata'])
		msg = item['message']
		shortmsg = shorten_line(msg)
		item['message'] = wiki_to_oneliner(item['message'],
                                                   self.req.hdf, self.env)
		item['shortmsg'] = wiki_to_oneliner(shorten_line(item['message']),
                                                    self.req.hdf, self.env)

            info.append(item)
        return info
        
    def render (self):
        self.perm.assert_permission(perm.TIMELINE_VIEW)
        
        _from = self.args.get('from', '')
        _daysback = self.args.get('daysback', '')

        try:
            _from = time.mktime(time.strptime(_from, '%x')) + 86399
            pass
        except:
            _from = time.time()
        try:
            daysback = int(_daysback)
            assert daysback >= 0
        except:
            daysback = 90
        self.req.hdf.setValue('timeline.from',
                              time.strftime('%x', time.localtime(_from)))
        self.req.hdf.setValue('timeline.daysback', str(daysback))

        stop  = _from
        start = stop - daysback * 86400
        maxrows = int(self.args.get('max', 0))

        wiki = self.args.has_key('wiki') 
        ticket = self.args.has_key('ticket')
        changeset = self.args.has_key('changeset')
        milestone = self.args.has_key('milestone')
        if not (wiki or ticket or changeset or milestone):
            wiki = ticket = changeset = milestone = 1
           
        if wiki:
            self.req.hdf.setValue('timeline.wiki', 'checked')
        if ticket:
            self.req.hdf.setValue('timeline.ticket', 'checked')
        if changeset:
            self.req.hdf.setValue('timeline.changeset', 'checked')
        if milestone:
            self.req.hdf.setValue('timeline.milestone', 'checked')
        
        info = self.get_info (start, stop, maxrows, ticket,
                              changeset, wiki, milestone)
        add_dictlist_to_hdf(info, self.req.hdf, 'timeline.items')
        self.req.hdf.setValue('title', 'Timeline')


    def display_rss(self):
        self.req.display(self.template_rss_name, 'text/xml')
