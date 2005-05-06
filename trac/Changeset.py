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

from trac import mimeview, perm, util
from trac.core import *
from trac.Timeline import ITimelineEventProvider
from trac.versioncontrol import Changeset, Node
from trac.versioncontrol.diff import get_diff_options, hdf_diff, unified_diff
from trac.web.chrome import add_link
from trac.web.main import IRequestHandler
from trac.WikiFormatter import wiki_to_html, wiki_to_oneliner

import time
import re


class ChangesetModule(Component):

    implements(IRequestHandler, ITimelineEventProvider)

    # IRequestHandler methods

    def match_request(self, req):
        match = re.match(r'/changeset/([0-9]+)$', req.path_info)
        if match:
            req.args['rev'] = match.group(1)
            return 1

    def process_request(self, req):
        req.perm.assert_permission(perm.CHANGESET_VIEW)

        add_link(req, 'alternate', '?format=diff', 'Unified Diff',
                 'text/plain', 'diff')
        add_link(req, 'alternate', '?format=zip', 'Zip Archive',
                 'application/zip', 'zip')

        rev = req.args.get('rev')
        repos = self.env.get_repository(req.authname)

        diff_options = get_diff_options(req)
        if req.args.has_key('update'):
            req.redirect(self.env.href.changeset(rev))

        chgset = repos.get_changeset(rev)
        req.check_modified(chgset.date, diff_options[0] + ''.join(diff_options[1]))

        format = req.args.get('format')
        if format == 'diff':
            self.render_diff(req, repos, chgset, diff_options)
        elif format == 'zip':
            self.render_zip(req, repos, chgset)
        else:
            self.render_html(req, repos, chgset, diff_options)
            return 'changeset.cs', None

    # ITimelineEventProvider methods

    def get_timeline_filters(self, req):
        if req.perm.has_permission(perm.CHANGESET_VIEW):
            yield ('changeset', 'Repository checkins')

    def get_timeline_events(self, req, start, stop, filters):
        if 'changeset' in filters:
            absurls = req.args.get('format') == 'rss' # Kludge
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
                    if absurls:
                        href = self.env.abs_href.changeset(chgset.rev)
                    else:
                        href = self.env.href.changeset(chgset.rev)
                    title = 'Changeset <em>[%s]</em> by %s' % (
                            util.escape(chgset.rev), util.escape(chgset.author))
                    message = wiki_to_oneliner(util.shorten_line(chgset.message or '--'),
                                               self.env, db, absurls=absurls)
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

    def render_html(self, req, repos, chgset, diff_options):
        """HTML version"""
        db = self.env.get_db_cnx()
        req.hdf['title'] = '[%s]' % chgset.rev
        req.hdf['changeset'] = {
            'revision': chgset.rev,
            'time': time.strftime('%c', time.localtime(chgset.date)),
            'author': util.escape(chgset.author or 'anonymous'),
            'message': wiki_to_html(chgset.message or '--', req.hdf, self.env,
                                    db, escape_newlines=True)
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
            old_content = old_node.get_content().read()
            if mimeview.is_binary(old_content):
                continue
            new_content = new_node.get_content().read()
            if old_content != new_content:
                context = 3
                for option in diff_options:
                    if option[:2] == '-U':
                        context = int(option[2:])
                        break
                tabwidth = int(self.config.get('diff', 'tab_width'))
                changes = hdf_diff(old_content.splitlines(),
                                   new_content.splitlines(),
                                   context, tabwidth,
                                   ignore_blank_lines='-B' in diff_options,
                                   ignore_case='-i' in diff_options,
                                   ignore_space_changes='-b' in diff_options)
                req.hdf['changeset.changes.%d.diff' % idx] = changes

    def render_diff(self, req, repos, chgset, diff_options):
        """Raw Unified Diff version"""
        req.send_response(200)
        req.send_header('Content-Type', 'text/plain;charset=utf-8')
        req.send_header('Content-Disposition',
                        'filename=Changeset%s.diff' % req.args.get('rev'))
        req.end_headers()

        for path, kind, change, base_path, base_rev in chgset.get_changes():
            if change is Changeset.ADD:
                old_node = None
            else:
                old_node = repos.get_node(base_path or path, base_rev)
            if change is Changeset.DELETE:
                new_node = None
            else:
                new_node = repos.get_node(path, chgset.rev)

            # TODO: Property changes

            # Content changes
            if kind is 'dir':
                continue
            new_content = old_content = ''
            new_node_info = old_node_info = ('','')
            if old_node:
                old_content = old_node.get_content().read()
                old_node_info = (old_node.path, old_node.rev)
            if mimeview.is_binary(old_content):
                continue
            if new_node:
                new_content = new_node.get_content().read()
                new_node_info = (new_node.path, new_node.rev)
            if old_content != new_content:
                context = 3
                for option in diff_options:
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
                                         ignore_blank_lines='-B' in diff_options,
                                         ignore_case='-i' in diff_options,
                                         ignore_space_changes='-b' in diff_options):
                    req.write(line + util.CRLF)

    def render_zip(self, req, repos, chgset):
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
            if kind is Node.FILE and change is not Changeset.DELETE:
                node = repos.get_node(path, chgset.rev)
                zipinfo = ZipInfo()
                zipinfo.filename = node.path
                zipinfo.date_time = time.gmtime(node.last_modified)[:6]
                zipinfo.compress_type = ZIP_DEFLATED
                zipfile.writestr(zipinfo, node.get_content().read())
        zipfile.close()
        req.write(buf.getvalue())
