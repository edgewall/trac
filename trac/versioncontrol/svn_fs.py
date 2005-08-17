# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2005 Edgewall Software
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
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
# Author: Christopher Lenz <cmlenz@gmx.de>

from __future__ import generators

from trac.util import TracError
from trac.versioncontrol import Changeset, Node, Repository

import os.path
import time
import weakref

from svn import fs, repos, core, delta

_kindmap = {core.svn_node_dir: Node.DIRECTORY,
            core.svn_node_file: Node.FILE}

try:
    import threading
except ImportError:
    import dummy_threading as threading

apr_lock = threading.Lock()
apr_refcount = 0

    
def _get_history(path, authz, fs_ptr, pool, start, end, limit=None):
    history = []
    if hasattr(repos, 'svn_repos_history2'):
        # For Subversion >= 1.1
        def authz_cb(root, path, pool):
            if limit and len(history) >= limit:
                return 0
            return authz.has_permission(path) and 1 or 0
        def history2_cb(path, rev, pool):
            history.append((path, rev))
        repos.svn_repos_history2(fs_ptr, path, history2_cb, authz_cb,
                                 start, end, 1, pool)
    else:
        # For Subversion 1.0.x
        def history_cb(path, rev, pool):
            if authz.has_permission(path):
                history.append((path, rev))
        repos.svn_repos_history(fs_ptr, path, history_cb, start, end, 1, pool)
    for item in history:
        yield item


class Pool(object):
    """
    A wrapper for a new Subversion `pool` object that ties the lifetime of the
    pool to that of a  given object.
    
    Instances of this type return their associated `pool when called.
    """
    
    def __init__(self, parent, parent_pool=None):
        """
        Create a new pool that is a sub-pool of `parent_pool`, and arrange for
        `self._close` to be called up when the `parent` object is destroyed.
        
        The `parent` object must be weak-referenceable.  The returned `Pool`
        instance will have the value of the newly created pool. 
        """
        self._parent_pool = parent_pool
        self._children = []
        self._waiting_to_close = False
        # Make sure apr_init is called before the first pool is created
        global apr_refcount
        apr_lock.acquire()
        try:
            assert apr_refcount >= 0
            apr_refcount += 1
            if apr_refcount == 1:
                core.apr_initialize()
        finally:
            apr_lock.release()
            
        if self._parent_pool:
            self._pool = core.svn_pool_create(self._parent_pool())        
            self._parent_pool._children.append(self)
        else:
            self._pool = core.svn_pool_create(None)
        
        try:
            parent._pool_closer = weakref.ref(parent, self._close)
        except TypeError:
            self._close(None)
            raise
    
    def __call__(self):
        return self._pool
    
    def _child_closed(self, child):
        self._children.remove(child)
        if self._waiting_to_close:
            self._close(None)
    
    def _close(self, x):
        """
        The parent object has been destroyed so it is time for us to go.
        
        If we still have children that are alive, we do not clean up just
        yet.  This would lead to their memory being freed from under them.
        Instead, we wait for our child to notify us that they have been
        closed and clean up then. 
        
        -- So long, and thanks for all the fish!
        """
        assert self._pool
        
        if self._children:
            self._waiting_to_close = True
            return
        core.svn_pool_destroy(self._pool)
        self._pool = None
        # Make sure apr_terminate is called after the last pool is destroyed
        global apr_refcount
        apr_lock.acquire()
        try:
            apr_refcount -= 1
            assert apr_refcount >= 0
            if apr_refcount == 0:
                core.apr_terminate()
        finally:
            apr_lock.release()
            
        if self._parent_pool:
            self._parent_pool._child_closed(self)
            self._parent_pool = None


class SubversionRepository(Repository):
    """
    Repository implementation based on the svn.fs API.
    """

    pool = property(fget=lambda self: self._pool(),
                    fset=lambda self, pool: setattr(self, '_pool', pool))

    def __init__(self, path, authz, log):
        Repository.__init__(self, authz, log)

        if core.SVN_VER_MAJOR < 1:
            raise TracError, \
                  "Subversion >= 1.0 required: Found %d.%d.%d" % \
                  (core.SVN_VER_MAJOR, core.SVN_VER_MINOR, core.SVN_VER_MICRO)

        self.pool = None
        self.repos = None
        self.fs_ptr = None
        self.path = path
        self.pool = Pool(self)

        # Remove any trailing slash or else subversion might abort
        if not os.path.split(path)[1]:
            path = os.path.split(path)[0]
        self.path = repos.svn_repos_find_root_path(path, self.pool)
        if self.path is None:
            raise TracError, "%s does not appear to be a Subversion repository." % (path, )
        if self.path != path:
            self.scope = path[len(self.path):]
            if not self.scope[-1] == '/':
                self.scope += '/'
        else:
            self.scope = '/'
        self.log.debug("Opening subversion file-system at %s with scope %s" % (self.path, self.scope))

        self.repos = repos.svn_repos_open(self.path, self.pool)
        self.fs_ptr = repos.svn_repos_fs(self.repos)
        self.rev = fs.youngest_rev(self.fs_ptr, self.pool)

        self.history = None
        if self.scope != '/':
            self.history = []
            for path,rev in _get_history(self.scope[1:], self.authz,
                                         self.fs_ptr, self.pool, 0, self.rev):
                self.history.append(rev)

    def __del__(self):
        self.close()

    def normalize_path(self, path):
        return path == '/' and path or path.strip('/')

    def normalize_rev(self, rev):
        try:
            rev =  int(rev)
        except (ValueError, TypeError):
            rev = None
        if rev is None:
            rev = self.youngest_rev
        elif rev > self.youngest_rev:
            raise TracError, "Revision %s doesn't exist yet" % rev
        return rev

    def close(self):
        if self._pool:
            self.log.debug("Closing subversion file-system at %s" % self.path)
            self.pool = None
            self.repos = None
            self.fs_ptr = None
            self.rev = None

    def get_changeset(self, rev):
        return SubversionChangeset(int(rev), self.authz, self.scope,
                                   self.fs_ptr, self._pool)

    def get_node(self, path, rev=None):
        self.authz.assert_permission(self.scope + path)
        if path and path[-1] == '/':
            path = path[:-1]

        rev = self.normalize_rev(rev)

        return SubversionNode(path, rev, self.authz, self.scope, self.fs_ptr,
                              self._pool)

    def get_oldest_rev(self):
        rev = 0
        if self.scope == '/':
            return rev
        return self.history[-1]

    def get_youngest_rev(self):
        rev = self.rev
        if self.scope == '/':
            return rev
        return self.history[0]

    def previous_rev(self, rev):
        rev = int(rev)
        if rev == 0:
            return None
        if self.scope == '/':
            return rev - 1
        idx = self.history.index(rev)
        if idx + 1 < len(self.history):
            return self.history[idx + 1]
        return None

    def next_rev(self, rev):
        rev = int(rev)
        if rev == self.rev:
            return None
        if self.scope == '/':
            return rev + 1
        if rev == 0:
            return self.oldest_rev
        idx = self.history.index(rev)
        if idx > 0:
            return self.history[idx - 1]
        return None

    def rev_older_than(self, rev1, rev2):
        return self.normalize_rev(rev1) < self.normalize_rev(rev2)

    def get_youngest_rev_in_cache(self, db):
        """
        Get the latest stored revision by sorting the revision strings numerically
        """
        cursor = db.cursor()
        cursor.execute("SELECT rev FROM revision ORDER BY -LENGTH(rev), rev DESC LIMIT 1")
        row = cursor.fetchone()
        return row and row[0] or None

    def get_path_history(self, path, rev=None, limit=None):
        path = self.normalize_path(path)
        rev = self.normalize_rev(rev)
        expect_deletion = False
        while rev:
            rev_root = fs.revision_root(self.fs_ptr, rev, self.pool)
            node_type = fs.check_path(rev_root, path, self.pool)
            if node_type in _kindmap: # then path exists at that rev
                if expect_deletion:
                    # it was missing, now it's there again: rev+1 must be a delete
                    yield path, rev+1, Changeset.DELETE
                newer = None # 'newer' is the previously seen history tuple
                older = None # 'older' is the currently examined history tuple
                for p, r in _get_history(path, self.authz, self.fs_ptr,
                                         self.pool, 0, rev, limit):
                    older = (self.normalize_path(p), r, Changeset.ADD)
                    rev = self.previous_rev(r)
                    if newer:
                        if older[0] == path: # still on the path: 'newer' was an edit
                            yield newer[0], newer[1], Changeset.EDIT
                        else: # the path changed: 'newer' was a copy
                            rev = self.previous_rev(newer[1]) # restart before the copy op
                            yield newer[0], newer[1], Changeset.COPY
                            older = (older[0], older[1], 'unknown')
                            break
                    newer = older
                if older: # either a real ADD or the source of a COPY
                    yield older
            else:
                expect_deletion = True
                rev = self.previous_rev(rev)


class SubversionNode(Node):

    pool = property(fget=lambda self: self._pool(),
                    fset=lambda self, pool: setattr(self, '_pool', pool))

    def __init__(self, path, rev, authz, scope, fs_ptr, pool):
        self.authz = authz
        self.scope = scope
        if scope != '/':
            self.scoped_path = scope + path
        else:
            self.scoped_path = path
        self.fs_ptr = fs_ptr
        self.pool = Pool(self, pool)
        self._requested_rev = rev

        self.root = fs.revision_root(fs_ptr, rev, self.pool)
        node_type = fs.check_path(self.root, self.scoped_path, self.pool)
        if not node_type in _kindmap:
            raise TracError, "No node at %s in revision %s" % (path, rev)
        self.created_rev = fs.node_created_rev(self.root, self.scoped_path, self.pool)
        self.created_path = fs.node_created_path(self.root, self.scoped_path, self.pool)
        # 'created_path' differs from 'path' if the last operation is a copy,
        # and furthermore, 'path' might not exist at 'create_rev'
        self.rev = self.created_rev
        
        Node.__init__(self, path, self.rev, _kindmap[node_type])

    def get_content(self):
        if self.isdir:
            return None
        return core.Stream(fs.file_contents(self.root, self.scoped_path,
                                            self.pool))

    def get_entries(self):
        if self.isfile:
            return
        entries = fs.dir_entries(self.root, self.scoped_path, self.pool)
        for item in entries.keys():
            path = '/'.join((self.path, item))
            if not self.authz.has_permission(path):
                continue
            yield SubversionNode(path, self._requested_rev, self.authz,
                                 self.scope, self.fs_ptr, self._pool)

    def get_history(self,limit=None):
        newer = None # 'newer' is the previously seen history tuple
        older = None # 'older' is the currently examined history tuple
        for path, rev in _get_history(self.scoped_path, self.authz, self.fs_ptr,
                                      self.pool, 0, self._requested_rev, limit):
            if rev > 0 and path.startswith(self.scope):
                older = (path[len(self.scope):], rev, Changeset.ADD)
                if newer:
                    change = newer[0] == older[0] and Changeset.EDIT or Changeset.COPY
                    newer = (newer[0], newer[1], change)
                    yield newer
                newer = older
        if newer:
            yield newer

    def get_properties(self):
        props = fs.node_proplist(self.root, self.scoped_path, self.pool)
        for name,value in props.items():
            props[name] = str(value) # Make sure the value is a proper string
        return props

    def get_content_length(self):
        if self.isdir:
            return None
        return fs.file_length(self.root, self.scoped_path, self.pool)

    def get_content_type(self):
        if self.isdir:
            return None
        return self._get_prop(core.SVN_PROP_MIME_TYPE)

    def get_last_modified(self):
        date = fs.revision_prop(self.fs_ptr, self.created_rev,
                                core.SVN_PROP_REVISION_DATE, self.pool)
        return core.svn_time_from_cstring(date, self.pool) / 1000000

    def _get_prop(self, name):
        return fs.node_prop(self.root, self.scoped_path, name, self.pool)


class SubversionChangeset(Changeset):

    pool = property(fget=lambda self: self._pool(),
                    fset=lambda self, pool: setattr(self, '_pool', pool))

    def __init__(self, rev, authz, scope, fs_ptr, pool):
        self.rev = rev
        self.authz = authz
        self.scope = scope
        self.fs_ptr = fs_ptr
        self.pool = Pool(self, pool)
        message = self._get_prop(core.SVN_PROP_REVISION_LOG)
        author = self._get_prop(core.SVN_PROP_REVISION_AUTHOR)
        date = self._get_prop(core.SVN_PROP_REVISION_DATE)
        date = core.svn_time_from_cstring(date, self.pool) / 1000000
        Changeset.__init__(self, rev, message, author, date)

    def get_changes(self):
        root = fs.revision_root(self.fs_ptr, self.rev, self.pool)
        editor = repos.RevisionChangeCollector(self.fs_ptr, self.rev, self.pool)
        e_ptr, e_baton = delta.make_editor(editor, self.pool)
        repos.svn_repos_replay(root, e_ptr, e_baton, self.pool)

        idx = 0
        copies, deletions = {}, {}
        changes = []
        for path, change in editor.changes.items():
            if not self.authz.has_permission(path):
                # FIXME: what about base_path?
                continue
            if not path.startswith(self.scope[1:]):
                continue
            base_path = None
            if change.base_path:
                if change.base_path.startswith(self.scope):
                    base_path = change.base_path[len(self.scope):]
                else:
                    base_path = None
            action = ''
            if not change.path:
                action = Changeset.DELETE
                deletions[change.base_path] = idx
            elif change.added:
                if change.base_path and change.base_rev:
                    action = Changeset.COPY
                    copies[change.base_path] = idx
                else:
                    action = Changeset.ADD
            else:
                action = Changeset.EDIT
            kind = _kindmap[change.item_kind]
            path = path[len(self.scope) - 1:]
            changes.append([path, kind, action, base_path, change.base_rev])
            idx += 1

        moves = []
        for k,v in copies.items():
            if k in deletions:
                changes[v][2] = Changeset.MOVE
                moves.append(deletions[k])
        offset = 0
        for i in moves:
            del changes[i - offset]
            offset += 1

        for change in changes:
            yield tuple(change)

    def _get_prop(self, name):
        return fs.revision_prop(self.fs_ptr, self.rev, name, self.pool)
