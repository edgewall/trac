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

    MAX_MESSAGE_LEN = 75

    def get_info (self, start, stop, maxrows, tickets,
                  changeset, wiki, milestone):
        cursor = self.db.cursor ()

        if tickets == changeset == wiki == 0:
            return []

        # 1: change set
        # 2: new tickets
        # 3: closed tickets
        # 4: reopened tickets
        # 5: wiki
        # 6: milestone
        
        q = []
        if changeset:
            q.append("SELECT time, rev AS data, 1 AS type, message, author "
                        "FROM revision WHERE time>=%s AND time<=%s" %
                     (start, stop))
        if tickets:
            q.append("SELECT time, id AS data, 2 AS type, "
                     "summary AS message, reporter AS author "
                     "FROM ticket WHERE time>=%s AND time<=%s" %
                     (start, stop))
            q.append("SELECT time, ticket AS data, 3 AS type, "
                        "'' AS message, author "
                        "FROM ticket_change WHERE field='status' "
                        "AND newvalue='closed' AND time>=%s AND time<=%s" %
                     (start, stop))
            q.append("SELECT time, ticket AS data, 4 AS type, "
                     "'' AS message, author "
                     "FROM ticket_change WHERE field='status' "
                     "AND newvalue='reopened' AND time>=%s AND time<=%s" %
                     (start, stop))
        if wiki:
            q.append("SELECT time, name AS data, 5 AS type, "
                     "'' AS message, author "
                        "FROM wiki WHERE time>=%s AND time<=%s" %
                     (start, stop))
            pass

	if milestone:
	    q.append("SELECT time, name AS data, 6 AS type, "
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
                    'data': row['data'],
                    'type': int(row['type']),
                    'message': row['message'],
                    'author': row['author']}
            if item['type'] == 1:
                item['changeset_href'] = self.href.changeset(int(row['data']))
                # Just recode this to iso8859-15 until we have propper unicode
                # support
                msg = utf8_to_iso(item['message'])
                shortmsg = shorten_line(msg)
                item['shortmsg'] = wiki_to_oneliner(shortmsg,
                                                    self.req.hdf, self.href)
                item['message'] = wiki_to_oneliner(msg,
                                                   self.req.hdf, self.href)
            elif item['type'] == 5:
		item['wiki_href'] = self.href.wiki(row['data'])
	    elif item['type'] == 6:
		item['shortmsg'] = ''
	    else:
		item['ticket_href'] = self.href.ticket(int(row['data']))
		msg = item['message']
		shortmsg = shorten_line(msg)
		item['message'] = wiki_to_oneliner(msg, self.req.hdf,
                                                   self.href)
		item['shortmsg'] = wiki_to_oneliner(shortmsg, self.req.hdf,
                                                    self.href)

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
