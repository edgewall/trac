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

import sys
from cStringIO import StringIO
import re
import string
from svn import fs, util, delta, repos

line_re = re.compile('@@ [+-]([0-9]+),([0-9]+) [+-]([0-9]+),([0-9]+) @@')
header_re = re.compile('header ([^\|]+) \| ([^\|]+) header')
space_re = re.compile('  ')

class DiffColorizer:
    def __init__(self, out=sys.stdout):
        self.count = 0
        self.block = []
        self.type  = None
        self.p_block = []
        self.p_type  = None
        self.out = out
        self.out.write('<table class="diff-table" cellspacing="0">')

    def writeadd (self, text):
        self.out.write ('<tr><td class="add-left"></td>'
                        '<td class="add-right">'
                        '%s</td></tr>' % text)
        
    def writeremove (self, text):
        self.out.write ('<tr><td class="rem-left">%s</td>'
                        '<td class="rem-right"></td></tr>' % text)
    
    def writeunmodified (self, text):
        self.out.write ('<tr><td class="unmod-left">%s</td>'
                        '<td class="unmod-right">%s</td></tr>' %
                        (text, text))

    def writemodified (self, old, new):
        self.out.write ('<tr><td class="mod-left">%s</td>'
                        '<td class="mod-right">%s</td></tr>' %
                        (old, new))
        
    def print_block (self):
        if self.p_type == '-' and self.type == '+':
            self.writemodified(string.join(self.p_block, '<br />'),
                              string.join(self.block, '<br />'))
        elif self.type == '+':
            self.writeadd(string.join(self.block, '<br />'))
        elif self.type == '-':
            self.writeremove(string.join(self.block, '<br />'))
        elif self.type == ' ':
            self.writeunmodified(string.join(self.block, '<br />'))
        self.block = self.p_block = []
    
    def writeline(self, text):
        match = header_re.search(text)
        if match:
            self.out.write ('<tr><td class="diff-line">%s</td>'
                            '<td class="diff-line">%s</td></tr>' %
                            (match.group(1), match.group(2)))
            return
        self.count = self.count + 1
        if self.count < 3:
            return
        match = line_re.search(text)
        if match:
            self.print_block()
            self.out.write ('<tr><td class="diff-line">line %s</td>'
                            '<td class="diff-line">line %s</td></tr>' %
                            (match.group(1), match.group(3)))
            return
        type = text[0]
        text = text[1:]
        text = space_re.sub ('&nbsp; ', text.expandtabs(8))
        if type == self.type:
            self.block.append(text)
        else:
            if type == '+' and self.type == '-':
                self.p_block = self.block
                self.p_type = self.type
            else:
                self.print_block()
            self.block = [text]
            self.type = type


    def close(self):
        self.print_block()
        self.out.write('</table>')


class HtmlDiffEditor (delta.Editor):
    """
    generates a htmlized unified diff of the changes for a given changeset.
    the output is written to stdout.
    """
    def __init__(self, old_root, new_root, rev, output):
        self.old_root = old_root
        self.new_root = new_root
        self.rev = rev
        self.output = output

    def print_diff (self, old_path, new_path, pool):
        if not old_path or not new_path:
            return
        differ = fs.FileDiff(self.old_root, old_path,
                             self.new_root, new_path, pool, ['-u'])
        differ.get_files()
        pobj = differ.get_pipe()
        self.output.write('<div class="chg-diff-file">')
        self.output.write('<h3 class="chg-diff-hdr">%s</h3>' % new_path)
        filter = DiffColorizer(self.output)
        while 1:
            line = pobj.readline()
            if not line:
                break
            filter.writeline(escape(line))
        filter.close()
        self.output.write('</div>')

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
    def print_diff (self, old_path, new_path, pool):
        if not old_path or not new_path:
            return

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

        
def render_diffs(fs_ptr, rev, pool, diff_class=HtmlDiffEditor):
    """
    generates a unified diff of the changes for a given changeset.
    the output is written to stdout.
    """
    old_root = fs.revision_root(fs_ptr, rev - 1, pool)
    new_root = fs.revision_root(fs_ptr, rev, pool)

    output = StringIO()

    editor = diff_class(old_root, new_root, rev, output)

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
    return output.getvalue()

class Changeset (Module):
    template_name = 'changeset.cs'

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
                         'file_href': self.env.href.file(row['name']),
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
        # Just recode this to iso8859-15 until we have propper unicode
        # support
        self.req.hdf.setValue('changeset.author', author)
        self.req.hdf.setValue('changeset.message', wiki_to_html(changeset_info['message'], self.req.hdf, self.env))
        self.req.hdf.setValue('changeset.revision', str(self.rev))

        add_dictlist_to_hdf(change_info, self.req.hdf, 'changeset.changes')
        self.req.hdf.setValue('title', '[%d] (changeset)' % self.rev)
        
        difftext = render_diffs(self.fs_ptr, int(self.rev), self.pool)
        self.req.hdf.setValue('changeset.diff_output', difftext)

    def display_diff (self):
        self.req.send_response(200)
        self.req.send_header('Content-Type', 'text/plain')
        self.req.end_headers()
        difftext = render_diffs(self.fs_ptr, int(self.rev), self.pool, UnifiedDiffEditor)
        self.req.write(difftext)
        
        
