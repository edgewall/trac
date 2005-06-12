# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2003, 2004, 2005 Edgewall Software
# Copyright (C) 2003, 2004, 2005 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2004, 2005 Christopher Lenz <cmlenz@gmx.de>
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
#         Christopher Lenz <cmlenz@gmx.de>

from __future__ import generators
import os
import re
import time
import StringIO

from trac import perm
from trac.attachment import attachment_to_hdf, Attachment
from trac.core import *
from trac.Timeline import ITimelineEventProvider
from trac.util import enum, escape, get_reporter_id, shorten_line, TracError
from trac.versioncontrol.diff import get_diff_options, hdf_diff
from trac.web.chrome import add_link, add_stylesheet, INavigationContributor
from trac.web.main import IRequestHandler
from trac.wiki.model import WikiPage
from trac.wiki.formatter import wiki_to_html, wiki_to_oneliner


class WikiModule(Component):

    implements(INavigationContributor, IRequestHandler, ITimelineEventProvider)

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'wiki'

    def get_navigation_items(self, req):
        if not req.perm.has_permission(perm.WIKI_VIEW):
            return
        yield 'metanav', 'help', '<a href="%s" accesskey="6">Help/Guide</a>' \
              % escape(self.env.href.wiki('TracGuide'))
        yield 'mainnav', 'wiki', '<a href="%s" accesskey="1">Wiki</a>' \
              % escape(self.env.href.wiki())

    # IRequestHandler methods

    def match_request(self, req):
        match = re.match(r'^/wiki(?:/(.*))?', req.path_info)
        if match:
            if match.group(1):
                req.args['page'] = match.group(1)
            return 1

    def process_request(self, req):
        action = req.args.get('action', 'view')
        pagename = req.args.get('page', 'WikiStart')
        version = req.args.get('version')

        db = self.env.get_db_cnx()
        page = WikiPage(self.env, pagename, version, db)

        add_stylesheet(req, 'wiki.css')

        if req.method == 'POST':
            if action == 'edit':
                if req.args.has_key('cancel'):
                    req.redirect(self.env.href.wiki(page.name))
                elif req.args.has_key('preview'):
                    action = 'preview'
                    self._render_editor(req, db, page, preview=True)
                else:
                    self._do_save(req, db, page)
            elif action == 'delete':
                self._do_delete(req, db, page)
            elif action == 'diff':
                get_diff_options(req)
                req.redirect(self.env.href.wiki(page.name, version=page.version,
                                                action='diff'))
        elif action == 'delete':
            self._render_confirm(req, db, page)
        elif action == 'edit':
            self._render_editor(req, db, page)
        elif action == 'diff':
            self._render_diff(req, db, page)
        elif action == 'history':
            self._render_history(req, db, page)
        else:
            if req.args.get('format') == 'txt':
                req.send_response(200)
                req.send_header('Content-Type', 'text/plain;charset=utf-8')
                req.end_headers()
                req.write(page.text)
                return
            self._render_view(req, db, page)

        req.hdf['wiki.action'] = action
        req.hdf['wiki.page_name'] = escape(page.name)
        req.hdf['wiki.current_href'] = escape(self.env.href.wiki(page.name))
        return 'wiki.cs', None

    # ITimelineEventProvider methods

    def get_timeline_filters(self, req):
        if req.perm.has_permission(perm.WIKI_VIEW):
            yield ('wiki', 'Wiki changes')

    def get_timeline_events(self, req, start, stop, filters):
        if 'wiki' in filters:
            format = req.args.get('format')
            db = self.env.get_db_cnx()
            cursor = db.cursor()
            cursor.execute("SELECT time,name,comment,author "
                           "FROM wiki WHERE time>=%s AND time<=%s",
                           (start, stop))
            for t,name,comment,author in cursor:
                title = '<em>%s</em> edited by %s' % (
                        escape(name), escape(author))
                if format == 'rss':
                    href = self.env.abs_href.wiki(name)
                    comment = wiki_to_html(comment or '--', self.env, db,
                                           absurls=True)
                else:
                    href = self.env.href.wiki(name)
                    comment = wiki_to_oneliner(shorten_line(comment), self.env,
                                               db)
                yield 'wiki', href, title, t, author, comment

    # Internal methods

    def _do_delete(self, req, db, page):
        if page.readonly:
            req.perm.assert_permission(perm.WIKI_ADMIN)
        else:
            req.perm.assert_permission(perm.WIKI_DELETE)

        if 'cancel' in req.args.keys():
            req.redirect(self.env.href.wiki(page.name))

        version = None
        if req.args.has_key('delete_version'):
            version = int(req.args.get('version', 0))

        page.delete(version, db)
        db.commit()

        if not page.exists:
            req.redirect(self.env.href.wiki())
        else:
            req.redirect(self.env.href.wiki(page.name))

    def _do_save(self, req, db, page):
        if page.readonly:
            req.perm.assert_permission(perm.WIKI_ADMIN)
        elif not page.exists:
            req.perm.assert_permission(perm.WIKI_CREATE)
        else:
            req.perm.assert_permission(perm.WIKI_MODIFY)

        page.text = req.args.get('text')
        if req.perm.has_permission(perm.WIKI_ADMIN):
            # Modify the read-only flag if it has been changed and the user is
            # WIKI_ADMIN
            page.readonly = int(req.args.has_key('readonly'))

        # We store the page version when we start editing a page.
        # This way we can stop users from saving changes if they are
        # not based on the latest version any more
        version = int(req.args.get('version'))
        if version != page.version:
            raise TracError('Sorry, cannot create new version. This page has '
                            'already been modified by someone else.')

        page.save(req.args.get('author'), req.args.get('comment'),
                  req.remote_addr)
        req.redirect(self.env.href.wiki(page.name))

    def _render_confirm(self, req, db, page):
        if page.readonly:
            req.perm.assert_permission(perm.WIKI_ADMIN)
        else:
            req.perm.assert_permission(perm.WIKI_DELETE)

        version = None
        if req.args.has_key('delete_version'):
            version = int(req.args.get('version', 0))

        req.hdf['title'] = escape(page.name) + ' (delete)'
        req.hdf['wiki'] = {'page_name': escape(page.name), 'mode': 'delete'}
        if version is not None:
            req.hdf['wiki.version'] = version
            num_versions = 0
            for change in page.get_history():
                num_versions += 1;
                if num_versions > 1:
                    break
            req.hdf['wiki.only_version'] = num_versions == 1

    def _render_diff(self, req, db, page):
        req.perm.assert_permission(perm.WIKI_VIEW)

        if not page.exists:
            raise TracError, "Version %s of page %s does not exist" \
                             % (req.args.get('version'), page.name)

        add_stylesheet(req, 'diff.css')

        # Ask web spiders to not index old versions
        req.hdf['html.norobots'] = 1

        info = {
            'version': page.version,
            'history_href': escape(self.env.href.wiki(page.name,
                                                      action='history'))
        }
        old_page = None
        for version,t,author,comment,ipnr in page.get_history():
            if version == page.version:
                info['time'] = time.strftime('%c', time.localtime(int(t)))
                info['author'] = escape(author or 'anonymous')
                info['comment'] = escape(comment)
                info['ipnr'] = escape(ipnr or '')
            elif version < page.version:
                old_page = WikiPage(self.env, page.name, version)
                break
        req.hdf['wiki'] = info

        diff_style, diff_options = get_diff_options(req)

        oldtext = old_page and old_page.text.splitlines() or []
        newtext = page.text.splitlines()
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

    def _render_editor(self, req, db, page, preview=False):
        req.perm.assert_permission(perm.WIKI_MODIFY)

        if req.args.has_key('text'):
            page.text = req.args.get('text')
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
            'edit_rows': editrows,
            'scroll_bar_pos': req.args.get('scroll_bar_pos', '')
        }
        if page.exists:
            info['history_href'] = escape(self.env.href.wiki(page.name,
                                                             action='history'))
        if preview:
            info['page_html'] = wiki_to_html(page.text, self.env, req, db)
            info['readonly'] = int(req.args.has_key('readonly'))
        req.hdf['wiki'] = info

    def _render_history(self, req, db, page):
        """
        Extract the complete history for a given page and stores it in the hdf.
        This information is used to present a changelog/history for a given
        page.
        """
        req.perm.assert_permission(perm.WIKI_VIEW)

        if not page.exists:
            raise TracError, "Page %s does not exist" % page.name

        history = []
        for version,t,author,comment,ipnr in page.get_history():
            history.append({
                'url': escape(self.env.href.wiki(page.name, version=version)),
                'diff_url': escape(self.env.href.wiki(page.name,
                                                      version=version,
                                                      action='diff')),
                'version': version,
                'time': time.strftime('%x %X', time.localtime(int(t))),
                'author': escape(author),
                'comment': wiki_to_oneliner(comment or '', self.env, db),
                'ipaddr': ipnr
            })
        req.hdf['wiki.history'] = history

    def _render_view(self, req, db, page):
        req.perm.assert_permission(perm.WIKI_VIEW)

        if page.name == 'WikiStart':
            req.hdf['title'] = ''
        else:
            req.hdf['title'] = escape(page.name)

        version = req.args.get('version')
        if version:
            # Ask web spiders to not index old versions
            req.hdf['html.norobots'] = 1

        txt_href = self.env.href.wiki(page.name, version=version, format='txt')
        add_link(req, 'alternate', txt_href, 'Plain Text', 'text/plain')

        req.hdf['wiki'] = {'page_name': page.name, 'exists': page.exists,
                           'version': page.version, 'readonly': page.readonly}
        if page.exists:
            req.hdf['wiki.page_html'] = wiki_to_html(page.text, self.env, req)
            history_href = self.env.href.wiki(page.name, action='history')
            req.hdf['wiki.history_href'] = escape(history_href)
        else:
            if not req.perm.has_permission(perm.WIKI_CREATE):
                raise TracError('Page %s not found' % page.name)
            req.hdf['wiki.page_html'] = '<p>Describe "%s" here</p>' % page.name

        # Show attachments
        attachments = []
        for attachment in Attachment.select(self.env, 'wiki', page.name, db):
            attachments.append(attachment_to_hdf(self.env, db, req, attachment))
        req.hdf['wiki.attachments'] = attachments
        if req.perm.has_permission(perm.WIKI_MODIFY):
            attach_href = self.env.href.attachment('wiki', page.name)
            req.hdf['wiki.attach_href'] = attach_href
