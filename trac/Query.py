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

from __future__ import nested_scopes
from types import ListType

import perm
import util
from Module import Module
from Ticket import get_custom_fields, insert_custom_fields, Ticket


class QueryModule(Module):
    template_name = 'query.cs'

    def get_constraints(self):
        constraints = {}
        custom_fields = [f['name'] for f in get_custom_fields(self.env)]
        constrained_fields = [k for k in self.args.keys()
                              if k in Ticket.std_fields or k in custom_fields]
        for field in constrained_fields:
            vals = self.args[field]
            if type(vals) is ListType:
                vals = map(lambda x: x.value, filter(None, vals))
            elif vals.value:
                vals = [vals.value]
            else:
                continue
            constraints[field] = vals
        return constraints

    def get_results(self, sql):
        cursor = self.db.cursor()
        cursor.execute(sql)
        results = []
        previous_id = 0
        while 1:
            row = cursor.fetchone()
            if not row:
                break
            id = int(row['id'])
            if id == previous_id:
                result = results[-1]
                result[row['name']] = row['value']
            else:
                result = {
                    'id': id,
                    'href': self.env.href.ticket(id),
                    'summary': util.escape(row['summary'] or '(no summary)'),
                    'status': row['status'] or '',
                    'component': row['component'] or '',
                    'owner': row['owner'] or '',
                    'priority': row['priority'] or ''
                }
                results.append(result)
                previous_id = id
        cursor.close()
        return results

    def render(self):
        self.perm.assert_permission(perm.TICKET_VIEW)

        constraints = self.get_constraints()
        order = self.args.get('order', 'priority')
        desc = self.args.has_key('desc')

        if self.args.has_key('search'):
            self.req.redirect(self.env.href.query(constraints, order, desc,
                                                  action='view'))

        action = self.args.get('action')
        if not action and not constraints:
            action = 'edit'

        self.req.hdf.setValue('query.action', action or 'view')
        if action == 'edit':
            self._render_editor(constraints, order, desc)
        else:
            self._render_results(constraints, order, desc)

    def _render_editor(self, constraints, order, desc):
        self.req.hdf.setValue('title', 'Custom Query')
        util.add_to_hdf(constraints, self.req.hdf, 'query.constraints')
        self.req.hdf.setValue('query.order', order)
        if desc: self.req.hdf.setValue('query.desc', '1')

        def add_options(field, constraints, prefix, options):
            check = constraints.has_key(field)
            for option in options:
                if check and (option['name'] in constraints[field]):
                    option['selected'] = 1
            util.add_to_hdf(options, self.req.hdf, prefix + field)
            if check:
                del constraints[field]

        def add_db_options(field, constraints, prefix, cursor, sql):
            cursor.execute(sql)
            options = []
            while 1:
                row = cursor.fetchone()
                if not row: break
                if row[0]: options.append({'name': row[0]})
            add_options(field, constraints, prefix, options)

        add_options('status', constraints, 'query.options.',
                    [{'name': 'new'}, {'name': 'assigned'},
                     {'name': 'reopened'}, {'name': 'closed'}])
        add_options('resolution', constraints, 'query.options.',
                    [{'name': 'fixed'}, {'name': 'invalid'}, {'name': 'wontfix'},
                     {'name': 'duplicate'}, {'name': 'worksforme'}])
        cursor = self.db.cursor()
        add_db_options('component', constraints, 'query.options.', cursor,
                       'SELECT name FROM component ORDER BY name', )
        add_db_options('milestone', constraints, 'query.options.', cursor,
                       'SELECT name FROM milestone ORDER BY name')
        add_db_options('version', constraints, 'query.options.', cursor,
                       'SELECT name FROM version ORDER BY name')
        add_db_options('priority', constraints, 'query.options.', cursor,
                       'SELECT name FROM enum WHERE type=\'priority\'')
        add_db_options('severity', constraints, 'query.options.', cursor,
                       'SELECT name FROM enum WHERE type=\'severity\'')

        custom_fields = get_custom_fields(self.env)
        for custom in custom_fields:
            if custom['type'] == 'select' or custom['type'] == 'radio':
                check = constraints.has_key(custom['name'])
                options = filter(None, custom['options'])
                for i in range(len(options)):
                    options[i] = {'name': options[i]}
                    if check and (options[i]['name'] in constraints[custom['name']]):
                        options[i]['selected'] = 1
                custom['options'] = options
        util.add_to_hdf(custom_fields, self.req.hdf, 'query.custom')

    def _render_results(self, constraints, order, desc):
        self.req.hdf.setValue('title', 'Custom Query')
        self.req.hdf.setValue('query.edit_href',
            self.env.href.query(constraints, order, desc, action='edit'))

        # FIXME: the user should be able to configure which columns should
        # be displayed
        headers = [ 'id', 'summary', 'status', 'component', 'owner' ]
        cols = headers
        if not 'priority' in cols:
            cols.append('priority')
        sql = 'SELECT ' + ', '.join(['ticket.%s AS %s' % (header, header)
                                     for header in headers])

        if order != 'id' and not order in Ticket.std_fields:
            # order by priority by default
            order = 'priority'
        for i in range(len(headers)):
            self.req.hdf.setValue('query.headers.%d.name' % i, headers[i])
            if headers[i] == order:
                self.req.hdf.setValue('query.headers.%d.href' % i,
                    self.env.href.query(constraints, order, not desc))
                self.req.hdf.setValue('query.headers.%d.order' % i,
                    desc and 'desc' or 'asc')
            else:
                self.req.hdf.setValue('query.headers.%d.href' % i,
                    self.env.href.query(constraints, headers[i]))

        custom_fields = [f['name'] for f in get_custom_fields(self.env)]
        if [k for k in constraints.keys() if k in custom_fields]:
            sql += ", ticket_custom.name AS name, " \
                   "ticket_custom.value AS value " \
                   "FROM ticket OUTER JOIN ticket_custom ON id = ticket"
        else:
            sql += " FROM ticket"
        sql += " INNER JOIN (SELECT name AS priority_name, value AS priority_value " \
               "             FROM enum WHERE type = 'priority') AS p" \
               " ON priority_name = priority"

        clauses = []
        for k, v in constraints.items():
            clause = []
            col = k
            if not col in Ticket.std_fields:
                col = 'value'
            if len(v) > 1:
                inlist = ["'" + util.sql_escape(item) + "'" for item in v]
                clause.append("%s IN (%s)" % (col, ", ".join(inlist)))
            elif k in ['keywords', 'cc']:
                clause.append("%s LIKE '%%%s%%'" % (col, util.sql_escape(v[0])))
            else:
                clause.append("%s = '%s'" % (col, util.sql_escape(v[0])))
            if not k in Ticket.std_fields:
                clauses.append("(name='%s' AND (" % k + " OR ".join(clause) + "))")
            else:
                clauses.append(" OR ".join(clause))
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)

        if order in ['priority', 'severity']:
            sql += " ORDER BY %s_value" % order
        else:
            sql += " ORDER BY " + order
        if desc:
            sql += " DESC"

        self.log.debug("SQL Query: %s" % sql)

        results = self.get_results(sql)
        util.add_to_hdf(results, self.req.hdf, 'query.results')
