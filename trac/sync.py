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

from svn import fs, util, delta, repos, core


def sync(db, repos, fs_ptr, pool):
    """
    Update the revision and node_change tables to be in sync with
    the repository.
    """

    if util.SVN_VER_MAJOR < 1:
        raise EnvironmentError, \
              "Subversion >= 1.0 required: Found %d.%d.%d" % \
              (util.SVN_VER_MAJOR, util.SVN_VER_MINOR, util.SVN_VER_MICRO)

    cursor = db.cursor()
    cursor.execute("SELECT COALESCE(max(rev),0) FROM revision")
    youngest_stored =  int(cursor.fetchone()[0])
    max_rev = fs.youngest_rev(fs_ptr, pool)
    num = max_rev - youngest_stored
    offset = youngest_stored + 1
    
    subpool = core.svn_pool_create(pool)
    for rev in range(num):
        message = fs.revision_prop(fs_ptr, rev + offset,
                                   util.SVN_PROP_REVISION_LOG, subpool)
        author = fs.revision_prop(fs_ptr, rev + offset,
                                  util.SVN_PROP_REVISION_AUTHOR, subpool)
        date = fs.revision_prop(fs_ptr, rev + offset,
                                util.SVN_PROP_REVISION_DATE, subpool)

        date = util.svn_time_from_cstring(date, subpool) / 1000000
        
        cursor.execute ('INSERT INTO revision (rev, time, author, message) '
                        'VALUES (%s, %s, %s, %s)', rev + offset, date,
                        author, message)
        insert_change (subpool, fs_ptr, rev + offset, cursor)
        core.svn_pool_clear(subpool)

    core.svn_pool_destroy(subpool)
    db.commit()


def insert_change(pool, fs_ptr, rev, cursor):
    """
    Save node changes for revision 'rev'.

    Analyse the difference tree at revision 'rev', as given by
    'repos.svn_repos_replay' (which offers usable 'copyfrom_' information).

    The results are cached in the 'node_change' table, as follows:

    || rev || action || name                                          ||
    || --- || ------ || --------------------------------------------- ||
    ||     ||  'A'   || added path                                    ||
    ||     ||  'D'   || removed path                                  ||
    ||     ||  'M'   || modified path                                 ||
    ||     ||  'C'   || original rev, original path // copied path    ||
    ||     ||  'R'   || original rev, original path // renamed path   ||
    ||     ||  'd'   || original rev, original path // deleted path   ||

    The 'ADM' operations are direct operations.
    The 'CR' operation can be direct operations.
    The 'CRdm' may happen after a 'CR' operation on a parent path.
    """

    class ChangeEditor(delta.Editor):
        def __init__(self, rev, new_root, cursor):
            self.rev = rev
            self.cursor = cursor
            self.new_root = new_root
            self.additions = [] # List of tuples
                                # (file/dir,new_path,old_path,old_rev,action)
            self.deletions = {} # Used to detect rename and copy operations.
            self.skip_dir_prop_change = 0
            
        def _norm(self, path):
            if path and path[0] == '/':
                path = path[1:]
            return path

        # -- svn.delta.Editor callbacks
        
        # A directory_baton is a tuple (old_path,old_rev,new_path).
        # This information is used to keep track of the original path
        # after a copy or a rename operation on the parent.

        # -- -- directory
        
        def open_root(self, base_revision, dir_pool):
            return (None, None, '/')
        # Note: '/' is needed for proper handling of prop changes at root
        #       (like SVK does for the svm:mirrors property).

        def add_directory(self, path, dir_baton, copyfrom_path, copyfrom_rev,
                          dir_pool):
            old_path, old_rev = dir_baton[:2]
            if copyfrom_path: # copied or renamed directory
                old_path = self._norm(copyfrom_path)
                old_rev = copyfrom_rev
                action = 'C'
            elif old_path:    # already on a branch, expand the original path
                old_path = posixpath.join(old_path, posixpath.split(path)[1])
                action = 'A'
            else:
                self._save_change(core.svn_node_file, 'A', path) 
                action = None

            if action:
                self.additions.append( (core.svn_node_dir, self._norm(path),
                                        old_path, old_rev, action) )

            # don't create an additional 'M' entry for this directory
            # in case there's also a dir property change
            self.skip_dir_prop_change = 1 

            return (old_path, old_rev, path)

        def open_directory(self, path, dir_baton, base_revision, dir_pool):
            old_path, old_rev = dir_baton[:2]
            if old_path: # already on a branch, expand the original path
                old_path = posixpath.join(old_path, posixpath.split(path)[1])
            self.skip_dir_prop_change = 0
            return (old_path, old_rev, path)

        def change_dir_prop(self, dir_baton, name, value, pool):
            if self.skip_dir_prop_change:
                return
            old_path, old_rev, path = dir_baton
            if old_path: # already on a branch
                self._save_change(core.svn_node_dir, 'm', path, old_path, old_rev)
            else:
                self._save_change(core.svn_node_dir, 'M', path)

            self.skip_dir_prop_change = 1

        def close_directory(self, dir_baton):
            self.skip_dir_prop_change = 0

        def delete_entry(self, path, revision, dir_baton, pool):
            """
            This is a removed path. It corresponds to one of the
            following actions: 'R'ename, 'D'elete, or 'd'elete on a branch.
            """
            old_path, old_rev = dir_baton[:2]
            if old_path: # already on a branch, expand the original path
                old_path = posixpath.join(old_path, posixpath.split(path)[1])
                path_info = (old_path, old_rev)
            else:
                path_info = core.svn_node_unknown
            self.deletions[self._norm(path)] = path_info

        # -- -- file

        def add_file(self, path, dir_baton, copyfrom_path, copyfrom_revision,
                     dir_pool):
            old_path, old_rev = dir_baton[:2]
            if copyfrom_path: # copied or renamed file
                old_path = self._norm(copyfrom_path)
                old_rev = copyfrom_revision
                action = 'C'
            elif old_path: # already on a branch, resolve old_rev later
                old_path = posixpath.join(old_path, posixpath.split(path)[1])
                old_rev = -1
                action = 'A'
            else:
                return self._save_change(core.svn_node_file, 'A', self._norm(path))
            
            self.additions.append( (core.svn_node_file, self._norm(path),
                                    old_path, old_rev, action) )

        def open_file(self, path, dir_baton, dummy_rev, file_pool):
            old_path, old_rev = dir_baton[:2]
            if old_path: # already on a branch (at b_rev)
                old_path = posixpath.join(old_path, posixpath.split(path)[1])
                # then this is a copy from a file for which f_rev > b_rev
                self.additions.append( (core.svn_node_file, self._norm(path),
                                        old_path, -1, 'C') )
            else: # no branch, it must be a modification
                self._save_change(core.svn_node_file, 'M', self._norm(path))

        def _save_change(self, node_type, action, path, old_path=None, old_rev=None):
            # Note: node_type is ignored for now
            if old_path and old_rev:
                path = "%s // %d, %s" % ( path, old_rev, old_path )
            self.cursor.execute('INSERT INTO node_change (rev, name, change) '
                                'VALUES (%s, %s, %s)', self.rev, path, action)

        def finalize(self):
            """
            The rename detection is deferred until the end of edition,
            as 'delete' and 'add' notifications can happen in any order.
            """
            for node_type, path, old_path, old_rev, action in self.additions:
                if self.deletions.has_key(old_path): # normal rename
                    del self.deletions[old_path]
                    action = 'R'
                elif self.deletions.has_key(path):   # copy+modification in a branch
                    action = 'C'
                    # FIXME: actually, this could be a 'R' if the parent branch
                    #        is a 'R'. This can be fixed if the parent branch
                    #        is recorded in addition to the old_path.
                    del self.deletions[path]
                if action == 'A':                    # add on a branch
                    old_path = old_rev = None
                self._save_change(node_type, action, path, old_path, old_rev)
            for path, path_info in self.deletions.items(): 
                if path_info == core.svn_node_unknown: # simple deletion
                    self._save_change(core.svn_node_unknown, 'D', path)
                else:                   # delete on a branch
                    self._save_change(core.svn_node_unknown, 'd', path, *path_info)


    new_root = fs.revision_root(fs_ptr, rev, pool)

    editor = ChangeEditor(rev, new_root, cursor)
    e_ptr, e_baton = delta.make_editor(editor, pool)

    repos.svn_repos_replay(new_root, e_ptr, e_baton, pool)

    editor.finalize() # Editor's close_edit not called...


