# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2009 Edgewall Software
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
# Copyright (C) 2005-2007 Christian Boos <cboos@neuf.fr>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.
#
# Author: Christopher Lenz <cmlenz@gmx.de>
#         Christian Boos <cboos@neuf.fr>

"""Filesystem access to Subversion repositories.

'''Note about Unicode:'''

The Subversion bindings are not unicode-aware and they expect to
receive UTF-8 encoded `string` parameters,

On the other hand, all paths manipulated by Trac are `unicode` objects.

Therefore:

 * before being handed out to SVN, the Trac paths have to be encoded to
   UTF-8, using `_to_svn()`
 * before being handed out to Trac, a SVN path has to be decoded from
   UTF-8, using `_from_svn()`

Whenever a value has to be stored as utf8, we explicitly mark the
variable name with "_utf8", in order to avoid any possible confusion.

Warning:
  `SubversionNode.get_content()` returns an object from which one can read
  a stream of bytes. NO guarantees can be given about what that stream of
  bytes represents. It might be some text, encoded in some way or another.
  SVN properties __might__ give some hints about the content, but they
  actually only reflect the beliefs of whomever set those properties...
"""

import os.path
import weakref
import posixpath

from trac.config import ListOption
from trac.core import *
from trac.env import ISystemInfoProvider
from trac.versioncontrol import Changeset, Node, Repository, \
                                IRepositoryConnector, \
                                NoSuchChangeset, NoSuchNode
from trac.versioncontrol.cache import CachedRepository
from trac.util import embedded_numbers
from trac.util.text import exception_to_unicode, to_unicode
from trac.util.translation import _
from trac.util.datefmt import from_utimestamp


application_pool = None


def _import_svn():
    global fs, repos, core, delta, _kindmap
    from svn import fs, repos, core, delta
    _kindmap = {core.svn_node_dir: Node.DIRECTORY,
                core.svn_node_file: Node.FILE}
    # Protect svn.core methods from GC
    Pool.apr_pool_clear = staticmethod(core.apr_pool_clear)
    Pool.apr_pool_destroy = staticmethod(core.apr_pool_destroy)

def _to_svn(pool, *args):
    """Expect a pool and a list of `unicode` path components.
    
    Returns an UTF-8 encoded string suitable for the Subversion python 
    bindings (the returned path never starts with a leading "/")
    """
    return core.svn_path_canonicalize('/'.join(args).lstrip('/')
                                                    .encode('utf-8'),
                                      pool)

def _from_svn(path):
    """Expect an UTF-8 encoded string and transform it to an `unicode` object

    But Subversion repositories built from conversion utilities can have
    non-UTF-8 byte strings, so we have to convert using `to_unicode`.
    """
    return path and to_unicode(path, 'utf-8')
    
# The following 3 helpers deal with unicode paths

def _normalize_path(path):
    """Remove leading "/", except for the root."""
    return path and path.strip('/') or '/'

def _path_within_scope(scope, fullpath):
    """Remove the leading scope from repository paths.

    Return `None` if the path is not is scope.
    """
    if fullpath is not None:
        fullpath = fullpath.lstrip('/')
        if scope == '/':
            return _normalize_path(fullpath)
        scope = scope.strip('/')
        if (fullpath + '/').startswith(scope + '/'):
            return fullpath[len(scope) + 1:] or '/'

def _is_path_within_scope(scope, fullpath):
    """Check whether the given `fullpath` is within the given `scope`"""
    if scope == '/':
        return fullpath is not None
    fullpath = fullpath and fullpath.lstrip('/') or ''
    scope = scope.strip('/')
    return (fullpath + '/').startswith(scope + '/')

# svn_opt_revision_t helpers

def _svn_rev(num):
    value = core.svn_opt_revision_value_t()
    value.number = num
    revision = core.svn_opt_revision_t()
    revision.kind = core.svn_opt_revision_number
    revision.value = value
    return revision

def _svn_head():
    revision = core.svn_opt_revision_t()
    revision.kind = core.svn_opt_revision_head
    return revision

# apr_pool_t helpers

def _mark_weakpool_invalid(weakpool):
    if weakpool():
        weakpool()._mark_invalid()


class Pool(object):
    """A Pythonic memory pool object"""

    def __init__(self, parent_pool=None):
        """Create a new memory pool"""

        global application_pool
        self._parent_pool = parent_pool or application_pool

        # Create pool
        if self._parent_pool:
            self._pool = core.svn_pool_create(self._parent_pool())
        else:
            # If we are an application-level pool,
            # then initialize APR and set this pool
            # to be the application-level pool
            core.apr_initialize()
            application_pool = self

            self._pool = core.svn_pool_create(None)
        self._mark_valid()

    def __call__(self):
        return self._pool

    def valid(self):
        """Check whether this memory pool and its parents
        are still valid"""
        return hasattr(self,"_is_valid")

    def assert_valid(self):
        """Assert that this memory_pool is still valid."""
        assert self.valid()

    def clear(self):
        """Clear embedded memory pool. Invalidate all subpools."""
        self.apr_pool_clear(self._pool)
        self._mark_valid()

    def destroy(self):
        """Destroy embedded memory pool. If you do not destroy
        the memory pool manually, Python will destroy it
        automatically."""

        global application_pool

        self.assert_valid()

        # Destroy pool
        self.apr_pool_destroy(self._pool)

        # Clear application pool and terminate APR if necessary
        if not self._parent_pool:
            application_pool = None

        self._mark_invalid()

    def __del__(self):
        """Automatically destroy memory pools, if necessary"""
        if self.valid():
            self.destroy()

    def _mark_valid(self):
        """Mark pool as valid"""
        if self._parent_pool:
            # Refer to self using a weakreference so that we don't
            # create a reference cycle
            weakself = weakref.ref(self)

            # Set up callbacks to mark pool as invalid when parents
            # are destroyed
            self._weakref = weakref.ref(self._parent_pool._is_valid,
                                        lambda x: \
                                        _mark_weakpool_invalid(weakself))

        # mark pool as valid
        self._is_valid = lambda: 1

    def _mark_invalid(self):
        """Mark pool as invalid"""
        if self.valid():
            # Mark invalid
            del self._is_valid

            # Free up memory
            del self._parent_pool
            if hasattr(self, "_weakref"):
                del self._weakref


class SvnCachedRepository(CachedRepository):
    """Subversion-specific cached repository, zero-pads revision numbers
    in the cache tables.
    """
    def db_rev(self, rev):
        return '%010d' % rev

    def rev_db(self, rev):
        return int(rev or 0)


class SubversionConnector(Component):

    implements(ISystemInfoProvider, IRepositoryConnector)

    branches = ListOption('svn', 'branches', 'trunk,branches/*', doc=
        """Comma separated list of paths categorized as branches.
        If a path ends with '*', then all the directory entries found below 
        that path will be included. 
        Example: `/trunk, /branches/*, /projectAlpha/trunk, /sandbox/*`
        """)

    tags = ListOption('svn', 'tags', 'tags/*', doc=
        """Comma separated list of paths categorized as tags.
        
        If a path ends with '*', then all the directory entries found below
        that path will be included.
        Example: `/tags/*, /projectAlpha/tags/A-1.0, /projectAlpha/tags/A-v1.1`
        """)

    error = None

    def __init__(self):
        self._version = None
        try:
            _import_svn()
            self.log.debug('Subversion bindings imported')
        except ImportError, e:
            self.error = e
            self.log.info('Failed to load Subversion bindings', exc_info=True)
        else:
            version = (core.SVN_VER_MAJOR, core.SVN_VER_MINOR,
                       core.SVN_VER_MICRO)
            self._version = '%d.%d.%d' % version + core.SVN_VER_TAG
            if version[0] < 1:
                self.error = _("Subversion >= 1.0 required, found %(version)s",
                               version=self._version)
            Pool()

    # ISystemInfoProvider methods
    
    def get_system_info(self):
        if self._version is not None:
            yield 'Subversion', self._version
        
    # IRepositoryConnector methods
    
    def get_supported_types(self):
        prio = 1
        if self.error:
            prio = -1
        yield ("direct-svnfs", prio*4)
        yield ("svnfs", prio*4)
        yield ("svn", prio*2)

    def get_repository(self, type, dir, params):
        """Return a `SubversionRepository`.

        The repository is wrapped in a `CachedRepository`, unless `type` is
        'direct-svnfs'.
        """
        params.update(tags=self.tags, branches=self.branches)
        fs_repos = SubversionRepository(dir, params, self.log)
        if type == 'direct-svnfs':
            repos = fs_repos
        else:
            repos = SvnCachedRepository(self.env, fs_repos, self.log)
            repos.has_linear_changesets = True
        return repos


class SubversionRepository(Repository):
    """Repository implementation based on the svn.fs API."""

    def __init__(self, path, params, log):
        self.log = log
        self.pool = Pool()
        
        # Remove any trailing slash or else subversion might abort
        if isinstance(path, unicode):
            path_utf8 = path.encode('utf-8')
        else: # note that this should usually not happen (unicode arg expected)
            path_utf8 = to_unicode(path).encode('utf-8')

        path_utf8 = os.path.normpath(path_utf8).replace('\\', '/')
        self.path = path_utf8.decode('utf-8')
        
        root_path_utf8 = repos.svn_repos_find_root_path(path_utf8, self.pool())
        if root_path_utf8 is None:
            raise TracError(_("%(path)s does not appear to be a Subversion "
                              "repository.", path=to_unicode(path_utf8)))

        try:
            self.repos = repos.svn_repos_open(root_path_utf8, self.pool())
        except core.SubversionException, e:
            raise TracError(_("Couldn't open Subversion repository %(path)s: "
                              "%(svn_error)s", path=to_unicode(path_utf8),
                              svn_error=exception_to_unicode(e)))
        self.fs_ptr = repos.svn_repos_fs(self.repos)
        
        self.uuid = fs.get_uuid(self.fs_ptr, self.pool())
        self.base = 'svn:%s:%s' % (self.uuid, _from_svn(root_path_utf8))
        name = 'svn:%s:%s' % (self.uuid, self.path)

        Repository.__init__(self, name, params, log)

        # if root_path_utf8 is shorter than the path_utf8, the difference is
        # this scope (which always starts with a '/')
        if root_path_utf8 != path_utf8:
            self.scope = path_utf8[len(root_path_utf8):].decode('utf-8')
            if not self.scope[-1] == '/':
                self.scope += '/'
        else:
            self.scope = '/'
        assert self.scope[0] == '/'
        # we keep root_path_utf8 for  RA 
        ra_prefix = os.name == 'nt' and 'file:///' or 'file://'
        self.ra_url_utf8 = ra_prefix + root_path_utf8
        self.clear()

    def clear(self, youngest_rev=None):
        self.youngest = None
        if youngest_rev is not None:
            self.youngest = self.normalize_rev(youngest_rev)
        self.oldest = None

    def __del__(self):
        self.close()

    def has_node(self, path, rev=None, pool=None):
        if not pool:
            pool = self.pool
        rev = self.normalize_rev(rev)
        rev_root = fs.revision_root(self.fs_ptr, rev, pool())
        node_type = fs.check_path(rev_root, _to_svn(pool(), self.scope, path),
                                  pool())
        return node_type in _kindmap

    def normalize_path(self, path):
        return _normalize_path(path)

    def normalize_rev(self, rev):
        if rev is None or isinstance(rev, basestring) and \
               rev.lower() in ('', 'head', 'latest', 'youngest'):
            return self.youngest_rev
        else:
            try:
                rev = int(rev)
                if rev <= self.youngest_rev:
                    return rev
            except (ValueError, TypeError):
                pass
            raise NoSuchChangeset(rev)

    def close(self):
        if self.pool:
            self.pool.destroy()
        self.repos = self.fs_ptr = self.pool = None

    def get_base(self):
        return self.base
        
    def _get_tags_or_branches(self, paths):
        """Retrieve known branches or tags."""
        for path in self.params.get(paths, []):
            if path.endswith('*'):
                folder = posixpath.dirname(path)
                try:
                    entries = [n for n in self.get_node(folder).get_entries()]
                    for node in sorted(entries, key=lambda n: 
                                       embedded_numbers(n.path.lower())):
                        if node.kind == Node.DIRECTORY:
                            yield node
                except: # no right (TODO: should use a specific Exception here)
                    pass
            else:
                try:
                    yield self.get_node(path)
                except: # no right
                    pass

    def get_quickjump_entries(self, rev):
        """Retrieve known branches, as (name, id) pairs.
        
        Purposedly ignores `rev` and always takes the last revision.
        """
        for n in self._get_tags_or_branches('branches'):
            yield 'branches', n.path, n.path, None
        for n in self._get_tags_or_branches('tags'):
            yield 'tags', n.path, n.created_path, n.created_rev

    def get_path_url(self, path, rev):
        url = self.params.get('url', '').rstrip('/')
        if url:
            if not path or path == '/':
                return url
            return url + '/' + path.lstrip('/')
    
    def get_changeset(self, rev):
        rev = self.normalize_rev(rev)
        return SubversionChangeset(self, rev, self.scope, self.pool)

    def get_changeset_uid(self, rev):
        return (self.uuid, rev)

    def get_node(self, path, rev=None):
        path = path or ''
        if path and path[-1] == '/':
            path = path[:-1]

        rev = self.normalize_rev(rev) or self.youngest_rev

        return SubversionNode(path, rev, self, self.pool)

    def _get_node_revs(self, path, last=None, first=None):
        """Return the revisions affecting `path` between `first` and `last` 
        revs. If `first` is not given, it goes down to the revision in which
        the branch was created.
        """
        node = self.get_node(path, last)
        revs = []
        for (p, r, chg) in node.get_history():
            if p != path or (first and r < first):
                break
            revs.append(r)
        return revs

    def _history(self, path, start, end, pool):
        """`path` is a unicode path in the scope.

        Generator yielding `(path, rev)` pairs, where `path` is an `unicode`
        object.
        Must start with `(path, created rev)`.
        """
        path_utf8 = _to_svn(pool(), self.scope, path)
        if start < end:
            start, end = end, start
        if (start, end) == (1, 0): # only happens for empty repos
            return
        root = fs.revision_root(self.fs_ptr, start, pool())
        # fs.node_history leaks when path doesn't exist (#6588)
        if fs.check_path(root, path_utf8, pool()) == core.svn_node_none:
            return
        tmp1 = Pool(pool)
        tmp2 = Pool(pool)
        history_ptr = fs.node_history(root, path_utf8, tmp1())
        cross_copies = 1
        while history_ptr:
            history_ptr = fs.history_prev(history_ptr, cross_copies, tmp2())
            tmp1.clear()
            tmp1, tmp2 = tmp2, tmp1
            if history_ptr:
                path_utf8, rev = fs.history_location(history_ptr, tmp2())
                tmp2.clear()
                if rev < end:
                    break
                path = _from_svn(path_utf8)
                yield path, rev
        del tmp1
        del tmp2
    
    def _previous_rev(self, rev, path='', pool=None):
        if rev > 1: # don't use oldest here, as it's too expensive
            for _, prev in self._history(path, 1, rev-1, pool or self.pool):
                return prev
        return None
    

    def get_oldest_rev(self):
        if self.oldest is None:
            self.oldest = 1
            # trying to figure out the oldest rev for scoped repository
            # is too expensive and uncovers a big memory leak (#5213)
            # if self.scope != '/':
            #    self.oldest = self.next_rev(0, find_initial_rev=True)
        return self.oldest

    def get_youngest_rev(self):
        if not self.youngest:
            self.youngest = fs.youngest_rev(self.fs_ptr, self.pool())
            if self.scope != '/':
                for path, rev in self._history('', 1, self.youngest, self.pool):
                    self.youngest = rev
                    break
        return self.youngest

    def previous_rev(self, rev, path=''):
        rev = self.normalize_rev(rev)
        return self._previous_rev(rev, path)

    def next_rev(self, rev, path='', find_initial_rev=False):
        rev = self.normalize_rev(rev)
        next = rev + 1
        youngest = self.youngest_rev
        subpool = Pool(self.pool)
        while next <= youngest:
            subpool.clear()            
            for _, next in self._history(path, rev+1, next, subpool):
                return next
            else:
                if not find_initial_rev and \
                         not self.has_node(path, next, subpool):
                    return next # a 'delete' event is also interesting...
            next += 1
        return None

    def rev_older_than(self, rev1, rev2):
        return self.normalize_rev(rev1) < self.normalize_rev(rev2)

    def get_youngest_rev_in_cache(self, db):
        """Get the latest stored revision by sorting the revision strings
        numerically

        (deprecated, only used for transparent migration to the new caching
        scheme).
        """
        cursor = db.cursor()
        cursor.execute("SELECT rev FROM revision "
                       "ORDER BY -LENGTH(rev), rev DESC LIMIT 1")
        row = cursor.fetchone()
        return row and row[0] or None

    def get_path_history(self, path, rev=None, limit=None):
        path = self.normalize_path(path)
        rev = self.normalize_rev(rev)
        expect_deletion = False
        subpool = Pool(self.pool)
        numrevs = 0
        while rev and (not limit or numrevs < limit):
            subpool.clear()
            if self.has_node(path, rev, subpool):
                if expect_deletion:
                    # it was missing, now it's there again:
                    #  rev+1 must be a delete
                    numrevs += 1
                    yield path, rev+1, Changeset.DELETE
                newer = None # 'newer' is the previously seen history tuple
                older = None # 'older' is the currently examined history tuple
                for p, r in self._history(path, 1, rev, subpool):
                    older = (_path_within_scope(self.scope, p), r,
                             Changeset.ADD)
                    rev = self._previous_rev(r, pool=subpool)
                    if newer:
                        numrevs += 1
                        if older[0] == path:
                            # still on the path: 'newer' was an edit
                            yield newer[0], newer[1], Changeset.EDIT
                        else:
                            # the path changed: 'newer' was a copy
                            rev = self._previous_rev(newer[1], pool=subpool)
                            # restart before the copy op
                            yield newer[0], newer[1], Changeset.COPY
                            older = (older[0], older[1], 'unknown')
                            break
                    newer = older
                if older:
                    # either a real ADD or the source of a COPY
                    numrevs += 1
                    yield older
            else:
                expect_deletion = True
                rev = self._previous_rev(rev, pool=subpool)

    def get_changes(self, old_path, old_rev, new_path, new_rev,
                    ignore_ancestry=0):
        old_node = new_node = None
        old_rev = self.normalize_rev(old_rev)
        new_rev = self.normalize_rev(new_rev)
        if self.has_node(old_path, old_rev):
            old_node = self.get_node(old_path, old_rev)
        else:
            raise NoSuchNode(old_path, old_rev, 'The Base for Diff is invalid')
        if self.has_node(new_path, new_rev):
            new_node = self.get_node(new_path, new_rev)
        else:
            raise NoSuchNode(new_path, new_rev,
                             'The Target for Diff is invalid')
        if new_node.kind != old_node.kind:
            raise TracError(_('Diff mismatch: Base is a %(oldnode)s '
                              '(%(oldpath)s in revision %(oldrev)s) and '
                              'Target is a %(newnode)s (%(newpath)s in '
                              'revision %(newrev)s).', oldnode=old_node.kind,
                              oldpath=old_path, oldrev=old_rev,
                              newnode=new_node.kind, newpath=new_path,
                              newrev=new_rev))
        subpool = Pool(self.pool)
        if new_node.isdir:
            editor = DiffChangeEditor()
            e_ptr, e_baton = delta.make_editor(editor, subpool())
            old_root = fs.revision_root(self.fs_ptr, old_rev, subpool())
            new_root = fs.revision_root(self.fs_ptr, new_rev, subpool())
            def authz_cb(root, path, pool):
                return 1
            text_deltas = 0 # as this is anyway re-done in Diff.py...
            entry_props = 0 # "... typically used only for working copy updates"
            repos.svn_repos_dir_delta(old_root,
                                      _to_svn(subpool(), self.scope, old_path),
                                      '', new_root,
                                      _to_svn(subpool(), self.scope, new_path),
                                      e_ptr, e_baton, authz_cb,
                                      text_deltas,
                                      1, # directory
                                      entry_props,
                                      ignore_ancestry,
                                      subpool())
            for path, kind, change in editor.deltas:
                path = _from_svn(path)
                old_node = new_node = None
                if change != Changeset.ADD:
                    old_node = self.get_node(posixpath.join(old_path, path),
                                             old_rev)
                if change != Changeset.DELETE:
                    new_node = self.get_node(posixpath.join(new_path, path),
                                             new_rev)
                else:
                    kind = _kindmap[fs.check_path(old_root,
                                                  _to_svn(subpool(),
                                                          self.scope,
                                                          old_node.path),
                                                  subpool())]
                yield  (old_node, new_node, kind, change)
        else:
            old_root = fs.revision_root(self.fs_ptr, old_rev, subpool())
            new_root = fs.revision_root(self.fs_ptr, new_rev, subpool())
            if fs.contents_changed(old_root,
                                   _to_svn(subpool(), self.scope, old_path),
                                   new_root,
                                   _to_svn(subpool(), self.scope, new_path),
                                   subpool()):
                yield (old_node, new_node, Node.FILE, Changeset.EDIT)


class SubversionNode(Node):

    def __init__(self, path, rev, repos, pool=None, parent_root=None):
        self.fs_ptr = repos.fs_ptr
        self.scope = repos.scope
        self.pool = Pool(pool)
        pool = self.pool()
        self._scoped_path_utf8 = _to_svn(pool, self.scope, path)

        if parent_root:
            self.root = parent_root
        else:
            self.root = fs.revision_root(self.fs_ptr, rev, pool)
        node_type = fs.check_path(self.root, self._scoped_path_utf8, pool)
        if not node_type in _kindmap:
            raise NoSuchNode(path, rev)
        cp_utf8 = fs.node_created_path(self.root, self._scoped_path_utf8, pool)
        cp = _from_svn(cp_utf8)
        cr = fs.node_created_rev(self.root, self._scoped_path_utf8, pool)
        # Note: `cp` differs from `path` if the last change was a copy,
        #        In that case, `path` doesn't even exist at `cr`.
        #        The only guarantees are:
        #          * this node exists at (path,rev)
        #          * the node existed at (created_path,created_rev)
        # Also, `cp` might well be out of the scope of the repository,
        # in this case, we _don't_ use the ''create'' information.
        if _is_path_within_scope(self.scope, cp):
            self.created_rev = cr
            self.created_path = _path_within_scope(self.scope, cp)
        else:
            self.created_rev, self.created_path = rev, path
        # TODO: check node id
        Node.__init__(self, repos, path, rev, _kindmap[node_type])

    def get_content(self):
        if self.isdir:
            return None
        s = core.Stream(fs.file_contents(self.root, self._scoped_path_utf8,
                                         self.pool()))
        # Make sure the stream object references the pool to make sure the pool
        # is not destroyed before the stream object.
        s._pool = self.pool
        return s

    def get_entries(self):
        if self.isfile:
            return
        pool = Pool(self.pool)
        entries = fs.dir_entries(self.root, self._scoped_path_utf8, pool())
        for item in entries.keys():
            path = posixpath.join(self.path, _from_svn(item))
            yield SubversionNode(path, self.rev, self.repos, self.pool,
                                 self.root)

    def get_history(self, limit=None):
        newer = None # 'newer' is the previously seen history tuple
        older = None # 'older' is the currently examined history tuple
        pool = Pool(self.pool)
        numrevs = 0
        for path, rev in self.repos._history(self.path, 1, self.rev, pool):
            path = _path_within_scope(self.scope, path)
            if rev > 0 and path:
                older = (path, rev, Changeset.ADD)
                if newer:
                    if newer[0] == older[0]: # stay on same path
                        change = Changeset.EDIT
                    else:
                        change = Changeset.COPY
                    newer = (newer[0], newer[1], change)
                    numrevs += 1
                    yield newer
                newer = older
            if limit and numrevs >= limit:
                break
        if newer and (not limit or numrevs < limit):
            yield newer

    def get_annotations(self):
        annotations = []
        if self.isfile:
            def blame_receiver(line_no, revision, author, date, line, pool):
                annotations.append(revision)
            try:
                rev = _svn_rev(self.rev)
                start = _svn_rev(0)
                file_url_utf8 = posixpath.join(self.repos.ra_url_utf8,
                                               self._scoped_path_utf8)
                self.repos.log.info('opening ra_local session to %r',
                                    file_url_utf8)
                from svn import client
                client.blame2(file_url_utf8, rev, start, rev, blame_receiver,
                              client.create_context(), self.pool())
            except (core.SubversionException, AttributeError), e:
                # svn thinks file is a binary or blame not supported
                raise TracError(_('svn blame failed on %(path)s: %(error)s',
                                  path=self.path, error=to_unicode(e)))
        return annotations

#    def get_previous(self):
#        # FIXME: redo it with fs.node_history

    def get_properties(self):
        props = fs.node_proplist(self.root, self._scoped_path_utf8, self.pool())
        for name, value in props.items():
            # Note that property values can be arbitrary binary values
            # so we can't assume they are UTF-8 strings...
            props[_from_svn(name)] = to_unicode(value)
        return props

    def get_content_length(self):
        if self.isdir:
            return None
        return fs.file_length(self.root, self._scoped_path_utf8, self.pool())

    def get_content_type(self):
        if self.isdir:
            return None
        return self._get_prop(core.SVN_PROP_MIME_TYPE)

    def get_last_modified(self):
        _date = fs.revision_prop(self.fs_ptr, self.created_rev,
                                 core.SVN_PROP_REVISION_DATE, self.pool())
        if not _date:
            return None
        return from_utimestamp(core.svn_time_from_cstring(_date, self.pool()))

    def _get_prop(self, name):
        return fs.node_prop(self.root, self._scoped_path_utf8, name,
                            self.pool())

    def get_branch_origin(self):
        """Return the revision in which the node's path was created"""
        root_and_path = fs.closest_copy(self.root, self._scoped_path_utf8)
        if root_and_path:
            return fs.revision_root_revision(root_and_path[0])

    def get_copy_ancestry(self):
        """Retrieve the list of `(path,rev)` copy ancestors of this node.
        Most recent ancestor first. Each ancestor `(path, rev)` corresponds 
        to the path and revision of the source at the time the copy or move
        operation was performed.
        """
        ancestors = []
        previous = (self._scoped_path_utf8, self.rev, self.root)
        while previous:
            (previous_path, previous_rev, previous_root) = previous
            previous = None
            root_path = fs.closest_copy(previous_root, previous_path)
            if root_path:
                (root, path) = root_path
                path = path.lstrip('/')
                rev = fs.revision_root_revision(root)
                relpath = None
                if path != previous_path:
                    # `previous_path` is a subfolder of `path` and didn't
                    # change since `path` was copied
                    relpath = previous_path[len(path):].strip('/')
                copied_from = fs.copied_from(root, path)
                if copied_from:
                    (rev, path) = copied_from
                    path = path.lstrip('/')
                    root = fs.revision_root(self.fs_ptr, rev, self.pool())
                    if relpath:
                        path += '/' + relpath
                    ui_path = _path_within_scope(self.scope, _from_svn(path))
                    if ui_path:
                        ancestors.append((ui_path, rev))
                    previous = (path, rev, root)
        return ancestors


class SubversionChangeset(Changeset):

    def __init__(self, repos, rev, scope, pool=None):
        self.rev = rev
        self.scope = scope
        self.fs_ptr = repos.fs_ptr
        self.pool = Pool(pool)
        try:
            message = self._get_prop(core.SVN_PROP_REVISION_LOG)
        except core.SubversionException:
            raise NoSuchChangeset(rev)
        author = self._get_prop(core.SVN_PROP_REVISION_AUTHOR)
        # we _hope_ it's UTF-8, but can't be 100% sure (#4321)
        message = message and to_unicode(message, 'utf-8')
        author = author and to_unicode(author, 'utf-8')
        _date = self._get_prop(core.SVN_PROP_REVISION_DATE)
        if _date:
            ts = core.svn_time_from_cstring(_date, self.pool())
            date = from_utimestamp(ts)
        else:
            date = None
        Changeset.__init__(self, repos, rev, message, author, date)

    def get_properties(self):
        props = fs.revision_proplist(self.fs_ptr, self.rev, self.pool())
        properties = {}
        for k, v in props.iteritems():
            if k not in (core.SVN_PROP_REVISION_LOG,
                         core.SVN_PROP_REVISION_AUTHOR,
                         core.SVN_PROP_REVISION_DATE):
                properties[k] = to_unicode(v)
                # Note: the above `to_unicode` has a small probability
                # to mess-up binary properties, like icons.
        return properties

    def get_changes(self):
        pool = Pool(self.pool)
        tmp = Pool(pool)
        root = fs.revision_root(self.fs_ptr, self.rev, pool())
        editor = repos.RevisionChangeCollector(self.fs_ptr, self.rev, pool())
        e_ptr, e_baton = delta.make_editor(editor, pool())
        repos.svn_repos_replay(root, e_ptr, e_baton, pool())

        idx = 0
        copies, deletions = {}, {}
        changes = []
        revroots = {}
        for path_utf8, change in editor.changes.items():
            new_path = _from_svn(path_utf8)

            # Filtering on `path`
            if not _is_path_within_scope(self.scope, new_path):
                continue

            path_utf8 = change.path
            base_path_utf8 = change.base_path
            path = _from_svn(path_utf8)
            base_path = _from_svn(base_path_utf8)
            base_rev = change.base_rev
            change_action = getattr(change, 'action', None)

            # Ensure `base_path` is within the scope
            if not _is_path_within_scope(self.scope, base_path):
                base_path, base_rev = None, -1

            # Determine the action
            if not path and not new_path and self.scope == '/':
                action = Changeset.EDIT # root property change
            elif not path or (change_action is not None
                              and change_action == repos.CHANGE_ACTION_DELETE):
                if new_path:            # deletion
                    action = Changeset.DELETE
                    deletions[new_path.lstrip('/')] = idx
                else:                   # deletion outside of scope, ignore
                    continue
            elif change.added or not base_path: # add or copy
                action = Changeset.ADD
                if base_path and base_rev:
                    action = Changeset.COPY
                    copies[base_path.lstrip('/')] = idx
            else:
                action = Changeset.EDIT
                # identify the most interesting base_path/base_rev
                # in terms of last changed information (see r2562)
                if revroots.has_key(base_rev):
                    b_root = revroots[base_rev]
                else:
                    b_root = fs.revision_root(self.fs_ptr, base_rev, pool())
                    revroots[base_rev] = b_root
                tmp.clear()
                cbase_path_utf8 = fs.node_created_path(b_root, base_path_utf8,
                                                       tmp())
                cbase_path = _from_svn(cbase_path_utf8)
                cbase_rev = fs.node_created_rev(b_root, base_path_utf8, tmp()) 
                # give up if the created path is outside the scope
                if _is_path_within_scope(self.scope, cbase_path):
                    base_path, base_rev = cbase_path, cbase_rev

            kind = _kindmap[change.item_kind]
            path = _path_within_scope(self.scope, new_path or base_path)
            base_path = _path_within_scope(self.scope, base_path)
            changes.append([path, kind, action, base_path, base_rev])
            idx += 1

        moves = []
        # a MOVE is a COPY whose `base_path` corresponds to a `new_path`
        # which has been deleted
        for k, v in copies.items():
            if k in deletions:
                changes[v][2] = Changeset.MOVE
                moves.append(deletions[k])
        offset = 0
        moves.sort()
        for i in moves:
            del changes[i - offset]
            offset += 1

        changes.sort()
        for change in changes:
            yield tuple(change)

    def _get_prop(self, name):
        return fs.revision_prop(self.fs_ptr, self.rev, name, self.pool())


#
# Delta editor for diffs between arbitrary nodes
#
# Note 1: the 'copyfrom_path' and 'copyfrom_rev' information is not used
#         because 'repos.svn_repos_dir_delta' *doesn't* provide it.
#
# Note 2: the 'dir_baton' is the path of the parent directory
#


def DiffChangeEditor():

    class DiffChangeEditor(delta.Editor): 

        def __init__(self):
            self.deltas = []
    
        # -- svn.delta.Editor callbacks

        def open_root(self, base_revision, dir_pool):
            return ('/', Changeset.EDIT)

        def add_directory(self, path, dir_baton, copyfrom_path, copyfrom_rev,
                          dir_pool):
            self.deltas.append((path, Node.DIRECTORY, Changeset.ADD))
            return (path, Changeset.ADD)

        def open_directory(self, path, dir_baton, base_revision, dir_pool):
            return (path, dir_baton[1])

        def change_dir_prop(self, dir_baton, name, value, pool):
            path, change = dir_baton
            if change != Changeset.ADD:
                self.deltas.append((path, Node.DIRECTORY, change))

        def delete_entry(self, path, revision, dir_baton, pool):
            self.deltas.append((path, None, Changeset.DELETE))

        def add_file(self, path, dir_baton, copyfrom_path, copyfrom_revision,
                     dir_pool):
            self.deltas.append((path, Node.FILE, Changeset.ADD))

        def open_file(self, path, dir_baton, dummy_rev, file_pool):
            self.deltas.append((path, Node.FILE, Changeset.EDIT))

    return DiffChangeEditor() 

