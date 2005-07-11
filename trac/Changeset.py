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
import time
import re

from trac import mimeview, util
from trac.core import *
from trac.perm import IPermissionRequestor
from trac.Timeline import ITimelineEventProvider
from trac.versioncontrol import Changeset, Node
from trac.versioncontrol.diff import get_diff_options, hdf_diff, unified_diff
from trac.web.chrome import add_link, add_stylesheet, INavigationContributor
from trac.web.main import IRequestHandler
from trac.wiki import wiki_to_html, wiki_to_oneliner, IWikiSyntaxProvider


class ChangesetModule(Component):

    implements(INavigationContributor, IPermissionRequestor, IRequestHandler,
               ITimelineEventProvider, IWikiSyntaxProvider)

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'browser'

    def get_navigation_items(self, req):
        return []

    # IPermissionRequestor methods

    def get_permission_actions(self):
        return ['CHANGESET_VIEW']

    # IRequestHandler methods

    def match_request(self, req):
        match = re.match(r'/changeset/([0-9]+)$', req.path_info)
        if match:
            req.args['rev'] = match.group(1)
            return 1

    def process_request(self, req):
        req.perm.assert_permission('CHANGESET_VIEW')

        rev = req.args.get('rev')
        repos = self.env.get_repository(req.authname)

        diff_options = get_diff_options(req)
        if req.args.has_key('update'):
            req.redirect(self.env.href.changeset(rev))

        chgset = repos.get_changeset(rev)
        req.check_modified(chgset.date,
                           diff_options[0] + ''.join(diff_options[1]))

        format = req.args.get('format')
        if format == 'diff':
            self._render_diff(req, repos, chgset, diff_options)
            return
        elif format == 'zip':
            self._render_zip(req, repos, chgset)
            return

        self._render_html(req, repos, chgset, diff_options)
        add_link(req, 'alternate', '?format=diff', 'Unified Diff',
                 'text/plain', 'diff')
        add_link(req, 'alternate', '?format=zip', 'Zip Archive',
                 'application/zip', 'zip')
        add_stylesheet(req, 'css/changeset.css')
        add_stylesheet(req, 'css/diff.css')
        return 'changeset.cs', None

    # ITimelineEventProvider methods

    def get_timeline_filters(self, req):
        if req.perm.has_permission('CHANGESET_VIEW'):
            yield ('changeset', 'Repository checkins')

    def get_timeline_events(self, req, start, stop, filters):
        if 'changeset' in filters:
            format = req.args.get('format')
            show_files = int(self.config.get('timeline',
                                             'changeset_show_files'))
            db = self.env.get_db_cnx()
            repos = self.env.get_repository()
            rev = repos.youngest_rev
            while rev:
                chgset = repos.get_changeset(rev)
                if chgset.date < start:
                    return
                if chgset.date < stop:
                    title = 'Changeset <em>[%s]</em> by %s' % (
                            util.escape(chgset.rev), util.escape(chgset.author))
                    if format == 'rss':
                        href = self.env.abs_href.changeset(chgset.rev)
                        message = wiki_to_html(chgset.message or '--', self.env,
                                               db, absurls=True)
                    else:
                        href = self.env.href.changeset(chgset.rev)
                        excerpt = util.shorten_line(chgset.message or '--')
                        message = wiki_to_oneliner(excerpt, self.env, db)
                    if show_files:
                        files = []
                        for chg in chgset.get_changes():
                            if show_files > 0 and len(files) >= show_files:
                                files.append('...')
                                break
                            files.append('<span class="%s">%s</span>'
                                         % (chg[2], util.escape(chg[0])))
                        message = '<span class="changes">' + ', '.join(files) +\
                                  '</span>: ' + message
                    yield 'changeset', href, title, chgset.date, chgset.author,\
                          message
                rev = repos.previous_rev(rev)

    # Internal methods

    def _render_html(self, req, repos, chgset, diff_options):
        """HTML version"""
        req.hdf['title'] = '[%s]' % chgset.rev
        req.hdf['changeset'] = {
            'revision': chgset.rev,
            'time': time.strftime('%c', time.localtime(chgset.date)),
            'author': util.escape(chgset.author or 'anonymous'),
            'message': wiki_to_html(chgset.message or '--', self.env, req,
                                    escape_newlines=True)
        }

        oldest_rev = repos.oldest_rev
        if chgset.rev != oldest_rev:
            add_link(req, 'first', self.env.href.changeset(oldest_rev),
                     'Changeset %s' % oldest_rev)
            previous_rev = repos.previous_rev(chgset.rev)
            add_link(req, 'prev', self.env.href.changeset(previous_rev),
                     'Changeset %s' % previous_rev)
        youngest_rev = repos.youngest_rev
        if str(chgset.rev) != str(youngest_rev):
            next_rev = repos.next_rev(chgset.rev)
            add_link(req, 'next', self.env.href.changeset(next_rev),
                     'Changeset %s' % next_rev)
            add_link(req, 'last', self.env.href.changeset(youngest_rev),
                     'Changeset %s' % youngest_rev)

        edits = []
        idx = 0
        for path, kind, change, base_path, base_rev in chgset.get_changes():
            info = {'change': change}
            if base_path:
                info['path.old'] = base_path
                info['rev.old'] = base_rev
                info['browser_href.old'] = self.env.href.browser(base_path,
                                                                 rev=base_rev)
            if path:
                info['path.new'] = path
                info['rev.new'] = chgset.rev
                info['browser_href.new'] = self.env.href.browser(path,
                                                                 rev=chgset.rev)
            if change in (Changeset.COPY, Changeset.EDIT, Changeset.MOVE):
                edits.append((idx, path, kind, base_path, base_rev))
            req.hdf['changeset.changes.%d' % idx] = info
            idx += 1

        for idx, path, kind, base_path, base_rev in edits:
            old_node = repos.get_node(base_path or path, base_rev)
            new_node = repos.get_node(path, chgset.rev)

            # Property changes
            old_props = old_node.get_properties()
            new_props = new_node.get_properties()
            changed_props = {}
            if old_props != new_props:
                for k,v in old_props.items():
                    if not k in new_props:
                        changed_props[k] = {'old': v}
                    elif v != new_props[k]:
                        changed_props[k] = {'old': v, 'new': new_props[k]}
                for k,v in new_props.items():
                    if not k in old_props:
                        changed_props[k] = {'new': v}
                req.hdf['changeset.changes.%d.props' % idx] = changed_props

            if kind == Node.DIRECTORY:
                continue

            # Content changes
            default_charset = self.config.get('trac', 'default_charset')
            old_content = old_node.get_content().read()
            if mimeview.is_binary(old_content):
                continue
            charset = mimeview.get_charset(old_node.content_type) or \
                      default_charset
            old_content = util.to_utf8(old_content, charset)

            new_content = new_node.get_content().read()
            if mimeview.is_binary(new_content):
                continue
            charset = mimeview.get_charset(new_node.content_type) or \
                      default_charset
            new_content = util.to_utf8(new_content, charset)

            if old_content != new_content:
                context = 3
                for option in diff_options[1]:
                    if option[:2] == '-U':
                        context = int(option[2:])
                        break
                tabwidth = int(self.config.get('diff', 'tab_width'))
                changes = hdf_diff(old_content.splitlines(),
                                   new_content.splitlines(),
                                   context, tabwidth,
                                   ignore_blank_lines='-B' in diff_options[1],
                                   ignore_case='-i' in diff_options[1],
                                   ignore_space_changes='-b' in diff_options[1])
                req.hdf['changeset.changes.%d.diff' % idx] = changes

    def _render_diff(self, req, repos, chgset, diff_options):
        """Raw Unified Diff version"""
        req.send_response(200)
        req.send_header('Content-Type', 'text/plain;charset=utf-8')
        req.send_header('Content-Disposition',
                        'filename=Changeset%s.diff' % req.args.get('rev'))
        req.end_headers()

        for path, kind, change, base_path, base_rev in chgset.get_changes():
            if change == Changeset.ADD:
                old_node = None
            else:
                old_node = repos.get_node(base_path or path, base_rev)
            if change == Changeset.DELETE:
                new_node = None
            else:
                new_node = repos.get_node(path, chgset.rev)

            # TODO: Property changes

            # Content changes
            if kind == 'dir':
                continue

            default_charset = self.config.get('trac', 'default_charset')
            new_content = old_content = ''
            new_node_info = old_node_info = ('','')

            if old_node:
                charset = mimeview.get_charset(old_node.content_type) or \
                          default_charset
                old_content = util.to_utf8(old_node.get_content().read(),
                                           charset)
                old_node_info = (old_node.path, old_node.rev)
            if mimeview.is_binary(old_content):
                continue

            if new_node:
                charset = mimeview.get_charset(new_node.content_type) or \
                          default_charset
                new_content = util.to_utf8(new_node.get_content().read(),
                                           charset)
                new_node_info = (new_node.path, new_node.rev)
            if mimeview.is_binary(new_content):
                continue

            if old_content != new_content:
                context = 3
                for option in diff_options[1]:
                    if option[:2] == '-U':
                        context = int(option[2:])
                        break
                req.write('Index: ' + path + util.CRLF)
                req.write('=' * 67 + util.CRLF)
                req.write('--- %s (revision %s)' % old_node_info +
                          util.CRLF)
                req.write('+++ %s (revision %s)' % new_node_info +
                          util.CRLF)
                for line in unified_diff(old_content.splitlines(),
                                         new_content.splitlines(), context,
                                         ignore_blank_lines='-B' in diff_options[1],
                                         ignore_case='-i' in diff_options[1],
                                         ignore_space_changes='-b' in diff_options[1]):
                    req.write(line + util.CRLF)

    def _render_zip(self, req, repos, chgset):
        """ZIP archive with all the added and/or modified files."""
        req.send_response(200)
        req.send_header('Content-Type', 'application/zip')
        req.send_header('Content-Disposition',
                        'filename=Changeset%s.zip' % chgset.rev)
        req.end_headers()

        try:
            from cStringIO import StringIO
        except ImportError:
            from StringIO import StringIO
        from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

        buf = StringIO()
        zipfile = ZipFile(buf, 'w', ZIP_DEFLATED)
        for path, kind, change, base_path, base_rev in chgset.get_changes():
            if kind == Node.FILE and change != Changeset.DELETE:
                node = repos.get_node(path, chgset.rev)
                zipinfo = ZipInfo()
                zipinfo.filename = node.path
                zipinfo.date_time = time.gmtime(node.last_modified)[:6]
                zipinfo.compress_type = ZIP_DEFLATED
                zipfile.writestr(zipinfo, node.get_content().read())
        zipfile.close()
        req.write(buf.getvalue())

    # IWikiSyntaxProvider methods
    
    def get_wiki_syntax(self):
        yield (r"!?\[\d+\]|\br\d+\b", (lambda x, y, z: self._format_link(x, 'changeset', y[0] == 'r' and y[1:] or y[1:-1], y)))

    def get_link_resolvers(self):
        yield ('changeset', self._format_link)

    def _format_link(self, formatter, ns, rev, label):
        cursor = formatter.db.cursor()
        cursor.execute('SELECT message FROM revision WHERE rev=%s', (rev,))
        row = cursor.fetchone()
        if row:
            return '<a class="changeset" title="%s" href="%s">%s</a>' \
                   % (util.escape(util.shorten_line(row[0])),
                      formatter.href.changeset(rev), label)
        else:
            return '<a class="missing changeset" href="%s" rel="nofollow">%s</a>' \
                   % (formatter.href.changeset(rev), label)

