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
from StringIO import StringIO
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

import svn
import svn.delta
import svn.fs

import Diff
import perm
import Module
from WikiFormatter import wiki_to_html


class BaseDiffEditor(svn.delta.Editor):
    """
    Base class for diff renderers.
    """

    def __init__(self, old_root, new_root, rev, req, args, env):
        self.old_root = old_root
        self.new_root = new_root
        self.rev = rev
        self.req = req
        self.args = args
        self.env = env

    def open_directory(self, path, parent_baton, base_revision, dir_pool):
        return [path, path, dir_pool]

    def open_file(self, path, parent_baton, base_revision, file_pool):
        return [path, path, file_pool]


class HtmlDiffEditor(BaseDiffEditor):
    """
    Generates a htmlized unified diff of the changes for a given changeset.
    the output is written to stdout.
    """

    def __init__(self, old_root, new_root, rev, req, args, env):
        BaseDiffEditor.__init__(self, old_root, new_root, rev, req, args, env)
        self.prev_path = None
        self.fileno = -1
        self.prefix = None

    def _check_next(self, old_path, new_path, pool):
        if self.prev_path == (old_path or new_path):
            return

        self.fileno += 1
        self.prev_path = old_path or new_path

        self.prefix = 'changeset.changes.%d' % (self.fileno)
        if old_path:
            old_rev = svn.fs.node_created_rev(self.old_root, old_path, pool)
            self.req.hdf.setValue('%s.rev.old' % self.prefix, str(old_rev))
            self.req.hdf.setValue('%s.browser_href.old' % self.prefix,
                                  self.env.href.browser(old_path, old_rev))
        if new_path:
            new_rev = svn.fs.node_created_rev(self.new_root, new_path, pool)
            self.req.hdf.setValue('%s.rev.new' % self.prefix, str(new_rev))
            self.req.hdf.setValue('%s.browser_href.new' % self.prefix,
                                  self.env.href.browser(new_path, new_rev))

    def add_directory(self, path, parent_baton, copyfrom_path,
                      copyfrom_revision, dir_pool):
        self._check_next(None, path, dir_pool)

    def delete_entry(self, path, revision, parent_baton, pool):
        self._check_next(path, None, pool)

    def change_dir_prop(self, dir_baton, name, value, dir_pool):
        if not dir_baton:
            return
        (old_path, new_path, pool) = dir_baton
        self._check_next(old_path, new_path, dir_pool)

        prefix = '%s.props.%s' % (self.prefix, name)
        if old_path:
            old_value = svn.fs.node_prop(self.old_root, old_path, name, dir_pool)
            if old_value:
                self.req.hdf.setValue(prefix + '.old', old_value)
        if value:
            self.req.hdf.setValue(prefix + '.new', value)

    def add_file(self, path, parent_baton, copyfrom_path, copyfrom_revision,
                 file_pool):
        self._check_next(None, path, file_pool)

    def apply_textdelta(self, file_baton, base_checksum):
        if not file_baton:
            return
        (old_path, new_path, pool) = file_baton
        self._check_next(old_path, new_path, pool)

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
            self.log.debug("Charset %s selected" % charset)
        else:
            charset = self.env.get_config('trac', 'default_charset',
                                          'iso-8859-15')

        # Start up the diff process
        options = Diff.get_options(self.env, self.req, self.args, 1)
        differ = svn.fs.FileDiff(self.old_root, old_path, self.new_root,
                                 new_path, pool, options)
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

    def change_file_prop(self, file_baton, name, value, file_pool):
        if not file_baton:
            return
        (old_path, new_path, pool) = file_baton
        self._check_next(old_path, new_path, file_pool)

        prefix = '%s.props.%s' % (self.prefix, name)
        if old_path:
            old_value = svn.fs.node_prop(self.old_root, old_path, name, file_pool)
            if old_value:
                self.req.hdf.setValue(prefix + '.old', old_value)
        if value:
            self.req.hdf.setValue(prefix + '.new', value)


class UnifiedDiffEditor(BaseDiffEditor):
    """
    Generates a unified diff of the changes for a given changeset.
    the output is written to stdout.
    """

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
        while line:
            self.req.write(line)
            line = pobj.readline()
        pobj.close()
        if sys.platform[:3] != "win" and sys.platform != "os2emx":
            try:
                os.waitpid(-1, 0)
            except OSError: pass


class ZipDiffEditor(BaseDiffEditor):
    """
    Generates a ZIP archive containing the modified and added files.
    """

    def __init__(self, old_root, new_root, rev, req, args, env):
        BaseDiffEditor.__init__(self, old_root, new_root, rev, req, args, env)
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

    def get_change_info (self, rev):
        cursor = self.db.cursor ()
        cursor.execute ('SELECT name, change FROM node_change ' +
                        'WHERE rev=%d', rev)
        info = []
        while 1:
            row = cursor.fetchone()
            if not row:
                break
            info.append({'name': row['name'],
                         'change': row['change'],
                         'log_href': self.env.href.log(row['name'])})
        return info

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

        change_info = self.get_change_info (self.rev)
        changeset_info = self.get_changeset_info (self.rev)

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
        generates a unified diff of the changes for a given changeset.
        the output is written to stdout.
        """
        try:
            old_root = svn.fs.revision_root(self.fs_ptr, int(self.rev) - 1, self.pool)
            new_root = svn.fs.revision_root(self.fs_ptr, int(self.rev), self.pool)
        except svn.core.SubversionException:
            raise util.TracError('Invalid revision number: %d' % int(self.rev))

        editor = editor_class(old_root, new_root, int(self.rev), self.req,
                              self.args, self.env)
        e_ptr, e_baton = svn.delta.make_editor(editor, self.pool)

        def authz_cb(root, path, pool):
            return self.authzperm.has_permission(path) and 1 or 0
        svn.repos.svn_repos_dir_delta(old_root, '', '',
                                      new_root, '', e_ptr, e_baton, authz_cb,
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
