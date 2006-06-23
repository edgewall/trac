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
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://projects.edgewall.com/trac/.
#
# Author: Jonas Borgström <jonas@edgewall.com>

import re
from StringIO import StringIO
import urllib

from trac import util
from trac.core import *
from trac.db import get_column_names
from trac.perm import IPermissionRequestor
from trac.util import sorted
from trac.util.datefmt import format_date, format_time, format_datetime, \
                               http_date
from trac.util.markup import html
from trac.web import IRequestHandler
from trac.web.chrome import add_link, add_stylesheet, INavigationContributor
from trac.wiki import wiki_to_html, IWikiSyntaxProvider, Formatter


class ReportModule(Component):

    implements(INavigationContributor, IPermissionRequestor, IRequestHandler,
               IWikiSyntaxProvider)

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'tickets'

    def get_navigation_items(self, req):
        if not req.perm.has_permission('REPORT_VIEW'):
            return
        yield ('mainnav', 'tickets',
               html.A('View Tickets', href=req.href.report()))

    # IPermissionRequestor methods  

    def get_permission_actions(self):  
        actions = ['REPORT_CREATE', 'REPORT_DELETE', 'REPORT_MODIFY',  
                   'REPORT_SQL_VIEW', 'REPORT_VIEW']  
        return actions + [('REPORT_ADMIN', actions)]  

    # IRequestHandler methods

    def match_request(self, req):
        match = re.match(r'/report(?:/([0-9]+))?', req.path_info)
        if match:
            if match.group(1):
                req.args['id'] = match.group(1)
            return True

    def process_request(self, req):
        req.perm.assert_permission('REPORT_VIEW')

        # did the user ask for any special report?
        id = int(req.args.get('id', -1))
        action = req.args.get('action', 'list')

        db = self.env.get_db_cnx()

        if req.method == 'POST':
            if action == 'new':
                self._do_create(req, db)
            elif action == 'delete':
                self._do_delete(req, db, id)
            elif action == 'edit':
                self._do_save(req, db, id)
        elif action in ('copy', 'edit', 'new'):
            self._render_editor(req, db, id, action == 'copy')
        elif action == 'delete':
            self._render_confirm_delete(req, db, id)
        else:
            resp = self._render_view(req, db, id)
            if not resp:
               return None
            template, content_type = resp
            if content_type:
               return resp

        if id != -1 or action == 'new':
            add_link(req, 'up', req.href.report(), 'Available Reports')

            # Kludge: Reset session vars created by query module so that the
            # query navigation links on the ticket page don't confuse the user
            for var in ('query_constraints', 'query_time', 'query_tickets'):
                if req.session.has_key(var):
                    del req.session[var]

        # Kludge: only show link to custom query if the query module is actually
        # enabled
        from trac.ticket.query import QueryModule
        if req.perm.has_permission('TICKET_VIEW') and \
           self.env.is_component_enabled(QueryModule):
            req.hdf['report.query_href'] = req.href.query()

        add_stylesheet(req, 'common/css/report.css')
        return 'report.cs', None

    # Internal methods

    def _do_create(self, req, db):
        req.perm.assert_permission('REPORT_CREATE')

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
        req.perm.assert_permission('REPORT_DELETE')

        if req.args.has_key('cancel'):
            req.redirect(req.href.report(id))

        cursor = db.cursor()
        cursor.execute("DELETE FROM report WHERE id=%s", (id,))
        db.commit()
        req.redirect(req.href.report())

    def _do_save(self, req, db, id):
        """
        Saves report changes to the database
        """
        req.perm.assert_permission('REPORT_MODIFY')

        if not req.args.has_key('cancel'):
            title = req.args.get('title', '')
            query = req.args.get('query', '')
            description = req.args.get('description', '')
            cursor = db.cursor()
            cursor.execute("UPDATE report SET title=%s,query=%s,description=%s "
                           "WHERE id=%s", (title, query, description, id))
            db.commit()
        req.redirect(req.href.report(id))

    def _render_confirm_delete(self, req, db, id):
        req.perm.assert_permission('REPORT_DELETE')

        cursor = db.cursor()
        cursor.execute("SELECT title FROM report WHERE id = %s", (id,))
        row = cursor.fetchone()
        if not row:
            raise TracError('Report %s does not exist.' % id,
                            'Invalid Report Number')
        req.hdf['title'] = 'Delete Report {%s} %s' % (id, row[0])
        req.hdf['report'] = {
            'id': id,
            'mode': 'delete',
            'title': row[0],
            'href': req.href.report(id)
        }

    def _render_editor(self, req, db, id, copy=False):
        if id == -1:
            req.perm.assert_permission('REPORT_CREATE')
            title = query = description = ''
        else:
            req.perm.assert_permission('REPORT_MODIFY')
            cursor = db.cursor()
            cursor.execute("SELECT title,description,query FROM report "
                           "WHERE id=%s", (id,))
            row = cursor.fetchone()
            if not row:
                raise TracError('Report %s does not exist.' % id,
                                'Invalid Report Number')
            title = row[0] or ''
            description = row[1] or ''
            query = row[2] or ''

        if copy:
            title += ' (copy)'

        if copy or id == -1:
            req.hdf['title'] = 'Create New Report'
            req.hdf['report.href'] = req.href.report()
            req.hdf['report.action'] = 'new'
        else:
            req.hdf['title'] = 'Edit Report {%d} %s' % (id, title)
            req.hdf['report.href'] = req.href.report(id)
            req.hdf['report.action'] = 'edit'

        req.hdf['report.id'] = id
        req.hdf['report.mode'] = 'edit'
        req.hdf['report.title'] = title
        req.hdf['report.sql'] = query
        req.hdf['report.description'] = description

    def _render_view(self, req, db, id):
        """
        uses a user specified sql query to extract some information
        from the database and presents it as a html table.
        """
        actions = {'create': 'REPORT_CREATE', 'delete': 'REPORT_DELETE',
                   'modify': 'REPORT_MODIFY'}
        for action in [k for k,v in actions.items()
                       if req.perm.has_permission(v)]:
            req.hdf['report.can_' + action] = True
        req.hdf['report.href'] = req.href.report(id)

        try:
            args = self.get_var_args(req)
        except ValueError,e:
            raise TracError, 'Report failed: %s' % e

        title, description, sql = self.get_info(db, id, args)

        format = req.args.get('format')
        if format == 'sql':
            self._render_sql(req, id, title, description, sql)
            return

        req.hdf['report.mode'] = 'list'
        if id > 0:
            title = '{%i} %s' % (id, title)
        req.hdf['title'] = title
        req.hdf['report.title'] = title
        req.hdf['report.id'] = id
        req.hdf['report.description'] = wiki_to_html(description, self.env, req)
        if id != -1:
            self.add_alternate_links(req, args)

        try:
            cols, rows = self.execute_report(req, db, id, sql, args)
        except Exception, e:
            req.hdf['report.message'] = 'Report execution failed: %s' % e
            return 'report.cs', None

        # Convert the header info to HDF-format
        idx = 0
        for col in cols:
            title=col.capitalize()
            prefix = 'report.headers.%d' % idx
            req.hdf['%s.real' % prefix] = col[0]
            if title.startswith('__') and title.endswith('__'):
                continue
            elif title[0] == '_' and title[-1] == '_':
                title = title[1:-1].capitalize()
                req.hdf[prefix + '.fullrow'] = 1
            elif title[0] == '_':
                continue
            elif title[-1] == '_':
                title = title[:-1]
                req.hdf[prefix + '.breakrow'] = 1
            req.hdf[prefix] = title
            idx = idx + 1

        if req.args.has_key('sort'):
            sortCol = req.args.get('sort')
            colIndex = None
            hiddenCols = 0
            for x in range(len(cols)):
                colName = cols[x]
                if colName == sortCol:
                    colIndex = x
                if colName.startswith('__') and colName.endswith('__'):
                    hiddenCols += 1
            if colIndex != None:
                k = 'report.headers.%d.asc' % (colIndex - hiddenCols)
                asc = req.args.get('asc', None)
                if asc:
                    asc = int(asc) # string '0' or '1' to int/boolean
                else:
                    asc = 1
                req.hdf[k] = asc
                def sortkey(row):
                    val = row[colIndex]
                    if isinstance(val, basestring):
                        val = val.lower()
                    return val
                rows = sorted(rows, key=sortkey, reverse=(not asc))

        # Get the email addresses of all known users
        email_map = {}
        for username, name, email in self.env.get_known_users():
            if email:
                email_map[username] = email

        # Convert the rows and cells to HDF-format
        row_idx = 0
        for row in rows:
            col_idx = 0
            numrows = len(row)
            for cell in row:
                cell = unicode(cell)
                column = cols[col_idx]
                value = {}
                # Special columns begin and end with '__'
                if column.startswith('__') and column.endswith('__'):
                    value['hidden'] = 1
                elif (column[0] == '_' and column[-1] == '_'):
                    value['fullrow'] = 1
                    column = column[1:-1]
                    req.hdf[prefix + '.breakrow'] = 1
                elif column[-1] == '_':
                    value['breakrow'] = 1
                    value['breakafter'] = 1
                    column = column[:-1]
                elif column[0] == '_':
                    value['hidehtml'] = 1
                    column = column[1:]
                if column in ('ticket', 'id', '_id', '#', 'summary'):
                    id_cols = [idx for idx, col in enumerate(cols)
                               if col in ('ticket', 'id', '_id')]
                    if id_cols:
                        id_val = row[id_cols[0]]
                        value['ticket_href'] = req.href.ticket(id_val)
                elif column == 'description':
                    desc = wiki_to_html(cell, self.env, req, db,
                                        absurls=(format == 'rss'))
                    value['parsed'] = format == 'rss' and unicode(desc) or desc
                elif column == 'reporter':
                    if cell.find('@') != -1:
                        value['rss'] = cell
                    elif cell in email_map:
                        value['rss'] = email_map[cell]
                elif column == 'report':
                    value['report_href'] = req.href.report(cell)
                elif column in ('time', 'date','changetime', 'created', 'modified'):
                    value['date'] = format_date(cell)
                    value['time'] = format_time(cell)
                    value['datetime'] = format_datetime(cell)
                    value['gmt'] = http_date(cell)
                prefix = 'report.items.%d.%s' % (row_idx, unicode(column))
                req.hdf[prefix] = unicode(cell)
                for key in value.keys():
                    req.hdf[prefix + '.' + key] = value[key]

                col_idx += 1
            row_idx += 1
        req.hdf['report.numrows'] = row_idx

        if format == 'rss':
            return 'report_rss.cs', 'application/rss+xml'
        elif format == 'csv':
            self._render_csv(req, cols, rows)
            return None
        elif format == 'tab':
            self._render_csv(req, cols, rows, '\t')
            return None

        return 'report.cs', None

    def add_alternate_links(self, req, args):
        params = args
        if req.args.has_key('sort'):
            params['sort'] = req.args['sort']
        if req.args.has_key('asc'):
            params['asc'] = req.args['asc']
        href = ''
        if params:
            href = '&' + urllib.urlencode(params)
        add_link(req, 'alternate', '?format=rss' + href, 'RSS Feed',
                 'application/rss+xml', 'rss')
        add_link(req, 'alternate', '?format=csv' + href,
                 'Comma-delimited Text', 'text/plain')
        add_link(req, 'alternate', '?format=tab' + href,
                 'Tab-delimited Text', 'text/plain')
        if req.perm.has_permission('REPORT_SQL_VIEW'):
            add_link(req, 'alternate', '?format=sql', 'SQL Query',
                     'text/plain')

    def execute_report(self, req, db, id, sql, args):
        sql, args = self.sql_sub_vars(req, sql, args)
        if not sql:
            raise TracError('Report %s has no SQL query.' % id)
        if sql.find('__group__') == -1:
            req.hdf['report.sorting.enabled'] = 1

        self.log.debug('Executing report with SQL "%s" (%s)', sql, args)

        cursor = db.cursor()
        cursor.execute(sql, args)

        # FIXME: fetchall should probably not be used.
        info = cursor.fetchall() or []
        cols = get_column_names(cursor)

        db.rollback()

        return cols, info

    def get_info(self, db, id, args):
        if id == -1:
            # If no particular report was requested, display
            # a list of available reports instead
            title = 'Available Reports'
            sql = 'SELECT id AS report, title FROM report ORDER BY report'
            description = 'This is a list of reports available.'
        else:
            cursor = db.cursor()
            cursor.execute("SELECT title,query,description from report "
                           "WHERE id=%s", (id,))
            row = cursor.fetchone()
            if not row:
                raise TracError('Report %d does not exist.' % id,
                                'Invalid Report Number')
            title = row[0] or ''
            sql = row[1]
            description = row[2] or ''

        return [title, description, sql]

    def get_var_args(self, req):
        report_args = {}
        for arg in req.args.keys():
            if not arg == arg.upper():
                continue
            report_args[arg] = req.args.get(arg)

        # Set some default dynamic variables
        if not report_args.has_key('USER'):
            report_args['USER'] = req.authname

        return report_args

    def sql_sub_vars(self, req, sql, args):
        values = []
        def add_value(aname):
            try:
                arg = args[aname]
            except KeyError:
                raise TracError("Dynamic variable '$%s' not defined." \
                                % aname)
            req.hdf['report.var.' + aname] = arg
            values.append(arg)

        # simple parameter substitution
        def repl(match):
            add_value(match.group(1))
            return '%s'

        var_re = re.compile("'?[$]([A-Z]+)'?")
        sql_io = StringIO()

        # break SQL into literals and non-literals to handle replacing
        # variables within them with query parameters
        for expr in re.split("('(?:[^']|(?:''))*')", sql):
            sql_io.write(var_re.sub(repl, expr))
        return sql_io.getvalue(), values

    def _render_csv(self, req, cols, rows, sep=','):
        req.send_response(200)
        req.send_header('Content-Type', 'text/plain;charset=utf-8')
        req.end_headers()

        req.write(sep.join(cols) + '\r\n')
        for row in rows:
            req.write(sep.join(
                [unicode(c).replace(sep,"_")
                 .replace('\n',' ').replace('\r',' ') for c in row]) + '\r\n')

    def _render_sql(self, req, id, title, description, sql):
        req.perm.assert_permission('REPORT_SQL_VIEW')
        req.send_response(200)
        req.send_header('Content-Type', 'text/plain;charset=utf-8')
        req.end_headers()

        req.write('-- ## %s: %s ## --\n\n' % (id, title))
        if description:
            req.write('-- %s\n\n' % '\n-- '.join(description.splitlines()))
        req.write(sql)
        
    # IWikiSyntaxProvider methods
    
    def get_link_resolvers(self):
        yield ('report', self._format_link)

    def get_wiki_syntax(self):
        yield (r"!?\{(?P<it_report>%s\s*)\d+\}" % Formatter.INTERTRAC_SCHEME,
               lambda x, y, z: self._format_link(x, 'report', y[1:-1], y, z))

    def _format_link(self, formatter, ns, target, label, fullmatch=None):
        intertrac = formatter.shorthand_intertrac_helper(ns, target, label,
                                                         fullmatch)
        if intertrac:
            return intertrac
        report, args, fragment = formatter.split_link(target)
        return html.A(label, href=formatter.href.report(report) + args,
                      class_='report')
