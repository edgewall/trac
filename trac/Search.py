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

import string
import time
import re

from util import *
from Module import Module
import perm

class Search(Module):
    template_name = 'search.cs'

    RESULTS_PER_PAGE = 10

    def query_to_sql(self, query, name):
        query = query.replace('\'', '\'\'\'\'')
        keywords = query.split(' ')
        # The line below doesn't work in python2.1
        # x = map(lambda x: name + ' LIKE \'%' + x + '%\'', keywords)
        x = []
        for keyword in keywords:
            x.append(name + ' LIKE \'%' + keyword + '%\'')
        return string.join(x, ' AND ')

    def shorten_result(self, text='', keywords=[], maxlen=240, fuzz=60):
        if not text: text = ''
        text_low = text.lower()
        beg = -1
        for k in keywords:
            i = text_low.find(k.lower())
            if (i > -1 and i < beg) or beg == -1:
                beg = i
        excerpt_beg = 0
        if beg > fuzz:
            for sep in ".:;= ":
                eb = text.find(sep, beg - fuzz, beg - 1)
                if eb > -1:
                    eb += 1
                    break
            else:
                eb = beg - fuzz
            excerpt_beg = eb
        if excerpt_beg < 0: excerpt_beg = 0
        msg = text[excerpt_beg:beg+maxlen]
        if beg > fuzz:
            msg = '... ' + msg
        if beg < len(text)-maxlen:
            msg = msg + ' ...'
        return msg
    
    def perform_query (self, query, changeset, tickets, wiki, page=0):
        keywords = query.split(' ')

        if len(keywords) == 1:
            kwd = keywords[0]
            redir = None
            # Prepending a '!' disables quickjump feature
            if kwd[0] == '!':
                keywords[0] = kwd[1:]
                query = query[1:]
                self.req.hdf.setValue('search.q', query)
            # Ticket quickjump
            elif kwd[0] == '#' and kwd[1:].isdigit():
                redir = self.href.ticket(kwd[1:])
            # Changeset quickjump
            elif kwd[0] == '[' and kwd[-1] == ']' and kwd[1:-1].isdigit():
                redir = self.href.changeset(kwd[1:-1])
            # Report quickjump
            elif kwd[0] == '{' and kwd[-1] == '}' and kwd[1:-1].isdigit():
                redir = self.href.report(kwd[1:-1])
            elif kwd[0].isupper() and kwd[1].islower():
                r = "((^|(?<=[^A-Za-z]))[!]?[A-Z][a-z/]+(?:[A-Z][a-z/]+)+)"
                if re.match (r, kwd):
                    redir = self.href.wiki(kwd)
            if redir:
                self.req.hdf.setValue('search.q', '')
                self.req.redirect(redir)

        cursor = self.db.cursor ()

        q = []
        if changeset:
            q.append('SELECT 1 as type, message AS title, message, author, '
                     ' "" AS keywords, rev AS data, time,0 AS ver'
                     ' FROM revision WHERE %s' %
                     self.query_to_sql(query, 'message'))
        if tickets:
            q.append('SELECT 2 as type, summary AS title, '
                     ' description AS message, reporter AS author, keywords,'
                     ' id AS data, time,0 AS ver'
                     ' FROM ticket WHERE %s OR %s OR %s' %
                      (self.query_to_sql(query, 'summary'),
                       self.query_to_sql(query, 'keywords'),
                       self.query_to_sql(query, 'description')))
        if wiki:
            q.append('SELECT 3 as type, text AS title, text AS message,'
                     ' author, '' AS keywords, w1.name AS data, time,'
                     ' w1.version as ver'
                     ' FROM wiki w1, '
                     ' (SELECT name,max(version) AS ver '
                     '    FROM wiki GROUP BY name) w2'
                     ' WHERE w1.version = w2.ver AND w1.name = w2.name  AND'
                     ' (%s OR %s) ' %
                     (self.query_to_sql(query, 'w1.name'),
                      self.query_to_sql(query, 'w1.text')))

        if not q: return []

        q_str = string.join(q, ' UNION ALL ')
        q_str += ' ORDER BY time DESC LIMIT %d OFFSET %d' % \
                 (self.RESULTS_PER_PAGE, self.RESULTS_PER_PAGE * page)
        cursor.execute(q_str)

        # Make the data more HDF-friendly
        info = []
        while 1:
            row = cursor.fetchone()
            if not row:
                break
            msg = row['message']
            t = time.localtime(int(row['time']))
            item = {'type': int(row['type']),
                    'keywords': row['keywords'] or '',
                    'data': row['data'],
                    'title': row['title'],
                    'datetime' : time.strftime('%c', t),
                    'author': row['author']}
            if item['type'] == 1:
                item['changeset_href'] = self.href.changeset(int(row['data']))
                msg = utf8_to_iso(msg)
            elif item['type'] == 2:
                item['ticket_href'] = self.href.ticket(int(row['data']))
            elif item['type'] == 3:
                item['wiki_href'] = self.href.wiki(row['data'])

            shortmsg = shorten_line(msg)
            item['shortmsg'] = shortmsg
            item['message'] = escape(self.shorten_result(msg, keywords))
            info.append(item)
        return info
        
    def render (self):
        self.perm.assert_permission(perm.SEARCH_VIEW)
        self.req.hdf.setValue('title', 'Search')
        self.req.hdf.setValue('search.ticket', 'checked')
        self.req.hdf.setValue('search.changeset', 'checked')
        self.req.hdf.setValue('search.wiki', 'checked')
        self.req.hdf.setValue('search.results_per_page', str(self.RESULTS_PER_PAGE))
        
        if self.args.has_key('q'):
            query = self.args['q']
            self.req.hdf.setValue('title', 'Search Results (search)')
            self.req.hdf.setValue('search.q', query)
            tickets = self.args.has_key('ticket')
            changesets = self.args.has_key('changeset')
            wiki = self.args.has_key('wiki')

            if self.args.has_key('page'):
                page = int(self.args['page'])
                self.req.hdf.setValue('search.result.page', str(page))
            else:
                page = 0
            if not tickets:
                self.req.hdf.setValue('search.ticket', '')
            if not changesets:
                self.req.hdf.setValue('search.changeset', '')
            if not wiki:
                self.req.hdf.setValue('search.wiki', '')
            info = self.perform_query(query, changesets, tickets, wiki, page)
            self.req.hdf.setValue('search.result.count', str(len(info)))
            if len(info) == self.RESULTS_PER_PAGE:
                self.req.hdf.setValue('search.result.more', '1')
            add_dictlist_to_hdf(info, self.req.hdf, 'search.result')

