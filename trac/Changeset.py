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

from __future__ import nested_scopes

from trac.Diff import get_diff_options, hdf_diff, unified_diff
from trac.Module import Module
from trac.WikiFormatter import wiki_to_html
from trac import authzperm, perm

import svn.core
import svn.delta
import svn.fs
import svn.repos
import svn.util

import os
import time
import util
import re
import posixpath
from StringIO import StringIO
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED


class BaseDiffEditor(svn.delta.Editor):
    """
    Base class for diff renderers.
    """

    def __init__(self, old_root, new_root, rev, req, env, path_info,
                 diff_options):
        self.path_info = path_info
        self.old_root = old_root
        self.new_root = new_root
        self.rev = rev
        self.req = req
        self.env = env
        self.diff_options = diff_options

    # svn.delta.Editor callbacks:
    #   This editor will be driven by a 'repos.svn_repos_dir_delta' call.
    #   With this driver, The 'copyfrom_path' will always be 'None'.
    #   We can't use it.
    #   This is why we merge the path_info data (obtained during a
    #   'repos.svn_repos_replay' call) back into this process.
    
    def _read_file(self, root, path, pool, charset):
        fd = svn.fs.file_contents(root, path, pool)
        chunks = []
        while 1:
            chunk = svn.util.svn_stream_read(fd, svn.core.SVN_STREAM_CHUNK_SIZE)
            if not chunk:
                break
            chunks.append(util.to_utf8(chunk, charset))
        return ''.join(chunks)

    def _retrieve_old_path(self, parent_baton, path, pool):
        old_path = parent_baton[0]
        self.prefix = None
        if self.path_info.has_key(path): # retrieve 'copyfrom_path' info
            seq, old_path = self.path_info[path][:2]
            self.prefix = 'changeset.changes.%d' % seq
        elif old_path:    # already on a branch, expand the original path
            old_path = posixpath.join(old_path, posixpath.split(path)[1])
        else:
            old_path = path
        return (old_path, path, pool)

    def open_root(self, base_revision, dir_pool):
        return self._retrieve_old_path((None, None, None), '/', dir_pool)
    
    def open_directory(self, path, dir_baton, base_revision, dir_pool):
        return self._retrieve_old_path(dir_baton, path, dir_pool)

    def open_file(self, path, parent_baton, base_revision, file_pool):
        return self._retrieve_old_path(parent_baton, path, file_pool)


class HtmlDiffEditor(BaseDiffEditor):
    """
    Generates a htmlized unified diff of the changes for a given changeset.
    the output is written to stdout.
    """

    def __init__(self, old_root, new_root, rev, req, env, change_info,
                 diff_options):
        BaseDiffEditor.__init__(self, old_root, new_root, rev, req, env,
                                change_info, diff_options)
        self.prefix = None

    def add_directory(self, path, parent_baton, copyfrom_path,
                      copyfrom_revision, dir_pool):
        return self._retrieve_old_path(parent_baton, path, dir_pool)

    def add_file(self, path, parent_baton, copyfrom_path, copyfrom_revision,
                 file_pool):
        return self._retrieve_old_path(parent_baton, path, file_pool)

    def delete_entry(self, path, revision, parent_baton, pool):
        old_path = self._retrieve_old_path(parent_baton, path, pool)[0]
        return old_path, None, pool


    # -- changes:

    def _old_root(self, new_path, pool):
        if not new_path:
            return 
        old_rev = self.path_info[new_path][2]
        if not old_rev:
            return 
        elif old_rev == self.rev - 1:
            return self.old_root
        else:
            return svn.fs.revision_root(svn.fs.root_fs(self.old_root),
                                        old_rev, pool)
        
    # -- -- textual changes:

    def apply_textdelta(self, file_baton, base_checksum):
        old_path, new_path, pool = file_baton
        if not old_path or not new_path:
            return
        old_root = self._old_root(new_path, pool)
        if not old_root:
            return

        # Try to figure out the charset used. We assume that both the old
        # and the new version uses the same charset, not always the case
        # but that's all we can do...
        mime_type = svn.fs.node_prop(self.new_root, new_path,
                                     svn.util.SVN_PROP_MIME_TYPE, pool)
        if mime_type and svn.core.svn_mime_type_is_binary(mime_type):
            return

        # We don't have to guess if the charset is specified in the
        # svn:mime-type property
        ctpos = mime_type and mime_type.find('charset=') or -1
        if ctpos >= 0:
            charset = mime_type[ctpos + 8:]
        else:
            charset = self.env.get_config('trac', 'default_charset',
                                          'iso-8859-15')

        fromfile = self._read_file(old_root, old_path, pool, charset)
        tofile = self._read_file(self.new_root, new_path, pool, charset)
        if self.env.mimeview.is_binary(fromfile):
            return

        context = 3
        for option in self.diff_options:
            if option[:2] == '-U':
                context = int(option[2:])
                break
        tabwidth = int(self.env.get_config('diff', 'tab_width', '8'))
        changes = hdf_diff(fromfile.splitlines(), tofile.splitlines(),
                           context, tabwidth,
                           ignore_blank_lines='-B' in self.diff_options,
                           ignore_case='-i' in self.diff_options,
                           ignore_space_changes='-b' in self.diff_options)
        self.req.hdf[self.prefix + '.diff'] = changes

    # -- -- property changes:

    def change_dir_prop(self, dir_baton, name, value, dir_pool):
        self._change_prop(dir_baton, name, value, dir_pool)

    def change_file_prop(self, file_baton, name, value, file_pool):
        self._change_prop(file_baton, name, value, file_pool)

    def _change_prop(self, baton, name, value, pool):
        old_path, new_path, pool = baton

        prefix = '%s.props.%s' % (self.prefix, name)
        if old_path:
            old_root = self._old_root(new_path, pool)
            if old_root:
                old_value = svn.fs.node_prop(old_root, old_path, name, pool)
                if old_value:
                    if value == old_value:
                        return # spurious change prop after a copy
                    self.req.hdf[prefix + '.old'] = util.escape(old_value)
        if value:
            self.req.hdf[prefix + '.new'] = util.escape(value)


class UnifiedDiffEditor(BaseDiffEditor):
    """
    Generates a unified diff of the changes for a given changeset.
    the output is written to stdout.
    """

    def _old_root(self, new_path, pool):
        if not new_path:
            return 
        old_rev = self.path_info[new_path][2]
        if not old_rev:
            return 
        elif old_rev == self.rev - 1:
            return self.old_root
        else:
            return svn.fs.revision_root(svn.fs.root_fs(self.old_root),
                                        old_rev, pool)

    def add_file(self, path, parent_baton, copyfrom_path, copyfrom_revision,
                 file_pool):
        return (None, path, file_pool)

    def delete_entry(self, path, revision, parent_baton, pool):
        if svn.fs.check_path(self.old_root, path, pool) == svn.core.svn_node_file:
            self.apply_textdelta((path, None, pool),None)

    # -- -- textual changes:

    def apply_textdelta(self, file_baton, base_checksum):
        if not file_baton:
            return
        (old_path, new_path, pool) = file_baton
        old_root = self._old_root(new_path, pool)
        if not old_root:
            return

        mime_type = svn.fs.node_prop(self.new_root, new_path,
                                     svn.util.SVN_PROP_MIME_TYPE, pool)
        if mime_type and svn.core.svn_mime_type_is_binary(mime_type):
            return

        # We don't have to guess if the charset is specified in the
        # svn:mime-type property
        ctpos = mime_type and mime_type.find('charset=') or -1
        if ctpos >= 0:
            charset = mime_type[ctpos + 8:]
        else:
            charset = self.env.get_config('trac', 'default_charset',
                                          'iso-8859-15')

        fromfile = self._read_file(old_root, old_path, pool, charset)
        tofile = self._read_file(self.new_root, new_path, pool, charset)
        if self.env.mimeview.is_binary(fromfile):
            return

        context = 3
        for option in self.diff_options:
            if option[:2] == '-U':
                context = int(option[2:])
                break
        self.req.write('Index: ' + new_path + util.CRLF)
        self.req.write('=' * 67 + util.CRLF)
        self.req.write('--- %s (revision %s)' % (new_path, self.rev - 1) + util.CRLF)
        self.req.write('+++ %s (revision %s)' % (new_path, self.rev) + util.CRLF)
        for line in unified_diff(fromfile.split('\n'), tofile.split('\n'),
                                 context,
                                 ignore_blank_lines='-B' in self.diff_options,
                                 ignore_case='-i' in self.diff_options,
                                 ignore_space_changes='-b' in self.diff_options):
            self.req.write(line + util.CRLF)

    # -- -- property changes:

    def change_dir_prop(self, dir_baton, name, value, dir_pool):
        self._change_prop(dir_baton, name, value, dir_pool)

    def change_file_prop(self, file_baton, name, value, file_pool):
        self._change_prop(file_baton, name, value, file_pool)

    def _change_prop(self, baton, name, value, pool):
        old_path, new_path, pool = baton
        # FIXME: print the property change like 'svn diff' does


class ZipDiffEditor(BaseDiffEditor):
    """
    Generates a ZIP archive containing the modified and added files.
    """

    def __init__(self, old_root, new_root, rev, req, env, path_info,
                 diff_options):
        BaseDiffEditor.__init__(self, old_root, new_root, rev, req, env,
                                path_info, diff_options)
        self.buffer = StringIO()
        self.zip = ZipFile(self.buffer, 'w', ZIP_DEFLATED)

    def add_file(self, path, parent_baton, copyfrom_path,
                 copyfrom_revision, file_pool):
        self._add_file_to_zip(path, file_pool)

    def open_file(self, path, parent_baton, base_revision, file_pool):
        self._add_file_to_zip(path, file_pool)

    def close_edit(self):
        self.zip.close()
        self.req.write(self.buffer.getvalue())

    def _add_file_to_zip(self, path, pool):
        fd = svn.fs.file_contents(self.new_root, path, pool)
        info = ZipInfo()
        info.filename = path
        date = svn.fs.revision_prop(svn.fs.root_fs(self.new_root), self.rev,
                                    svn.util.SVN_PROP_REVISION_DATE, pool)
        date = svn.util.svn_time_from_cstring(date, pool) / 1000000
        date = time.localtime(date)
        info.date_time = date[:6]
        info.compress_type = ZIP_DEFLATED
        data = ""
        while 1:
            chunk = svn.util.svn_stream_read(fd, 512)
            if not chunk:
                break
            data = data + chunk
        self.zip.writestr(info, data)


class Changeset(Module):
    template_name = 'changeset.cs'

    # set by the module_factory
    authzperm = None
    fs_ptr = None
    pool = None
    repos = None

    def get_changeset_info (self, rev):
        cursor = self.db.cursor ()
        cursor.execute("SELECT time, author, message FROM revision "
                       "WHERE rev=%s", (rev,))
        row = cursor.fetchone()
        if not row:
            raise util.TracError('Changeset %s does not exist.' % rev,
                                 'Invalid Changset')
        return row

    def get_change_info(self, rev):
        cursor = self.db.cursor ()
        cursor.execute("SELECT name, change FROM node_change "
                       "WHERE rev=%s", (rev,))
        info = []
        while 1:
            row = cursor.fetchone()
            if not row:
                break
            change = row['change']
            name = row['name']
            if change in 'CRdm': # 'C'opy, 'R'eplace or 'd'elete on a branch
                # the name column contains the encoded ''path_info''
                # (see _save_change method in sync.py).
                m = re.match('(.*) // (-?\d+), (.*)', name)
                if change == 'd':
                    new_path = None
                else:
                    new_path = m.group(1)
                old_rev = int(m.group(2))
                if old_rev < 0:
                    old_rev = None
                old_path = m.group(3)
            elif change == 'D':         # 'D'elete
                new_path = None
                old_path = name
                old_rev = None
            elif change == 'A':         # 'A'dd
                new_path = name
                old_path = old_rev = None
            else:                       # 'M'odify
                new_path = old_path = name
                old_rev = None
            if old_path and not old_rev: # 'D' and 'M'
                history = svn.fs.node_history(self.old_root, old_path, self.pool)
                history = svn.fs.history_prev(history, 0, self.pool) # what an API...
                old_rev = svn.fs.history_location(history, self.pool)[1]
                # Note: 'node_created_rev' doesn't work reliably
            key = (new_path or old_path)
            info.append((key, change, new_path, old_path, old_rev))

        info = filter(lambda x,self=self: self.authzperm.has_permission(x[2]) \
                                      and self.authzperm.has_permission(x[3]),
                      info)

        info.sort(lambda x,y: cmp(x[0],y[0]))
        self.path_info = {}
        #  path_info is a mapping of paths to sequence number and additional info
        #   'new_path' to '(seq, copyfrom_path, copyfrom_rev)',
        #   'old_path' to '(seq)'
        sinfo = []
        seq = 0
        for _, change, new_path, old_path, old_rev in info:
            cinfo = { 'name.new': new_path,
                      'name.old': old_path,
                      'log_href': new_path or old_path }
            if new_path:
                self.path_info[new_path] = (seq, old_path, old_rev)
                cinfo['rev.new'] = str(rev)
                cinfo['browser_href.new'] = self.env.href.browser(new_path, rev)
            if old_path:
                cinfo['rev.old'] = str(old_rev)
                cinfo['browser_href.old'] = self.env.href.browser(old_path, old_rev)
            if change in 'CRm':
                cinfo['copyfrom_path'] = old_path
            cinfo['change'] = change.upper()
            cinfo['seq'] = seq
            sinfo.append(cinfo)
            seq += 1
        return sinfo

    def render(self, req):
        self.perm.assert_permission (perm.CHANGESET_VIEW)

        self.add_link('alternate', '?format=diff', 'Unified Diff',
                      'text/plain', 'diff')
        self.add_link('alternate', '?format=zip', 'Zip Archive',
                      'application/zip', 'zip')

        youngest_rev = svn.fs.youngest_rev(self.fs_ptr, self.pool)
        if req.args.has_key('rev'):
            self.rev = int(req.args.get('rev'))
        else:
            self.rev = youngest_rev

        self.diff_options = get_diff_options(req)
        if req.args.has_key('update'):
            req.redirect(self.env.href.changeset(self.rev))

        try:
            self.old_root = svn.fs.revision_root(self.fs_ptr,
                int(self.rev) - 1, self.pool)
            self.new_root = svn.fs.revision_root(self.fs_ptr,
                int(self.rev), self.pool)
        except svn.core.SubversionException:
            raise util.TracError('Invalid revision number: %d' % int(self.rev))

        changeset_info = self.get_changeset_info(self.rev)
        req.check_modified(int(changeset_info['time']),
                           self.diff_options[0] + "".join(self.diff_options[1]))
        change_info = self.get_change_info(self.rev)

        req.hdf['title'] = '[%d] (changeset)' % self.rev
        req.hdf['changeset.time'] = time.asctime(time.localtime(int(changeset_info['time'])))
        author = changeset_info['author'] or 'anonymous'
        req.hdf['changeset.author'] = util.escape(author)
        message = changeset_info['message'] or '--'
        req.hdf['changeset.message'] = wiki_to_html(util.wiki_escape_newline(message),
                                                    req.hdf, self.env, self.db)
        req.hdf['changeset.revision'] = self.rev
        req.hdf['changeset.changes'] = change_info
        req.hdf['changeset.href'] = self.env.href.changeset(self.rev)
        
        if len(change_info) == 0:
            raise authzperm.AuthzPermissionError()
        
        if self.rev > 1:
            self.add_link('first', self.env.href.changeset(1), 'Changeset 1')
            self.add_link('prev', self.env.href.changeset(self.rev - 1),
                          'Changeset %d' % (self.rev - 1))
        if self.rev < youngest_rev:
            self.add_link('next', self.env.href.changeset(self.rev + 1),
                          'Changeset %d' % (self.rev + 1))
            self.add_link('last', self.env.href.changeset(youngest_rev),
                          'Changeset %d' % youngest_rev)

    def render_diffs(self, req, editor_class=HtmlDiffEditor):
        """
        Generate a unified diff of the changes for a given changeset.
        The output is written to stdout.
        """
        editor = editor_class(self.old_root, self.new_root, int(self.rev), req,
                              self.env, self.path_info, self.diff_options[1])
        e_ptr, e_baton = svn.delta.make_editor(editor, self.pool)

        def authz_cb(root, path, pool):
            return self.authzperm.has_permission(path) and 1 or 0
        svn.repos.svn_repos_dir_delta(self.old_root, '', '',
                                      self.new_root, '', e_ptr, e_baton, authz_cb,
                                      0, 1, 0, 1, self.pool)

    def display(self, req):
        """Pretty HTML view of the changeset"""
        self.render_diffs(req)
        Module.display(self, req)

    def display_diff(self, req):
        """Raw Unified Diff version"""
        req.send_response(200)
        req.send_header('Content-Type', 'text/plain;charset=utf-8')
        req.send_header('Content-Disposition',
                        'filename=Changeset%d.diff' % self.rev)
        req.end_headers()
        self.render_diffs(req, UnifiedDiffEditor)

    def display_zip(self, req):
        """ZIP archive with all the added and/or modified files."""
        req.send_response(200)
        req.send_header('Content-Type', 'application/zip')
        req.send_header('Content-Disposition',
                        'filename=Changeset%d.zip' % self.rev)
        req.end_headers()
        self.render_diffs(req, ZipDiffEditor)

    def display_hdf(self, req):
        self.render_diffs(req)
        Module.display_hdf(self, req)
