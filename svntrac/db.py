# svntrac
#
# Copyright (C) 2003 Xyche Software
# Copyright (C) 2003 Jonas Borgström <jonas@xyche.com>
#
# svntrac is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version.
#
# svntrac is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#
# Author: Jonas Borgström <jonas@xyche.com>

import sqlite

from svn import fs, util, delta, repos

db_name = None

class ChangeEditor (delta.Editor):
    def __init__(self, rev, old_root, new_root, cursor):
        self.rev = rev
        self.cursor = cursor
        self.old_root = old_root
        self.new_root = new_root
        
    def delete_entry(self, path, revision, parent_baton, pool):
        self.cursor.execute ('INSERT INTO node_change (rev, name, change) '
                             'VALUES (%s, %s, \'D\')', self.rev, path)
        
    def add_directory(self, path, parent_baton,
                      copyfrom_path, copyfrom_revision, dir_pool):
        self.cursor.execute ('INSERT INTO node_change (rev, name, change) '
                             'VALUES (%s, %s, \'A\')', self.rev, path)

    def add_file(self, path, parent_baton,
                 copyfrom_path, copyfrom_revision, file_pool):
        self.cursor.execute ('INSERT INTO node_change (rev, name, change) '
                             'VALUES (%s, %s, \'A\')',self.rev, path)

    def open_file(self, path, parent_baton, base_revision, file_pool):
        self.cursor.execute ('INSERT INTO node_change (rev, name, change) '
                             'VALUES (%s, %s, \'M\')',self.rev, path)

def get_youngest_stored (cursor):
    cursor.execute ('SELECT MAX(rev) FROM (SELECT MAX(rev) as rev FROM '
                    'revision UNION SELECT 0 as rev)')
    return int(cursor.fetchone()[0])

def init (conf):
    global db_name
    db_name = conf.get('general', 'database')

def get_connection ():
    return sqlite.connect (db_name)

def sync (repos, fs_ptr, pool):
    """
    updates the revision and node_change tables to be in sync with
    the repository.
    """
    cnx = get_connection ()

    cursor  = cnx.cursor ()
    youngest_stored  = get_youngest_stored (cursor)
    max_rev = fs.youngest_rev(fs_ptr, pool)
    num = max_rev - youngest_stored
    offset = youngest_stored + 1
    for rev in range (num):
        
        message = fs.revision_prop(fs_ptr, rev + offset,
                                   util.SVN_PROP_REVISION_LOG, pool)
        author  = fs.revision_prop(fs_ptr, rev + offset,
                                   util.SVN_PROP_REVISION_AUTHOR, pool)
        date    = fs.revision_prop(fs_ptr, rev + offset,
                                   util.SVN_PROP_REVISION_DATE, pool)
        
        date    = util.svn_time_from_cstring(date, pool) / 1000000
        
        cursor.execute ('INSERT INTO revision (rev, time, author, message) '
                        'VALUES (%s, %s, %s, %s)', rev + offset, date,
                        author, message)
        insert_change (pool, fs_ptr, rev + offset, cursor)
    cnx.commit()

def insert_change (pool, fs_ptr, rev, cursor):
    old_root = fs.revision_root(fs_ptr, rev - 1, pool)
    new_root = fs.revision_root(fs_ptr, rev, pool)
    
    editor = ChangeEditor(rev, old_root, new_root, cursor)
    e_ptr, e_baton = delta.make_editor(editor, pool)

    repos.svn_repos_dir_delta(old_root, '', None,
                               new_root, '', e_ptr, e_baton,
                               0, 1, 0, 1, pool)
