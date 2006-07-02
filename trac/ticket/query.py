# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2006 Edgewall Software
# Copyright (C) 2004-2005 Christopher Lenz <cmlenz@gmx.de>
# Copyright (C) 2005-2006 Christian Boos <cboos@neuf.fr>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://projects.edgewall.com/trac/.
#
# Author: Christopher Lenz <cmlenz@gmx.de>

import re
from StringIO import StringIO
import time

from trac.core import *
from trac.db import get_column_names
from trac.perm import IPermissionRequestor
from trac.ticket import Ticket, TicketSystem
from trac.util.datefmt import format_datetime, http_date
from trac.util.text import shorten_line, CRLF
from trac.util.markup import escape, html, unescape
from trac.web import IRequestHandler
from trac.web.chrome import add_link, add_script, add_stylesheet, \
                            INavigationContributor
from trac.wiki import wiki_to_html, wiki_to_oneliner, IWikiSyntaxProvider
from trac.wiki.macros import WikiMacroBase
from trac.mimeview.api import Mimeview, IContentConverter

class QuerySyntaxError(Exception):
    """Exception raised when a ticket query cannot be parsed from a string."""


class Query(object):

    def __init__(self, env, constraints=None, order=None, desc=0, group=None,
                 groupdesc = 0, verbose=0):
        self.env = env
        self.constraints = constraints or {}
        self.order = order
        self.desc = desc
        self.group = group
        self.groupdesc = groupdesc
        self.verbose = verbose
        self.fields = TicketSystem(self.env).get_ticket_fields()
        self.cols = [] # lazily initialized

        if self.order != 'id' \
                and self.order not in [f['name'] for f in self.fields]:
            # order by priority by default
            self.order = 'priority'

        if self.group not in [f['name'] for f in self.fields]:
            self.group = None

    def from_string(cls, env, string, **kw):
        filters = string.split('&')
        kw_strs = ['order', 'group']
        kw_bools = ['desc', 'groupdesc', 'verbose']
        constraints = {}
        for filter in filters:
            filter = filter.split('=')
            if len(filter) != 2:
                raise QuerySyntaxError, 'Query filter requires field and ' \
                                        'constraints separated by a "="'
            field,values = filter
            if not field:
                raise QuerySyntaxError, 'Query filter requires field name'
            values = values.split('|')
            mode, neg = '', ''
            if field[-1] in ('~', '^', '$'):
                mode = field[-1]
                field = field[:-1]
            if field[-1] == '!':
                neg = '!'
                field = field[:-1]
            values = map(lambda x: neg + mode + x, values)
            try:
                field = str(field)
                if field in kw_strs:
                    kw[field] = values[0]
                elif field in kw_bools:
                    kw[field] = True
                else:
                    constraints[field] = values
            except UnicodeError:
                pass # field must be a str, see `get_href()`
        return cls(env, constraints, **kw)
    from_string = classmethod(from_string)

    def get_columns(self):
        if self.cols:
            return self.cols

        # FIXME: the user should be able to configure which columns should
        # be displayed
        cols = ['id']
        cols += [f['name'] for f in self.fields if f['type'] != 'textarea']
        for col in ('reporter', 'keywords', 'cc'):
            if col in cols:
                cols.remove(col)
                cols.append(col)

        # Semi-intelligently remove columns that are restricted to a single
        # value by a query constraint.
        for col in [k for k in self.constraints.keys() if k in cols]:
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
            # Ticket ID is always the first column
            if 'id' in [col1, col2]:
                return col1 == 'id' and -1 or 1
            # Ticket summary is always the second column
            elif 'summary' in [col1, col2]:
                return col1 == 'summary' and -1 or 1
            # Constrained columns appear before other columns
            elif col1 in constrained_fields or col2 in constrained_fields:
                return col1 in constrained_fields and -1 or 1
            return 0
        cols.sort(sort_columns)

        # Only display the first eight columns by default
        # FIXME: Make this configurable on a per-user and/or per-query basis
        self.cols = cols[:7]
        if not self.order in self.cols and not self.order == self.group:
            # Make sure the column we order by is visible, if it isn't also
            # the column we group by
            self.cols[-1] = self.order

        return self.cols

    def execute(self, req, db=None):
        if not self.cols:
            self.get_columns()

        sql, args = self.get_sql()
        self.env.log.debug("Query SQL: " + sql % tuple([repr(a) for a in args]))

        if not db:
            db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute(sql, args)
        columns = get_column_names(cursor)
        results = []
        for row in cursor:
            id = int(row[0])
            result = {'id': id, 'href': req.href.ticket(id)}
            for i in range(1, len(columns)):
                name, val = columns[i], row[i]
                if name == self.group:
                    val = val or 'None'
                elif name == 'reporter':
                    val = val or 'anonymous'
                elif name in ['changetime', 'time']:
                    val = int(val)
                elif val is None:
                    val = '--'
                result[name] = val
            results.append(result)
        cursor.close()
        return results

    def get_href(self, req, order=None, desc=None, format=None):
        # FIXME: only use .href from that 'req' for now
        if desc is None:
            desc = self.desc
        if order is None:
            order = self.order
        return req.href.query(order=order, desc=desc and 1 or None,
                              group=self.group or None,
                              groupdesc=self.groupdesc and 1 or None,
                              verbose=self.verbose and 1 or None,
                              format=format, **self.constraints)

    def get_sql(self):
        """Return a (sql, params) tuple for the query."""
        if not self.cols:
            self.get_columns()

        # Build the list of actual columns to query
        cols = self.cols[:]
        def add_cols(*args):
            for col in args:
                if not col in cols:
                    cols.append(col)
        if self.group and not self.group in cols:
            add_cols(self.group)
        if self.verbose:
            add_cols('reporter', 'description')
        add_cols('priority', 'time', 'changetime', self.order)
        cols.extend([c for c in self.constraints.keys() if not c in cols])

        custom_fields = [f['name'] for f in self.fields if f.has_key('custom')]

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
        for col in [c for c in ('status', 'resolution', 'priority', 'severity')
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

            if mode == '~':
                value = '%' + value + '%'
            elif mode == '^':
                value = value + '%'
            elif mode == '$':
                value = '%' + value
            return ("COALESCE(%s,'') %sLIKE %%s" % (name, neg and 'NOT ' or ''),
                    value)

        clauses = []
        args = []
        for k, v in self.constraints.items():
            # Determine the match mode of the constraint (contains, starts-with,
            # negation, etc)
            neg = v[0].startswith('!')
            mode = ''
            if len(v[0]) > neg and v[0][neg] in ('~', '^', '$'):
                mode = v[0][neg]

            # Special case for exact matches on multiple values
            if not mode and len(v) > 1:
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
                    clauses.append("(" + " AND ".join([item[0] for item in constraint_sql]) + ")")
                else:
                    clauses.append("(" + " OR ".join([item[0] for item in constraint_sql]) + ")")
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
            if name == 'id':
                # FIXME: This is a somewhat ugly hack.  Can we also have the
                #        column type for this?  If it's an integer, we do first
                #        one, if text, we do 'else'
                if desc:
                    sql.append("COALESCE(%s,0)=0 DESC," % col)
                else:
                    sql.append("COALESCE(%s,0)=0," % col)
            else:
                if desc:
                    sql.append("COALESCE(%s,'')='' DESC," % col)
                else:
                    sql.append("COALESCE(%s,'')=''," % col)
            if name in ['status', 'resolution', 'priority', 'severity']:
                if desc:
                    sql.append("%s.value DESC" % name)
                else:
                    sql.append("%s.value" % name)
            elif col in ['t.milestone', 't.version']:
                time_col = name == 'milestone' and 'milestone.due' or 'version.time'
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

        return "".join(sql), args


class QueryModule(Component):

    implements(IRequestHandler, INavigationContributor, IWikiSyntaxProvider,
               IContentConverter)

    # IContentConverter methods
    def get_supported_conversions(self):
        yield ('rss', 'RSS Feed', 'xml',
               'trac.ticket.Query', 'application/rss+xml', 8)
        yield ('csv', 'Comma-delimited Text', 'csv',
               'trac.ticket.Query', 'text/csv', 8)
        yield ('tab', 'Tab-delimited Text', 'tsv',
               'trac.ticket.Query', 'text/tab-separated-values', 8)

    def convert_content(self, req, mimetype, query, key):
        if key == 'rss':
            return self.export_rss(req, query)
        elif key == 'csv':
            return self.export_csv(req, query, mimetype='text/csv')
        elif key == 'tab':
            return self.export_csv(req, query, '\t', 'text/tab-separated-values')

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'tickets'

    def get_navigation_items(self, req):
        from trac.ticket.report import ReportModule
        if req.perm.has_permission('TICKET_VIEW') and \
                not self.env.is_component_enabled(ReportModule):
            yield ('mainnav', 'tickets',
                   html.A('View Tickets', href=req.href.query()))

    # IRequestHandler methods

    def match_request(self, req):
        return req.path_info == '/query'

    def process_request(self, req):
        req.perm.assert_permission('TICKET_VIEW')

        constraints = self._get_constraints(req)
        if not constraints and not req.args.has_key('order'):
            # avoid displaying all tickets when the query module is invoked
            # with no parameters. Instead show only open tickets, possibly
            # associated with the user
            constraints = {'status': ('new', 'assigned', 'reopened')}
            if req.authname and req.authname != 'anonymous':
                constraints['owner'] = (req.authname,)
            else:
                email = req.session.get('email')
                name = req.session.get('name')
                if email or name:
                    constraints['cc'] = ('~%s' % email or name,)

        query = Query(self.env, constraints, req.args.get('order'),
                      req.args.has_key('desc'), req.args.get('group'),
                      req.args.has_key('groupdesc'),
                      req.args.has_key('verbose'))

        if req.args.has_key('update'):
            # Reset session vars
            for var in ('query_constraints', 'query_time', 'query_tickets'):
                if req.session.has_key(var):
                    del req.session[var]
            req.redirect(query.get_href(req))

        # Add registered converters
        for conversion in Mimeview(self.env).get_supported_conversions(
                                             'trac.ticket.Query'):
            add_link(req, 'alternate',
                     query.get_href(req, format=conversion[0]),
                     conversion[1], conversion[3])

        constraints = {}
        for k, v in query.constraints.items():
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
        req.hdf['query.constraints'] = constraints

        format = req.args.get('format')
        if format:
            Mimeview(self.env).send_converted(req, 'trac.ticket.Query', query,
                                              format, 'query')

        self.display_html(req, query)
        return 'query.cs', None

    # Internal methods

    def _get_constraints(self, req):
        constraints = {}
        ticket_fields = [f['name'] for f in
                         TicketSystem(self.env).get_ticket_fields()]

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
                    vals = map(lambda x: mode + x, vals)
                if remove_constraints.has_key(field):
                    idx = remove_constraints[field]
                    if idx >= 0:
                        del vals[idx]
                        if not vals:
                            continue
                    else:
                        continue
                constraints[field] = vals

        return constraints

    def _get_constraint_modes(self):
        modes = {}
        modes['text'] = [
            {'name': "contains", 'value': "~"},
            {'name': "doesn't contain", 'value': "!~"},
            {'name': "begins with", 'value': "^"},
            {'name': "ends with", 'value': "$"},
            {'name': "is", 'value': ""},
            {'name': "is not", 'value': "!"}
        ]
        modes['select'] = [
            {'name': "is", 'value': ""},
            {'name': "is not", 'value': "!"}
        ]
        return modes

    def display_html(self, req, query):
        req.hdf['title'] = 'Custom Query'
        add_stylesheet(req, 'common/css/report.css')
        add_script(req, 'common/js/query.js')

        db = self.env.get_db_cnx()

        for field in query.fields:
            if field['type'] == 'textarea':
                continue
            hdf = {}
            hdf.update(field)
            del hdf['name']
            req.hdf['query.fields.' + field['name']] = hdf
        req.hdf['query.modes'] = self._get_constraint_modes()

        # For clients without JavaScript, we add a new constraint here if
        # requested
        if req.args.has_key('add'):
            field = req.args.get('add_filter')
            if field:
                idx = 0
                if query.constraints.has_key(field):
                    idx = len(query.constraints[field])
                req.hdf['query.constraints.%s.values.%d' % (field, idx)] = ''

        cols = query.get_columns()
        labels = dict([(f['name'], f['label']) for f in query.fields])
        for idx, col in enumerate(cols):
            req.hdf['query.headers.%d' % idx] = {
                'name': col, 'label': labels.get(col, 'Ticket'),
                'href': query.get_href(req, order=col,
                                       desc=(col == query.order and
                                             not query.desc))
            }

        href = req.href.query(group=query.group,
                              groupdesc=query.groupdesc and 1 or None,
                              verbose=query.verbose and 1 or None,
                              **query.constraints)
        req.hdf['query.order'] = query.order
        req.hdf['query.href'] = href
        if query.desc:
            req.hdf['query.desc'] = True
        if query.group:
            req.hdf['query.group'] = query.group
            if query.groupdesc:
                req.hdf['query.groupdesc'] = True
        if query.verbose:
            req.hdf['query.verbose'] = True

        tickets = query.execute(req, db)
        req.hdf['query.num_matches'] = len(tickets)

        # The most recent query is stored in the user session
        orig_list = rest_list = None
        orig_time = int(time.time())
        query_constraints = unicode(query.constraints)
        if query_constraints != req.session.get('query_constraints') \
                or int(req.session.get('query_time', 0)) < orig_time - 3600:
            # New or outdated query, (re-)initialize session vars
            req.session['query_constraints'] = query_constraints
            req.session['query_tickets'] = ' '.join([str(t['id']) for t in tickets])
        else:
            orig_list = [int(id) for id in req.session.get('query_tickets', '').split()]
            rest_list = orig_list[:]
            orig_time = int(req.session.get('query_time', 0))
        req.session['query_href'] = query.get_href(req)
        req.session['query_time'] = orig_time

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
                            'summary': html.EM(e)}
                tickets.insert(orig_list.index(rest_id), data)

        num_matches_group = {}
        for ticket in tickets:
            if orig_list:
                # Mark tickets added or changed since the query was first
                # executed
                if int(ticket['time']) > orig_time:
                    ticket['added'] = True
                elif int(ticket['changetime']) > orig_time:
                    ticket['changed'] = True
            for field, value in ticket.items():
                if field == query.group:
                    num_matches_group[value] = num_matches_group.get(value, 0)+1
                if field == 'time':
                    ticket[field] = format_datetime(value)
                elif field == 'description':
                    ticket[field] = wiki_to_html(value or '', self.env, req, db)
                else:
                    ticket[field] = value

        req.hdf['query.results'] = tickets
        req.hdf['query.num_matches_group'] = num_matches_group
        req.session['query_tickets'] = ' '.join([str(t['id']) for t in tickets])

        # Kludge: only show link to available reports if the report module is
        # actually enabled
        from trac.ticket.report import ReportModule
        if req.perm.has_permission('REPORT_VIEW') and \
           self.env.is_component_enabled(ReportModule):
            req.hdf['query.report_href'] = req.href.report()

    def export_csv(self, req, query, sep=',', mimetype='text/plain'):
        content = StringIO()
        cols = query.get_columns()
        content.write(sep.join([col for col in cols]) + CRLF)

        results = query.execute(req, self.env.get_db_cnx())
        for result in results:
            content.write(sep.join([unicode(result[col]).replace(sep, '_')
                                                        .replace('\n', ' ')
                                                        .replace('\r', ' ')
                                    for col in cols]) + CRLF)
        return (content.getvalue(), '%s;charset=utf-8' % mimetype)

    def export_rss(self, req, query):
        query.verbose = True
        db = self.env.get_db_cnx()
        results = query.execute(req, db)
        for result in results:
            result['href'] = req.abs_href.ticket(result['id'])
            if result['reporter'].find('@') == -1:
                result['reporter'] = ''
            if result['description']:
                # unicode() cancels out the Markup() returned by wiki_to_html
                descr = wiki_to_html(result['description'], self.env, req, db,
                                     absurls=True)
                result['description'] = unicode(descr)
            if result['time']:
                result['time'] = http_date(result['time'])
        req.hdf['query.results'] = results
        req.hdf['query.href'] = req.abs_href.query(group=query.group,
                groupdesc=query.groupdesc and 1 or None,
                verbose=query.verbose and 1 or None,
                **query.constraints)
        return (req.hdf.render('query_rss.cs'), 'application/rss+xml')

    # IWikiSyntaxProvider methods
    
    def get_wiki_syntax(self):
        return []
    
    def get_link_resolvers(self):
        yield ('query', self._format_link)

    def _format_link(self, formatter, ns, query, label):
        if query[0] == '?':
            return html.A(label, class_='query',
                          href=formatter.href.query() + query.replace(' ', '+'))
        else:
            from trac.ticket.query import Query, QuerySyntaxError
            try:
                query = Query.from_string(formatter.env, query)
                return html.A(label, href=query.get_href(formatter), # Hack
                              class_='query')
            except QuerySyntaxError, e:
                return html.EM('[Error: %s]' % e, class_='error')


class TicketQueryMacro(WikiMacroBase):
    """Macro that lists tickets that match certain criteria.
    
    This macro accepts two parameters, the second of which is optional.
    
    The first parameter is the query itself, and uses the same syntax as for
    {{{query:}}} wiki links. The second parameter determines how the list of
    tickets is presented: the default presentation is to list the ticket ID next
    to the summary, with each ticket on a separate line. If the second parameter
    is given and set to '''compact''' then the tickets are presented as a
    comma-separated list of ticket IDs.
    """

    def render_macro(self, req, name, content):
        query_string = ''
        compact = 0
        argv = content.split(',')
        if len(argv) > 0:
            query_string = argv[0]
            if len(argv) > 1:
                if argv[1].strip().lower() == 'compact':
                    compact = 1

        buf = StringIO()

        query = Query.from_string(self.env, query_string)
        query.order = 'id'
        tickets = query.execute(req)
        if tickets:
            if compact:
                links = []
                for ticket in tickets:
                    href = req.href.ticket(int(ticket['id']))
                    summary = escape(shorten_line(ticket['summary']))
                    a = '<a class="%s ticket" href="%s" title="%s">#%s</a>' % \
                        (ticket['status'], href, summary, ticket['id'])
                    links.append(a)
                buf.write(', '.join(links))
            else:
                buf.write('<dl class="wiki compact">')
                for ticket in tickets:
                    href = req.href.ticket(int(ticket['id']))
                    dt = '<dt><a class="%s ticket" href="%s">#%s</a></dt>' % \
                         (ticket['status'], href, ticket['id'])
                    buf.write(dt)
                    buf.write('<dd>%s</dd>' % (escape(ticket['summary'])))
                buf.write('</dl>')

        return buf.getvalue()
