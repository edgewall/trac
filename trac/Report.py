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

import os,os.path
import time
import re

from util import *
from Module import Module
from Wiki import wiki_to_html
import perm

dynvars_re = re.compile('\$([A-Z]+)')
dynvars_disallowed_var_chars_re = re.compile('[^A-Z0-9_]')
dynvars_disallowed_value_chars_re = re.compile('[^a-zA-Z0-9-_@.,]')

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
            raise TracError("Dynamic variable '$%s' not defined." % aname)
        self.req.hdf.setValue('report.var.'+aname , arg)
        sql = m.string[:m.start()] + arg + m.string[m.end():]
        return self.sql_sub_vars(sql, args)
    
    def get_info(self, id, args):
        cursor = self.db.cursor()

        if id == -1:
            # If no particular report was requested, display
            # a list of available reports instead
            cursor.execute("SELECT id AS report, title "
                           "FROM report "
                           "ORDER BY report")
            title = 'Available reports'
        else:
            cursor.execute('SELECT title, sql from report WHERE id=%s', id)
            row = cursor.fetchone()
            try:
                if not row:
                    raise TracError('Report %d does not exist.' % id,
                                'Invalid Report Number')
                title = row[0]
                sql   = self.sql_sub_vars(row[1], args)
                cursor.execute(sql)
            except Exception, e:
                self.error = e
                self.req.hdf.setValue('report.message',
                                      'report failed: %s' % e)
                return None

        # FIXME: fetchall should probably not be used.
        info = cursor.fetchall()
        cols = cursor.rs.col_defs
        # Escape the values so that they are safe to have as html parameters
#        info = map(lambda row: map(lambda x: escape(x), row), info)
        return [cols, info, title]
        
    def create_report(self, title, sql):
        self.perm.assert_permission(perm.REPORT_CREATE)

        cursor = self.db.cursor()
        
        cursor.execute('INSERT INTO report (id, title, sql)'
                        'VALUES (NULL, %s, %s)', title, sql)
        id = self.db.db.sqlite_last_insert_rowid()
        self.db.commit()
        self.req.redirect(self.href.report(id))

    def delete_report(self, id):
        self.perm.assert_permission(perm.REPORT_DELETE)
        
        cursor = self.db.cursor ()
        cursor.execute('DELETE FROM report WHERE id=%s', id)
        self.db.commit()
        self.req.redirect(self.href.report())

    def commit_changes(self, id):
        """
        saves report changes to the database
        """
        self.perm.assert_permission(perm.REPORT_MODIFY)

        cursor = self.db.cursor()
        title = self.args['title']
        sql   = self.args['sql']

        cursor.execute('UPDATE report SET title=%s, sql=%s WHERE id=%s',
                       title, sql, id)
        self.db.commit()
        self.req.redirect(self.href.report(id))

    def render_report_editor(self, id, action='commit', copy=0):
        self.perm.assert_permission(perm.REPORT_MODIFY)
        cursor = self.db.cursor()

        if id == -1:
            title = sql = ""
        else:
            cursor.execute('SELECT title, sql FROM report WHERE id=%s', id)
            row = cursor.fetchone()
            sql = row[1]
            title = row[0]

        if copy:
            title += ' copy'
        
        self.req.hdf.setValue('report.mode', 'editor')
        self.req.hdf.setValue('report.title', title)
        self.req.hdf.setValue('report.id', str(id))
        self.req.hdf.setValue('report.action', action)
        self.req.hdf.setValue('report.sql', sql)
    
    def render_report_list(self, id, args={}):
        """
        uses a user specified sql query to extract some information
        from the database and presents it as a html table.
        """
        if self.perm.has_permission(perm.REPORT_CREATE):
            self.req.hdf.setValue('report.create_href',
                                  self.href.report(None, 'new'))
            
        if id != -1:
            if self.perm.has_permission(perm.REPORT_MODIFY):
                self.req.hdf.setValue('report.edit_href',
                                      self.href.report(id, 'edit'))
            if self.perm.has_permission(perm.REPORT_CREATE):
                self.req.hdf.setValue('report.copy_href',
                                      self.href.report(id, 'copy'))
            if self.perm.has_permission(perm.REPORT_DELETE):
                self.req.hdf.setValue('report.delete_href',
                                      self.href.report(id, 'delete'))

        self.req.hdf.setValue('report.mode', 'list')
        info = self.get_info(id, args)
        if not info:
            return
        [self.cols, self.rows, title] = info
        self.error = None
        
        self.req.hdf.setValue('title', title + ' (report)')
        self.req.hdf.setValue('report.title', title)
        self.req.hdf.setValue('report.id', str(id))

        # Convert the header info to HDF-format
        idx = 0
        for col in self.cols:
            title=col[0].capitalize()
            prefix = 'report.headers.%d' % idx
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
                    value['ticket_href'] = self.href.ticket(cell)
                elif column == 'description':
                    value['parsed'] = wiki_to_html(cell, self.req.hdf,
                                                   self.href)
                elif column == 'report':
                    value['report_href'] = self.href.report(cell)
                elif column in ['time', 'date','changetime', 'created', 'modified']:
                    t = time.localtime(int(cell))
                    value['date'] = time.strftime('%x', t)
                    value['time'] = time.strftime('%X', t)
                    value['datetime'] = time.strftime('%c', t)
                    value['gmt'] = time.strftime('%a, %d %b %Y %H:%M:%S GMT',
                                                 time.gmtime(int(cell)))
                prefix = 'report.items.%d.%s' % (row_idx, str(column))
                self.req.hdf.setValue(prefix, escape(str(cell)))
                for key in value.keys():
                    self.req.hdf.setValue(prefix + '.' + key, str(value[key]))

                col_idx += 1
            row_idx += 1

    def get_var_args(self):
        report_args = {}
        for arg in self.args.keys():
            if not arg == arg.upper():
                continue
            m = re.search(dynvars_disallowed_var_chars_re, arg)
            if m:
                raise ValueError("The character '%s' is not allowed "
                                 " in variable names." % m.group())
            val = self.args[arg]
            m = re.search(dynvars_disallowed_value_chars_re, val)
            if m:
                raise ValueError("The character '%s' is not allowed "
                                 " in variable data." % m.group())
            report_args[arg] = val

        # Set some default dynamic variables
        if hasattr(self,'authname'):  # FIXME: Is authname always there? - dln
            report_args['USER'] = self.req.authname
            
        return report_args

    def render(self):
        self.perm.assert_permission(perm.REPORT_VIEW)
        # did the user ask for any special report?
        id = int(self.args.get('id', -1))
        action = self.args.get('action', 'list')

        try:
            report_args = self.get_var_args()
        except ValueError,e:
            self.req.hdf.setValue('report.message', 'report failed: %s' % e)
            return
        
        if action == 'create':
            self.create_report(self.args['title'], self.args['sql'])
        elif action == 'delete':
            self.delete_report(id)
        elif action == 'commit':
            self.commit_changes(id)
        elif action == 'new':
            self.render_report_editor(-1, 'create')
        elif action == 'copy':
            self.render_report_editor(id, 'create', 1)
        elif action == 'edit':
            self.render_report_editor(id, 'commit')
        else:
            self.render_report_list(id, report_args)

    def display_rss(self):
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


