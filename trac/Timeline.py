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
from Wiki import wiki_to_oneliner, wiki_to_html

AVAILABLE_FILTERS = ('wiki', 'ticket', 'changeset', 'milestone')


class Timeline (Module):
    template_name = 'timeline.cs'
    template_rss_name = 'timeline_rss.cs'

    def get_info(self, req, start, stop, maxrows,
                 filters=('tickets', 'changeset', 'wiki', 'milestone'),
                 absurls=0):
        perm_map = {'tickets': perm.TICKET_VIEW, 'changeset': perm.CHANGESET_VIEW,
                    'wiki': perm.WIKI_VIEW, 'milestone': perm.MILESTONE_VIEW}
        for k,v in perm_map.items():
            if not self.perm.has_permission(v): filters.remove(k)
        if not filters:
            return []

        sql, params = [], []
        if 'changeset' in filters:
            sql.append("SELECT time,rev,'','changeset',message,author"
                       " FROM revision WHERE time>=%s AND time<=%s")
            params += (start, stop)
        if 'ticket' in filters:
            sql.append("SELECT time,id,'','newticket',summary,reporter"
                       " FROM ticket WHERE time>=%s AND time<=%s")
            params += (start, stop)
            sql.append("SELECT time,ticket,'','closedticket','',author "
                       "FROM ticket_change WHERE field='status' "
                       "AND newvalue='reopened' AND time>=%s AND time<=%s")
            params += (start, stop)
            sql.append("SELECT t1.time,t1.ticket,t2.newvalue,'reopenedticket',"
                       "t3.newvalue,t1.author"
                       " FROM ticket_change t1"
                       "   INNER JOIN ticket_change t2 ON t1.ticket = t2.ticket"
                       "     AND t1.time = t2.time"
                       "   LEFT OUTER JOIN ticket_change t3 ON t1.time = t3.time"
                       "     AND t1.ticket = t3.ticket AND t3.field = 'comment'"
                       " WHERE t1.field = 'status' AND t1.newvalue = 'closed'"
                       "   AND t2.field = 'resolution'"
                       "   AND t1.time >= %s AND t1.time <= %s")
            params += (start,stop)
        if 'wiki' in filters:
            sql.append("SELECT time,-1,name,'wiki',comment,author"
                       " FROM wiki WHERE time>=%s AND time<=%s")
            params += (start, stop)
        if 'milestone' in filters:
            sql.append("SELECT completed,-1,'','milestone',name,''" 
                       " FROM milestone WHERE completed>=%s AND completed<=%s")
            params += (start, stop)

        sql = ' UNION ALL '.join(sql) + ' ORDER BY time DESC'
        if maxrows:
            sql += ' LIMIT %d'
            params += (maxrows,)

        cursor = self.db.cursor()
        cursor.execute(sql, params)

        href = self.env.href
        if absurls:
            href = self.env.abs_href

        # Make the data more HDF-friendly
        info = []
        while 1:
            row = cursor.fetchone()
            if not row:
                break

            if len(info) == 0:
                req.check_modified(int(row[0]))

            t = time.localtime(int(row[0]))
            gmt = time.gmtime(int(row[0]))
            item = {
                'time': time.strftime('%H:%M', t),
                'date': time.strftime('%x', t),
                'datetime': time.strftime('%a, %d %b %Y %H:%M:%S GMT', gmt),
                'idata': int(row[1]),
                'tdata': util.escape(row[2]),
                'type': row[3],
                'message': row[4] or '',
                'author': util.escape(row[5] or 'anonymous')
            }

            if item['type'] == 'changeset':
                item['href'] = util.escape(href.changeset(item['idata']))
                msg = item['message']
                item['shortmsg'] = util.escape(util.shorten_line(msg))
                item['msg_nowiki'] = util.escape(msg)
                item['msg_escwiki'] = util.escape(wiki_to_html(msg,
                                                               req.hdf,
                                                               self.env,
                                                               self.db,
                                                               absurls=absurls))
                item['message'] = wiki_to_oneliner(msg, self.env, self.db,
                                                   absurls=absurls)
                try:
                    max_node = int(self.env.get_config('timeline', 'changeset_show_files', 0))
                except ValueError, e:
                    self.env.log.warning("Invalid 'changeset_show_files' value, "
                                         "please edit trac.ini : %s" % e)
                    max_node = 0
                    
                if max_node != 0:
                    cursor_node = self.db.cursor()
                    cursor_node.execute("SELECT name, change "
                                        "FROM node_change WHERE rev=%s", item['idata'])
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

            elif item['type'] == 'wiki':
                item['href'] = util.escape(href.wiki(item['tdata']))
                item['message'] = wiki_to_oneliner(util.shorten_line(item['message']),
                                                   self.env, self.db, absurls=absurls)
                item['msg_escwiki'] = util.escape(item['message'])
            elif item['type'] == 'milestone':
                item['href'] = util.escape(href.milestone(item['message']))
                item['message'] = util.escape(item['message'])
            else: # newticket, closedticket, reopenedticket
                item['href'] = util.escape(href.ticket(item['idata']))
                msg = item['message']
                item['shortmsg'] = util.escape(util.shorten_line(msg))
                item['message'] = wiki_to_oneliner(util.shorten_line(item['message']),
                                                   self.env, self.db, absurls=absurls)
                item['msg_escwiki'] = util.escape(wiki_to_html(msg,
                                                               req.hdf,
                                                               self.env,
                                                               self.db,
                                                               absurls=absurls))
            # Kludges for RSS
            item['author.rss'] = item['author']
            if item['author.rss'].find('@') == -1:
                item['author.rss'] = ''
            item['message.rss'] = util.escape(item['message'] or '')

            info.append(item)
        return info

    def render(self, req):
        self.perm.assert_permission(perm.TIMELINE_VIEW)

        _from = req.args.get('from', '')
        _daysback = req.args.get('daysback', '')

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
        req.hdf.setValue('timeline.from',
                              time.strftime('%x', time.localtime(_from)))
        req.hdf.setValue('timeline.daysback', str(daysback))

        stop  = _from
        start = stop - (daysback + 1) * 86400
        maxrows = int(req.args.get('max', 0))

        filters = [k for k in AVAILABLE_FILTERS if k in req.args]
        if not filters:
            filters = AVAILABLE_FILTERS[:]

        self.add_link('alternate', '?daysback=90&max=50&%s&format=rss' \
                      % '&'.join(['%s=on' % k for k in filters]),
                      'RSS Feed', 'application/rss+xml', 'rss')

        req.hdf.setValue('title', 'Timeline')
        for f in filters:
            req.hdf.setValue('timeline.%s' % f, 'checked')

        absurls = 0
        if req.args.get('format') == 'rss':
            absurls = 1
        info = self.get_info(req, start, stop, maxrows, filters,
                             absurls=absurls)
        util.add_to_hdf(info, req.hdf, 'timeline.items')

    def display_rss(self, req):
        base_url = self.env.get_config('trac', 'base_url', '')
        req.hdf.setValue('baseurl', base_url)
        req.display(self.template_rss_name, 'text/xml')
