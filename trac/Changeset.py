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
from Href import href
import db
import perm
from xml.sax.saxutils import escape

import re
import string
from svn import fs, util, delta, repos

line_re = re.compile('@@ [+-]([0-9]+),([0-9]+) [+-]([0-9]+),([0-9]+) @@')
space_re = re.compile('  ')

class DiffColorizer:
    def __init__(self):
        self.count = 0
        self.block = []
        self.type  = None
        self.p_block = []
        self.p_type  = None

        print '<table class="diff-table" cellspacing="0">'

    def writeadd (self, text):
        print ('<tr><td class="diff-add-left"></td>'
               '<td class="diff-add-right">'
               '%s</td></tr>' % text)
        
    def writeremove (self, text):
        print ('<tr><td class="diff-remove-left">%s</td>'
               '<td class="diff-remove-right"></td></tr>' % text)
    
    def writeunmodified (self, text):
        print ('<tr><td class="diff-unmodified">%s</td>'
               '<td class="diff-unmodified">%s</td></tr>' %
               (text, text))

    def writemodified (self, old, new):
        print ('<tr><td class="diff-modified">%s</td>'
               '<td class="diff-modified">%s</td></tr>' %
               (old, new))
        
    def print_block (self):
        if self.p_type == '-' and self.type == '+':
            self.writemodified(string.join(self.p_block, '<br>'),
                              string.join(self.block, '<br>'))
        elif self.type == '+':
            self.writeadd(string.join(self.block, '<br>'))
        elif self.type == '-':
            self.writeremove(string.join(self.block, '<br>'))
        elif self.type == ' ':
            self.writeunmodified(string.join(self.block, '<br>'))
        self.block = self.p_block = []
    
    def writeline(self, text):
        self.count = self.count + 1
        if self.count < 3:
            return
        match = line_re.search(text)
        if match:
            self.print_block()
            print ('<tr><td class="diff-line">line %s</td>'
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
        print '</table>'


class DiffEditor (delta.Editor):
    """
    generates a unified diff of the changes for a given changeset.
    the output is written to stdout.
    """
    def __init__(self, old_root, new_root):
        self.old_root = old_root
        self.new_root = new_root

    def print_diff (self, old_path, new_path, pool):
        old_root = new_root = None
        if old_path:
            old_root = self.old_root
            name = old_path
        if new_path:
            new_root = self.new_root
            name = new_path
        differ = fs.FileDiff(old_root, old_path,
                             new_root, new_path, pool, ['-u'])
        differ.get_files()
        pobj = differ.get_pipe()
        print '<h3>%s</h3>' % name
        filter = DiffColorizer()
        while 1:
            line = pobj.readline()
            if not line:
                break
            filter.writeline(escape(line))
        filter.close()


    def add_file(self, path, parent_baton,
                 copyfrom_path, copyfrom_revision, file_pool):
        self.print_diff (None, path, file_pool)
        return [None, path, file_pool]
    
    def open_file(self, path, parent_baton, base_revision, file_pool):
        return [path, path, file_pool]

    def apply_textdelta(self, file_baton, base_checksum):
        self.print_diff (*file_baton)
        
def render_diffs(fs_ptr, rev, pool):
    """
    generates a unified diff of the changes for a given changeset.
    the output is written to stdout.
    """
    old_root = fs.revision_root(fs_ptr, rev - 1, pool)
    new_root = fs.revision_root(fs_ptr, rev, pool)
    
    editor = DiffEditor(old_root, new_root)
    e_ptr, e_baton = delta.make_editor(editor, pool)

    try:
        repos.svn_repos_dir_delta(old_root, '', None,
                                  new_root, '', e_ptr, e_baton, None, None,
                              0, 1, 0, 1, pool)
    except TypeError:
        # Subversion frequently changes the API
        # dir_delta on subversion < 0.33 only takes 12 arguments
        repos.svn_repos_dir_delta(old_root, '', None,
                                  new_root, '', e_ptr, e_baton,
                              0, 1, 0, 1, pool)
        

class Changeset (Module):
    template_name = 'changeset.cs'

    def get_changeset_info (self, rev):
        cnx = db.get_connection()
        cursor = cnx.cursor ()

        cursor.execute ('SELECT time, author, message FROM revision ' +
                        'WHERE rev=%d' % rev)
        return cursor.fetchone()
        
    def get_change_info (self, rev):
        cnx = db.get_connection()
        cursor = cnx.cursor ()

        cursor.execute ('SELECT name, change FROM node_change ' +
                        'WHERE rev=%d' % rev)
        info = []
        while 1:
            row = cursor.fetchone()
            if not row:
                break
            info.append({'name': row['name'],
                         'change': row['change'],
                         'log_href': href.log(row['name'])})
        return info
        
    def render (self):
        perm.assert_permission (perm.CHANGESET_VIEW)
        
        if self.args.has_key('rev'):
            self.rev = int(self.args['rev'])
        else:
            self.rev = fs.youngest_rev(self.fs_ptr, self.pool)

        change_info = self.get_change_info (self.rev)
        for item in change_info:
            item['log_href'] = href.log(item['name'])

        changeset_info = self.get_changeset_info (self.rev)
        
        self.cgi.hdf.setValue('changeset.time',
                              time_to_string (int(changeset_info['time'])))
        self.cgi.hdf.setValue('changeset.author', changeset_info['author'])
        self.cgi.hdf.setValue('changeset.message', changeset_info['message'])
        self.cgi.hdf.setValue('changeset.revision', str(self.rev))

        add_dictlist_to_hdf(change_info, self.cgi.hdf, 'changeset.changes')
        
    def apply_template (self):
        Module.apply_template(self)
        render_diffs(self.fs_ptr, int(self.rev), self.pool)
        import neo_cs
        cs = neo_cs.CS(self.cgi.hdf)
        cs.parseFile('../templates/footer.cs')
        sys.stdout.write(cs.render())

