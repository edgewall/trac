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
import os.path
import sqlite

db_name = None

def get_youngest_stored(cursor):
    cursor.execute('SELECT ifnull(max(rev), 0) FROM revision')
    return int(cursor.fetchone()[0])

def init():
    global db_name

    db_name = os.getenv('TRAC_DB')
    if not db_name:
        raise EnvironmentError, \
              'Missing environment variable "TRAC_DB". Trac ' \
              'requires this variable to a valid Trac database.'
    directory = os.path.dirname(db_name)
    if not os.access(db_name, os.R_OK + os.W_OK) or \
           not os.access(directory, os.R_OK + os.W_OK):
        tmp = db_name
        db_name = None
        raise EnvironmentError, \
              'The web server user requires read _and_ write permission\n' \
              'to the database %s and the directory this file is located in.' % tmp
        

def load_config():
    """
    load configuration from the config table.

    The configuration is returned as a section-dictionary containing
    name-value dictionaries.
    """
    cnx = get_connection()
    cursor = cnx.cursor()
    cursor.execute('SELECT section, name, value FROM config')
    config = {}
    rows = cursor.fetchall()
    for row in rows:
        if not config.has_key(row[0]):
            config[row[0]] = {}
        config[row[0]][row[1]] = row[2]
    return config

def get_connection():
    return sqlite.connect(db_name, timeout=5000)

def sync(repos, fs_ptr, pool):
    """
    updates the revision and node_change tables to be in sync with
    the repository.
    """
    from svn import fs, util, delta, repos

    if util.SVN_VER_MAJOR == 0 and util.SVN_VER_MINOR < 37:
        raise EnvironmentError, \
              "Subversion >= 0.37 required: Found %d.%d.%d" % \
              (util.SVN_VER_MAJOR, util.SVN_VER_MINOR, util.SVN_VER_MICRO)

    cnx = get_connection()

    cursor = cnx.cursor()
    youngest_stored = get_youngest_stored(cursor)
    max_rev = fs.youngest_rev(fs_ptr, pool)
    num = max_rev - youngest_stored
    offset = youngest_stored + 1
    for rev in range(num):
        message = fs.revision_prop(fs_ptr, rev + offset,
                                   util.SVN_PROP_REVISION_LOG, pool)
        author = fs.revision_prop(fs_ptr, rev + offset,
                                  util.SVN_PROP_REVISION_AUTHOR, pool)
        date = fs.revision_prop(fs_ptr, rev + offset,
                                util.SVN_PROP_REVISION_DATE, pool)
        
        date = util.svn_time_from_cstring(date, pool) / 1000000
        
        cursor.execute ('INSERT INTO revision (rev, time, author, message) '
                        'VALUES (%s, %s, %s, %s)', rev + offset, date,
                        author, message)
        insert_change (pool, fs_ptr, rev + offset, cursor)
    cnx.commit()

def insert_change (pool, fs_ptr, rev, cursor):
    from svn import fs, delta, repos
    
    class ChangeEditor(delta.Editor):
        def __init__(self, rev, old_root, new_root, cursor):
            self.rev = rev
            self.cursor = cursor
            self.old_root = old_root
            self.new_root = new_root
        
        def delete_entry(self, path, revision, parent_baton, pool):
            self.cursor.execute('INSERT INTO node_change (rev, name, change) '
                                'VALUES (%s, %s, \'D\')', self.rev, path)
        
        def add_directory(self, path, parent_baton,
                          copyfrom_path, copyfrom_revision, dir_pool):
            self.cursor.execute('INSERT INTO node_change (rev, name, change) '
                                'VALUES (%s, %s, \'A\')', self.rev, path)

        def add_file(self, path, parent_baton,
                     copyfrom_path, copyfrom_revision, file_pool):
            self.cursor.execute('INSERT INTO node_change (rev, name, change) '
                                'VALUES (%s, %s, \'A\')',self.rev, path)
            
        def open_file(self, path, parent_baton, base_revision, file_pool):
            self.cursor.execute('INSERT INTO node_change (rev, name, change) '
                                'VALUES (%s, %s, \'M\')',self.rev, path)


    old_root = fs.revision_root(fs_ptr, rev - 1, pool)
    new_root = fs.revision_root(fs_ptr, rev, pool)
    
    editor = ChangeEditor(rev, old_root, new_root, cursor)
    e_ptr, e_baton = delta.make_editor(editor, pool)

    repos.svn_repos_dir_delta(old_root, '', '',
                              new_root, '', e_ptr, e_baton, None, None,
			      0, 1, 0, 1, pool)

