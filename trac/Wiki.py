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
import time
import urllib
import difflib
import StringIO

import perm
from Module import Module
from util import escape, TracError, get_reporter_id
from WikiFormatter import *


__all__ = ['populate_page_dict', 'WikiPage', 'WikiModule']


def populate_page_dict(db, env):
    """Extract wiki page names. This is used to detect broken wiki-links"""
    page_dict = {}
    cursor = db.cursor()
    cursor.execute('SELECT DISTINCT name FROM wiki')
    while 1:
        row = cursor.fetchone()
        if not row:
            break
        page_dict[row[0]] = 1
    env._wiki_pages = page_dict


class WikiPage:
    """WikiPage: Represents a wiki page (new or existing).
    """
    def __init__(self, name, version, perm, db):
        self.db = db
        self.name = name
        self.perm = perm
        cursor = self.db.cursor ()
        if version:
            cursor.execute ('SELECT version, text, readonly FROM wiki '
                            'WHERE name=%s AND version=%s',
                            name, version)
        else:
            cursor.execute ('SELECT version, text, readonly FROM wiki '
                            'WHERE name=%s ORDER BY version DESC LIMIT 1', name)
        row = cursor.fetchone()
        if row:
            self.new = 0
            self.version = int(row[0])
            self.text = row[1]
            self.readonly = row[2] and int(row[2]) or 0
        else:
            self.version = 0
            self.new = 1
            if not self.perm.has_permission( 'WIKI_CREATE' ):
                self.text = 'Wiki page %s not found' % name
                self.readonly = 1
            else:
                self.text = 'describe %s here' % name
                self.readonly = 0
                
        self.old_readonly = self.readonly
        self.modified = 0

    def set_content (self, text):
        self.modified = self.text != text
        self.text = text
        self.version = self.version + 1

    def commit (self, author, comment, remote_addr):
        if self.new:
            self.perm.assert_permission (perm.WIKI_CREATE)
        else:
            self.perm.assert_permission (perm.WIKI_MODIFY)
        if self.readonly:
            self.perm.assert_permission (perm.WIKI_ADMIN)

        cursor = self.db.cursor ()
        if not self.modified and self.readonly != self.old_readonly:
            cursor.execute ('UPDATE wiki SET readonly=%s WHERE name=%s and VERSION=%s',
                            self.readonly, self.name, self.version - 1)
            self.db.commit ()
            self.old_readonly = self.readonly
        elif self.modified:
            cursor.execute ('INSERT INTO WIKI '
                            '(name, version, time, author, ipnr, text, comment, readonly) '
                            'VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
                            self.name, self.version, int(time.time()),
                            author, remote_addr, self.text, comment, self.readonly)
            self.db.commit ()
            self.old_readonly = self.readonly
            self.modified = 0
        else:
            del cursor
            raise TracError('Page not modified')
            

class WikiModule(Module):
    template_name = 'wiki.cs'

    def generate_history(self, pagename):
        """
        Extract the complete history for a given page and stores it in the hdf.
        This information is used to present a changelog/history for a given page
        """
        cursor = self.db.cursor ()
        cursor.execute ('SELECT version, time, author, comment, ipnr FROM wiki '
                        'WHERE name=%s ORDER BY version DESC', pagename)
        i = 0
        while 1:
            row = cursor.fetchone()
            if not row: break
            elif i == 0:
                self.req.hdf.setValue('wiki.history', '1')

            time_str = time.strftime('%x %X', time.localtime(int(row[1])))

            n = 'wiki.history.%d' % i
            self.req.hdf.setValue(n, str(i))
            self.req.hdf.setValue(n+'.url',
                                  escape(self.env.href.wiki(pagename, str(row[0]))))
            self.req.hdf.setValue(n+'.diff_url',
                                  escape(self.env.href.wiki(pagename, str(row[0]), 1)))
            self.req.hdf.setValue(n+'.version', str(row[0]))
            self.req.hdf.setValue(n+'.time', time_str)
            self.req.hdf.setValue(n+'.author', str(row[2]))
            self.req.hdf.setValue(n+'.comment', wiki_to_oneliner(row[3] or '', self.req.hdf, self.env, self.db))
            self.req.hdf.setValue(n+'.ipaddr', str(row[4]))
            i = i + 1

    def generate_diff(self, pagename, version):
        import Diff
        Diff.get_options(self.env, self.req)
        if self.req.args.has_key('update'):
           self.req.redirect(self.env.href.wiki(pagename, version, 1))

        cursor = self.db.cursor()
        cursor.execute ('SELECT text,author,comment,time FROM wiki '
                        'WHERE name=%s AND (version=%s or version=%s)'
                        'ORDER BY version ASC', pagename, version - 1, version)
        res = cursor.fetchall()
        if not res:
            raise TracError('Version %d of page "%s" not found.'
                            % (version, pagename),
                            'Page Not Found')

        if len(res) == 1:
            old = ''
        else:
            old = res[0][0].splitlines()
        new = res[-1][0].splitlines()
        author = res[-1][1] or ''
        comment = res[-1][2] or ''
        time_str = time.strftime('%c', time.localtime(int(res[-1][3])))
        self.req.hdf.setValue('wiki.version', str(version))
        self.req.hdf.setValue('wiki.time', time_str)
        self.req.hdf.setValue('wiki.author', escape(author))
        self.req.hdf.setValue('wiki.comment', escape(comment))

        builder = Diff.HDFBuilder(self.req.hdf, 'wiki.diff')
        builder.writeline('@@ -1,%d +1,%d @@' % (len(old), len(new)))
        try:
            for line in difflib.Differ().compare(old, new):
                if line != '  ':
                    builder.writeline(line)
        except AttributeError:
            raise TracError('Python >= 2.2 is required for diff support.')
        builder.close()

    def render(self, req):
        self.req = req # FIXME
        name = req.args.get('page', 'WikiStart')
        author = req.args.get('author', get_reporter_id(self.req))
        edit_version = req.args.get('edit_version', None)
        delete_ver = req.args.get('delete_ver', None)
        delete_page = req.args.get('delete_page', None)
        comment = req.args.get('comment', '')
        save = req.args.get('save', None)
        edit = req.args.get('edit', None)
        diff = req.args.get('diff', None)
        cancel = req.args.get('cancel', None)
        preview = req.args.get('preview', None)
        history = req.args.get('history', None)
        version = int(req.args.get('version', 0))
        readonly = req.args.get('readonly', None)

        # Ask web spiders to not index old version
        if diff or version:
            req.hdf.setValue('html.norobots', '1')

        if cancel:
            req.redirect(self.env.href.wiki(name))
            # Not reached

        if delete_ver and edit_version and name:
            # Delete only a specific page version
            self.perm.assert_permission(perm.WIKI_DELETE)
            cursor = self.db.cursor()
            cursor.execute ('DELETE FROM wiki WHERE name=%s and version=%s',
                            name, int(edit_version))
            self.db.commit()
            self.log.info('Deleted version %d of page %s' % (int(edit_version), name))
            if int(edit_version) > 1:
                req.redirect(self.env.href.wiki(name))
            else:
                # Delete orphaned attachments
                for attachment in self.env.get_attachments(self.db, 'wiki', name):
                    self.env.delete_attachment(self.db, 'wiki', name, attachment[0])
                req.redirect(self.env.href.wiki())
            # Not reached

        if delete_page and name:
            # Delete a wiki page completely
            self.perm.assert_permission(perm.WIKI_DELETE)
            cursor = self.db.cursor()
            cursor.execute ('DELETE FROM wiki WHERE name=%s', name)
            self.db.commit()
            self.log.info('Deleted version %d of page ' + name)
            # Delete orphaned attachments
            for attachment in self.env.get_attachments(self.db, 'wiki', name):
                self.env.delete_attachment(self.db, 'wiki', name, attachment[0])
            req.redirect(self.env.href.wiki())
            # Not reached

        req.hdf.setValue('wiki.name', escape(name))
        req.hdf.setValue('wiki.author', escape(author))
        req.hdf.setValue('wiki.comment', escape(comment))
        # Workaround so that we can attach files to wiki pages
        # even if the page name contains a '/'
        req.hdf.setValue('wiki.namedoublequoted',
                              urllib.quote(urllib.quote(name, '')))

        editrows = req.args.get('editrows')
        if editrows:
            req.hdf.setValue('wiki.edit_rows', editrows)
            pref = req.session.get('wiki_editrows', '20')
            if editrows != pref:
                req.session.set_var('wiki_editrows', editrows)
        else:
            req.hdf.setValue('wiki.edit_rows',
                                  req.session.get('wiki_editrows', '20'))

        if save:
            req.hdf.setValue('wiki.action', 'save')
        elif edit:
            self.perm.assert_permission (perm.WIKI_MODIFY)
            req.hdf.setValue('wiki.action', 'edit')
            req.hdf.setValue('title', escape(name) + ' (edit)')
        elif preview:
            req.hdf.setValue('wiki.action', 'preview')
            req.hdf.setValue('wiki.scroll_bar_pos',
                                  req.args.get('scroll_bar_pos', ''))
            req.hdf.setValue('title', escape(name) + ' (preview)')
        elif diff and version > 0:
            req.hdf.setValue('wiki.action', 'diff')
            self.generate_diff(name, version)
            req.hdf.setValue('title', escape(name) + ' (diff)')
        elif history:
            req.hdf.setValue('wiki.action', 'history')
            self.generate_history(name)
            req.hdf.setValue('title', escape(name) + ' (history)')
        else:
            self.perm.assert_permission (perm.WIKI_VIEW)
            if version:
                self.add_link('alternate',
                    '?version=%d&amp;format=txt' % version, 'Plain Text',
                    'text/plain')
            else:
                self.add_link('alternate', '?format=txt', 'Plain Text',
                    'text/plain')
            if req.args.has_key('text'):
                del req.args['text']
            req.hdf.setValue('wiki.action', 'view')
            if name == 'WikiStart':
                req.hdf.setValue('title', '')
            else:
                req.hdf.setValue('title', escape(name))
            self.env.get_attachments_hdf(self.db, 'wiki', name, req.hdf,
                                         'wiki.attachments')

        self.page = WikiPage(name, version, self.perm, self.db)
        if req.args.has_key('text'):
            self.page.set_content (req.args.get('text'))
        else:
            self.page.modified = 0

        # Modify the read-only flag if it has been changed and the user is WIKI_ADMIN
        if save and self.perm.has_permission(perm.WIKI_ADMIN):
            if readonly:
                self.page.readonly = 1
            else:
                self.page.readonly = 0
                
        req.hdf.setValue('wiki.readonly', str(self.page.readonly))
        # We store the page version when we start editing a page.
        # This way we can stop users from saving changes if they are
        # not based on the latest version any more
        if edit_version:
            req.hdf.setValue('wiki.edit_version', edit_version)
        else:
            req.hdf.setValue('wiki.edit_version', str(self.page.version))

        if save and edit_version != str(self.page.version - 1):
            raise TracError('Sorry, Cannot create new version, this page has '
                            'already been modified by someone else.')

        if save:
            self.page.commit(author, comment, req.remote_addr)
            req.redirect(self.env.href.wiki(self.page.name))

        req.hdf.setValue('wiki.current_href',
                              escape(self.env.href.wiki(self.page.name)))
        req.hdf.setValue('wiki.history_href',
                              escape(self.env.href.wiki(self.page.name,
                                                        history=1)))
        req.hdf.setValue('wiki.page_name', escape(self.page.name))
        req.hdf.setValue('wiki.page_source', escape(self.page.text))
        out = StringIO.StringIO()
        Formatter(req.hdf, self.env,self.db).format(self.page.text, out)
        req.hdf.setValue('wiki.page_html', out.getvalue())

    def display_txt(self, req):
        req.send_response(200)
        req.send_header('Content-Type', 'text/plain;charset=utf-8')
        req.end_headers()
        req.write(self.page.text)
