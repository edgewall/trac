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
import sys
import time
import util
import re
import posixpath
from StringIO import StringIO
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

import svn
import svn.delta
import svn.fs
import svn.core

import Diff
import perm
import Module
from WikiFormatter import wiki_to_html


class BaseDiffEditor(svn.delta.Editor):
    """
    Base class for diff renderers.
    """

    def __init__(self, old_root, new_root, rev, req, args, env, path_info):
        self.path_info = path_info
        self.old_root = old_root
        self.new_root = new_root
        self.rev = rev
        self.req = req
        self.args = args
        self.env = env

    # svn.delta.Editor callbacks:
    #   This editor will be driven by a 'repos.svn_repos_dir_delta' call.
    #   With this driver, The 'copyfrom_path' will always be 'None'.
    #   We can't use it.
    #   This is why we merge the path_info data (obtained during a
    #   'repos.svn_repos_replay' call) back into this process.
    
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

    def __init__(self, old_root, new_root, rev, req, args, env, change_info):
        BaseDiffEditor.__init__(self, old_root, new_root, rev, req, args,
                                env, change_info)
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
        if not self.prefix or not (old_path and new_path):
            return
        old_root = self._old_root(new_path, pool)
        if not old_root:
            return
        
        # Try to figure out the charset used. We assume that both the old
        # and the new version uses the same charset, not always the case
        # but that's all we can do...
        mime_type = svn.fs.node_prop(self.new_root, new_path,
                                     svn.util.SVN_PROP_MIME_TYPE, pool)
        # We don't have to guess if the charset is specified in the
        # svn:mime-type property
        ctpos = mime_type and mime_type.find('charset=') or -1
        if ctpos >= 0:
            charset = mime_type[ctpos + 8:]
        else:
            charset = self.env.get_config('trac', 'default_charset',
                                          'iso-8859-15')

        # Start up the diff process
        options = Diff.get_options(self.env, self.req, self.args, 1)
        differ = svn.fs.FileDiff(old_root, old_path,
                                 self.new_root, new_path, pool, options)
        differ.get_files()
        pobj = differ.get_pipe()

        tabwidth = int(self.env.get_config('diff', 'tab_width', '8'))
        builder = Diff.HDFBuilder(self.req.hdf, '%s.diff' % self.prefix, tabwidth)
        while 1:
            line = pobj.readline()
            if not line:
                break
            builder.writeline(util.to_utf8(line, charset))
        builder.close()
        pobj.close()
        # svn.fs.FileDiff creates a child process and there is no waitpid()
        # calls to eliminate zombies (this is a problem especially when 
        # mod_python is used.
        if sys.platform[:3] != "win" and sys.platform != "os2emx":
            try:
                os.waitpid(-1, 0)
            except OSError: pass

    # -- -- property changes:
    
    def change_dir_prop(self, dir_baton, name, value, dir_pool):
        self._change_prop(dir_baton, name, value, dir_pool)

    def change_file_prop(self, file_baton, name, value, file_pool):
        self._change_prop(file_baton, name, value, file_pool)

    def _change_prop(self, baton, name, value, pool):
        if not self.prefix:
            return
        old_path, new_path, pool = baton

        prefix = '%s.props.%s' % (self.prefix, name)
        if old_path:
            old_root = self._old_root(new_path, pool)
            if old_root:
                old_value = svn.fs.node_prop(old_root, old_path, name, pool)
                if old_value:
                    if value == old_value:
                        return # spurious change prop after a copy
                    self.req.hdf.setValue(prefix + '.old', util.escape(old_value))
        if value:
            self.req.hdf.setValue(prefix + '.new', util.escape(value))


class UnifiedDiffEditor(BaseDiffEditor):
    """
    Generates a unified diff of the changes for a given changeset.
    the output is written to stdout.
    """

    def add_file(self, path, parent_baton, copyfrom_path, copyfrom_revision,
                 file_pool):
        return (None, path, file_pool)

    def delete_entry(self, path, revision, parent_baton, pool):
        if svn.fs.check_path(self.old_root, path, pool) == svn.core.svn_node_file:
            self.apply_textdelta((path, None, pool),None)

    def apply_textdelta(self, file_baton, base_checksum):
        if not file_baton:
            return
        (old_path, new_path, pool) = file_baton
        options = ['-u']
        options.append('-L')
        options.append("%s\t(revision %d)" % (old_path, self.rev-1))
        options.append('-L')
        options.append("%s\t(revision %d)" % (new_path, self.rev))

        differ = svn.fs.FileDiff(self.old_root, old_path,
                                 self.new_root, new_path, pool, options)
        differ.get_files()
        pobj = differ.get_pipe()
        line = pobj.readline()
        # rewrite 'None' as appropriate ('A' and 'D' support)
        fix_second_line = 0
        if line[:6] != 'Files ' and line[:7] != 'Binary ':
            if old_path == None:            # 'A'
                line = '--- %s %s' % (new_path, line[9:])
            elif new_path == None:          # 'D'        
                fix_second_line = 1
        while line:
            self.req.write(line)
            line = pobj.readline()
            if fix_second_line:         # 'D'
                line = '--- %s %s' % (old_path, line[9:])
                fix_second_line = 0
        pobj.close()
        if sys.platform[:3] != "win" and sys.platform != "os2emx":
            try:
                os.waitpid(-1, 0)
            except OSError: pass


class ZipDiffEditor(BaseDiffEditor):
    """
    Generates a ZIP archive containing the modified and added files.
    """

    def __init__(self, old_root, new_root, rev, req, args, env, path_info):
        BaseDiffEditor.__init__(self, old_root, new_root, rev, req, args,
                                env, path_info)
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


class Changeset (Module.Module):
    template_name = 'changeset.cs'
    perm = None
    fs_ptr = None
    pool = None

    def get_changeset_info (self, rev):
        cursor = self.db.cursor ()
        cursor.execute ('SELECT time, author, message FROM revision ' +
                        'WHERE rev=%d', rev)
        row = cursor.fetchone()
        if not row:
            raise util.TracError('Changeset %d does not exist.' % rev,
                                 'Invalid Changset')
        return row

    def get_change_info(self, rev):
        cursor = self.db.cursor ()
        cursor.execute ('SELECT name, change FROM node_change ' +
                        'WHERE rev=%d', rev)
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

    def render(self):
        self.perm.assert_permission (perm.CHANGESET_VIEW)

        self.add_link('alternate', '?format=diff', 'Unified Diff',
            'text/plain', 'diff')
        self.add_link('alternate', '?format=zip', 'Zip Archive',
            'application/zip', 'zip')

        youngest_rev = svn.fs.youngest_rev(self.fs_ptr, self.pool)
        if self.args.has_key('rev'):
            self.rev = int(self.args.get('rev'))
        else:
            self.rev = youngest_rev

        Diff.get_options(self.env, self.req, self.args, 1)
        if self.args.has_key('update'):
            self.req.redirect(self.env.href.changeset(self.rev))

        try:
            self.old_root = svn.fs.revision_root(self.fs_ptr,
                int(self.rev) - 1, self.pool)
            self.new_root = svn.fs.revision_root(self.fs_ptr,
                int(self.rev), self.pool)
        except svn.core.SubversionException:
            raise util.TracError('Invalid revision number: %d' % int(self.rev))

        changeset_info = self.get_changeset_info(self.rev)
        self.req.check_modified(int(changeset_info['time']))

        change_info = self.get_change_info(self.rev)

        self.req.hdf.setValue('title', '[%d] (changeset)' % self.rev)
        self.req.hdf.setValue('changeset.time',
                              time.asctime(time.localtime(int(changeset_info['time']))))
        author = changeset_info['author'] or 'anonymous'
        self.req.hdf.setValue('changeset.author', util.escape(author))
        self.req.hdf.setValue('changeset.message',
                              wiki_to_html(util.wiki_escape_newline(
                                           changeset_info['message']),
                                           self.req.hdf, self.env, self.db))
        self.req.hdf.setValue('changeset.revision', str(self.rev))
        util.add_to_hdf(change_info, self.req.hdf, 'changeset.changes')

        self.req.hdf.setValue('changeset.href',
                              self.env.href.changeset(self.rev))
        if self.rev > 1:
            self.add_link('first', self.env.href.changeset(1), 'Changeset 1')
            self.add_link('prev', self.env.href.changeset(self.rev - 1),
                          'Changeset %d' % (self.rev - 1))
        if self.rev < youngest_rev:
            self.add_link('next', self.env.href.changeset(self.rev + 1),
                          'Changeset %d' % (self.rev + 1))
            self.add_link('last', self.env.href.changeset(youngest_rev),
                          'Changeset %d' % youngest_rev)

    def render_diffs(self, editor_class=HtmlDiffEditor):
        """
        Generate a unified diff of the changes for a given changeset.
        The output is written to stdout.
        """
        editor = editor_class(self.old_root, self.new_root, int(self.rev), self.req,
                              self.args, self.env, self.path_info)
        e_ptr, e_baton = svn.delta.make_editor(editor, self.pool)

        def authz_cb(root, path, pool):
            return self.authzperm.has_permission(path) and 1 or 0
        svn.repos.svn_repos_dir_delta(self.old_root, '', '',
                                      self.new_root, '', e_ptr, e_baton, authz_cb,
                                      0, 1, 0, 1, self.pool)

    def display(self):
        """Pretty HTML view of the changeset"""
        self.render_diffs()
        Module.Module.display(self)

    def display_diff(self):
        """Raw Unified Diff version"""
        self.req.send_response(200)
        self.req.send_header('Content-Type', 'text/plain;charset=utf-8')
        self.req.send_header('Content-Disposition', 'filename=Changeset%d.diff' % self.rev)
        self.req.end_headers()
        self.render_diffs(UnifiedDiffEditor)

    def display_zip(self):
        """ZIP archive with all the added and/or modified files."""
        self.req.send_response(200)
        self.req.send_header('Content-Type', 'application/zip')
        self.req.send_header('Content-Disposition', 'filename=Changeset%d.zip' % self.rev)
        self.req.end_headers()
        self.render_diffs(ZipDiffEditor)

    def display_hdf(self):
        self.render_diffs()
        Module.Module.display_hdf(self)
