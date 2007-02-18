# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2006 Edgewall Software
# Copyright (C) 2003-2004 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2006 Christian Boos <cboos@neuf.fr>
# Copyright (C) 2006 Matthew Good <trac@matt-good.net>
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
# Author: Jonas Borgström <jonas@edgewall.com>

import csv
import re
from StringIO import StringIO

from trac.config import IntOption
from trac.context import Context
from trac.core import *
from trac.db import get_column_names
from trac.perm import IPermissionRequestor
from trac.util import sorted
from trac.util.text import to_unicode, unicode_urlencode
from trac.util.html import html
from trac.web.api import IRequestHandler, RequestDone
from trac.web.chrome import add_link, add_stylesheet, INavigationContributor, \
                            Chrome
from trac.wiki import IWikiSyntaxProvider, WikiParser

class ReportModule(Component):

    implements(INavigationContributor, IPermissionRequestor, IRequestHandler,
               IWikiSyntaxProvider)

    default_report = IntOption('ticket', 'default_report', -1,
        """Report number to show when selecting ''View Tickets''.
        Defaults to `-1`, the list of available reports.
        (Since 0.11)""")

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'tickets'

    def get_navigation_items(self, req):
        if 'REPORT_VIEW' in req.perm:
            yield ('mainnav', 'tickets',
                   html.A('View Tickets', href=req.href.report()))

    # IPermissionRequestor methods  

    def get_permission_actions(self):  
        actions = ['REPORT_CREATE', 'REPORT_DELETE', 'REPORT_MODIFY',  
                   'REPORT_SQL_VIEW', 'REPORT_VIEW']  
        return actions + [('REPORT_ADMIN', actions)]  

    # IRequestHandler methods

    def match_request(self, req):
        match = re.match(r'/report(?:/(-?[0-9]+))?', req.path_info)
        if match:
            if match.group(1):
                req.args['id'] = match.group(1)
            return True

    def process_request(self, req):
        req.perm.require('REPORT_VIEW')

        # did the user ask for any special report?
        id = int(req.args.get('id', self.default_report))
        action = req.args.get('action', 'view')

        db = self.env.get_db_cnx()

        data = {}
        if req.method == 'POST':
            if action == 'new':
                self._do_create(req, db)
            elif action == 'delete':
                self._do_delete(req, db, id)
            elif action == 'edit':
                self._do_save(req, db, id)
        elif action in ('copy', 'edit', 'new'):
            template = 'report_edit.html'
            data = self._render_editor(req, db, id, action=='copy')
        elif action == 'delete':
            template = 'report_delete.html'
            data = self._render_confirm_delete(req, db, id)
        else:
            template, data, content_type = self._render_view(req, db, id)
            if content_type: # i.e. alternate format
               return template, data, content_type

        if id != -1 or action == 'new':
            add_link(req, 'up', req.href.report(-1), 'Available Reports')

        # Kludge: only show link to custom query if the query module is actually
        # enabled
        from trac.ticket.query import QueryModule
        if 'TICKET_VIEW' in req.perm and \
                self.env.is_component_enabled(QueryModule):
            data['query_href'] = req.href.query()

        add_stylesheet(req, 'common/css/report.css')
        return template, data, None

    # Internal methods

    def _do_create(self, req, db):
        req.perm.require('REPORT_CREATE')

        if req.args.has_key('cancel'):
            req.redirect(req.href.report())

        title = req.args.get('title', '')
        query = req.args.get('query', '')
        description = req.args.get('description', '')
        cursor = db.cursor()
        cursor.execute("INSERT INTO report (title,query,description) "
                       "VALUES (%s,%s,%s)", (title, query, description))
        id = db.get_last_id(cursor, 'report')
        db.commit()
        req.redirect(req.href.report(id))

    def _do_delete(self, req, db, id):
        req.perm.require('REPORT_DELETE')

        if 'cancel' in req.args:
            req.redirect(req.href.report(id))

        cursor = db.cursor()
        cursor.execute("DELETE FROM report WHERE id=%s", (id,))
        db.commit()
        req.redirect(req.href.report())

    def _do_save(self, req, db, id):
        """Save report changes to the database"""
        req.perm.require('REPORT_MODIFY')

        if 'cancel' not in req.args:
            title = req.args.get('title', '')
            query = req.args.get('query', '')
            description = req.args.get('description', '')
            cursor = db.cursor()
            cursor.execute("UPDATE report SET title=%s,query=%s,description=%s "
                           "WHERE id=%s", (title, query, description, id))
            db.commit()
        req.redirect(req.href.report(id))

    def _render_confirm_delete(self, req, db, id):
        req.perm.require('REPORT_DELETE')

        cursor = db.cursor()
        cursor.execute("SELECT title FROM report WHERE id=%s", (id,))
        for title, in cursor:
            return {'title': 'Delete Report {%s} %s' % (id, title),
                    'action': 'delete',
                    'report': {'id': id, 'title': title}}
        else:
            raise TracError('Report %s does not exist.' % id,
                            'Invalid Report Number')

    def _render_editor(self, req, db, id, copy):
        if id != -1:
            req.perm.require('REPORT_MODIFY')
            cursor = db.cursor()
            cursor.execute("SELECT title,description,query FROM report "
                           "WHERE id=%s", (id,))
            for title, description, query in cursor:
                break
            else:
                raise TracError('Report %s does not exist.' % id,
                                'Invalid Report Number')
        else:
            req.perm.require('REPORT_CREATE')
            title = description = query = ''
        # an explicitly given 'query' parameter will override the saved query
        query = req.args.get('query', query)

        if copy:
            title += ' (copy)'

        if copy or id == -1:
            data = {'title': 'Create New Report',
                    'action': 'new'}
        else:
            data = {'title': 'Edit Report {%d} %s' % (id, title),
                    'action': 'edit', 'error': req.args.get('error')}

        data['report'] = {'id': id, 'title': title,
                          'sql': query, 'description': description}
        return data

    def _render_view(self, req, db, id):
        """Retrieve the report results and pre-process them for rendering."""

        actions = {'create': 'REPORT_CREATE', 'delete': 'REPORT_DELETE',
                   'modify': 'REPORT_MODIFY'}
        perms = {}
        for action in [k for k,v in actions.items() if v in req.perm]:
            perms[action] = True
        try:
            args = self.get_var_args(req)
        except ValueError,e:
            raise TracError, 'Report failed: %s' % e

        if id == -1:
            # If no particular report was requested, display
            # a list of available reports instead
            title = 'Available Reports'
            sql = 'SELECT id AS report, title FROM report ORDER BY report'
            description = 'This is a list of available reports.'
        else:
            cursor = db.cursor()
            cursor.execute("SELECT title,query,description from report "
                           "WHERE id=%s", (id,))
            for title, sql, description in cursor:
                break
            else:
                raise TracError('Report %d does not exist.' % id,
                                'Invalid Report Number')

        # If this is a saved custom query. redirect to the query module
        #
        # A saved query is either an URL query (?... or query:?...),
        # or a query language expression (query:...).
        #
        # It may eventually contain newlines, for increased clarity.
        #
        query = ''.join([line.strip() for line in sql.splitlines()])
        if query and (query[0] == '?' or query.startswith('query:?')):
            query = query[0] == '?' and query or query[6:]
            report_id = 'report=%s' % id
            if 'report=' in query:
                if not report_id in query:
                    err = 'When specified, report number should be "%s".' % id
                    req.redirect(req.href.report(id, action='edit', error=err))
            else:
                if query[-1] != '?':
                    query += '&'
                query += report_id
            req.redirect(req.href.query() + query)
        elif query.startswith('query:'):
            try:
                from trac.ticket.query import Query, QuerySyntaxError
                query = Query.from_string(self.env, req, query[6:], report=id)
                req.redirect(query.get_href(req))
            except QuerySyntaxError, e:
                req.redirect(req.href.report(id, action='edit',
                                             error=to_unicode(e)))

        format = req.args.get('format')
        if format == 'sql':
            self._send_sql(req, id, title, description, sql)

        if id > 0:
            title = '{%i} %s' % (id, title)

        context = Context(self.env, req, 'report', id)
        data = {'action': 'view', 'title': title,
                'context': context,
                'report': {'id': id, 'title': title,
                           'description': description,
                           'can': perms, 'args': args}}
        try:
            cols, results = self.execute_report(req, db, id, sql, args)
        except Exception, e:
            data['message'] = 'Report execution failed: ' + to_unicode(e)
            return 'report_view.html', data, None

        sort_col = ''
        if req.args.has_key('sort'):
            sort_col = req.args.get('sort')
        asc = req.args.get('asc', 1)
        asc = bool(int(asc)) # string '0' or '1' to int/boolean

        # Place retrieved columns in groups, according to naming conventions
        #  * _col_ means fullrow, i.e. a group with one header
        #  * col_ means finish the current group and start a new one
        header_groups = [[]]
        for idx, col in enumerate(cols):
            header = {'col': col, 'title': col.strip('_').capitalize()}

            if col == sort_col:
                header['asc'] = asc
                def sortkey(row):
                    val = row[idx]
                    if isinstance(val, basestring):
                        val = val.lower()
                    return val
                results = sorted(results, key=sortkey, reverse=(not asc))

            header_group = header_groups[-1]
            
            if col.startswith('__') and col.endswith('__'): # __col__
                header['hidden'] = True
            elif col[0] == '_' and col[-1] == '_':          # _col_
                header_group = []
                header_groups.append(header_group)
                header_groups.append([])
            elif col[0] == '_':                             # _col
                header['hidden'] = True
            elif col[-1] == '_':                            # col_
                header_groups.append([])
            header_group.append(header)

        # Structure the rows and cells:
        #  - group rows according to __group__ value, if defined
        #  - group cells the same way headers are grouped
        row_groups = []
        prev_group_value = None
        for row_idx, result in enumerate(results):
            col_idx = 0
            cell_groups = []
            row = {'cell_groups': cell_groups}
            realm = 'ticket'
            for header_group in header_groups:
                cell_group = []
                for header in header_group:
                    value = unicode(result[col_idx])
                    col_idx += 1
                    cell = {'value': value, 'header': header}
                    col = header['col']
                    # Detect and create new group
                    if col == '__group__' and value != prev_group_value:
                        prev_group_value = value
                        row_groups.append((value, []))
                    # Other row properties
                    row['__idx__'] = row_idx
                    if col in ('__style__', '__color__',
                               '__fgcolor__', '__bgcolor__'):
                        row[col] = value
                    if col in ('report', 'ticket', 'id', '_id'):
                        row['id'] = value
                    # Special casing based on column name
                    col = col.strip('_')
                    if col == 'reporter':
                        cell['author'] = value
                    elif col == 'realm':
                        realm = value
                    cell_group.append(cell)
                cell_groups.append(cell_group)
            row['context'] = context(realm, row.get('id'))
            if row_groups:
                row_group = row_groups[-1][1]
            else:
                row_group = []
                row_groups = [(None, row_group)]
            row_group.append(row)

        # Get the email addresses of all known users
        email_map = {}
        if Chrome(self.env).show_email_addresses:
            for username, name, email in self.env.get_known_users():
                if email:
                    email_map[username] = email

        data.update({'header_groups': header_groups,
                     'row_groups': row_groups,
                     'numrows': len(results),
                     'sorting_enabled': len(row_groups)==1,
                     'email_map': email_map})

        if id:
            self.add_alternate_links(req, args)

        if format == 'rss':
            return 'report.rss', data, 'application/rss+xml'
        elif format == 'csv':
            filename = id and 'report_%s.csv' % id or 'report.csv'
            self._send_csv(req, cols, results, mimetype='text/csv',
                           filename=filename)
        elif format == 'tab':
            filename = id and 'report_%s.tsv' % id or 'report.tsv'
            self._send_csv(req, cols, results, '\t',
                           mimetype='text/tab-separated-values',
                           filename=filename)
        else:
            if id != -1:
                # reuse the session vars of the query module so that
                # the query navigation links on the ticket can be used to 
                # navigate report results as well
                try:
                    req.session['query_tickets'] = \
                        ' '.join([str(int(row['id']))
                                  for rg in row_groups for row in rg[1]])
                    req.session['query_href'] = req.href.report(id)
                    # Kludge: we have to clear the other query session
                    # variables, but only if the above succeeded 
                    for var in ('query_constraints', 'query_time'):
                        if var in req.session:
                            del req.session[var]
                except (ValueError, KeyError):
                    pass
            return 'report_view.html', data, None

    def add_alternate_links(self, req, args):
        params = args
        if req.args.has_key('sort'):
            params['sort'] = req.args['sort']
        if req.args.has_key('asc'):
            params['asc'] = req.args['asc']
        href = ''
        if params:
            href = '&' + unicode_urlencode(params)
        add_link(req, 'alternate', '?format=rss' + href, 'RSS Feed',
                 'application/rss+xml', 'rss')
        add_link(req, 'alternate', '?format=csv' + href,
                 'Comma-delimited Text', 'text/plain')
        add_link(req, 'alternate', '?format=tab' + href,
                 'Tab-delimited Text', 'text/plain')
        if 'REPORT_SQL_VIEW' in req.perm:
            add_link(req, 'alternate', '?format=sql', 'SQL Query',
                     'text/plain')

    def execute_report(self, req, db, id, sql, args):
        sql, args = self.sql_sub_vars(sql, args, db)
        if not sql:
            raise TracError('Report %s has no SQL query.' % id)
        self.log.debug('Executing report with SQL "%s" (%s)', sql, args)

        cursor = db.cursor()
        cursor.execute(sql, args)

        # FIXME: fetchall should probably not be used.
        info = cursor.fetchall() or []
        cols = get_column_names(cursor)

        db.rollback()

        return cols, info

    def get_var_args(self, req):
        report_args = {}
        for arg in req.args.keys():
            if not arg.isupper():
                continue
            report_args[arg] = req.args.get(arg)

        # Set some default dynamic variables
        if not report_args.has_key('USER'):
            report_args['USER'] = req.authname

        return report_args

    def sql_sub_vars(self, sql, args, db=None):
        if db is None:
            db = self.env.get_db_cnx()
        values = []
        def add_value(aname):
            try:
                arg = args[aname]
            except KeyError:
                raise TracError("Dynamic variable '$%s' not defined." % aname)
            values.append(arg)

        var_re = re.compile("[$]([A-Z]+)")

        # simple parameter substitution outside literal
        def repl(match):
            add_value(match.group(1))
            return '%s'

        # inside a literal break it and concatenate with the parameter
        def repl_literal(expr):
            parts = var_re.split(expr[1:-1])
            if len(parts) == 1:
                return expr
            params = parts[1::2]
            parts = ["'%s'" % p for p in parts]
            parts[1::2] = ['%s'] * len(params)
            for param in params:
                add_value(param)
            return db.concat(*parts)

        sql_io = StringIO()

        # break SQL into literals and non-literals to handle replacing
        # variables within them with query parameters
        for expr in re.split("('(?:[^']|(?:''))*')", sql):
            if expr.startswith("'"):
                sql_io.write(repl_literal(expr))
            else:
                sql_io.write(var_re.sub(repl, expr))
        return sql_io.getvalue(), values

    def _send_csv(self, req, cols, rows, sep=',', mimetype='text/plain',
                  filename=None):
        req.send_response(200)
        req.send_header('Content-Type', mimetype + ';charset=utf-8')
        if filename:
            req.send_header('Content-Disposition', 'filename=' + filename)
        req.end_headers()

        writer = csv.writer(req, delimiter=sep)
        writer.writerow([unicode(c).encode('utf-8') for c in cols])
        for row in rows:
            writer.writerow([unicode(c).encode('utf-8') for c in row])

        raise RequestDone

    def _send_sql(self, req, id, title, description, sql):
        req.perm.require('REPORT_SQL_VIEW')
        req.send_response(200)
        req.send_header('Content-Type', 'text/plain;charset=utf-8')
        if id:
            req.send_header('Content-Disposition',
                            'filename=report_%s.sql' % id)
        req.end_headers()

        req.write('-- ## %s: %s ## --\n\n' % (id, title))
        if description:
            req.write('-- %s\n\n' % '\n-- '.join(description.splitlines()))
        req.write(sql)
        raise RequestDone
        
    # IWikiSyntaxProvider methods
    
    def get_link_resolvers(self):
        yield ('report', self._format_link)

    def get_wiki_syntax(self):
        yield (r"!?\{(?P<it_report>%s\s*)\d+\}" % WikiParser.INTERTRAC_SCHEME,
               lambda x, y, z: self._format_link(x, 'report', y[1:-1], y, z))

    def _format_link(self, formatter, ns, target, label, fullmatch=None):
        intertrac = formatter.shorthand_intertrac_helper(ns, target, label,
                                                         fullmatch)
        if intertrac:
            return intertrac
        report, args, fragment = formatter.split_link(target)
        return html.A(label, href=formatter.href.report(report) + args,
                      class_='report')
