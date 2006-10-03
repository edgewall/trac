# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2006 Edgewall Software
# Copyright (C) 2004-2005 Christopher Lenz <cmlenz@gmx.de>
# Copyright (C) 2005-2006 Christian Boos <cboos@neuf.fr>
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

import re
from StringIO import StringIO
import time

from trac.core import *
from trac.db import get_column_names
from trac.perm import IPermissionRequestor
from trac.ticket import Ticket, TicketSystem
from trac.util.html import escape, html, unescape
from trac.util.text import shorten_line, CRLF
from trac.web import IRequestHandler
from trac.web.chrome import add_link, add_script, add_stylesheet, \
                            INavigationContributor, Chrome
from trac.wiki.api import IWikiSyntaxProvider, parse_args
from trac.wiki.formatter import wiki_to_html, wiki_to_oneliner
from trac.wiki.macros import WikiMacroBase # TODO: should be moved in .api
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

    def template_data(self, req, db, tickets, orig_list=None, orig_time=None):
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
        headers = [{
            'name': col, 'label': labels.get(col, 'Ticket'),
            'href': self.get_href(req, order=col, desc=(col == self.order and
                                                         not self.desc))
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

        groups = {}
        groupsequence = []
        for ticket in tickets:
            if orig_list:
                # Mark tickets added or changed since the query was first
                # executed
                if int(ticket['time']) > orig_time:
                    ticket['added'] = True
                elif int(ticket['changetime']) > orig_time:
                    ticket['changed'] = True
            for field, value in ticket.items():
                if field == self.group:
                    groups.setdefault(value, []).append(ticket)
                    if not groupsequence or groupsequence[-1] != value:
                        groupsequence.append(value)
                if field == 'time':
                    ticket[field] = value
                elif field == 'description':
                    ticket[field] = \
                                  wiki_to_html(value or '', self.env, req, db)
                else:
                    ticket[field] = value
        groupsequence = [(value, groups[value]) for value in groupsequence]

        return {'query': self,
                'constraints': constraints,
                'headers': headers,
                'fields': fields,
                'modes': modes,
                'tickets': tickets,
                'groups': groupsequence or [(None, tickets)]}


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

    def display_html(self, req, query):
        db = self.env.get_db_cnx()
        tickets = query.execute(req, db)

        # The most recent query is stored in the user session;
        orig_list = rest_list = None
        orig_time = int(time.time())
        query_constraints = unicode(query.constraints)
        if query_constraints != req.session.get('query_constraints') \
                or int(req.session.get('query_time', 0)) < orig_time - 3600:
            # New or outdated query, (re-)initialize session vars
            req.session['query_constraints'] = query_constraints
            req.session['query_tickets'] = ' '.join([str(t['id'])
                                                     for t in tickets])
        else:
            orig_list = [int(id)
                         for id in req.session.get('query_tickets', '').split()]
            rest_list = orig_list[:]
            orig_time = int(req.session.get('query_time', 0))

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

        data = query.template_data(req, db, tickets, orig_list, orig_time)

        # For clients without JavaScript, we add a new constraint here if
        # requested
        constraints = data['constraints']
        if req.args.has_key('add'):
            field = req.args.get('add_filter')
            if field:
                constraint = constraints.setdefault(field, {})
                constraint.setdefault('values', []).append('')

        # FIXME: is this used somewhere?
        query_href = req.href.query(group=query.group,
                                    groupdesc=query.groupdesc and 1 or None,
                                    verbose=query.verbose and 1 or None,
                                    **query.constraints)

        req.session['query_href'] = query.get_href(req)
        req.session['query_time'] = orig_time
        req.session['query_tickets'] = ' '.join([str(t['id']) for t in tickets])

        # Kludge: only show link to available reports if the report module is
        # actually enabled
        from trac.ticket.report import ReportModule
        report_href = None
        if req.perm.has_permission('REPORT_VIEW') and \
               self.env.is_component_enabled(ReportModule):
            report_href = req.href.report()
        data['report_href'] = report_href
        # data['href'] = query_href, # FIXME: apparently not used in template...

        data['title'] = 'Custom Query',

        add_stylesheet(req, 'common/css/report.css')
        add_script(req, 'common/js/query.js')
        
        return 'query.html', data, None

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
            if result['reporter'].find('@') == -1:
                result['reporter'] = ''
            if result['description']:
                result['description'] = wiki_to_html(result['description'],
                                                     self.env, req, db,
                                                     absurls=True)
        query_href = req.abs_href.query(group=query.group,
                                        groupdesc=query.groupdesc and 1 or None,
                                        verbose=query.verbose and 1 or None,
                                        **query.constraints)
        data = {'results': results, 'query_href': query_href}
        template = Chrome(self.env).load_template('query.rss', req, data)
        return template.generate(**data).render('xml'), 'application/rss+xml'

    # IWikiSyntaxProvider methods
    
    def get_wiki_syntax(self):
        return []
    
    def get_link_resolvers(self):
        yield ('query', self._format_link)

    def _format_link(self, formatter, ns, query, label):
        if query.startswith('?'):
            return html.A(label, class_='query',
                          href=formatter.href.query() + query.replace(' ', '+'))
        else:
            try:
                query = Query.from_string(formatter.env, query)
                return html.A(label, href=query.get_href(formatter), # Hack
                              class_='query')
            except QuerySyntaxError, e:
                return html.EM('[Error: %s]' % e, class_='error')


class TicketQueryMacro(WikiMacroBase):
    """Macro that lists tickets that match certain criteria.
    
    This macro accepts a comma-separated list of keyed parameters,
    in the form "key=value".

    If the key is the name of a field, the value must use the same syntax as for
    `query:` wiki links (but '''not''' the variant syntax starting with "?").

    There are

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
    (defaults to not being set). For '''table''' format only.

    The optional `groupdesc` parameter indicates whether the natural display
    order of the groups should be reversed (defaults to '''false''').
    For '''table''' format only.

    The optional `verbose` parameter can be set to a true value in order to
    get the description for the listed tickets. For '''table''' format only.

    For compatibility with Trac 0.10, if there's a second positional parameter
    given to the macro, it will be used to specify the `format`.
    Also, using "&" as a field separator still work but is deprecated.
    """

    def render_macro(self, req, name, content):
        query_string = ''
        argv, kwargs = parse_args(content)
        if len(argv) > 0 and not 'format' in kwargs: # 0.10 compatibility hack
            kwargs['format'] = argv[0]

        kwargs.setdefault('order', 'id')
        format = kwargs.pop('format', 'list').strip().lower()
        query_string = '&'.join(['%s=%s' % item for item in kwargs.iteritems()])

        query = Query.from_string(self.env, query_string)
        tickets = query.execute(req)

        if format == 'count':
            cnt = tickets and len(tickets) or 0
            return html.SPAN(cnt, title='%d tickets for which %s' %
                             (cnt, query_string))
        if tickets:
            def ticket_anchor(ticket):
                return html.A('#%s' % ticket['id'],
                              class_=ticket['status'],
                              href=req.href.ticket(int(ticket['id'])),
                              title=shorten_line(ticket['summary']))
            if format == 'compact':
                alist = [ticket_anchor(ticket) for ticket in tickets]
                return html.SPAN(alist[0], *[(', ', a) for a in alist[1:]])
            elif format == 'table':
                db = self.env.get_db_cnx()
                tickets = query.execute(req, db)
                data = query.template_data(req, db, tickets)

                add_stylesheet(req, 'common/css/report.css')
                
                template = Chrome(self.env).load_template('query_div.html',
                                                          req, data)
                return template.generate(**data).render('xhtml')
            else:
                return html.DL([(html.DT(ticket_anchor(ticket)),
                                 html.DD(ticket['summary']))
                                for ticket in tickets], class_='wiki compact')
