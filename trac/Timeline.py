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

import time
import string
import urllib
import sys

import perm
import util
from Module import Module
from Wiki import wiki_to_oneliner,wiki_to_html


class Timeline (Module):
    template_name = 'timeline.cs'
    template_rss_name = 'timeline_rss.cs'

    def get_info (self, start, stop, maxrows, tickets,
                  changeset, wiki, milestone):
        cursor = self.db.cursor ()

        tickets = tickets and self.perm.has_permission(perm.TICKET_VIEW)
        changeset = changeset and self.perm.has_permission(perm.CHANGESET_VIEW)
        wiki = wiki and self.perm.has_permission(perm.WIKI_VIEW)
        milestone = milestone and self.perm.has_permission(perm.MILESTONE_VIEW)

        if tickets == changeset == wiki == milestone == 0:
            return []

        CHANGESET = 1
        NEW_TICKET = 2
        CLOSED_TICKET = 3
        REOPENED_TICKET = 4
        WIKI = 5
        MILESTONE = 6

        q = []
        if changeset:
            q.append("SELECT time, rev AS idata, '' AS tdata, 1 AS type, "
                     " message, author "
                     "FROM revision WHERE time>=%s AND time<=%s" %
                     (start, stop))
        if tickets:
            q.append("SELECT time, id AS idata, '' AS tdata, 2 AS type, "
                     "summary AS message, reporter AS author "
                     "FROM ticket WHERE time>=%s AND time<=%s" %
                     (start, stop))
            q.append("SELECT time, ticket AS idata, '' AS tdata, 4 AS type, "
                     "'' AS message, author "
                     "FROM ticket_change WHERE field='status' "
                     "AND newvalue='reopened' AND time>=%s AND time<=%s" %
                     (start, stop))
            q.append("SELECT t1.time AS time, t1.ticket AS idata,"
                     "       t2.newvalue AS tdata, 3 AS type,"
                     "       t3.newvalue AS message, t1.author AS author"
                     " FROM ticket_change t1"
                     "   INNER JOIN ticket_change t2 ON t1.ticket = t2.ticket"
                     "     AND t1.time = t2.time"
                     "   LEFT OUTER JOIN ticket_change t3 ON t1.time = t3.time"
                     "     AND t1.ticket = t3.ticket AND t3.field = 'comment'"
                     " WHERE t1.field = 'status' AND t1.newvalue = 'closed'"
                     "   AND t2.field = 'resolution'"
                     "   AND t1.time >= %s AND t1.time <= %s" % (start,stop))
        if wiki:
            q.append("SELECT time, -1 AS idata, name AS tdata, 5 AS type, "
                     "comment AS message, author "
                        "FROM wiki WHERE time>=%s AND time<=%s" %
                     (start, stop))
        if milestone:
            q.append("SELECT time, -1 AS idata, '' AS tdata, 6 AS type, "
                     "name AS message, '' AS author " 
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

            if len(info) == 0:
                self.req.check_modified(int(row['time']))

            t = time.localtime(int(row['time']))
            gmt = time.gmtime(int(row['time']))
            item = {'time': time.strftime('%H:%M', t),
                    'date': time.strftime('%x', t),
                    'datetime': time.strftime('%a, %d %b %Y %H:%M:%S GMT', gmt),
                    'idata': int(row['idata']),
                    'tdata': row['tdata'],
                    'type': int(row['type']),
                    'message': row['message'] or '',
                    'author': util.escape(row['author'] or 'anonymous')
                    }

            if item['type'] == CHANGESET:
                item['href'] = self.env.href.changeset(item['idata'])
                msg = item['message']
                item['shortmsg'] = util.escape(util.shorten_line(msg))
                item['msg_nowiki'] = util.escape(msg)
                item['msg_escwiki'] = util.escape(wiki_to_html(msg,
                                                               self.req.hdf,
                                                               self.env,
                                                               self.db,
                                                               absurls=1))
                item['message'] = wiki_to_oneliner(msg, self.req.hdf,
                                                   self.env, self.db,absurls=1)
                try:
                    max_node = int(self.env.get_config('timeline', 'changeset_show_files', 0))
                except ValueError, e:
                    self.env.log.warning("Invalid 'changeset_show_files' value, "
                                         "please edit trac.ini : %s" % e)
                    max_node = 0
                    
                if max_node != 0:
                    cursor_node = self.db.cursor ()
                    cursor_node.execute("SELECT name, change "
                                        "FROM node_change WHERE rev=%d" % item['idata'])
                    node_list = ''
                    node_data = ''
                    node_count = 0;
                    while 1:
                        row_node = cursor_node.fetchone()
                        if not row_node:
                            break
                        if node_count != 0:
                            node_list += ', '
                        if (max_node != -1) and (node_count >= max_node):
                            node_list += '...'
                            break
                        if row_node['change'] == 'A':
                            node_data = '<span class="diff-add">' + row_node['name'] + "</span>"
                        elif row_node['change'] == 'M':
                            node_data = '<span class="diff-mod">' + row_node['name'] + "</span>"
                        elif row_node['change'] == 'D':
                            node_data = '<span class="diff-rem">' + row_node['name'] + "</span>"
                        node_list += node_data
                        node_count += 1
                    item['node_list'] = node_list + ': '

            elif item['type'] == WIKI:
                item['href'] = self.env.href.wiki(row['tdata'])
                item['message'] = wiki_to_oneliner(util.shorten_line(item['message']),
                                                   self.req.hdf, self.env, self.db, absurls=1)
            elif item['type'] == MILESTONE:
                item['href'] = self.env.href.milestone(item['message'])
                item['message'] = util.escape(item['message'])
            else:               # TICKET
                item['href'] = self.env.href.ticket(item['idata'])
                msg = item['message']
                item['shortmsg'] = util.escape(util.shorten_line(msg))
                item['message'] = wiki_to_oneliner(
                    util.shorten_line(item['message']),
                    self.req.hdf, self.env, self.db, absurls=1)
                item['msg_escwiki'] = util.escape(wiki_to_html(msg,
                                                               self.req.hdf,
                                                               self.env,
                                                               self.db,
                                                               absurls=1))
            # Kludges for RSS
            item['author.rss'] = item['author']
            if item['author.rss'].find('@') == -1:
                item['author.rss'] = ''
            item['message.rss'] = util.escape(item['message'] or '')

            info.append(item)
        return info

    def render (self):
        self.perm.assert_permission(perm.TIMELINE_VIEW)

        self.add_link('alternate', '?daysback=90&max=50&format=rss',
            'RSS Feed', 'application/rss+xml', 'rss')

        _from = self.args.get('from', '')
        _daysback = self.args.get('daysback', '')

        # Parse the from date and adjust the timestamp to the last second of the day
        t = time.localtime()
        if _from:
            try:
                t = time.strptime(_from, '%x')
            except:
                pass
        _from = time.mktime((t[0], t[1], t[2], 23, 59, 59, t[6], t[7], t[8]))
        try:
            daysback = int(_daysback)
            assert daysback >= 0
        except:
            daysback = 30
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

        info = self.get_info (start, stop, maxrows, ticket,
                              changeset, wiki, milestone)
        util.add_to_hdf(info, self.req.hdf, 'timeline.items')

        self.req.hdf.setValue('title', 'Timeline')
        if wiki:
            self.req.hdf.setValue('timeline.wiki', 'checked')
        if ticket:
            self.req.hdf.setValue('timeline.ticket', 'checked')
        if changeset:
            self.req.hdf.setValue('timeline.changeset', 'checked')
        if milestone:
            self.req.hdf.setValue('timeline.milestone', 'checked')

    def display_rss(self):
        base_url = self.env.get_config('trac', 'base_url', '')         
        self.req.hdf.setValue('baseurl', base_url)
        self.req.display(self.template_rss_name, 'text/xml')
