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

from util import *
from Href import href
from Module import Module
from Wiki import wiki_to_oneliner
import db
import perm

class Search(Module):
    template_name = 'search.cs'

    def __init__(self, config, args, pool):
        Module.__init__(self, config, args, pool)
        self._args = args

    def query_to_sql(self, query, name):
        query = query.replace('\'', '\'\'\'\'')
        keywords = query.split(' ')
        # The line below doesn't work in python2.1
        # x = map(lambda x: name + ' LIKE \'%' + x + '%\'', keywords)
        x = []
        for keyword in keywords:
            x.append(name + ' LIKE \'%' + keyword + '%\'')
        return string.join(x, ' AND ')
    
    def perform_query (self, query, changeset, tickets):
        cnx = db.get_connection()
        cursor = cnx.cursor ()

        q = []
        if changeset:
            q.append('SELECT 1 as type, message, author, rev AS data, '
                     'time FROM revision WHERE %s' %
                     self.query_to_sql(query, 'message'))
        if tickets:
            q.append('SELECT 2 as type, summary AS message, '
                     'reporter AS author, id AS data, time '
                     'FROM ticket WHERE %s OR %s' %
                     (self.query_to_sql(query, 'summary'),
                      self.query_to_sql(query, 'description')))

        q_str = string.join(q, ' UNION ALL ')
        q_str += ' ORDER BY time DESC LIMIT 20'
        cursor.execute(q_str)

        # Make the data more HDF-friendly
        info = []
        while 1:
            row = cursor.fetchone()
            if not row:
                break
            item = {'type': int(row['type']),
                    'message': wiki_to_oneliner(row['message']),
                    'data': row['data'],
                    'author': row['author']}
            if item['type'] == 1:
                item['changeset_href'] = href.changeset(int(row['data']))
            elif item['type'] == 2:
                item['ticket_href'] = href.ticket(int(row['data']))
            elif item['type'] == 3:
                item['wiki_href'] = href.wiki(row['data'])
            info.append(item)
        return info
        
    def render (self):
        perm.assert_permission(perm.SEARCH_VIEW)
        self.cgi.hdf.setValue('title', 'Search')
        self.cgi.hdf.setValue('search.ticket', 'checked')
        self.cgi.hdf.setValue('search.changeset', 'checked')
        
        if self._args.has_key('q'):
            query = self._args['q']
            self.cgi.hdf.setValue('search.q', query)
            tickets = self._args.has_key('ticket')
            changesets = self._args.has_key('changeset')
            if not tickets:
                self.cgi.hdf.setValue('search.ticket', '')
            if not changesets:
                self.cgi.hdf.setValue('search.changeset', '')
            info = self.perform_query(query, changesets, tickets)
            add_dictlist_to_hdf(info, self.cgi.hdf, 'search.result')

