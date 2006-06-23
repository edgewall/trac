# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2006 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2004-2005 Christopher Lenz <cmlenz@gmx.de>
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
#         Christopher Lenz <cmlenz@gmx.de>

import os
import re
import StringIO

from trac.attachment import attachments_to_hdf, Attachment, AttachmentModule
from trac.core import *
from trac.perm import IPermissionRequestor
from trac.Search import ISearchSource, search_to_sql, shorten_result
from trac.Timeline import ITimelineEventProvider
from trac.util import get_reporter_id
from trac.util.datefmt import format_datetime, pretty_timedelta
from trac.util.text import shorten_line
from trac.util.markup import html, Markup
from trac.versioncontrol.diff import get_diff_options, hdf_diff
from trac.web.chrome import add_link, add_stylesheet, INavigationContributor
from trac.web import HTTPNotFound, IRequestHandler
from trac.wiki.api import IWikiPageManipulator, WikiSystem
from trac.wiki.model import WikiPage
from trac.wiki.formatter import wiki_to_html, wiki_to_oneliner
from trac.mimeview.api import Mimeview, IContentConverter


class InvalidWikiPage(TracError):
    """Exception raised when a Wiki page fails validation."""


class WikiModule(Component):

    implements(INavigationContributor, IPermissionRequestor, IRequestHandler,
               ITimelineEventProvider, ISearchSource, IContentConverter)

    page_manipulators = ExtensionPoint(IWikiPageManipulator)

    # IContentConverter methods
    def get_supported_conversions(self):
        yield ('txt', 'Plain Text', 'txt', 'text/x-trac-wiki', 'text/plain', 9)

    def convert_content(self, req, mimetype, content, key):
        return (content, 'text/plain;charset=utf-8')

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'wiki'

    def get_navigation_items(self, req):
        if not req.perm.has_permission('WIKI_VIEW'):
            return
        yield ('mainnav', 'wiki',
               html.A('Wiki', href=req.href.wiki(), accesskey=1))
        yield ('metanav', 'help',
               html.A('Help/Guide', href=req.href.wiki('TracGuide'),
                      accesskey=6))

    # IPermissionRequestor methods

    def get_permission_actions(self):
        actions = ['WIKI_CREATE', 'WIKI_DELETE', 'WIKI_MODIFY', 'WIKI_VIEW']
        return actions + [('WIKI_ADMIN', actions)]

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

        if pagename.endswith('/'):
            req.redirect(req.href.wiki(pagename.strip('/')))

        db = self.env.get_db_cnx()
        page = WikiPage(self.env, pagename, version, db)

        add_stylesheet(req, 'common/css/wiki.css')

        if req.method == 'POST':
            if action == 'edit':
                latest_version = WikiPage(self.env, pagename, None, db).version
                if req.args.has_key('cancel'):
                    req.redirect(req.href.wiki(page.name))
                elif int(version) != latest_version:
                    action = 'collision'
                    self._render_editor(req, db, page)
                elif req.args.has_key('preview'):
                    action = 'preview'
                    self._render_editor(req, db, page, preview=True)
                else:
                    self._do_save(req, db, page)
            elif action == 'delete':
                self._do_delete(req, db, page)
            elif action == 'diff':
                get_diff_options(req)
                req.redirect(req.href.wiki(page.name, version=page.version,
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
            format = req.args.get('format')
            if format:
                Mimeview(self.env).send_converted(req, 'text/x-trac-wiki',
                                                  page.text, format, page.name)
            self._render_view(req, db, page)

        req.hdf['wiki.action'] = action
        req.hdf['wiki.current_href'] = req.href.wiki(page.name)
        return 'wiki.cs', None

    # ITimelineEventProvider methods

    def get_timeline_filters(self, req):
        if req.perm.has_permission('WIKI_VIEW'):
            yield ('wiki', 'Wiki changes')

    def get_timeline_events(self, req, start, stop, filters):
        if 'wiki' in filters:
            wiki = WikiSystem(self.env)
            format = req.args.get('format')
            href = format == 'rss' and req.abs_href or req.href
            db = self.env.get_db_cnx()
            cursor = db.cursor()
            cursor.execute("SELECT time,name,comment,author "
                           "FROM wiki WHERE time>=%s AND time<=%s",
                           (start, stop))
            for t,name,comment,author in cursor:
                title = Markup('<em>%s</em> edited by %s',
                               wiki.format_page_name(name), author)
                if format == 'rss':
                    comment = wiki_to_html(comment or '--', self.env, req, db,
                                           absurls=True)
                else:
                    comment = wiki_to_oneliner(comment, self.env, db,
                                               shorten=True)
                yield 'wiki', href.wiki(name), title, t, author, comment

            # Attachments
            def display(id):
                return Markup('ticket ', html.EM('#', id))
            att = AttachmentModule(self.env)
            for event in att.get_timeline_events(req, db, 'wiki', format,
                                                 start, stop,
                                                 lambda id: html.EM(id)):
                yield event

    # Internal methods

    def _set_title(self, req, page, action):
        title = name = WikiSystem(self.env).format_page_name(page.name)
        if action:
            title += ' (%s)' % action
        req.hdf['wiki.page_name'] = name
        req.hdf['title'] = title
        return title

    def _do_delete(self, req, db, page):
        if page.readonly:
            req.perm.assert_permission('WIKI_ADMIN')
        else:
            req.perm.assert_permission('WIKI_DELETE')

        if req.args.has_key('cancel'):
            req.redirect(req.href.wiki(page.name))

        version = None
        if req.args.has_key('version'):
            version = int(req.args.get('version', 0))

        page.delete(version, db)
        db.commit()

        if not page.exists:
            req.redirect(req.href.wiki())
        else:
            req.redirect(req.href.wiki(page.name))

    def _do_save(self, req, db, page):
        if page.readonly:
            req.perm.assert_permission('WIKI_ADMIN')
        elif not page.exists:
            req.perm.assert_permission('WIKI_CREATE')
        else:
            req.perm.assert_permission('WIKI_MODIFY')

        page.text = req.args.get('text')
        if req.perm.has_permission('WIKI_ADMIN'):
            # Modify the read-only flag if it has been changed and the user is
            # WIKI_ADMIN
            page.readonly = int(req.args.has_key('readonly'))

        # Give the manipulators a pass at post-processing the page
        for manipulator in self.page_manipulators:
            for field, message in manipulator.validate_wiki_page(req, page):
                if field:
                    raise InvalidWikiPage("The Wiki page field %s is invalid: %s"
                                          % (field, message))
                else:
                    raise InvalidWikiPage("Invalid Wiki page: %s" % message)

        page.save(get_reporter_id(req, 'author'), req.args.get('comment'),
                  req.remote_addr)
        req.redirect(req.href.wiki(page.name))

    def _render_confirm(self, req, db, page):
        if page.readonly:
            req.perm.assert_permission('WIKI_ADMIN')
        else:
            req.perm.assert_permission('WIKI_DELETE')

        version = None
        if req.args.has_key('delete_version'):
            version = int(req.args.get('version', 0))

        self._set_title(req, page, 'delete')
        req.hdf['wiki'] = {'mode': 'delete'}
        if version is not None:
            req.hdf['wiki.version'] = version
            num_versions = 0
            for change in page.get_history():
                num_versions += 1;
                if num_versions > 1:
                    break
            req.hdf['wiki.only_version'] = num_versions == 1

    def _render_diff(self, req, db, page):
        req.perm.assert_permission('WIKI_VIEW')

        if not page.exists:
            raise TracError("Version %s of page %s does not exist" %
                            (req.args.get('version'), page.name))

        add_stylesheet(req, 'common/css/diff.css')

        self._set_title(req, page, 'diff')

        # Ask web spiders to not index old versions
        req.hdf['html.norobots'] = 1

        old_version = req.args.get('old_version')
        if old_version:
            old_version = int(old_version)
            if old_version == page.version:
                old_version = None
            elif old_version > page.version: # FIXME: what about reverse diffs?
                old_version, page = page.version, \
                                    WikiPage(self.env, page.name, old_version)
        new_version = int(page.version)
        info = {
            'version': new_version,
            'history_href': req.href.wiki(page.name, action='history')
        }
        num_changes = 0
        old_page = None
        for version,t,author,comment,ipnr in page.get_history():
            if version == new_version:
                if t:
                    info['time'] = format_datetime(t)
                    info['time_delta'] = pretty_timedelta(t)
                info['author'] = author or 'anonymous'
                info['comment'] = comment or '--'
                info['ipnr'] = ipnr or ''
            else:
                num_changes += 1
                if version < new_version:
                    if (old_version and version == old_version) or \
                            not old_version:
                        old_page = WikiPage(self.env, page.name, version)
                        info['num_changes'] = num_changes
                        info['old_version'] = version
                        break
        req.hdf['wiki'] = info

        # -- prev/next links
        if new_version > 1:
            add_link(req, 'prev', req.href.wiki(page.name, action='diff',
                                                version=new_version-1),
                     'Version %d' % (new_version-1))
        latest_page = WikiPage(self.env, page.name)
        if new_version < latest_page.version:
            add_link(req, 'next', req.href.wiki(page.name, action='diff',
                                                version=new_version+1),
                     'Version %d' % (new_version+1))

        # -- text diffs
        diff_style, diff_options = get_diff_options(req)

        oldtext = old_page and old_page.text.splitlines() or []
        newtext = page.text.splitlines()
        context = 3
        for option in diff_options:
            if option.startswith('-U'):
                context = int(option[2:])
                break
        if context < 0:
            context = None
        changes = hdf_diff(oldtext, newtext, context=context,
                           ignore_blank_lines='-B' in diff_options,
                           ignore_case='-i' in diff_options,
                           ignore_space_changes='-b' in diff_options)
        req.hdf['wiki.diff'] = changes

    def _render_editor(self, req, db, page, preview=False):
        req.perm.assert_permission('WIKI_MODIFY')

        if req.args.has_key('text'):
            page.text = req.args.get('text')
        if preview:
            page.readonly = req.args.has_key('readonly')

        author = get_reporter_id(req, 'author')
        comment = req.args.get('comment', '')
        editrows = req.args.get('editrows')
        if editrows:
            pref = req.session.get('wiki_editrows', '20')
            if editrows != pref:
                req.session['wiki_editrows'] = editrows
        else:
            editrows = req.session.get('wiki_editrows', '20')

        self._set_title(req, page, 'edit')
        info = {
            'page_source': page.text,
            'version': page.version,
            'author': author,
            'comment': comment,
            'readonly': page.readonly,
            'edit_rows': editrows,
            'scroll_bar_pos': req.args.get('scroll_bar_pos', '')
        }
        if page.exists:
            info['history_href'] = req.href.wiki(page.name,
                                                      action='history')
        if preview:
            info['page_html'] = wiki_to_html(page.text, self.env, req, db)
            info['readonly'] = int(req.args.has_key('readonly'))
        req.hdf['wiki'] = info

    def _render_history(self, req, db, page):
        """Extract the complete history for a given page and stores it in the
        HDF.

        This information is used to present a changelog/history for a given
        page.
        """
        req.perm.assert_permission('WIKI_VIEW')

        if not page.exists:
            raise TracError, "Page %s does not exist" % page.name

        self._set_title(req, page, 'history')

        history = []
        for version, t, author, comment, ipnr in page.get_history():
            history.append({
                'url': req.href.wiki(page.name, version=version),
                'diff_url': req.href.wiki(page.name, version=version,
                                          action='diff'),
                'version': version,
                'time': format_datetime(t),
                'time_delta': pretty_timedelta(t),
                'author': author,
                'comment': wiki_to_oneliner(comment or '', self.env, db),
                'ipaddr': ipnr
            })
        req.hdf['wiki.history'] = history

    def _render_view(self, req, db, page):
        req.perm.assert_permission('WIKI_VIEW')

        page_name = self._set_title(req, page, '')
        if page.name == 'WikiStart':
            req.hdf['title'] = ''

        version = req.args.get('version')
        if version:
            # Ask web spiders to not index old versions
            req.hdf['html.norobots'] = 1

        # Add registered converters
        for conversion in Mimeview(self.env).get_supported_conversions(
                                             'text/x-trac-wiki'):
            conversion_href = req.href.wiki(page.name, version=version,
                                            format=conversion[0])
            add_link(req, 'alternate', conversion_href, conversion[1],
                     conversion[3])

        req.hdf['wiki'] = {'exists': page.exists,
                           'version': page.version, 'readonly': page.readonly}
        if page.exists:
            req.hdf['wiki.page_html'] = wiki_to_html(page.text, self.env, req)
            history_href = req.href.wiki(page.name, action='history')
            req.hdf['wiki.history_href'] = history_href
        else:
            if not req.perm.has_permission('WIKI_CREATE'):
                raise HTTPNotFound('Page %s not found', page.name)
            req.hdf['wiki.page_html'] = html.P('Describe "%s" here' % page_name)

        # Show attachments
        req.hdf['wiki.attachments'] = attachments_to_hdf(self.env, req, db,
                                                         'wiki', page.name)
        if req.perm.has_permission('WIKI_MODIFY'):
            attach_href = req.href.attachment('wiki', page.name)
            req.hdf['wiki.attach_href'] = attach_href

    # ISearchSource methods

    def get_search_filters(self, req):
        if req.perm.has_permission('WIKI_VIEW'):
            yield ('wiki', 'Wiki')

    def get_search_results(self, req, terms, filters):
        if not 'wiki' in filters:
            return
        db = self.env.get_db_cnx()
        sql_query, args = search_to_sql(db, ['w1.name', 'w1.author', 'w1.text'], terms)
        cursor = db.cursor()
        cursor.execute("SELECT w1.name,w1.time,w1.author,w1.text "
                       "FROM wiki w1,"
                       "(SELECT name,max(version) AS ver "
                       "FROM wiki GROUP BY name) w2 "
                       "WHERE w1.version = w2.ver AND w1.name = w2.name "
                       "AND " + sql_query, args)

        for name, date, author, text in cursor:
            yield (req.href.wiki(name), '%s: %s' % (name, shorten_line(text)),
                   date, author, shorten_result(text, terms))
