# -*- coding: iso-8859-1 -*-
#
# Copyright (C) 2003-2005 Edgewall Software
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

import time
import re

from trac import util
from trac.core import *
from trac.mimeview import Mimeview, is_binary
from trac.perm import IPermissionRequestor
from trac.Search import ISearchSource, query_to_sql, shorten_result
from trac.Timeline import ITimelineEventProvider
from trac.versioncontrol import Changeset, Node
from trac.versioncontrol.svn_authz import SubversionAuthorizer
from trac.versioncontrol.diff import get_diff_options, hdf_diff, unified_diff
from trac.web import IRequestHandler
from trac.web.chrome import add_link, add_stylesheet, INavigationContributor
from trac.wiki import wiki_to_html, wiki_to_oneliner, IWikiSyntaxProvider


class ChangesetModule(Component):

    implements(INavigationContributor, IPermissionRequestor, IRequestHandler,
               ITimelineEventProvider, IWikiSyntaxProvider, ISearchSource)

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
        authzperm = SubversionAuthorizer(self.env, req.authname)
        authzperm.assert_permission_for_changeset(rev)

        diff_options = get_diff_options(req)
        if req.args.has_key('update'):
            req.redirect(self.env.href.changeset(rev))

        chgset = repos.get_changeset(rev)
        req.check_modified(chgset.date, [
            diff_options[0],
            ''.join(diff_options[1]),
            repos.name,
            repos.rev_older_than(rev, repos.youngest_rev),
            chgset.message,
            util.pretty_timedelta(chgset.date, None, 3600)])

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
        add_stylesheet(req, 'common/css/changeset.css')
        add_stylesheet(req, 'common/css/diff.css')
        add_stylesheet(req, 'common/css/code.css')
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
            repos = self.env.get_repository(req.authname)
            for chgset in repos.get_changesets(start, stop):
                message = chgset.message or '--'
                if format == 'rss':
                    title = util.Markup('Changeset <em>[%s]</em>: %s',
                                        chgset.rev, util.shorten_line(message))
                    href = self.env.abs_href.changeset(chgset.rev)
                    message = wiki_to_html(message, self.env, req, db,
                                           absurls=True)
                else:
                    title = util.Markup('Changeset <em>[%s]</em> by %s',
                                        chgset.rev, chgset.author)
                    href = self.env.href.changeset(chgset.rev)
                    message = wiki_to_oneliner(message, self.env, db,
                                               shorten=True)
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
                      util.Markup(message)

    # Internal methods

    def _render_html(self, req, repos, chgset, diff_options):
        """HTML version"""
        req.hdf['title'] = '[%s]' % chgset.rev
        req.hdf['changeset'] = {
            'revision': chgset.rev,
            'time': util.format_datetime(chgset.date),
            'age': util.pretty_timedelta(chgset.date, None, 3600),
            'author': chgset.author or 'anonymous',
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
            if next_rev:
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
                info['rev.old'] = repos.short_rev(base_rev)
                info['browser_href.old'] = self.env.href.browser(base_path,
                                                                 rev=base_rev)
            if path:
                info['path.new'] = path
                info['rev.new'] = repos.short_rev(chgset.rev)
                info['browser_href.new'] = self.env.href.browser(path,
                                                                 rev=chgset.rev)
            if change in (Changeset.COPY, Changeset.EDIT, Changeset.MOVE):
                edits.append((idx, path, kind, base_path, base_rev))
            req.hdf['changeset.changes.%d' % idx] = info
            idx += 1

        hidden_properties = [p.strip() for p
                             in self.config.get('browser', 'hide_properties',
                                                'svk:merge').split(',')]

        mimeview = Mimeview(self.env)
            
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
                for k in hidden_properties:
                    if k in changed_props:
                        del changed_props[k]
                req.hdf['changeset.changes.%d.props' % idx] = changed_props

            if kind == Node.DIRECTORY:
                continue

            # Content changes
            data = old_node.get_content().read()
            if is_binary(data):
                continue
            old_content = mimeview.to_utf8(data, old_node.content_type)

            data = new_node.get_content().read()
            if is_binary(data):
                continue
            new_content = mimeview.to_utf8(data, new_node.content_type)

            if old_content != new_content:
                context = 3
                for option in diff_options[1]:
                    if option.startswith('-U'):
                        context = int(option[2:])
                        break
                if context < 0:
                    context = None
                tabwidth = int(self.config.get('diff', 'tab_width',
                                               self.config.get('mimeviewer',
                                                               'tab_width')))
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
        req.send_header('Content-Disposition', 'inline;'
                        'filename=Changeset%s.diff' % chgset.rev)
        req.end_headers()

        mimeview = Mimeview(self.env)

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

            new_content = old_content = ''
            new_node_info = old_node_info = ('','')

            if old_node:
                data = old_node.get_content().read()
                if is_binary(data):
                    continue
                old_content = mimeview.to_utf8(data, old_node.content_type)
                old_node_info = (old_node.path, old_node.rev)

            if new_node:
                data = new_node.get_content().read()
                if is_binary(data):
                    continue
                new_content = mimeview.to_utf8(data, new_node.content_type) 
                new_node_info = (new_node.path, new_node.rev)

            if old_content != new_content:
                context = 3
                for option in diff_options[1]:
                    if option.startswith('-U'):
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
        req.send_header('Content-Disposition', 'attachment;'
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
        yield (r"!?\[\d+\]|(?:\b|!)r\d+\b(?!:\d)",
               lambda x, y, z: self._format_link(x, 'changeset',
                                                 y[0] == 'r' and y[1:]
                                                 or y[1:-1], y))

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

    # ISearchProvider methods

    def get_search_filters(self, req):
        if req.perm.has_permission('CHANGESET_VIEW'):
            yield ('changeset', 'Changesets')

    def get_search_results(self, req, query, filters):
        if not 'changeset' in filters:
            return
        authzperm = SubversionAuthorizer(self.env, req.authname)
        db = self.env.get_db_cnx()
        sql, args = query_to_sql(db, query, 'message||author')
        cursor = db.cursor()
        cursor.execute("SELECT rev,time,author,message "
                       "FROM revision WHERE " + sql, args)
        for rev, date, author, log in cursor:
            if not authzperm.has_permission_for_changeset(rev):
                continue
            yield (self.env.href.changeset(rev),
                   '[%s]: %s' % (rev, util.shorten_line(log)),
                   date, author, shorten_result(log, query.split()))
