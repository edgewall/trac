# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2003, 2004, 2005 Edgewall Software
# Copyright (C) 2003, 2004, 2005 Jonas Borgström <jonas@edgewall.com>
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

from trac import perm
from trac.Diff import get_diff_options, hdf_diff
from trac.Module import Module
from trac.util import escape, TracError, get_reporter_id
from trac.WikiFormatter import *

import os
import time
import StringIO


__all__ = ['populate_page_dict', 'WikiPage', 'WikiModule']


def populate_page_dict(db, env):
    """Extract wiki page names. This is used to detect broken wiki-links"""
    page_dict = {}
    cursor = db.cursor()
    cursor.execute("SELECT DISTINCT name FROM wiki")
    while 1:
        row = cursor.fetchone()
        if not row:
            break
        page_dict[row[0]] = 1
    env._wiki_pages = page_dict


class WikiPage:
    """
    Represents a wiki page (new or existing).
    """

    def __init__(self, name, version, perm_, db):
        self.db = db
        self.name = name
        self.perm = perm_
        cursor = self.db.cursor ()
        if version:
            cursor.execute("SELECT version,text,readonly FROM wiki "
                           "WHERE name=%s AND version=%s",
                           (name, version))
        else:
            cursor.execute("SELECT version,text,readonly FROM wiki "
                           "WHERE name=%s ORDER BY version DESC LIMIT 1",
                           (name,))
        row = cursor.fetchone()
        if row:
            self.new = 0
            self.version = int(row[0])
            self.text = row[1]
            self.readonly = row[2] and int(row[2]) or 0
        else:
            self.version = 0
            self.new = 1
            if not self.perm.has_permission(perm.WIKI_CREATE):
                self.text = 'Wiki page %s not found' % name
                self.readonly = 1
            else:
                self.text = 'describe %s here' % name
                self.readonly = 0
        self.old_readonly = self.readonly
        self.modified = 0

    def set_content(self, text):
        self.modified = self.text != text
        self.text = text

    def commit(self, author, comment, remote_addr):
        if self.readonly:
            self.perm.assert_permission(perm.WIKI_ADMIN)
        elif self.new:
            self.perm.assert_permission(perm.WIKI_CREATE)
        else:
            self.perm.assert_permission(perm.WIKI_MODIFY)

        if not self.modified and self.readonly != self.old_readonly:
            cursor = self.db.cursor()
            cursor.execute("UPDATE wiki SET readonly=%s WHERE name=%s"
                           "AND version=%s",
                           (self.readonly, self.name, self.version))
            self.db.commit()
            self.old_readonly = self.readonly
        elif self.modified:
            cursor = self.db.cursor()
            cursor.execute ("INSERT INTO WIKI (name,version,time,author,ipnr,"
                            "text,comment,readonly) VALUES (%s,%s,%s,%s,%s,%s,"
                            "%s,%s)", (self.name, self.version + 1,
                            int(time.time()), author, remote_addr, self.text,
                            comment, self.readonly))
            self.db.commit()
            self.version += 1
            self.old_readonly = self.readonly
            self.modified = 0
        else:
            raise TracError('Page not modified')


class WikiModule(Module):
    template_name = 'wiki.cs'

    def render(self, req):
        action = req.args.get('action', 'view')
        pagename = req.args.get('page', 'WikiStart')
        req.hdf['wiki.action'] = action
        req.hdf['wiki.page_name'] = escape(pagename)
        req.hdf['wiki.current_href'] = escape(self.env.href.wiki(pagename))

        if action == 'diff':
            version = int(req.args.get('version', 0))
            self._render_diff(req, pagename, version)
        elif action == 'history':
            self._render_history(req, pagename)
        elif action == 'edit':
            self._render_editor(req, pagename)
        elif action == 'delete':
            version = None
            if req.args.has_key('delete_version'):
                version = int(req.args['version'])
            self._delete_page(req, pagename, version)
        elif action == 'save':
            if req.args.has_key('cancel'):
                req.redirect(self.env.href.wiki(pagename))
            elif req.args.has_key('preview'):
                req.hdf['wiki.action'] = 'preview'
                self._render_editor(req, pagename, 1)
            else:
                self._save_page(req, pagename)
        else:
            self._render_view(req, pagename)

    def display_txt(self, req):
        req.send_response(200)
        req.send_header('Content-Type', 'text/plain;charset=utf-8')
        req.end_headers()
        req.write(req.hdf.get('wiki.page_source', ''))

    def _delete_page(self, req, pagename, version=None):
        self.perm.assert_permission(perm.WIKI_DELETE)

        page_deleted = 0
        cursor = self.db.cursor()
        if version is not None: # Delete only a specific page version
            cursor = self.db.cursor()
            cursor.execute("DELETE FROM wiki WHERE name=%s and version=%s",
                           (pagename, version))
            self.log.info('Deleted version %d of page %s' % (version, pagename))
            cursor.execute("SELECT COUNT(*) FROM wiki WHERE name=%s", (pagename,))
            if not cursor.fetchone():
                page_deleted = 1
        else: # Delete a wiki page completely
            cursor.execute("DELETE FROM wiki WHERE name=%s", (pagename,))
            page_deleted = 1
            self.log.info('Deleted page %s' % pagename)
        self.db.commit()

        if page_deleted:
            # Delete orphaned attachments
            for attachment in self.env.get_attachments(self.db, 'wiki', pagename):
                self.env.delete_attachment(self.db, 'wiki', pagename,
                                           attachment[0])
            req.redirect(self.env.href.wiki())
        else:
            req.redirect(self.env.href.wiki(pagename))

    def _render_diff(self, req, pagename, version):
        # Stores the diff-style in the session if it has been changed, and adds
        # diff-style related item to the HDF
        self.perm.assert_permission(perm.WIKI_VIEW)

        diff_style, diff_options = get_diff_options(req)
        if req.args.has_key('update'):
           req.redirect(self.env.href.wiki(pagename, version, action='diff'))

        # Ask web spiders to not index old versions
        req.hdf['html.norobots'] = 1

        cursor = self.db.cursor()
        cursor.execute("SELECT text,author,comment,time FROM wiki "
                       "WHERE name=%s AND version IN (%s,%s) ORDER BY version",
                       (pagename, version - 1, version))
        rows = cursor.fetchall()
        if not rows:
            raise TracError('Version %d of page "%s" not found.'
                            % (version, pagename),
                            'Page Not Found')
        info = {
            'version': version,
            'time': time.strftime('%c', time.localtime(int(rows[-1][3]))),
            'author': escape(rows[-1][1] or ''),
            'comment': escape(rows[-1][2] or ''),
            'history_href': escape(self.env.href.wiki(pagename, action='history'))
        }
        req.hdf['wiki'] = info

        if len(rows) == 1:
            oldtext = ''
        else:
            oldtext = rows[0][0].splitlines()
        newtext = rows[-1][0].splitlines()

        context = 3
        for option in diff_options:
            if option[:2] == '-U':
                context = int(option[2:])
                break
        changes = hdf_diff(oldtext, newtext, context=context,
                           ignore_blank_lines='-B' in diff_options,
                           ignore_case='-i' in diff_options,
                           ignore_space_changes='-b' in diff_options)
        req.hdf['wiki.diff'] = changes

    def _render_editor(self, req, pagename, preview=0):
        self.perm.assert_permission(perm.WIKI_MODIFY)

        page = WikiPage(pagename, None, self.perm, self.db)
        if req.args.has_key('text'):
            page.set_content(req.args.get('text'))
        if preview:
            page.readonly = req.args.has_key('readonly')

        author = req.args.get('author', get_reporter_id(req))
        version = req.args.get('edit_version', None)
        comment = req.args.get('comment', '')
        editrows = req.args.get('editrows')
        if editrows:
            pref = req.session.get('wiki_editrows', '20')
            if editrows != pref:
                req.session['wiki_editrows'] = editrows
        else:
            editrows = req.session.get('wiki_editrows', '20')

        req.hdf['title'] = escape(page.name) + ' (edit)'
        info = {
            'page_source': escape(page.text),
            'version': page.version,
            'author': escape(author),
            'comment': escape(comment),
            'readonly': page.readonly,
            'history_href': escape(self.env.href.wiki(page.name, action='history')),
            'edit_rows': editrows,
            'scroll_bar_pos': req.args.get('scroll_bar_pos', '')
        }
        if preview:
            info['page_html'] = wiki_to_html(page.text, req.hdf, self.env, self.db)
        req.hdf['wiki'] = info

    def _render_history(self, req, pagename):
        """
        Extract the complete history for a given page and stores it in the hdf.
        This information is used to present a changelog/history for a given page
        """
        self.perm.assert_permission(perm.WIKI_VIEW)

        cursor = self.db.cursor ()
        cursor.execute("SELECT version,time,author,comment,ipnr FROM wiki "
                       "WHERE name=%s ORDER BY version DESC", (pagename,))
        i = 0
        while 1:
            row = cursor.fetchone()
            if not row:
                break
            item = {
                'url': escape(self.env.href.wiki(pagename, row[0])),
                'diff_url': escape(self.env.href.wiki(pagename, row[0], action='diff')),
                'version': row[0],
                'time': time.strftime('%x %X', time.localtime(int(row[1]))),
                'author': escape(row[2]),
                'comment': wiki_to_oneliner(row[3] or '', self.env, self.db),
                'ipaddr': row[4]
            }
            req.hdf['wiki.history.%d' % i] = item
            i = i + 1

    def _render_view(self, req, pagename):
        self.perm.assert_permission(perm.WIKI_VIEW)

        if pagename == 'WikiStart':
            req.hdf['title'] = ''
        else:
            req.hdf['title'] = escape(pagename)

        version = req.args.get('version')
        if version:
            self.add_link('alternate',
                          '?version=%s&amp;format=txt' % version, 'Plain Text',
                          'text/plain')
            # Ask web spiders to not index old versions
            req.hdf['html.norobots'] = 1
        else:
            self.add_link('alternate', '?format=txt', 'Plain Text',
                          'text/plain')

        page = WikiPage(pagename, version, self.perm, self.db)

        info = {
            'version': page.version,
            'readonly': page.readonly,
            'page_html': wiki_to_html(page.text, req.hdf, self.env, self.db),
            'page_source': page.text, # for plain text view
            'history_href': escape(self.env.href.wiki(page.name,
                                                      action='history'))
        }
        req.hdf['wiki'] = info

        self.env.get_attachments_hdf(self.db, 'wiki', pagename, req.hdf,
                                     'wiki.attachments')
        req.hdf['wiki.attach_href'] = self.env.href.attachment('wiki',
                                                               pagename, None)

    def _save_page(self, req, pagename):
        self.perm.assert_permission(perm.WIKI_MODIFY)

        page = WikiPage(pagename, None, self.perm, self.db)
        if req.args.has_key('text'):
            page.set_content(req.args.get('text'))

        # Modify the read-only flag if it has been changed and the user is
        # WIKI_ADMIN
        if self.perm.has_permission(perm.WIKI_ADMIN):
            page.readonly = int(req.args.has_key('readonly'))

        # We store the page version when we start editing a page.
        # This way we can stop users from saving changes if they are
        # not based on the latest version any more
        edit_version = int(req.args.get('version'))
        if edit_version != page.version:
            raise TracError('Sorry, cannot create new version. This page has '
                            'already been modified by someone else.')

        page.commit(req.args.get('author'), req.args.get('comment'),
                    req.remote_addr)
        req.redirect(self.env.href.wiki(page.name))
