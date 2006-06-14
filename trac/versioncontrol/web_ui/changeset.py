# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2006 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2004-2006 Christopher Lenz <cmlenz@gmx.de>
# Copyright (C) 2005-2006 Christian Boos <cboos@neuf.fr>
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
#         Christian Boos <cboos@neuf.fr>

import posixpath
import re
from StringIO import StringIO
import time

from trac import util
from trac.config import BoolOption, IntOption
from trac.core import *
from trac.mimeview import Mimeview, is_binary
from trac.perm import IPermissionRequestor
from trac.Search import ISearchSource, search_to_sql, shorten_result
from trac.Timeline import ITimelineEventProvider
from trac.util.datefmt import format_datetime, pretty_timedelta
from trac.util.markup import html, escape, unescape, Markup
from trac.util.text import unicode_urlencode, shorten_line, CRLF
from trac.versioncontrol import Changeset, Node
from trac.versioncontrol.diff import get_diff_options, hdf_diff, unified_diff
from trac.versioncontrol.svn_authz import SubversionAuthorizer
from trac.versioncontrol.web_ui.util import render_node_property
from trac.web import IRequestHandler
from trac.web.chrome import INavigationContributor, add_link, add_stylesheet
from trac.wiki import wiki_to_html, wiki_to_oneliner, IWikiSyntaxProvider, \
                      Formatter


class DiffArgs(dict):
    def __getattr__(self, str):
        return self[str]


class ChangesetModule(Component):
    """Provide flexible functionality for showing sets of differences.

    If the differences shown are coming from a specific changeset,
    then that changeset informations can be shown too.

    In addition, it is possible to show only a subset of the changeset:
    Only the changes affecting a given path will be shown.
    This is called the ''restricted'' changeset.

    But the differences can also be computed in a more general way,
    between two arbitrary paths and/or between two arbitrary revisions.
    In that case, there's no changeset information displayed.
    """

    implements(INavigationContributor, IPermissionRequestor, IRequestHandler,
               ITimelineEventProvider, IWikiSyntaxProvider, ISearchSource)

    timeline_show_files = IntOption('timeline', 'changeset_show_files', 0,
        """Number of files to show (`-1` for unlimited, `0` to disable).""")

    timeline_long_messages = BoolOption('timeline', 'changeset_long_messages',
                                        'false',
        """Whether wiki-formatted changeset messages should be multiline or not.

        If this option is not specified or is false and `wiki_format_messages`
        is set to true, changeset messages will be single line only, losing
        some formatting (bullet points, etc).""")

    max_diff_files = IntOption('changeset', 'max_diff_files', 0,
        """Maximum number of modified files for which the changeset view will
        attempt to show the diffs inlined (''since 0.10'')."""),

    max_diff_bytes = IntOption('changeset', 'max_diff_bytes', 10000000,
        """Maximum total size in bytes of the modified files (their old size
        plus their new size) for which the changeset view will attempt to show
        the diffs inlined (''since 0.10'').""")

    wiki_format_messages = BoolOption('changeset', 'wiki_format_messages',
                                      'true',
        """Whether wiki formatting should be applied to changeset messages.
        
        If this option is disabled, changeset messages will be rendered as
        pre-formatted text.""")

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'browser'

    def get_navigation_items(self, req):
        return []

    # IPermissionRequestor methods

    def get_permission_actions(self):
        return ['CHANGESET_VIEW']

    # IRequestHandler methods

    _request_re = re.compile(r"/changeset(?:/([^/]+))?(/.*)?$")

    def match_request(self, req):
        match = re.match(self._request_re, req.path_info)
        if match:
            new, new_path = match.groups()
            if new:
                req.args['new'] = new
            if new_path:
                req.args['new_path'] = new_path
            return True

    def process_request(self, req):
        """The appropriate mode of operation is inferred from the request
        parameters:

         * If `new_path` and `old_path` are equal (or `old_path` is omitted)
           and `new` and `old` are equal (or `old` is omitted),
           then we're about to view a revision Changeset: `chgset` is True.
           Furthermore, if the path is not the root, the changeset is
           ''restricted'' to that path (only the changes affecting that path,
           its children or its ancestor directories will be shown).
         * In any other case, the set of changes corresponds to arbitrary
           differences between path@rev pairs. If `new_path` and `old_path`
           are equal, the ''restricted'' flag will also be set, meaning in this
           case that the differences between two revisions are restricted to
           those occurring on that path.

        In any case, either path@rev pairs must exist.
        """
        req.perm.assert_permission('CHANGESET_VIEW')

        # -- retrieve arguments
        new_path = req.args.get('new_path')
        new = req.args.get('new')
        old_path = req.args.get('old_path')
        old = req.args.get('old')

        if old and '@' in old:
            old_path, old = unescape(old).split('@')
        if new and '@' in new:
            new_path, new = unescape(new).split('@')

        # -- normalize and check for special case
        repos = self.env.get_repository(req.authname)
        new_path = repos.normalize_path(new_path)
        new = repos.normalize_rev(new)
        old_path = repos.normalize_path(old_path or new_path)
        old = repos.normalize_rev(old or new)

        authzperm = SubversionAuthorizer(self.env, req.authname)
        authzperm.assert_permission_for_changeset(new)

        if old_path == new_path and old == new: # revert to Changeset
            old_path = old = None

        diff_options = get_diff_options(req)

        # -- setup the `chgset` and `restricted` flags, see docstring above.
        chgset = not old and not old_path
        if chgset:
            restricted = new_path not in ('', '/') # (subset or not)
        else:
            restricted = old_path == new_path # (same path or not)

        # -- redirect if changing the diff options
        if req.args.has_key('update'):
            if chgset:
                if restricted:
                    req.redirect(req.href.changeset(new, new_path))
                else:
                    req.redirect(req.href.changeset(new))
            else:
                req.redirect(req.href.changeset(new, new_path, old=old,
                                                old_path=old_path))

        # -- preparing the diff arguments
        if chgset:
            prev = repos.get_node(new_path, new).get_previous()
            if prev:
                prev_path, prev_rev = prev[:2]
            else:
                prev_path, prev_rev = new_path, repos.previous_rev(new)
            diff_args = DiffArgs(old_path=prev_path, old_rev=prev_rev,
                                 new_path=new_path, new_rev=new)
        else:
            if not new:
                new = repos.youngest_rev
            elif not old:
                old = repos.youngest_rev
            if not old_path:
                old_path = new_path
            diff_args = DiffArgs(old_path=old_path, old_rev=old,
                                 new_path=new_path, new_rev=new)
        if chgset:
            chgset = repos.get_changeset(new)
            message = chgset.message or '--'
            if self.wiki_format_messages:
                message = wiki_to_html(message, self.env, req,
                                              escape_newlines=True)
            else:
                message = html.PRE(message)
            req.check_modified(chgset.date, [
                diff_options[0],
                ''.join(diff_options[1]),
                repos.name,
                repos.rev_older_than(new, repos.youngest_rev),
                message,
                pretty_timedelta(chgset.date, None, 3600)])
        else:
            message = None # FIXME: what date should we choose for a diff?

        req.hdf['changeset'] = diff_args

        format = req.args.get('format')

        if format in ['diff', 'zip']:
            req.perm.assert_permission('FILE_VIEW')
            # choosing an appropriate filename
            rpath = new_path.replace('/','_')
            if chgset:
                if restricted:
                    filename = 'changeset_%s_r%s' % (rpath, new)
                else:
                    filename = 'changeset_r%s' % new
            else:
                if restricted:
                    filename = 'diff-%s-from-r%s-to-r%s' \
                                  % (rpath, old, new)
                elif old_path == '/': # special case for download (#238)
                    filename = '%s-r%s' % (rpath, old)
                else:
                    filename = 'diff-from-%s-r%s-to-%s-r%s' \
                               % (old_path.replace('/','_'), old, rpath, new)
            if format == 'diff':
                self._render_diff(req, filename, repos, diff_args,
                                  diff_options)
                return
            elif format == 'zip':
                self._render_zip(req, filename, repos, diff_args)
                return

        # -- HTML format
        self._render_html(req, repos, chgset, restricted, message,
                          diff_args, diff_options)
        if chgset:
            diff_params = 'new=%s' % new
        else:
            diff_params = unicode_urlencode({'new_path': new_path,
                                             'new': new,
                                             'old_path': old_path,
                                             'old': old})
        add_link(req, 'alternate', '?format=diff&'+diff_params, 'Unified Diff',
                 'text/plain', 'diff')
        add_link(req, 'alternate', '?format=zip&'+diff_params, 'Zip Archive',
                 'application/zip', 'zip')
        add_stylesheet(req, 'common/css/changeset.css')
        add_stylesheet(req, 'common/css/diff.css')
        add_stylesheet(req, 'common/css/code.css')
        return 'changeset.cs', None

    # Internal methods

    def _render_html(self, req, repos, chgset, restricted, message,
                     diff, diff_options):
        """HTML version"""
        req.hdf['changeset'] = {
            'chgset': chgset and True,
            'restricted': restricted,
            'href': {
                'new_rev': req.href.changeset(diff.new_rev),
                'old_rev': req.href.changeset(diff.old_rev),
                'new_path': req.href.browser(diff.new_path, rev=diff.new_rev),
                'old_path': req.href.browser(diff.old_path, rev=diff.old_rev)
            }
        }

        if chgset: # Changeset Mode (possibly restricted on a path)
            path, rev = diff.new_path, diff.new_rev

            # -- getting the change summary from the Changeset.get_changes
            def get_changes():
                for npath, kind, change, opath, orev in chgset.get_changes():
                    old_node = new_node = None
                    if (restricted and
                        not (npath == path or                # same path
                             npath.startswith(path + '/') or # npath is below
                             path.startswith(npath + '/'))): # npath is above
                        continue
                    if change != Changeset.ADD:
                        old_node = repos.get_node(opath, orev)
                    if change != Changeset.DELETE:
                        new_node = repos.get_node(npath, rev)
                    yield old_node, new_node, kind, change

            def _changeset_title(rev):
                if restricted:
                    return 'Changeset %s for %s' % (rev, path)
                else:
                    return 'Changeset %s' % rev

            title = _changeset_title(rev)
            properties = []
            for name, value, wikiflag, htmlclass in chgset.get_properties():
                if wikiflag:
                    value = wiki_to_html(value or '', self.env, req)
                properties.append({'name': name, 'value': value,
                                   'htmlclass': htmlclass})

            req.hdf['changeset'] = {
                'revision': chgset.rev,
                'time': format_datetime(chgset.date),
                'age': pretty_timedelta(chgset.date, None, 3600),
                'author': chgset.author or 'anonymous',
                'message': message, 'properties': properties
            }
            oldest_rev = repos.oldest_rev
            if chgset.rev != oldest_rev:
                if restricted:
                    prev = repos.get_node(path, rev).get_previous()
                    if prev:
                        prev_path, prev_rev = prev[:2]
                        if prev_rev:
                            prev_href = req.href.changeset(prev_rev, prev_path)
                    else:
                        prev_path = prev_rev = None
                else:
                    add_link(req, 'first', req.href.changeset(oldest_rev),
                             'Changeset %s' % oldest_rev)
                    prev_path = diff.old_path
                    prev_rev = repos.previous_rev(chgset.rev)
                    if prev_rev:
                        prev_href = req.href.changeset(prev_rev)
                if prev_rev:
                    add_link(req, 'prev', prev_href, _changeset_title(prev_rev))
            youngest_rev = repos.youngest_rev
            if str(chgset.rev) != str(youngest_rev):
                if restricted:
                    next_rev = repos.next_rev(chgset.rev, path)
                    if next_rev:
                        next_href = req.href.changeset(next_rev, path)
                else:
                    add_link(req, 'last', req.href.changeset(youngest_rev),
                             'Changeset %s' % youngest_rev)
                    next_rev = repos.next_rev(chgset.rev)
                    if next_rev:
                        next_href = req.href.changeset(next_rev)
                if next_rev:
                    add_link(req, 'next', next_href, _changeset_title(next_rev))

        else: # Diff Mode
            # -- getting the change summary from the Repository.get_changes
            def get_changes():
                for d in repos.get_changes(**diff):
                    yield d

            reverse_href = req.href.changeset(diff.old_rev, diff.old_path,
                                                   old=diff.new_rev,
                                                   old_path=diff.new_path)
            req.hdf['changeset.reverse_href'] = reverse_href
            req.hdf['changeset.href.log'] = req.href.log(
                diff.new_path, rev=diff.new_rev, stop_rev=diff.old_rev)
            title = self.title_for_diff(diff)
        req.hdf['title'] = title

        if not req.perm.has_permission('BROWSER_VIEW'):
            return

        def _change_info(old_node, new_node, change):
            info = {'change': change}
            if old_node:
                info['path.old'] = old_node.path
                info['rev.old'] = old_node.rev
                info['shortrev.old'] = repos.short_rev(old_node.rev)
                old_href = req.href.browser(old_node.created_path,
                                            rev=old_node.created_rev)
                # Reminder: old_node.path may not exist at old_node.rev
                #           as long as old_node.rev==old_node.created_rev
                #           ... and diff.old_rev may have nothing to do
                #           with _that_ node specific history...
                info['browser_href.old'] = old_href
            if new_node:
                info['path.new'] = new_node.path
                info['rev.new'] = new_node.rev # created rev.
                info['shortrev.new'] = repos.short_rev(new_node.rev)
                new_href = req.href.browser(new_node.created_path,
                                            rev=new_node.created_rev)
                # (same remark as above)
                info['browser_href.new'] = new_href
            return info

        hidden_properties = self.config.getlist('browser', 'hide_properties')

        def _prop_changes(old_node, new_node):
            old_props = old_node.get_properties()
            new_props = new_node.get_properties()
            changed_props = {}
            if old_props != new_props:
                for k,v in old_props.items():
                    if not k in new_props:
                        changed_props[k] = {
                            'old': render_node_property(self.env, k, v)}
                    elif v != new_props[k]:
                        changed_props[k] = {
                            'old': render_node_property(self.env, k, v),
                            'new': render_node_property(self.env, k,
                                                        new_props[k])}
                for k,v in new_props.items():
                    if not k in old_props:
                        changed_props[k] = {
                            'new': render_node_property(self.env, k, v)}
                for k in hidden_properties:
                    if k in changed_props:
                        del changed_props[k]
            changed_properties = []
            for name, props in changed_props.iteritems():
                props.update({'name': name})
                changed_properties.append(props)
            return changed_properties

        def _estimate_changes(old_node, new_node):
            old_size = old_node.get_content_length()
            new_size = new_node.get_content_length()
            return old_size + new_size

        def _content_changes(old_node, new_node):
            """Returns the list of differences.

            The list is empty when no differences between comparable files
            are detected, but the return value is None for non-comparable files.
            """
            old_content = old_node.get_content().read()
            if is_binary(old_content):
                return None

            new_content = new_node.get_content().read()
            if is_binary(new_content):
                return None

            mview = Mimeview(self.env)
            old_content = mview.to_unicode(old_content, old_node.content_type)
            new_content = mview.to_unicode(new_content, new_node.content_type)

            if old_content != new_content:
                context = 3
                options = diff_options[1]
                for option in options:
                    if option.startswith('-U'):
                        context = int(option[2:])
                        break
                if context < 0:
                    context = None
                tabwidth = self.config['diff'].getint('tab_width',
                                self.config['mimeviewer'].getint('tab_width'))
                return hdf_diff(old_content.splitlines(),
                                new_content.splitlines(),
                                context, tabwidth,
                                ignore_blank_lines='-B' in options,
                                ignore_case='-i' in options,
                                ignore_space_changes='-b' in options)
            else:
                return []

        if req.perm.has_permission('FILE_VIEW'):
            diff_bytes = diff_files = 0
            if self.max_diff_bytes or self.max_diff_files:
                for old_node, new_node, kind, change in get_changes():
                    if change == Changeset.EDIT and kind == Node.FILE:
                        diff_files += 1
                        diff_bytes += _estimate_changes(old_node, new_node)
            show_diffs = (not self.max_diff_files or \
                          diff_files <= self.max_diff_files) and \
                         (not self.max_diff_bytes or \
                          diff_bytes <= self.max_diff_bytes or \
                          diff_files == 1)
        else:
            show_diffs = False

        idx = 0
        for old_node, new_node, kind, change in get_changes():
            show_entry = change != Changeset.EDIT
            if change in (Changeset.EDIT, Changeset.COPY, Changeset.MOVE) and \
                   req.perm.has_permission('FILE_VIEW'):
                assert old_node and new_node
                props = _prop_changes(old_node, new_node)
                if props:
                    req.hdf['changeset.changes.%d.props' % idx] = props
                    show_entry = True
                if kind == Node.FILE and show_diffs:
                    diffs = _content_changes(old_node, new_node)
                    if diffs != []:
                        if diffs:
                            req.hdf['changeset.changes.%d.diff' % idx] = diffs
                        # elif None (means: manually compare to (previous))
                        show_entry = True
            if show_entry or not show_diffs:
                info = _change_info(old_node, new_node, change)
                if change == Changeset.EDIT and not show_diffs:
                    if chgset:
                        diff_href = req.href.changeset(new_node.rev,
                                                       new_node.path)
                    else:
                        diff_href = req.href.changeset(
                            new_node.created_rev, new_node.created_path,
                            old=old_node.created_rev,
                            old_path=old_node.created_path)
                    info['diff_href'] = diff_href
                req.hdf['changeset.changes.%d' % idx] = info
            idx += 1 # the sequence should be immutable

    def _render_diff(self, req, filename, repos, diff, diff_options):
        """Raw Unified Diff version"""
        req.send_response(200)
        req.send_header('Content-Type', 'text/plain;charset=utf-8')
        req.send_header('Content-Disposition', 'inline;'
                        'filename=%s.diff' % filename)
        req.end_headers()

        mimeview = Mimeview(self.env)
        for old_node, new_node, kind, change in repos.get_changes(**diff):
            # TODO: Property changes

            # Content changes
            if kind == Node.DIRECTORY:
                continue

            new_content = old_content = ''
            new_node_info = old_node_info = ('','')
            mimeview = Mimeview(self.env)

            if old_node:
                old_content = old_node.get_content().read()
                if is_binary(old_content):
                    continue
                old_node_info = (old_node.path, old_node.rev)
                old_content = mimeview.to_unicode(old_content,
                                                  old_node.content_type)
            if new_node:
                new_content = new_node.get_content().read()
                if is_binary(new_content):
                    continue
                new_node_info = (new_node.path, new_node.rev)
                new_path = new_node.path
                new_content = mimeview.to_unicode(new_content,
                                                  new_node.content_type)
            else:
                old_node_path = repos.normalize_path(old_node.path)
                diff_old_path = repos.normalize_path(diff.old_path)
                new_path = posixpath.join(diff.new_path,
                                          old_node_path[len(diff_old_path)+1:])

            if old_content != new_content:
                context = 3
                options = diff_options[1]
                for option in options:
                    if option.startswith('-U'):
                        context = int(option[2:])
                        break
                if not old_node_info[0]:
                    old_node_info = new_node_info # support for 'A'dd changes
                req.write('Index: ' + new_path + CRLF)
                req.write('=' * 67 + CRLF)
                req.write('--- %s (revision %s)' % old_node_info + CRLF)
                req.write('+++ %s (revision %s)' % new_node_info + CRLF)
                for line in unified_diff(old_content.splitlines(),
                                         new_content.splitlines(), context,
                                         ignore_blank_lines='-B' in options,
                                         ignore_case='-i' in options,
                                         ignore_space_changes='-b' in options):
                    req.write(line + CRLF)

    def _render_zip(self, req, filename, repos, diff):
        """ZIP archive with all the added and/or modified files."""
        new_rev = diff.new_rev
        req.send_response(200)
        req.send_header('Content-Type', 'application/zip')
        req.send_header('Content-Disposition', 'attachment;'
                        'filename=%s.zip' % filename)

        from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

        buf = StringIO()
        zipfile = ZipFile(buf, 'w', ZIP_DEFLATED)
        for old_node, new_node, kind, change in repos.get_changes(**diff):
            if kind == Node.FILE and change != Changeset.DELETE:
                assert new_node
                zipinfo = ZipInfo()
                zipinfo.filename = new_node.path.encode('utf-8')
                # Note: unicode filenames are not supported by zipfile.
                # UTF-8 is not supported by all Zip tools either,
                # but as some does, I think UTF-8 is the best option here.
                zipinfo.date_time = time.gmtime(new_node.last_modified)[:6]
                zipinfo.compress_type = ZIP_DEFLATED
                zipfile.writestr(zipinfo, new_node.get_content().read())
        zipfile.close()

        buf.seek(0, 2) # be sure to be at the end
        req.send_header("Content-Length", buf.tell())
        req.end_headers()

        req.write(buf.getvalue())

    def title_for_diff(self, diff):
        if diff.new_path == diff.old_path: # ''diff between 2 revisions'' mode
            return 'Diff r%s:%s for %s' \
                   % (diff.old_rev or 'latest', diff.new_rev or 'latest',
                      diff.new_path or '/')
        else:                              # ''arbitrary diff'' mode
            return 'Diff from %s@%s to %s@%s' \
                   % (diff.old_path or '/', diff.old_rev or 'latest',
                      diff.new_path or '/', diff.new_rev or 'latest')

    # ITimelineEventProvider methods

    def get_timeline_filters(self, req):
        if req.perm.has_permission('CHANGESET_VIEW'):
            yield ('changeset', 'Repository checkins')

    def get_timeline_events(self, req, start, stop, filters):
        if 'changeset' in filters:
            format = req.args.get('format')
            wiki_format = self.wiki_format_messages
            show_files = self.timeline_show_files
            db = self.env.get_db_cnx()
            repos = self.env.get_repository(req.authname)
            for chgset in repos.get_changesets(start, stop):
                message = chgset.message or '--'
                if wiki_format:
                    shortlog = wiki_to_oneliner(message, self.env, db,
                                                shorten=True)
                else:
                    shortlog = shorten_line(message)

                if format == 'rss':
                    title = Markup('Changeset [%s]: %s', chgset.rev, shortlog)
                    href = req.abs_href.changeset(chgset.rev)
                    if wiki_format:
                        message = wiki_to_html(message, self.env, req, db,
                                               absurls=True)
                    else:
                        message = html.PRE(message)
                else:
                    title = Markup('Changeset <em>[%s]</em> by %s', chgset.rev,
                                   chgset.author)
                    href = req.href.changeset(chgset.rev)

                    if wiki_format:
                        if self.timeline_long_messages:
                            message = wiki_to_html(message, self.env, req, db,
                                                   absurls=True)
                        else:
                            message = wiki_to_oneliner(message, self.env, db,
                                                       shorten=True)
                    else:
                        message = shortlog

                if show_files and req.perm.has_permission('BROWSER_VIEW'):
                    files = []
                    for chg in chgset.get_changes():
                        if show_files > 0 and len(files) >= show_files:
                            files.append(html.LI(Markup('&hellip;')))
                            break
                        files.append(html.LI(html.DIV(class_=chg[2]),
                                             chg[0] or '/'))
                    message = html.UL(files, class_="changes") + message

                yield 'changeset', href, title, chgset.date, chgset.author,\
                      message

    # IWikiSyntaxProvider methods

    CHANGESET_ID = r"(?:\d+|[a-fA-F\d]{6,})" # only "long enough" hexa ids

    def get_wiki_syntax(self):
        yield (
            # [...] form: start with optional intertrac: [T... or [trac ...
            r"!?\[(?P<it_changeset>%s\s*)" % Formatter.INTERTRAC_SCHEME +
            # hex digits + optional /path for the restricted changeset
            r"%s(?:/[^\]]*)?\]|" % self.CHANGESET_ID +
            # r... form: allow r1 but not r1:2 (handled by the log syntax)
            r"(?:\b|!)r%s\b(?!:%s)" % ((self.CHANGESET_ID,)*2),
            lambda x, y, z:
            self._format_changeset_link(x, 'changeset',
                                        y[0] == 'r' and y[1:] or y[1:-1],
                                        y, z))

    def get_link_resolvers(self):
        yield ('changeset', self._format_changeset_link)
        yield ('diff', self._format_diff_link)

    def _format_changeset_link(self, formatter, ns, chgset, label,
                               fullmatch=None):
        intertrac = formatter.shorthand_intertrac_helper(ns, chgset, label,
                                                         fullmatch)
        if intertrac:
            return intertrac
        sep = chgset.find('/')
        if sep > 0:
            rev, path = chgset[:sep], chgset[sep:]
        else:
            rev, path = chgset, None
        cursor = formatter.db.cursor()
        cursor.execute('SELECT message FROM revision WHERE rev=%s', (rev,))
        row = cursor.fetchone()
        if row:
            return html.A(label, class_="changeset",
                          title=shorten_line(row[0]),
                          href=formatter.href.changeset(rev, path))
        else:
            return html.A(label, class_="missing changeset",
                          href=formatter.href.changeset(rev, path),
                          rel="nofollow")

    def _format_diff_link(self, formatter, ns, params, label):
        def pathrev(path):
            if '@' in path:
                return path.split('@', 1)
            else:
                return (path, None)
        if '//' in params:
            p1, p2 = params.split('//', 1)
            old, new = pathrev(p1), pathrev(p2)
            diff = DiffArgs(old_path=old[0], old_rev=old[1],
                            new_path=new[0], new_rev=new[1])
        else:
            old_path, old_rev = pathrev(params)
            new_rev = None
            if old_rev and ':' in old_rev:
                old_rev, new_rev = old_rev.split(':', 1)
            diff = DiffArgs(old_path=old_path, old_rev=old_rev,
                            new_path=old_path, new_rev=new_rev)
        title = self.title_for_diff(diff)
        href = formatter.href.changeset(new_path=diff.new_path or None,
                                        new=diff.new_rev,
                                        old_path=diff.old_path or None,
                                        old=diff.old_rev)
        return html.A(label, class_="changeset", title=title, href=href)

    # ISearchSource methods

    def get_search_filters(self, req):
        if req.perm.has_permission('CHANGESET_VIEW'):
            yield ('changeset', 'Changesets')

    def get_search_results(self, req, terms, filters):
        if not 'changeset' in filters:
            return
        authzperm = SubversionAuthorizer(self.env, req.authname)
        db = self.env.get_db_cnx()
        sql, args = search_to_sql(db, ['message', 'author'], terms)
        cursor = db.cursor()
        cursor.execute("SELECT rev,time,author,message "
                       "FROM revision WHERE " + sql, args)
        for rev, date, author, log in cursor:
            if not authzperm.has_permission_for_changeset(rev):
                continue
            yield (req.href.changeset(rev),
                   '[%s]: %s' % (rev, shorten_line(log)),
                   date, author, shorten_result(log, terms))


class AnyDiffModule(Component):

    implements(IRequestHandler)

    # IRequestHandler methods

    def match_request(self, req):
        return re.match(r'/anydiff$', req.path_info)

    def process_request(self, req):
        # -- retrieve arguments
        new_path = req.args.get('new_path')
        new_rev = req.args.get('new_rev')
        old_path = req.args.get('old_path')
        old_rev = req.args.get('old_rev')

        # -- normalize
        repos = self.env.get_repository(req.authname)
        new_path = repos.normalize_path(new_path)
        new_rev = repos.normalize_rev(new_rev)
        old_path = repos.normalize_path(old_path)
        old_rev = repos.normalize_rev(old_rev)

        authzperm = SubversionAuthorizer(self.env, req.authname)
        authzperm.assert_permission_for_changeset(new_rev)
        authzperm.assert_permission_for_changeset(old_rev)

        # -- prepare rendering
        req.hdf['anydiff'] = {
            'new_path': new_path,
            'new_rev': new_rev,
            'old_path': old_path,
            'old_rev': old_rev,
            'changeset_href': req.href.changeset(),
        }

        return 'anydiff.cs', None
