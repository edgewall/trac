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

import os
import re
import time
import types
import urllib

import perm
import util
from Module import Module
from WikiFormatter import wiki_to_html

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
    template_csv_name = 'report_csv.cs'

    def sql_sub_vars(self, sql, args):
        m = re.search(dynvars_re, sql)
        if not m:
            return sql
        aname=m.group()[1:]
        try:
            arg = args[aname]
        except KeyError:
            raise util.TracError("Dynamic variable '$%s' not defined." % aname)
        self.req.hdf.setValue('report.var.'+aname , arg)
        sql = m.string[:m.start()] + arg + m.string[m.end():]
        return self.sql_sub_vars(sql, args)
    
    def get_info(self, id, args):
        cursor = self.db.cursor()

        if id == -1:
            # If no particular report was requested, display
            # a list of available reports instead
            title = 'Available Reports'
            sql = 'SELECT id AS report, title FROM report ORDER BY report'
            description = 'This is a list of reports available.'
        else:
            cursor.execute('SELECT title, sql, description from report '
                           ' WHERE id=%s', id)
            row = cursor.fetchone()
            if not row:
                raise util.TracError('Report %d does not exist.' % id,
                                     'Invalid Report Number')
            title = row[0] or ''
            sql = row[1]
            description = row[2] or ''

        return [title, description, sql]
        
    def create_report(self, title, description, sql):
        self.perm.assert_permission(perm.REPORT_CREATE)

        cursor = self.db.cursor()
        cursor.execute('INSERT INTO report (id, title, sql, description)'
                        'VALUES (NULL, %s, %s, %s)', title, sql, description)
        id = self.db.db.sqlite_last_insert_rowid()
        self.db.commit()
        self.req.redirect(self.env.href.report(id))

    def delete_report(self, id):
        self.perm.assert_permission(perm.REPORT_DELETE)

        if self.args.has_key('delete'):
            cursor = self.db.cursor ()
            cursor.execute('DELETE FROM report WHERE id=%s', id)
            self.db.commit()
            self.req.redirect(self.env.href.report())
        else:
            self.req.redirect(self.env.href.report(id))

    def execute_report(self, sql, args):
        cursor = self.db.cursor()
        sql = self.sql_sub_vars(sql, args)
        if not sql:
            raise util.TracError('Report %s has no SQL query.' % id)
        cursor.execute(sql)

        if sql.find('__group__') == -1:
            self.req.hdf.setValue('report.sorting.enabled', '1')

        # FIXME: fetchall should probably not be used.
        info = cursor.fetchall()
        cols = cursor.rs.col_defs
        # Escape the values so that they are safe to have as html parameters
        #info = map(lambda row: map(lambda x: escape(x), row), info)

        return [cols, info]

    def commit_changes(self, id):
        """
        saves report changes to the database
        """
        self.perm.assert_permission(perm.REPORT_MODIFY)

        cursor = self.db.cursor()
        title = self.args.get('title', '')
        sql   = self.args.get('sql', '')
        description   = self.args.get('description', '')

        cursor.execute('UPDATE report SET title=%s, sql=%s, description=%s '
                       ' WHERE id=%s',
                       title, sql, description, id)
        self.db.commit()
        self.req.redirect(self.env.href.report(id))

    def render_confirm_delete(self, id):
        self.perm.assert_permission(perm.REPORT_DELETE)
        cursor = self.db.cursor()

        cursor.execute('SELECT title FROM report WHERE id = %s', id)
        row = cursor.fetchone()
        if not row:
            raise util.TracError('Report %s does not exist.' % id,
                                 'Invalid Report Number')
        self.req.hdf.setValue('title', 'Delete {%s} %s (report)' % (id, row['title']))
        self.req.hdf.setValue('report.mode', 'delete')
        self.req.hdf.setValue('report.id', str(id))
        self.req.hdf.setValue('report.title', row['title'])

    def render_report_editor(self, id, action='commit', copy=0):
        self.perm.assert_permission(perm.REPORT_MODIFY)
        cursor = self.db.cursor()

        if id == -1:
            title = sql = description = ''
        else:
            cursor.execute('SELECT title, description, sql FROM report '
                           ' WHERE id=%s', id)
            row = cursor.fetchone()
            if not row:
                raise util.TracError('Report %s does not exist.' % id,
                                     'Invalid Report Number')
            sql = row[2] or ''
            description = row[1] or ''
            title = row[0] or ''

        if copy:
            title += ' copy'
        self.req.hdf.setValue('title', 'Create New Report')
        
        self.req.hdf.setValue('report.mode', 'editor')
        self.req.hdf.setValue('report.title', title)
        self.req.hdf.setValue('report.id', str(id))
        self.req.hdf.setValue('report.action', action)
        self.req.hdf.setValue('report.sql', sql)
        self.req.hdf.setValue('report.description', description)

    def add_alternate_links(self, args):
        params = args
        if self.args.has_key('sort'):
            params['sort'] = self.args['sort']
        if self.args.has_key('asc'):
            params['asc'] = self.args['asc']
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

    def render_report_list(self, id):
        """
        uses a user specified sql query to extract some information
        from the database and presents it as a html table.
        """
        if self.perm.has_permission(perm.REPORT_CREATE):
            self.req.hdf.setValue('report.create_href',
                                  self.env.href.report(None, 'new'))

        try:
            args = self.get_var_args()
        except ValueError,e:
            self.req.hdf.setValue('report.message', 'report failed: %s' % e)
            return
        
        if id != -1:
            self.add_alternate_links(args)
            if self.perm.has_permission(perm.REPORT_MODIFY):
                self.req.hdf.setValue('report.edit_href',
                                      self.env.href.report(id, 'edit'))
            if self.perm.has_permission(perm.REPORT_CREATE):
                self.req.hdf.setValue('report.copy_href',
                                      self.env.href.report(id, 'copy'))
            if self.perm.has_permission(perm.REPORT_DELETE):
                self.req.hdf.setValue('report.delete_href',
                                      self.env.href.report(id, 'delete'))

        self.req.hdf.setValue('report.mode', 'list')
        info = self.get_info(id, args)
        if not info:
            return
        [title, description, sql] = info
        self.error = None

        if id > 0:
            title = '{%i} %s' % (id, title)
        self.req.hdf.setValue('title', title)
        self.req.hdf.setValue('report.title', title)
        self.req.hdf.setValue('report.id', str(id))
        descr_html = wiki_to_html(description, self.req.hdf, self.env)
        self.req.hdf.setValue('report.description', descr_html)

        if self.args.get('format') == 'sql':
            return

        try:
            [self.cols, self.rows] = self.execute_report(sql, args)
        except Exception, e:
            self.error = e
            self.req.hdf.setValue('report.message',
                                  'Report failed: %s' % e)
            return None

        # Convert the header info to HDF-format
        idx = 0
        for col in self.cols:
            title=col[0].capitalize()
            prefix = 'report.headers.%d' % idx
            self.req.hdf.setValue('%s.real' % prefix, col[0])
            if title[:2] == '__' and title[-2:] == '__':
                continue
            elif title[0] == '_' and title[-1] == '_':
                title = title[1:-1].capitalize()
                self.req.hdf.setValue(prefix + '.fullrow', '1')
            elif title[0] == '_':
                continue
            elif title[-1] == '_':
                title = title[:-1]
                self.req.hdf.setValue(prefix + '.breakrow', '1')
            self.req.hdf.setValue(prefix, title)
            idx = idx + 1

        if self.args.has_key('sort'):
            sortCol = self.args.get('sort')
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
                asc = self.args.get('asc', None)
                if asc:
                    sorter = ColumnSorter(colIndex, int(asc))
                    self.req.hdf.setValue(k, asc)
                else:
                    sorter = ColumnSorter(colIndex)
                    self.req.hdf.setValue(k, '1')
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
                    self.req.hdf.setValue(prefix + '.breakrow', '1')
                elif column[-1] == '_':
                    value['breakrow'] = 1
                    value['breakafter'] = 1
                    column = column[:-1]
                elif column[0] == '_':
                    value['hidehtml'] = 1
                    column = column[1:]
                if column in ['ticket', '#']:
                    value['ticket_href'] = self.env.href.ticket(cell)
                elif column == 'description':
                    value['parsed'] = wiki_to_html(cell, self.req.hdf, self.env)
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
                self.req.hdf.setValue(prefix, util.escape(str(cell)))
                for key in value.keys():
                    self.req.hdf.setValue(prefix + '.' + key, str(value[key]))

                col_idx += 1
            row_idx += 1
        self.req.hdf.setValue('report.numrows', str(row_idx))

    def get_var_args(self):
        report_args = {}
        for arg in self.args.keys():
            if not arg == arg.upper():
                continue
            m = re.search(dynvars_disallowed_var_chars_re, arg)
            if m:
                raise ValueError("The character '%s' is not allowed "
                                 " in variable names." % m.group())
            val = self.args.get(arg)
            m = re.search(dynvars_disallowed_value_chars_re, val)
            if m:
                raise ValueError("The character '%s' is not allowed "
                                 " in variable data." % m.group())
            report_args[arg] = val

        # Set some default dynamic variables
        if hasattr(self.req,'authname'):  # FIXME: Is authname always there? - dln
            report_args['USER'] = self.req.authname
            
        return report_args

    def render(self):
        self.perm.assert_permission(perm.REPORT_VIEW)
        # did the user ask for any special report?
        id = int(self.args.get('id', -1))
        action = self.args.get('action', 'list')

        if action == 'create':
            if not (self.args.has_key('sql') or self.args.has_key('title')):
                action = 'list'
            else:
                self.create_report(self.args.get('title', ''),
                                   self.args.get('description', ''),
                                   self.args.get('sql', ''))
        if action == 'delete':
            self.render_confirm_delete(id)
        elif action == 'commit':
            self.commit_changes(id)
        elif action == 'confirm_delete':
            self.delete_report(id)
        elif action == 'new':
            self.render_report_editor(-1, 'create')
        elif action == 'copy':
            self.render_report_editor(id, 'create', 1)
        elif action == 'edit':
            self.render_report_editor(id, 'commit')
        elif action == 'list':
            self.render_report_list(id)

    def display_rss(self):
        item = self.req.hdf.getObj('report.items')
        item = item.child()
        while item:
            nodename = 'report.items.%s.summary' % item.name()
            summary = self.req.hdf.getValue(nodename, '')
            self.req.hdf.setValue(nodename, util.escape(summary))
            item = item.next()
        self.req.display(self.template_rss_name, 'text/xml')
            
    def display_csv(self,sep=','):
        self.req.send_response(200)
        self.req.send_header('Content-Type', 'text/plain')
        self.req.end_headers()
        titles = ''
        if self.error:
            self.req.write('Report failed: %s' % self.error)
            return
        self.req.write(sep.join([c[0] for c in self.cols]) + '\r\n')
        for row in self.rows:
            self.req.write(sep.join([str(c).replace(sep,"_").replace('\n',' ').replace('\r',' ') for c in row]) + '\r\n')

    def display_tab(self):
        self.display_csv('\t')

    def display_sql(self):
        self.perm.assert_permission(perm.REPORT_SQL_VIEW)
        self.req.send_response(200)
        self.req.send_header('Content-Type', 'text/plain')
        self.req.end_headers()
        rid = self.req.hdf.getValue('report.id', '')
        if self.error or not rid:
            self.req.write('Report failed: %s' % self.error)
            return
        title = self.req.hdf.getValue('report.title', '')
        if title:
            self.req.write('-- ## %s: %s ## --\n\n' % (rid, title))
        cursor = self.db.cursor()
        cursor.execute('SELECT sql,description FROM report WHERE id=%s', rid)
        row = cursor.fetchone()
        sql = row[0] or ''
        if row[1]:
            descr = '-- %s\n\n' % '\n-- '.join(row[1].splitlines())
            self.req.write(descr)
        self.req.write(sql)
