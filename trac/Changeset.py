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

from util import *
from Module import Module
from Wiki import wiki_to_html
import perm

import re
import string
from svn import fs, util, delta, repos, core

line_re = re.compile('@@ [+-]([0-9]+),([0-9]+) [+-]([0-9]+),([0-9]+) @@')
header_re = re.compile('header ([^\|]+) \| ([^\|]+) redaeh')
space_re = re.compile('  ')

class DiffColorizer:
    def __init__(self, hdf, prefix='changeset.diff'):
        self.count = 0
        self.block = []
        self.ttype  = None
        self.p_block = []
        self.p_type  = None
        self.hdf = hdf
        self.prefix = prefix
        self.changeno = 0
        self.blockno = 0

    def _write_block (self, prefix, dtype, old = None, new = None):
        self.hdf.setValue(prefix + '.type', dtype);
        if old: self.hdf.setValue(prefix + '.text.old', old);
        if new: self.hdf.setValue(prefix + '.text.new', new);

    def print_block (self):
        self.blockno += 1
        prefix = '%s.changes.%d.blocks.%d' % (self.prefix, self.changeno,
                                              self.blockno)
        if self.p_type == '-' and self.ttype == '+':
            self._write_block(prefix, 'mod',
                       old=string.join(self.p_block, '<br />'),
                       new=string.join(self.block, '<br />'))
        elif self.ttype == '+':
            self._write_block(prefix, 'add', new=string.join(self.block, '<br />'))
        elif self.ttype == '-':
            self._write_block(prefix, 'rem', old=string.join(self.block, '<br />'))
        elif self.ttype == ' ':
            self._write_block(prefix, 'unmod', old=string.join(self.block, '<br />'),
                              new=string.join(self.block, '<br />'))
        self.block = self.p_block = []

    def writeline(self, text):
        match = header_re.search(text)
        if match:
            self.hdf.setValue('%s.name.old' % self.prefix, match.group(1))
            self.hdf.setValue('%s.name.new' % self.prefix, match.group(2))
            return
        self.count = self.count + 1
        if self.count < 3:
            return
        match = line_re.search(text)
        if match:
            self.changeno += 1
            pfx = '%s.changes.%d.line' % (self.prefix, self.changeno)
            self.print_block()
            self.hdf.setValue('%s.old' % pfx, match.group(1))
            self.hdf.setValue('%s.new' % pfx, match.group(3))
            return
        ttype = text[0]
        text = text[1:]
        text = space_re.sub('&nbsp; ', text.expandtabs(8))
        if ttype == self.ttype:
            self.block.append(text)
        else:
            if ttype == '+' and self.ttype == '-':
                self.p_block = self.block
                self.p_type = self.ttype
            else:
                self.print_block()
            self.block = [text]
            self.ttype = ttype

    def close(self):
        self.print_block()


class HtmlDiffEditor (delta.Editor):
    """
    generates a htmlized unified diff of the changes for a given changeset.
    the output is written to stdout.
    """
    def __init__(self, old_root, new_root, rev, req):
        self.old_root = old_root
        self.new_root = new_root
        self.rev = rev
        self.hdf = req.hdf
        self.fileno = 0

    def print_diff (self, old_path, new_path, pool):
        if not old_path or not new_path:
            return
        differ = fs.FileDiff(self.old_root, old_path,
                             self.new_root, new_path, pool, ['-u'])
        differ.get_files()
        pobj = differ.get_pipe()
        prefix = 'changeset.diff.files.%d' % (self.fileno)
        filtr = DiffColorizer(self.hdf, prefix)
        self.fileno += 1
        filtr.writeline('header %s | %s redaeh' % (old_path, new_path))
        while 1:
            line = pobj.readline()
            if not line:
                break
            filtr.writeline(escape(line))
        filtr.close()

    def add_file(self, path, parent_baton, copyfrom_path,
                 copyfrom_revision, file_pool):
        return [None, path, file_pool]

    def open_file(self, path, parent_baton, base_revision, file_pool):
        return [path, path, file_pool]

    def apply_textdelta(self, file_baton, base_checksum):
        self.print_diff (*file_baton)


class UnifiedDiffEditor(HtmlDiffEditor):
    """
    generates a unified diff of the changes for a given changeset.
    the output is written to stdout.
    """

    def __init__(self, old_root, new_root, rev, req):
        HtmlDiffEditor.__init__(self, old_root, new_root, rev, req)
        self.output = req

    def print_diff (self, old_path, new_path, pool):
        options = ['-u']
        options.append('-L')
        options.append("%s\t(revision %d)" % (old_path, self.rev-1))
        options.append('-L')
        options.append("%s\t(revision %d)" % (new_path, self.rev))

        differ = fs.FileDiff(self.old_root, old_path,
                             self.new_root, new_path, pool, options)
        differ.get_files()
        pobj = differ.get_pipe()
        line = pobj.readline()
        while line:
            self.output.write(line)
            line = pobj.readline()

    def add_file(self, path, parent_baton, copyfrom_path,
                 copyfrom_revision, file_pool):
        return [None, path, file_pool]

    def open_file(self, path, parent_baton, base_revision, file_pool):
        return [path, path, file_pool]

    def apply_textdelta(self, file_baton, base_checksum):
        self.print_diff (*file_baton)


def render_diffs(fs_ptr, rev, pool, req, editor_class=HtmlDiffEditor):
    """
    generates a unified diff of the changes for a given changeset.
    the output is written to stdout.
    """
    try:
        old_root = fs.revision_root(fs_ptr, rev - 1, pool)
        new_root = fs.revision_root(fs_ptr, rev, pool)
    except core.SubversionException:
        raise TracError('Invalid revision number: %d' % rev)

    editor = editor_class(old_root, new_root, rev, req)
    e_ptr, e_baton = delta.make_editor(editor, pool)

    if util.SVN_VER_MAJOR == 0 and util.SVN_VER_MINOR == 37:
        repos.svn_repos_dir_delta(old_root, '', '',
                                  new_root, '', e_ptr, e_baton, None, None,
                                  0, 1, 0, 1, pool)
    else:
        def authz_cb(root, path, pool): return 1
        repos.svn_repos_dir_delta(old_root, '', '',
                                  new_root, '', e_ptr, e_baton, authz_cb,
                                  0, 1, 0, 1, pool)


class Changeset (Module):
    template_name = 'changeset.cs'
    perm = None
    fs_ptr = None
    pool = None

    def get_changeset_info (self, rev):
        cursor = self.db.cursor ()
        cursor.execute ('SELECT time, author, message FROM revision ' +
                        'WHERE rev=%d' % rev)
        row = cursor.fetchone()
        if not row:
            raise TracError('Changeset %d does not exist.' % rev,
                            'Invalid Changset')
        return row

    def get_change_info (self, rev):
        cursor = self.db.cursor ()
        cursor.execute ('SELECT name, change FROM node_change ' +
                        'WHERE rev=%d' % rev)
        info = []
        while 1:
            row = cursor.fetchone()
            if not row:
                break
            info.append({'name': row['name'],
                         'change': row['change'],
                         'browser_href': self.env.href.browser(row['name'], rev),
                         'log_href': self.env.href.log(row['name'])})
        return info

    def render (self):
        self.perm.assert_permission (perm.CHANGESET_VIEW)

        if self.args.has_key('rev'):
            self.rev = int(self.args.get('rev'))
        else:
            self.rev = fs.youngest_rev(self.fs_ptr, self.pool)

        change_info = self.get_change_info (self.rev)
        for item in change_info:
            item['log_href'] = self.env.href.log(item['name'])

        changeset_info = self.get_changeset_info (self.rev)

        self.req.hdf.setValue('changeset.time',
                              time.asctime (time.localtime(int(changeset_info['time']))))
        author = changeset_info['author'] or 'None'
        self.req.hdf.setValue('changeset.author', escape(author))
        self.req.hdf.setValue('changeset.message',
                              wiki_to_html(changeset_info['message'],
                                           self.req.hdf, self.env))
        self.req.hdf.setValue('changeset.revision', str(self.rev))
        add_dictlist_to_hdf(change_info, self.req.hdf, 'changeset.changes')
        self.req.hdf.setValue('title', '[%d] (changeset)' % self.rev)

    def display(self):
        """Pretty HTML view of the changeset"""
        render_diffs(self.fs_ptr, int(self.rev), self.pool, self.req)
        Module.display(self)

    def display_hdf(self):
        render_diffs(self.fs_ptr, int(self.rev), self.pool, self.req)
        Module.display_hdf(self)

    def display_diff (self):
        """Raw Unified Diff version"""
        self.req.send_response(200)
        self.req.send_header('Content-Type', 'text/plain')
        self.req.end_headers()
        render_diffs(self.fs_ptr, int(self.rev), self.pool, self.req,
                     UnifiedDiffEditor)

