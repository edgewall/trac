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

from __future__ import generators
import re
import time
import types
import urllib

from trac import util
from trac.core import *
from trac.perm import IPermissionRequestor
from trac.web.chrome import add_link, add_stylesheet, INavigationContributor
from trac.web.main import IRequestHandler
from trac.wiki import wiki_to_html, IWikiSyntaxProvider


dynvars_re = re.compile('\$([A-Z]+)')
dynvars_disallowed_var_chars_re = re.compile('[^A-Z0-9_]')
dynvars_disallowed_value_chars_re = re.compile(r'[^a-zA-Z0-9-_@.,\\]')

try:
    _StringTypes = [types.StringType, types.UnicodeType]
except AttributeError:
    _StringTypes = [types.StringType]


class ColumnSorter:

    def __init__(self, columnIndex, asc=1):
        self.columnIndex = columnIndex
        self.asc = asc

    def sort(self, x, y):
        const = -1
        if not self.asc:
            const = 1

        # make sure to ignore case in comparisons
        realX = x[self.columnIndex]
        if type(realX) in _StringTypes:
            realX = realX.lower()
        realY = y[self.columnIndex]
        if type(realY) in _StringTypes:
            realY = realY.lower()

        result = 0
        if realX < realY:
            result = const * 1
        elif realX > realY:
            result = const * -1

        return result


class ReportModule(Component):

    implements(INavigationContributor, IPermissionRequestor, IRequestHandler,
               IWikiSyntaxProvider)

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'tickets'

    def get_navigation_items(self, req):
        if not req.perm.has_permission('REPORT_VIEW'):
            return
        yield 'mainnav', 'tickets', '<a href="%s">View Tickets</a>' \
              % util.escape(self.env.href.report())

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
            return 1

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
            add_link(req, 'up', self.env.href.report(), 'Available Reports')

        from trac.ticket.query import QueryModule
        if req.perm.has_permission('TICKET_VIEW') and \
           self.env.is_component_enabled(QueryModule):
            req.hdf['report.query_href'] = self.env.href.query()

        add_stylesheet(req, 'css/report.css')
        return 'report.cs', None

    # Internal methods

    def _do_create(self, req, db):
        req.perm.assert_permission('REPORT_CREATE')

        if 'cancel' in req.args.keys():
            req.redirect(self.env.href.report())

        title = req.args.get('title', '')
        sql = req.args.get('sql', '')
        description = req.args.get('description', '')
        cursor = db.cursor()
        cursor.execute("INSERT INTO report (title,sql,description) "
                       "VALUES (%s,%s,%s)", (title, sql, description))
        id = db.get_last_id('report')
        db.commit()
        req.redirect(self.env.href.report(id))

    def _do_delete(self, req, db, id):
        req.perm.assert_permission('REPORT_DELETE')

        if 'cancel' in req.args.keys():
            req.redirect(self.env.href.report(id))

        cursor = db.cursor()
        cursor.execute("DELETE FROM report WHERE id=%s", (id,))
        db.commit()
        req.redirect(self.env.href.report())

    def _do_save(self, req, db, id):
        """
        Saves report changes to the database
        """
        req.perm.assert_permission('REPORT_MODIFY')

        if 'cancel' not in req.args.keys():
            title = req.args.get('title', '')
            sql = req.args.get('sql', '')
            description = req.args.get('description', '')
            cursor = db.cursor()
            cursor.execute("UPDATE report SET title=%s,sql=%s,description=%s "
                           "WHERE id=%s", (title, sql, description, id))
            db.commit()
        req.redirect(self.env.href.report(id))

    def _render_confirm_delete(self, req, db, id):
        req.perm.assert_permission('REPORT_DELETE')

        cursor = db.cursor()
        cursor.execute("SELECT title FROM report WHERE id = %s", (id,))
        row = cursor.fetchone()
        if not row:
            raise util.TracError('Report %s does not exist.' % id,
                                 'Invalid Report Number')
        req.hdf['title'] = 'Delete Report {%s} %s' % (id, row['title'])
        req.hdf['report'] = {
            'id': id,
            'mode': 'delete',
            'title': util.escape(row['title']),
            'href': self.env.href.report(id)
        }

    def _render_editor(self, req, db, id, copy=False):
        if id == -1:
            req.perm.assert_permission('REPORT_CREATE')
            title = sql = description = ''
        else:
            req.perm.assert_permission('REPORT_MODIFY')
            cursor = db.cursor()
            cursor.execute("SELECT title,description,sql FROM report "
                           "WHERE id=%s", (id,))
            row = cursor.fetchone()
            if not row:
                raise util.TracError('Report %s does not exist.' % id,
                                     'Invalid Report Number')
            title = row[0] or ''
            description = row[1] or ''
            sql = row[2] or ''

        if copy:
            title += ' (copy)'

        if copy or id == -1:
            req.hdf['title'] = 'Create New Report'
            req.hdf['report.href'] = self.env.href.report()
            req.hdf['report.action'] = 'new'
        else:
            req.hdf['title'] = 'Edit Report {%d} %s' % (id, title)
            req.hdf['report.href'] = self.env.href.report(id)
            req.hdf['report.action'] = 'edit'

        req.hdf['report.id'] = id
        req.hdf['report.mode'] = 'edit'
        req.hdf['report.title'] = util.escape(title)
        req.hdf['report.sql'] = util.escape(sql)
        req.hdf['report.description'] = util.escape(description)

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
        req.hdf['report.href'] = self.env.href.report(id)

        try:
            args = self.get_var_args(req)
        except ValueError,e:
            raise TracError, 'Report failed: %s' % e

        title, description, sql = self.get_info(db, id, args)

        if req.args.get('format') == 'sql':
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
            title=col[0].capitalize()
            prefix = 'report.headers.%d' % idx
            req.hdf['%s.real' % prefix] = col[0]
            if title[:2] == '__' and title[-2:] == '__':
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
                colName = cols[x][0]
                if colName == sortCol:
                    colIndex = x
                if colName[:2] == '__' and colName[-2:] == '__':
                    hiddenCols += 1
            if colIndex != None:
                k = 'report.headers.%d.asc' % (colIndex - hiddenCols)
                asc = req.args.get('asc', None)
                if asc:
                    sorter = ColumnSorter(colIndex, int(asc))
                    req.hdf[k] = asc
                else:
                    sorter = ColumnSorter(colIndex)
                    req.hdf[k] = 1
                rows.sort(sorter.sort)

        # Convert the rows and cells to HDF-format
        row_idx = 0
        for row in rows:
            col_idx = 0
            numrows = len(row)
            for cell in row:
                cell = str(cell)
                column = cols[col_idx][0]
                value = {}
                # Special columns begin and end with '__'
                if column[:2] == '__' and column[-2:] == '__':
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
                if column in ['id', 'ticket', '#', 'summary']:
                    id_cols = [idx for idx, col in util.enum(cols)
                               if col[0] in ('ticket', 'id')]
                    if id_cols:
                        id_val = row[id_cols[0]]
                        value['ticket_href'] = self.env.href.ticket(id_val)
                elif column == 'description':
                    value['parsed'] = wiki_to_html(cell, self.env, req, db)
                elif column == 'reporter':
                    value['reporter'] = cell
                    value['reporter.rss'] = cell.find('@') and cell or ''
                elif column == 'report':
                    value['report_href'] = self.env.href.report(cell)
                elif column in ['time', 'date','changetime', 'created', 'modified']:
                    t = time.localtime(int(cell))
                    value['date'] = time.strftime('%x', t)
                    value['time'] = time.strftime('%X', t)
                    value['datetime'] = time.strftime('%c', t)
                    value['gmt'] = time.strftime('%a, %d %b %Y %H:%M:%S GMT',
                                                 time.gmtime(int(cell)))
                prefix = 'report.items.%d.%s' % (row_idx, str(column))
                req.hdf[prefix] = util.escape(str(cell))
                for key in value.keys():
                    req.hdf[prefix + '.' + key] = value[key]

                col_idx += 1
            row_idx += 1
        req.hdf['report.numrows'] = row_idx

        format = req.args.get('format')
        if format == 'rss':
            self._render_rss(req)
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
        sql = self.sql_sub_vars(req, sql, args)
        if not sql:
            raise util.TracError('Report %s has no SQL query.' % id)
        if sql.find('__group__') == -1:
            req.hdf['report.sorting.enabled'] = 1

        cursor = db.cursor()
        cursor.execute(sql)

        # FIXME: fetchall should probably not be used.
        info = cursor.fetchall()
        cols = cursor.description

        db.rollback()

        return [cols, info]

    def get_info(self, db, id, args):
        if id == -1:
            # If no particular report was requested, display
            # a list of available reports instead
            title = 'Available Reports'
            sql = 'SELECT id AS report, title FROM report ORDER BY report'
            description = 'This is a list of reports available.'
        else:
            cursor = db.cursor()
            cursor.execute("SELECT title,sql,description from report "
                           "WHERE id=%s", (id,))
            row = cursor.fetchone()
            if not row:
                raise util.TracError('Report %d does not exist.' % id,
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
            m = re.search(dynvars_disallowed_var_chars_re, arg)
            if m:
                raise ValueError("The character '%s' is not allowed "
                                 " in variable names." % m.group())
            val = req.args.get(arg)
            m = re.search(dynvars_disallowed_value_chars_re, val)
            if m:
                raise ValueError("The character '%s' is not allowed "
                                 " in variable data." % m.group())
            report_args[arg] = val

        # Set some default dynamic variables
        if not report_args.has_key('USER'):
            report_args['USER'] = req.authname

        return report_args

    def sql_sub_vars(self, req, sql, args):
        def repl(match):
            aname = match.group()[1:]
            try:
                arg = args[aname]
            except KeyError:
                raise util.TracError("Dynamic variable '$%s' not defined." % aname)
            req.hdf['report.var.' + aname] = arg
            return arg

        return dynvars_re.sub(repl, sql)

    def _render_csv(self, req, cols, rows, sep=','):
        req.send_response(200)
        req.send_header('Content-Type', 'text/plain;charset=utf-8')
        req.end_headers()

        req.write(sep.join([c[0] for c in cols]) + '\r\n')
        for row in rows:
            sanitize = lambda x: str(x).replace(sep,"_") \
                                       .replace('\n',' ') \
                                       .replace('\r',' ')
            req.write(sep.join(map(sanitize, row)) + '\r\n')

    def _render_rss(self, req):
        # Escape HTML in the ticket summaries
        item = req.hdf.getObj('report.items')
        if item:
            item = item.child()
            while item:
                nodename = 'report.items.%s.summary' % item.name()
                summary = req.hdf.get(nodename, '')
                req.hdf[nodename] = util.escape(summary)
                item = item.next()

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
        yield (r"!?\{\d+\}", lambda x, y, z: self._format_link(x, 'report', y[1:-1], y))

    def _format_link(self, formatter, ns, target, label):
        return '<a class="report" href="%s">%s</a>' % (formatter.href.report(target), label)

