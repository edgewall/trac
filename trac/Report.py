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

from util import *
from Href import href
from Module import Module
import perm
import db

import time

class Report (Module):
    template_name = 'report.cs'

    def __init__(self, config, args, pool):
        Module.__init__(self, config, args, pool)
        
    def get_info (self, id):
        cnx = db.get_connection()
        cursor = cnx.cursor()

        if id == -1:
            # If no special report was requested, display
            # a list of available reports instead
            cursor.execute("SELECT id AS report, title "
                           "FROM report "
                           "ORDER BY report")
            title = 'Available reports'
        else:
            cursor.execute('SELECT title, sql from report WHERE id=%s', id)
            row = cursor.fetchone()
            title = row[0]
            sql   = row[1]
            cursor.execute(sql)

        # FIXME: fetchall should probably not be used.
        info = cursor.fetchall()
        cols = cursor.rs.col_defs
        # Escape the values so that they are safe to have as html parameters
        info = map(lambda row: map(lambda x: escape(x), row), info)
        return [cols, info, title]
        
    def create_report(self, title, sql):
        perm.assert_permission(perm.REPORT_CREATE)

        cnx = db.get_connection()
        cursor = cnx.cursor()
        
        cursor.execute('INSERT INTO report (id, title, sql)'
                        'VALUES (NULL, %s, %s)', title, sql)
        id = cnx.db.sqlite_last_insert_rowid()
        cnx.commit()
        redirect (href.report(id))

    def delete_report(self, id):
        perm.assert_permission(perm.REPORT_DELETE)
        
        cnx = db.get_connection()
        cursor = cnx.cursor ()

        cursor.execute('DELETE FROM report WHERE id=%s', id)
        cnx.commit()
        redirect(href.report())

    def commit_changes(self, id):
        """
        saves report changes to the database
        """
        perm.assert_permission(perm.REPORT_MODIFY)

        cnx = db.get_connection()
        cursor = cnx.cursor()

        title = self.args['title']
        sql   = self.args['sql']

        cursor.execute('UPDATE report SET title=%s, sql=%s WHERE id=%s',
                       title, sql, id)
        cnx.commit()
        redirect(href.report(id))

    def render_report_editor(self, id, action='commit', copy=0):
        cnx = db.get_connection()
        cursor = cnx.cursor()

        if id == -1:
            title = sql = ""
        else:
            cursor.execute('SELECT title, sql FROM report WHERE id=%s', id)
            row = cursor.fetchone()
            sql = row[1]
            title = row[0]

        if copy:
            title += ' copy'
        
        self.cgi.hdf.setValue('report.mode', 'editor')
        self.cgi.hdf.setValue('report.title', title)
        self.cgi.hdf.setValue('report.id', str(id))
        self.cgi.hdf.setValue('report.action', action)
        self.cgi.hdf.setValue('report.sql', sql)
    
    def render_report_list(self, id):
        """
        uses a user specified sql query to extract some information
        from the database and presents it as a html table.
        """
        if perm.has_permission(perm.REPORT_CREATE):
            self.cgi.hdf.setValue('report.create_href',
                                  href.report(None, 'new'))
            
        if id != -1:
            if perm.has_permission(perm.REPORT_MODIFY):
                self.cgi.hdf.setValue('report.edit_href',
                                      href.report(id, 'edit'))
            if perm.has_permission(perm.REPORT_CREATE):
                self.cgi.hdf.setValue('report.copy_href',
                                      href.report(id, 'copy'))
            if perm.has_permission(perm.REPORT_DELETE):
                self.cgi.hdf.setValue('report.delete_href',
                                      href.report(id, 'delete'))

        self.cgi.hdf.setValue('report.mode', 'list')
        try:
            [cols, rows, title] = self.get_info(id)
        except Exception, e:
            self.cgi.hdf.setValue('report.message', 'report failed: %s' % e)
            return
        
        self.cgi.hdf.setValue('report.title', title)
        self.cgi.hdf.setValue('report.id', str(id))

        # Convert the header info to HDF-format
        idx = 0
	for x in cols:
            self.cgi.hdf.setValue('report.headers.%d.title' % idx, x[0])
            idx = idx + 1

        # Convert the rows and cells to HDF-format
        row_idx = 0
        for row in rows:
            col_idx = 0
            for cell in row:
                prefix = 'report.items.%d.%d' % (row_idx, col_idx)
                self.cgi.hdf.setValue(prefix + '.value', str(cell))
                if cols[col_idx][0] in ['ticket', '#']:
                    self.cgi.hdf.setValue(prefix + '.type', 'ticket')
                    self.cgi.hdf.setValue(prefix + '.ticket_href',
                                          href.ticket(cell))
                elif cols[col_idx][0] == 'report':
                    self.cgi.hdf.setValue(prefix + '.type', 'report')
                    self.cgi.hdf.setValue(prefix + '.report_href',
                                          href.report(cell))
                elif cols[col_idx][0] in ['time', 'date', 'created', 'modified']:
                    self.cgi.hdf.setValue(prefix + '.type', 'time')
                    self.cgi.hdf.setValue(prefix + '.value',
                                          time.strftime('%F',
                                          time.localtime(int(cell))))
                elif cols[col_idx][0] in ['summary', 'owner',
                                          'severity', 'status', 'priority']:
                    self.cgi.hdf.setValue(prefix + '.type', cols[col_idx][0])
                else:
                    self.cgi.hdf.setValue(prefix + '.type', 'unknown')
                col_idx = col_idx + 1
            row_idx = row_idx + 1
        

    def render(self):
        # did the user ask for any special report?
        id = int(dict_get_with_default(self.args, 'id', -1))
        action = dict_get_with_default(self.args, 'action', 'list')

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
            self.render_report_list(id)

