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

from trac import perm, util
from trac.Module import Module
from trac.WikiFormatter import wiki_to_html

import re
import time
import types
import urllib


dynvars_re = re.compile('\$([A-Z]+)')
dynvars_disallowed_var_chars_re = re.compile('[^A-Z0-9_]')
dynvars_disallowed_value_chars_re = re.compile('[^a-zA-Z0-9-_@.,]')

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


class Report (Module):
    template_name = 'report.cs'
    template_rss_name = 'report_rss.cs'

    def sql_sub_vars(self, req, sql, args):
        m = re.search(dynvars_re, sql)
        if not m:
            return sql
        aname=m.group()[1:]
        try:
            arg = args[aname]
        except KeyError:
            raise util.TracError("Dynamic variable '$%s' not defined." % aname)
        req.hdf['report.var.' + aname] = arg
        sql = m.string[:m.start()] + arg + m.string[m.end():]
        return self.sql_sub_vars(req, sql, args)

    def get_info(self, id, args):

        if id == -1:
            # If no particular report was requested, display
            # a list of available reports instead
            title = 'Available Reports'
            sql = 'SELECT id AS report, title FROM report ORDER BY report'
            description = 'This is a list of reports available.'
        else:
            cursor = self.db.cursor()
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

    def create_report(self, req, title, description, sql):
        self.perm.assert_permission(perm.REPORT_CREATE)

        cursor = self.db.cursor()
        cursor.execute("INSERT INTO report (title,sql,description) "
                       "VALUES (%s,%s,%s)", (title, sql, description))
        id = self.db.get_last_id()
        self.db.commit()
        req.redirect(self.env.href.report(id))

    def delete_report(self, req, id):
        self.perm.assert_permission(perm.REPORT_DELETE)

        if not req.args.has_key('cancel'):
            cursor = self.db.cursor ()
            cursor.execute("DELETE FROM report WHERE id=%s", (id,))
            self.db.commit()
            req.redirect(self.env.href.report())
        else:
            req.redirect(self.env.href.report(id))

    def execute_report(self, req, sql, args):
        sql = self.sql_sub_vars(req, sql, args)
        if not sql:
            raise util.TracError('Report %s has no SQL query.' % id)
        if sql.find('__group__') == -1:
            req.hdf['report.sorting.enabled'] = 1

        cursor = self.db.cursor()
        cursor.execute(sql)

        # FIXME: fetchall should probably not be used.
        info = cursor.fetchall()
        cols = cursor.description

        self.db.rollback()

        return [cols, info]

    def commit_changes(self, req, id):
        """
        saves report changes to the database
        """
        self.perm.assert_permission(perm.REPORT_MODIFY)

        if not req.args.has_key('cancel'):
            cursor = self.db.cursor()
            title = req.args.get('title', '')
            sql = req.args.get('sql', '')
            description = req.args.get('description', '')

            cursor.execute("UPDATE report SET title=%s,sql=%s,description=%s "
                           "WHERE id=%s", (title, sql, description, id))
            self.db.commit()
        req.redirect(self.env.href.report(id))

    def render_confirm_delete(self, req, id):
        self.perm.assert_permission(perm.REPORT_DELETE)

        cursor = self.db.cursor()
        cursor.execute("SELECT title FROM report WHERE id = %s", (id,))
        row = cursor.fetchone()
        if not row:
            raise util.TracError('Report %s does not exist.' % id,
                                 'Invalid Report Number')
        req.hdf['title'] = 'Delete Report {%s} %s' % (id, row['title'])
        req.hdf['report.mode'] = 'delete'
        req.hdf['report.id'] = id
        req.hdf['report.title'] = row['title']

    def render_report_editor(self, req, id, action='commit', copy=0):
        self.perm.assert_permission(perm.REPORT_MODIFY)

        if id == -1:
            title = sql = description = ''
        else:
            cursor = self.db.cursor()
            cursor.execute("SELECT title,description,sql FROM report "
                           "WHERE id=%s", (id,))
            row = cursor.fetchone()
            if not row:
                raise util.TracError('Report %s does not exist.' % id,
                                     'Invalid Report Number')
            sql = row[2] or ''
            description = row[1] or ''
            title = row[0] or ''

        if copy:
            title += ' copy'

        if action == 'commit':
            req.hdf['title'] = 'Edit Report {%d} %s' % (id, row['title'])
        else:
            req.hdf['title'] = 'Create New Report'
        req.hdf['report.mode'] = 'editor'
        req.hdf['report.title'] = title
        req.hdf['report.id'] = id
        req.hdf['report.action'] = action
        req.hdf['report.sql'] = sql
        req.hdf['report.description'] = description

    def add_alternate_links(self, req, args):
        params = args
        if req.args.has_key('sort'):
            params['sort'] = req.args['sort']
        if req.args.has_key('asc'):
            params['asc'] = req.args['asc']
        href = ''
        if params:
            href = '&amp;' + urllib.urlencode(params).replace('&', '&amp;')
        self.add_link('alternate', '?format=rss' + href, 'RSS Feed',
            'application/rss+xml', 'rss')
        self.add_link('alternate', '?format=csv' + href,
            'Comma-delimited Text', 'text/plain')
        self.add_link('alternate', '?format=tab' + href,
            'Tab-delimited Text', 'text/plain')
        if self.perm.has_permission(perm.REPORT_SQL_VIEW):
            self.add_link('alternate', '?format=sql', 'SQL Query',
                'text/plain')

    def render_report_list(self, req, id):
        """
        uses a user specified sql query to extract some information
        from the database and presents it as a html table.
        """
        if self.perm.has_permission(perm.REPORT_CREATE):
            req.hdf['report.create_href'] = self.env.href.report(None, 'new')

        if id != -1:
            if self.perm.has_permission(perm.REPORT_MODIFY):
                req.hdf['report.edit_href'] = self.env.href.report(id, 'edit')
            if self.perm.has_permission(perm.REPORT_CREATE):
                req.hdf['report.copy_href'] = self.env.href.report(id, 'copy')
            if self.perm.has_permission(perm.REPORT_DELETE):
                req.hdf['report.delete_href'] = self.env.href.report(id, 'delete')

        try:
            args = self.get_var_args(req)
        except ValueError,e:
            req.hdf['report.message'] = 'Report failed: %s' % e
            return

        if id != -1:
            self.add_alternate_links(req, args)

        req.hdf['report.mode'] = 'list'
        info = self.get_info(id, args)
        if not info:
            return
        [title, description, sql] = info
        self.error = None

        if id > 0:
            title = '{%i} %s' % (id, title)
        req.hdf['title'] = title
        req.hdf['report.title'] = title
        req.hdf['report.id'] = id
        descr_html = wiki_to_html(description, req.hdf, self.env,self.db)
        req.hdf['report.description'] = descr_html

        if req.args.get('format') == 'sql':
            return

        try:
            [self.cols, self.rows] = self.execute_report(req, sql, args)
        except Exception, e:
            self.error = e
            req.hdf['report.message'] = 'Report failed: %s' % e
            return None

        # Convert the header info to HDF-format
        idx = 0
        for col in self.cols:
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
            for x in range(len(self.cols)):
                colName = self.cols[x][0]
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
                self.rows.sort(sorter.sort)


        # Convert the rows and cells to HDF-format
        row_idx = 0
        for row in self.rows:
            col_idx = 0
            numrows = len(row)
            for cell in row:
                cell = str(cell)
                column = self.cols[col_idx][0]
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
                if column in ['ticket', '#', 'summary']:
                    value['ticket_href'] = self.env.href.ticket(row['ticket'])
                elif column == 'description':
                    value['parsed'] = wiki_to_html(cell, req.hdf, self.env, self.db)
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
        report_args['USER'] = req.authname

        return report_args

    def render(self, req):
        self.perm.assert_permission(perm.REPORT_VIEW)

        # did the user ask for any special report?
        id = int(req.args.get('id', -1))
        action = req.args.get('action', 'list')

        if action == 'create':
            if req.args.has_key('cancel'):
                action = 'list'
            else:
                self.create_report(req, req.args.get('title', ''),
                                   req.args.get('description', ''),
                                   req.args.get('sql', ''))

        if id != -1 or action == 'new':
            self.add_link('up', self.env.href.report(), 'Available Reports')

        if action == 'delete':
            self.render_confirm_delete(req, id)
        elif action == 'commit':
            self.commit_changes(req, id)
        elif action == 'confirm_delete':
            self.delete_report(req, id)
        elif action == 'new':
            self.render_report_editor(req, -1, 'create')
        elif action == 'copy':
            self.render_report_editor(req, id, 'create', 1)
        elif action == 'edit':
            self.render_report_editor(req, id, 'commit')
        elif action == 'list':
            self.render_report_list(req, id)

    def display_rss(self, req):
        item = req.hdf.getObj('report.items')
        if item:
            item = item.child()
            while item:
                nodename = 'report.items.%s.summary' % item.name()
                summary = req.hdf.getValue(nodename, '')
                req.hdf[nodename] = util.escape(summary)
                item = item.next()
        req.display(self.template_rss_name, 'application/rss+xml')

    def display_csv(self, req, sep=','):
        req.send_response(200)
        req.send_header('Content-Type', 'text/plain;charset=utf-8')
        req.end_headers()
        titles = ''
        if self.error:
            req.write('Report failed: %s' % self.error)
            return
        req.write(sep.join([c[0] for c in self.cols]) + '\r\n')
        for row in self.rows:
            sanitize = lambda x: str(x).replace(sep,"_") \
                                       .replace('\n',' ') \
                                       .replace('\r',' ')
            req.write(sep.join(map(sanitize, row)) + '\r\n')

    def display_tab(self, req):
        self.display_csv(req, '\t')

    def display_sql(self, req):
        self.perm.assert_permission(perm.REPORT_SQL_VIEW)
        req.send_response(200)
        req.send_header('Content-Type', 'text/plain;charset=utf-8')
        req.end_headers()
        rid = req.hdf.getValue('report.id', '')
        if self.error or not rid:
            req.write('Report failed: %s' % self.error)
            return
        title = req.hdf.getValue('report.title', '')
        if title:
            req.write('-- ## %s: %s ## --\n\n' % (rid, title))
        cursor = self.db.cursor()
        cursor.execute("SELECT sql,description FROM report WHERE id=%s", (rid,))
        row = cursor.fetchone()
        sql = row[0] or ''
        if row[1]:
            descr = '-- %s\n\n' % '\n-- '.join(row[1].splitlines())
            req.write(descr)
        req.write(sql)
