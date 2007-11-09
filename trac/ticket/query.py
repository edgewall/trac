# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2007 Edgewall Software
# Copyright (C) 2004-2005 Christopher Lenz <cmlenz@gmx.de>
# Copyright (C) 2005-2007 Christian Boos <cboos@neuf.fr>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.
#
# Author: Christopher Lenz <cmlenz@gmx.de>

import csv
from datetime import datetime, timedelta
import re
from StringIO import StringIO

from genshi.builder import tag

from trac.core import *
from trac.db import get_column_names
from trac.mimeview.api import Mimeview, IContentConverter, Context
from trac.perm import IPermissionRequestor
from trac.resource import Resource
from trac.ticket.api import TicketSystem
from trac.ticket.model import Ticket
from trac.util import Ranges
from trac.util.compat import groupby
from trac.util.datefmt import to_timestamp, utc
from trac.util.html import escape, unescape
from trac.util.text import shorten_line, CRLF
from trac.util.translation import _
from trac.web import IRequestHandler
from trac.web.href import Href
from trac.web.chrome import add_link, add_script, add_stylesheet, \
                            INavigationContributor, Chrome
from trac.wiki.api import IWikiSyntaxProvider, parse_args
from trac.wiki.macros import WikiMacroBase # TODO: should be moved in .api
from trac.config import Option 

class QuerySyntaxError(Exception):
    """Exception raised when a ticket query cannot be parsed from a string."""


class Query(object):

    def __init__(self, env, report=None, constraints=None, cols=None,
                 order=None, desc=0, group=None, groupdesc=0, verbose=0,
                 rows=None, limit=None):
        self.env = env
        self.id = report # if not None, it's the corresponding saved query
        self.constraints = constraints or {}
        self.order = order
        self.desc = desc
        self.group = group
        self.groupdesc = groupdesc
        self.limit = limit
        if rows == None:
            rows = []
        if verbose and 'description' not in rows: # 0.10 compatibility
            rows.append('description')
        self.fields = TicketSystem(self.env).get_ticket_fields()
        field_names = [f['name'] for f in self.fields]
        self.cols = [c for c in cols or [] if c in field_names or c == 'id']
        self.rows = [c for c in rows if c in field_names]

        if self.order != 'id' and self.order not in field_names:
            # TODO: fix after adding time/changetime to the api.py
            if order == 'created':
                order = 'time'
            elif order == 'modified':
                order = 'changetime'
            if order in ('time', 'changetime'):
                self.order = order
            else:
                self.order = 'priority'

        if self.group not in field_names:
            self.group = None

    def from_string(cls, env, string, **kw):
        filters = string.split('&')
        kw_strs = ['order', 'group', 'limit']
        kw_arys = ['rows']
        kw_bools = ['desc', 'groupdesc', 'verbose']
        constraints = {}
        cols = []
        for filter_ in filters:
            filter_ = filter_.split('=')
            if len(filter_) != 2:
                raise QuerySyntaxError('Query filter requires field and ' 
                                       'constraints separated by a "="')
            field,values = filter_
            if not field:
                raise QuerySyntaxError('Query filter requires field name')
            # from last char of `field`, get the mode of comparison
            mode, neg = '', ''
            if field[-1] in ('~', '^', '$'):
                mode = field[-1]
                field = field[:-1]
            if field[-1] == '!':
                neg = '!'
                field = field[:-1]
            processed_values = []
            for val in values.split('|'):
                val = neg + mode + val # add mode of comparison
                processed_values.append(val)
            try:
                field = str(field)
                if field in kw_strs:
                    kw[field] = processed_values[0]
                elif field in kw_arys:
                    kw[field] = processed_values
                elif field in kw_bools:
                    kw[field] = True
                elif field == 'col':
                    cols.extend(processed_values)
                else:
                    constraints[field] = processed_values
            except UnicodeError:
                pass # field must be a str, see `get_href()`
        report = constraints.pop('report', None)
        report = kw.pop('report', report)
        return cls(env, report, constraints=constraints, cols=cols, **kw)
    from_string = classmethod(from_string)

    def get_columns(self):
        if not self.cols:
            self.cols = self.get_default_columns()
        return self.cols

    def get_all_textareas(self):
        return [f['name'] for f in self.fields if f['type'] == 'textarea']

    def get_all_columns(self):
        # Prepare the default list of columns
        cols = ['id']
        cols += [f['name'] for f in self.fields if f['type'] != 'textarea']
        for col in ('reporter', 'keywords', 'cc'):
            if col in cols:
                cols.remove(col)
                cols.append(col)

        # Semi-intelligently remove columns that are restricted to a single
        # value by a query constraint.
        for col in [k for k in self.constraints.keys()
                    if k != 'id' and k in cols]:
            constraint = self.constraints[col]
            if len(constraint) == 1 and constraint[0] \
                    and not constraint[0][0] in ('!', '~', '^', '$'):
                if col in cols:
                    cols.remove(col)
            if col == 'status' and not 'closed' in constraint \
                    and 'resolution' in cols:
                cols.remove('resolution')
        if self.group in cols:
            cols.remove(self.group)

        def sort_columns(col1, col2):
            constrained_fields = self.constraints.keys()
            if 'id' in (col1, col2):
                # Ticket ID is always the first column
                return col1 == 'id' and -1 or 1
            elif 'summary' in (col1, col2):
                # Ticket summary is always the second column
                return col1 == 'summary' and -1 or 1
            elif col1 in constrained_fields or col2 in constrained_fields:
                # Constrained columns appear before other columns
                return col1 in constrained_fields and -1 or 1
            return 0
        cols.sort(sort_columns)
        return cols

    def get_default_columns(self):
        all_cols = self.get_all_columns()
        # Only display the first seven columns by default
        cols = all_cols[:7]
        # Make sure the column we order by is visible, if it isn't also
        # the column we group by
        if not self.order in cols and not self.order == self.group:
            cols[-1] = self.order
        return cols

    def execute(self, req, db=None):
        if not self.cols:
            self.get_columns()

        sql, args = self.get_sql(req)
        self.env.log.debug("Query SQL: " + sql % tuple([repr(a) for a in args]))

        if not db:
            db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute(sql, args)
        columns = get_column_names(cursor)
        fields = []
        for column in columns:
            fields += [f for f in self.fields if f['name'] == column] or [None]
        results = []

        for row in cursor:
            id = int(row[0])
            result = {'id': id, 'href': req.href.ticket(id)}
            for i in range(1, len(columns)):
                name, field, val = columns[i], fields[i], row[i]
                if name == self.group:
                    val = val or 'None'
                elif name == 'reporter':
                    val = val or 'anonymous'
                elif val is None:
                    val = '--'
                elif name in ('changetime', 'time'):
                    val = datetime.fromtimestamp(int(val), utc)
                elif field and field['type'] == 'checkbox':
                    try:
                        val = bool(int(val))
                    except TypeError, ValueError:
                        val = False
                result[name] = val
            results.append(result)
        cursor.close()
        return results

    def get_href(self, href, id=None, order=None, desc=None, format=None):
        """Create a link corresponding to this query.

        :param href: the `Href` object used to build the URL
        :param id: optionally set or override the report `id`
        :param order: optionally override the order parameter of the query
        :param desc: optionally override the desc parameter
        :param format: optionally override the format of the query

        Note: `get_resource_url` of a 'query' resource?
        """
        if not isinstance(href, Href):
            href = href.href # compatibility with the `req` of the 0.10 API
        if id is None:
            id = self.id
        if desc is None:
            desc = self.desc
        if order is None:
            order = self.order
        cols = self.get_columns()
        # don't specify the columns in the href if they correspond to
        # the default columns, in the same order.  That keeps the query url
        # shorter in the common case where we just want the default columns.
        if cols == self.get_default_columns():
            cols = None
        return href.query(report=id,
                          order=order, desc=desc and 1 or None,
                          group=self.group or None,
                          groupdesc=self.groupdesc and 1 or None,
                          col=cols,
                          row=self.rows,
                          format=format, **self.constraints)

    def to_string(self):
        """Return a user readable and editable representation of the query.

        Note: for now, this is an "exploded" query href, but ideally should be
        expressed in TracQuery language.
        """
        query_string = self.get_href(Href(''))
        if query_string and '?' in query_string:
            query_string = query_string.split('?', 1)[1]
        return 'query:?' + query_string.replace('&', '\n&\n')

    def get_sql(self, req=None):
        """Return a (sql, params) tuple for the query."""
        if not self.cols:
            self.get_columns()

        enum_columns = ('resolution', 'priority', 'severity')
        # Build the list of actual columns to query
        cols = self.cols[:]
        def add_cols(*args):
            for col in args:
                if not col in cols:
                    cols.append(col)
        if self.group and not self.group in cols:
            add_cols(self.group)
        if self.rows:
            add_cols('reporter', *self.rows)
        add_cols('priority', 'time', 'changetime', self.order)
        cols.extend([c for c in self.constraints.keys() if not c in cols])

        custom_fields = [f['name'] for f in self.fields if 'custom' in f]

        sql = []
        sql.append("SELECT " + ",".join(['t.%s AS %s' % (c, c) for c in cols
                                         if c not in custom_fields]))
        sql.append(",priority.value AS priority_value")
        for k in [k for k in cols if k in custom_fields]:
            sql.append(",%s.value AS %s" % (k, k))
        sql.append("\nFROM ticket AS t")

        # Join with ticket_custom table as necessary
        for k in [k for k in cols if k in custom_fields]:
           sql.append("\n  LEFT OUTER JOIN ticket_custom AS %s ON " \
                      "(id=%s.ticket AND %s.name='%s')" % (k, k, k, k))

        # Join with the enum table for proper sorting
        for col in [c for c in enum_columns
                    if c == self.order or c == self.group or c == 'priority']:
            sql.append("\n  LEFT OUTER JOIN enum AS %s ON "
                       "(%s.type='%s' AND %s.name=%s)"
                       % (col, col, col, col, col))

        # Join with the version/milestone tables for proper sorting
        for col in [c for c in ['milestone', 'version']
                    if c == self.order or c == self.group]:
            sql.append("\n  LEFT OUTER JOIN %s ON (%s.name=%s)"
                       % (col, col, col))

        def get_constraint_sql(name, value, mode, neg):
            if name not in custom_fields:
                name = 't.' + name
            else:
                name = name + '.value'
            value = value[len(mode) + neg:]

            if mode == '':
                return ("COALESCE(%s,'')%s=%%s" % (name, neg and '!' or ''),
                        value)
            if not value:
                return None
            db = self.env.get_db_cnx()
            value = db.like_escape(value)
            if mode == '~':
                value = '%' + value + '%'
            elif mode == '^':
                value = value + '%'
            elif mode == '$':
                value = '%' + value
            return ("COALESCE(%s,'') %s%s" % (name, neg and 'NOT ' or '',
                                              db.like()),
                    value)

        clauses = []
        args = []
        for k, v in self.constraints.items():
            if req:
                v = [val.replace('$USER', req.authname) for val in v]
            # Determine the match mode of the constraint (contains,
            # starts-with, negation, etc.)
            neg = v[0].startswith('!')
            mode = ''
            if len(v[0]) > neg and v[0][neg] in ('~', '^', '$'):
                mode = v[0][neg]

            # Special case id ranges
            if k == 'id':
                ranges = Ranges()
                for r in v:
                    r = r.replace('!', '')
                    ranges.appendrange(r)
                ids = []
                id_clauses = []
                for a,b in ranges.pairs:
                    if a == b:
                        ids.append(str(a))
                    else:
                        id_clauses.append('id BETWEEN %s AND %s')
                        args.append(a)
                        args.append(b)
                if ids:
                    id_clauses.append('id IN (%s)' % (','.join(ids)))
                if id_clauses:
                    clauses.append('%s(%s)' % (neg and 'NOT ' or '',
                                               ' OR '.join(id_clauses)))
            # Special case for exact matches on multiple values
            elif not mode and len(v) > 1:
                if k not in custom_fields:
                    col = 't.' + k
                else:
                    col = k + '.value'
                clauses.append("COALESCE(%s,'') %sIN (%s)"
                               % (col, neg and 'NOT ' or '',
                                  ','.join(['%s' for val in v])))
                args += [val[neg:] for val in v]
            elif len(v) > 1:
                constraint_sql = filter(None,
                                        [get_constraint_sql(k, val, mode, neg)
                                         for val in v])
                if not constraint_sql:
                    continue
                if neg:
                    clauses.append("(" + " AND ".join(
                        [item[0] for item in constraint_sql]) + ")")
                else:
                    clauses.append("(" + " OR ".join(
                        [item[0] for item in constraint_sql]) + ")")
                args += [item[1] for item in constraint_sql]
            elif len(v) == 1:
                constraint_sql = get_constraint_sql(k, v[0], mode, neg)
                if constraint_sql:
                    clauses.append(constraint_sql[0])
                    args.append(constraint_sql[1])

        clauses = filter(None, clauses)
        if clauses:
            sql.append("\nWHERE " + " AND ".join(clauses))

        sql.append("\nORDER BY ")
        order_cols = [(self.order, self.desc)]
        if self.group and self.group != self.order:
            order_cols.insert(0, (self.group, self.groupdesc))
        for name, desc in order_cols:
            if name not in custom_fields:
                col = 't.' + name
            else:
                col = name + '.value'
            # FIXME: This is a somewhat ugly hack.  Can we also have the
            #        column type for this?  If it's an integer, we do first
            #        one, if text, we do 'else'
            if name in ('id', 'time', 'changetime'):
                if desc:
                    sql.append("COALESCE(%s,0)=0 DESC," % col)
                else:
                    sql.append("COALESCE(%s,0)=0," % col)
            else:
                if desc:
                    sql.append("COALESCE(%s,'')='' DESC," % col)
                else:
                    sql.append("COALESCE(%s,'')=''," % col)
            if name in enum_columns:
                if desc:
                    sql.append("%s.value DESC" % name)
                else:
                    sql.append("%s.value" % name)
            elif name in ('milestone', 'version'):
                if name == 'milestone': 
                    time_col = 'milestone.due'
                else:
                    time_col = 'version.time'
                if desc:
                    sql.append("COALESCE(%s,0)=0 DESC,%s DESC,%s DESC"
                               % (time_col, time_col, col))
                else:
                    sql.append("COALESCE(%s,0)=0,%s,%s"
                               % (time_col, time_col, col))
            else:
                if desc:
                    sql.append("%s DESC" % col)
                else:
                    sql.append("%s" % col)
            if name == self.group and not name == self.order:
                sql.append(",")
        if self.order != 'id':
            sql.append(",t.id")
            
        # Limit number of records
        if self.limit:
            sql.append("\nLIMIT %s")
            args.append(self.limit)       

        return "".join(sql), args

    def template_data(self, context, tickets, orig_list=None, orig_time=None):
        constraints = {}
        for k, v in self.constraints.items():
            constraint = {'values': [], 'mode': ''}
            for val in v:
                neg = val.startswith('!')
                if neg:
                    val = val[1:]
                mode = ''
                if val[:1] in ('~', '^', '$'):
                    mode, val = val[:1], val[1:]
                constraint['mode'] = (neg and '!' or '') + mode
                constraint['values'].append(val)
            constraints[k] = constraint

        cols = self.get_columns()
        labels = dict([(f['name'], f['label']) for f in self.fields])

        # TODO: remove after adding time/changetime to the api.py
        labels['changetime'] = _('Modified')
        labels['time'] = _('Created')

        headers = [{
            'name': col, 'label': labels.get(col, _('Ticket')),
            'href': self.get_href(context.href, order=col,
                                  desc=(col == self.order and not self.desc))
        } for col in cols]

        fields = {}
        for field in self.fields:
            if field['type'] == 'textarea':
                continue
            field_data = {}
            field_data.update(field)
            del field_data['name']
            fields[field['name']] = field_data

        modes = {}
        modes['text'] = [
            {'name': _("contains"), 'value': "~"},
            {'name': _("doesn't contain"), 'value': "!~"},
            {'name': _("begins with"), 'value': "^"},
            {'name': _("ends with"), 'value': "$"},
            {'name': _("is"), 'value': ""},
            {'name': _("is not"), 'value': "!"}
        ]
        modes['select'] = [
            {'name': _("is"), 'value': ""},
            {'name': _("is not"), 'value': "!"}
        ]

        groups = {}
        groupsequence = []
        for ticket in tickets:
            if orig_list:
                # Mark tickets added or changed since the query was first
                # executed
                if ticket['time'] > orig_time:
                    ticket['added'] = True
                elif ticket['changetime'] > orig_time:
                    ticket['changed'] = True
            if self.group:
                group_key = ticket[self.group]
                groups.setdefault(group_key, []).append(ticket)
                if not groupsequence or groupsequence[-1] != group_key:
                    groupsequence.append(group_key)
        groupsequence = [(value, groups[value]) for value in groupsequence]

        return {'query': self,
                'context': context,
                'col': cols,
                'row': self.rows,
                'constraints': constraints,
                'labels': labels,
                'headers': headers,
                'fields': fields,
                'modes': modes,
                'tickets': tickets,
                'groups': groupsequence or [(None, tickets)]}


class QueryModule(Component):

    implements(IRequestHandler, INavigationContributor, IWikiSyntaxProvider,
               IContentConverter)
               
    default_query = Option('query', 'default_query',  
                            default='status!=closed&owner=$USER', 
                            doc='The default query for authenticated users.') 
    
    default_anonymous_query = Option('query', 'default_anonymous_query',  
                               default='status!=closed&cc~=$USER', 
                               doc='The default query for anonymous users.') 

    # IContentConverter methods
    def get_supported_conversions(self):
        yield ('rss', _('RSS Feed'), 'xml',
               'trac.ticket.Query', 'application/rss+xml', 8)
        yield ('csv', _('Comma-delimited Text'), 'csv',
               'trac.ticket.Query', 'text/csv', 8)
        yield ('tab', _('Tab-delimited Text'), 'tsv',
               'trac.ticket.Query', 'text/tab-separated-values', 8)

    def convert_content(self, req, mimetype, query, key):
        if key == 'rss':
            return self.export_rss(req, query)
        elif key == 'csv':
            return self.export_csv(req, query, mimetype='text/csv')
        elif key == 'tab':
            return self.export_csv(req, query, '\t',
                                   mimetype='text/tab-separated-values')

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'tickets'

    def get_navigation_items(self, req):
        from trac.ticket.report import ReportModule
        if 'TICKET_VIEW' in req.perm and \
                not self.env.is_component_enabled(ReportModule):
            yield ('mainnav', 'tickets',
                   tag.a(_('View Tickets'), href=req.href.query()))

    # IRequestHandler methods

    def match_request(self, req):
        return req.path_info == '/query'

    def process_request(self, req):
        req.perm.assert_permission('TICKET_VIEW')

        constraints = self._get_constraints(req)
        if not constraints and not 'order' in req.args:
            # If no constraints are given in the URL, use the default ones.
            if req.authname and req.authname != 'anonymous':
                qstring = self.default_query 
                user = req.authname 
            else:
                email = req.session.get('email')
                name = req.session.get('name')
                qstring = self.default_anonymous_query 
                user = email or name or None 
                      
            if user: 
                qstring = qstring.replace('$USER', user) 
            self.log.debug('QueryModule: Using default query: %s', qstring) 
            constraints = Query.from_string(self.env, qstring).constraints 
            # Ensure no field constraints that depend on $USER are used 
            # if we have no username. 
            for field, vals in constraints.items(): 
                for val in vals: 
                    if val.endswith('$USER'): 
                        del constraints[field] 

        cols = req.args.get('col')
        if isinstance(cols, basestring):
            cols = [cols]
        # Since we don't show 'id' as an option to the user,
        # we need to re-insert it here.            
        if cols and 'id' not in cols: 
            cols.insert(0, 'id')
        rows = req.args.get('row', [])
        if isinstance(rows, basestring):
            rows = [rows]
        query = Query(self.env, req.args.get('report'),
                      constraints, cols, req.args.get('order'),
                      'desc' in req.args, req.args.get('group'),
                      'groupdesc' in req.args, 'verbose' in req.args,
                      rows,
                      req.args.get('limit'))

        if 'update' in req.args:
            # Reset session vars
            for var in ('query_constraints', 'query_time', 'query_tickets'):
                if var in req.session:
                    del req.session[var]
            req.redirect(query.get_href(req.href))

        # Add registered converters
        for conversion in Mimeview(self.env).get_supported_conversions(
                                             'trac.ticket.Query'):
            add_link(req, 'alternate',
                     query.get_href(req.href, format=conversion[0]),
                     conversion[1], conversion[4], conversion[0])

        format = req.args.get('format')
        if format:
            Mimeview(self.env).send_converted(req, 'trac.ticket.Query', query,
                                              format, 'query')

        return self.display_html(req, query)

    # Internal methods

    def _get_constraints(self, req):
        constraints = {}
        ticket_fields = [f['name'] for f in
                         TicketSystem(self.env).get_ticket_fields()]
        ticket_fields.append('id')

        # For clients without JavaScript, we remove constraints here if
        # requested
        remove_constraints = {}
        to_remove = [k[10:] for k in req.args.keys()
                     if k.startswith('rm_filter_')]
        if to_remove: # either empty or containing a single element
            match = re.match(r'(\w+?)_(\d+)$', to_remove[0])
            if match:
                remove_constraints[match.group(1)] = int(match.group(2))
            else:
                remove_constraints[to_remove[0]] = -1

        for field in [k for k in req.args.keys() if k in ticket_fields]:
            vals = req.args[field]
            if not isinstance(vals, (list, tuple)):
                vals = [vals]
            if vals:
                mode = req.args.get(field + '_mode')
                if mode:
                    vals = [mode + x for x in vals]
                if field in remove_constraints:
                    idx = remove_constraints[field]
                    if idx >= 0:
                        del vals[idx]
                        if not vals:
                            continue
                    else:
                        continue
                constraints[field] = vals

        return constraints

    def display_html(self, req, query):
        db = self.env.get_db_cnx()
        tickets = query.execute(req, db)

        # The most recent query is stored in the user session;
        orig_list = rest_list = None
        orig_time = datetime.now(utc)
        query_time = int(req.session.get('query_time', 0))
        query_time = datetime.fromtimestamp(query_time, utc)
        query_constraints = unicode(query.constraints)
        if query_constraints != req.session.get('query_constraints') \
                or query_time < orig_time - timedelta(hours=1):
            # New or outdated query, (re-)initialize session vars
            req.session['query_constraints'] = query_constraints
            req.session['query_tickets'] = ' '.join([str(t['id'])
                                                     for t in tickets])
        else:
            orig_list = [int(id) for id
                         in req.session.get('query_tickets', '').split()]
            rest_list = orig_list[:]
            orig_time = query_time

        # Find out which tickets originally in the query results no longer
        # match the constraints
        if rest_list:
            for tid in [t['id'] for t in tickets if t['id'] in rest_list]:
                rest_list.remove(tid)
            for rest_id in rest_list:
                try:
                    ticket = Ticket(self.env, int(rest_id), db=db)
                    data = {'id': ticket.id, 'time': ticket.time_created,
                            'changetime': ticket.time_changed, 'removed': True,
                            'href': req.href.ticket(ticket.id)}
                    data.update(ticket.values)
                except TracError, e:
                    data = {'id': rest_id, 'time': 0, 'changetime': 0,
                            'summary': tag.em(e)}
                tickets.insert(orig_list.index(rest_id), data)

        context = Context.from_request(req, 'query')
        data = query.template_data(context, tickets, orig_list, orig_time)

        # For clients without JavaScript, we add a new constraint here if
        # requested
        constraints = data['constraints']
        if 'add' in req.args:
            field = req.args.get('add_filter')
            if field:
                constraint = constraints.setdefault(field, {})
                constraint.setdefault('values', []).append('')
                # FIXME: '' not always correct (e.g. checkboxes)

        req.session['query_href'] = query.get_href(context.href)
        req.session['query_time'] = to_timestamp(orig_time)
        req.session['query_tickets'] = ' '.join([str(t['id'])
                                                 for t in tickets])
        title = _('Custom Query')

        # Only interact with the report module if it is actually enabled.
        #
        # Note that with saved custom queries, there will be some convergence
        # between the report module and the query module.
        from trac.ticket.report import ReportModule
        if 'REPORT_VIEW' in req.perm and \
               self.env.is_component_enabled(ReportModule):
            data['report_href'] = req.href.report()
            if query.id:
                cursor = db.cursor()
                cursor.execute("SELECT title,description FROM report "
                               "WHERE id=%s", (query.id,))
                for title, description in cursor:
                    data['report_resource'] = Resource('report', query.id)
                    data['description'] = description
        else:
            data['report_href'] = None
        data.setdefault('report', None)
        data.setdefault('description', None)
        data['title'] = title

        data['all_columns'] = query.get_all_columns()
        # Don't allow the user to remove the id column        
        data['all_columns'].remove('id')
        data['all_textareas'] = query.get_all_textareas()

        add_stylesheet(req, 'common/css/report.css')
        add_script(req, 'common/js/query.js')

        return 'query.html', data, None

    def export_csv(self, req, query, sep=',', mimetype='text/plain'):
        content = StringIO()
        cols = query.get_columns()
        writer = csv.writer(content, delimiter=sep)
        writer.writerow([unicode(c).encode('utf-8') for c in cols])

        results = query.execute(req, self.env.get_db_cnx())
        for result in results:
            if 'TICKET_VIEW' in req.perm('ticket', result['id']):
                writer.writerow([unicode(result[col]).encode('utf-8')
                                 for col in cols])
        return (content.getvalue(), '%s;charset=utf-8' % mimetype)

    def export_rss(self, req, query):
        if 'description' not in query.rows:
            query.rows.append('description')
        db = self.env.get_db_cnx()
        results = query.execute(req, db)
        query_href = req.abs_href.query(group=query.group,
                                        groupdesc=(query.groupdesc and 1
                                                   or None),
                                        row=query.rows, 
                                        **query.constraints)

        data = {
            'context': Context.from_request(req, 'query', absurls=True),
            'results': results,
            'query_href': query_href
        }
        output = Chrome(self.env).render_template(req, 'query.rss', data,
                                                  'application/rss+xml')
        return output, 'application/rss+xml'

    # IWikiSyntaxProvider methods
    
    def get_wiki_syntax(self):
        return []
    
    def get_link_resolvers(self):
        yield ('query', self._format_link)

    def _format_link(self, formatter, ns, query, label):
        if query.startswith('?'):
            return tag.a(label, class_='query',
                         href=formatter.href.query() + query.replace(' ', '+'))
        else:
            try:
                query = Query.from_string(self.env, query)
                return tag.a(label,
                             href=query.get_href(formatter.context.href),
                             class_='query')
            except QuerySyntaxError, e:
                return tag.em(_('[Error: %(error)s]', error=e), class_='error')


class TicketQueryMacro(WikiMacroBase):
    """Macro that lists tickets that match certain criteria.
    
    This macro accepts a comma-separated list of keyed parameters,
    in the form "key=value".

    If the key is the name of a field, the value must use the same syntax as
    for `query:` wiki links (but '''not''' the variant syntax starting with
    "?").

    The optional `format` parameter determines how the list of tickets is
    presented: 
     - '''list''' -- the default presentation is to list the ticket ID next
       to the summary, with each ticket on a separate line.
     - '''compact''' -- the tickets are presented as a comma-separated
       list of ticket IDs. 
     - '''count''' -- only the count of matching tickets is displayed
     - '''table'''  -- a view similar to the custom query view (but without
       the controls)

    The optional `order` parameter sets the field used for ordering tickets
    (defaults to '''id''').

    The optional `group` parameter sets the field used for grouping tickets
    (defaults to not being set).

    The optional `groupdesc` parameter indicates whether the natural display
    order of the groups should be reversed (defaults to '''false''').

    The optional `verbose` parameter can be set to a true value in order to
    get the description for the listed tickets. For '''table''' format only.
    ''deprecated in favor of the row parameter''.

    For compatibility with Trac 0.10, if there's a second positional parameter
    given to the macro, it will be used to specify the `format`.
    Also, using "&" as a field separator still works but is deprecated.
    """

    def expand_macro(self, formatter, name, content):
        req = formatter.req
        query_string = ''
        argv, kwargs = parse_args(content, strict=False)
        if len(argv) > 0 and not 'format' in kwargs: # 0.10 compatibility hack
            kwargs['format'] = argv[0]

        format = kwargs.pop('format', 'list').strip().lower()
        query_string = '&'.join(['%s=%s' % item
                                 for item in kwargs.iteritems()])

        query = Query.from_string(self.env, query_string)
        tickets = query.execute(req)

        if format == 'count':
            cnt = tickets and len(tickets) or 0
            return tag.span(cnt, title='%d tickets for which %s' %
                            (cnt, query_string), class_='query_count')
        if tickets:
            def ticket_anchor(ticket):
                return tag.a('#%s' % ticket['id'],
                             class_=ticket['status'],
                             href=req.href.ticket(int(ticket['id'])),
                             title=shorten_line(ticket['summary']))
            def ticket_groups():
                groups = []
                for v, g in groupby(tickets, lambda t: t[query.group]):
                    q = Query.from_string(self.env, query_string)
                    # produce the hint for the group
                    q.group = q.groupdesc = None
                    order = q.order
                    q.order = None
                    title = "%s %s tickets matching %s" % (v, query.group,
                                                           q.to_string())
                    # produce the href for the query corresponding to the group
                    q.constraints[str(query.group)] = v
                    q.order = order
                    href = q.get_href(formatter.context)
                    groups.append((v, [t for t in g], href, title))
                return groups

            if format == 'compact':
                if query.group:
                    groups = [tag.a('#%s' % ','.join([str(t['id'])
                                                      for t in g]),
                                    href=href, class_='query', title=title)
                              for v, g, href, title in ticket_groups()]
                    return tag(groups[0], [(', ', g) for g in groups[1:]])
                else:
                    alist = [ticket_anchor(ticket) for ticket in tickets]
                    return tag.span(alist[0], *[(', ', a) for a in alist[1:]])
            elif format == 'table':
                db = self.env.get_db_cnx()
                tickets = query.execute(req, db)
                data = query.template_data(formatter.context, tickets)

                add_stylesheet(req, 'common/css/report.css')
                
                return Chrome(self.env).render_template(
                    req, 'query_results.html', data, None, fragment=True)
            else:
                if query.group:
                    return tag.div(
                        [(tag.p(tag.a(query.group, ' ', v, href=href,
                                      class_='query', title=title)),
                          tag.dl([(tag.dt(ticket_anchor(t)),
                                   tag.dd(t['summary'])) for t in g],
                                 class_='wiki compact'))
                         for v, g, href, title in ticket_groups()])
                else:
                    return tag.div(tag.dl([(tag.dt(ticket_anchor(ticket)),
                                            tag.dd(ticket['summary']))
                                           for ticket in tickets],
                                          class_='wiki compact'))
        else:
            return tag.span(_("No results"), class_='query_no_results')
