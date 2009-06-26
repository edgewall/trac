# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2009 Edgewall Software
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
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

from datetime import datetime
import os
import posixpath

from trac.core import TracError
from trac.util.datefmt import utc, to_timestamp
from trac.util.translation import _
from trac.versioncontrol import Changeset, Node, Repository, Authorizer, \
                                NoSuchChangeset


_kindmap = {'D': Node.DIRECTORY, 'F': Node.FILE}
_actionmap = {'A': Changeset.ADD, 'C': Changeset.COPY,
              'D': Changeset.DELETE, 'E': Changeset.EDIT,
              'M': Changeset.MOVE}

CACHE_REPOSITORY_DIR = 'repository_dir'
CACHE_YOUNGEST_REV = 'youngest_rev'

CACHE_METADATA_KEYS = (CACHE_REPOSITORY_DIR, CACHE_YOUNGEST_REV)


class CachedRepository(Repository):

    has_linear_changesets = False

    def __init__(self, getdb, repos, authz, log):
        Repository.__init__(self, repos.name, authz, log)
        if callable(getdb):
            self.getdb = getdb
        else:
            self.getdb = lambda: getdb
        self.repos = repos

    def close(self):
        self.repos.close()

    def get_quickjump_entries(self, rev):
        for category, name, path, rev in self.repos.get_quickjump_entries(rev):
            yield category, name, path, rev

    def get_changeset(self, rev):
        return CachedChangeset(self.repos, self.repos.normalize_rev(rev),
                               self.getdb, self.authz)

    def get_changesets(self, start, stop):
        db = self.getdb()
        cursor = db.cursor()
        cursor.execute("SELECT rev FROM revision "
                       "WHERE time >= %s AND time < %s "
                       "ORDER BY time DESC, rev DESC",
                       (to_timestamp(start), to_timestamp(stop)))
        for rev, in cursor:
            try:
                if self.authz.has_permission_for_changeset(rev):
                    yield self.get_changeset(rev)
            except NoSuchChangeset:
                pass # skip changesets currently being resync'ed

    def sync_changeset(self, rev):
        cset = self.repos.get_changeset(rev)
        db = self.getdb()
        cursor = db.cursor()
        cursor.execute("UPDATE revision SET time=%s, author=%s, message=%s "
                       "WHERE rev=%s", (to_timestamp(cset.date),
                                        cset.author, cset.message,
                                        (str(cset.rev))))
        db.commit()
        
    def sync(self, feedback=None):
        db = self.getdb()
        cursor = db.cursor()
        cursor.execute("SELECT name, value FROM system WHERE name IN (%s)" %
                       ','.join(["'%s'" % key for key in CACHE_METADATA_KEYS]))
        metadata = {}
        for name, value in cursor:
            metadata[name] = value
        
        # -- check that we're populating the cache for the correct repository
        repository_dir = metadata.get(CACHE_REPOSITORY_DIR)
        if repository_dir:
            # directory part of the repo name can vary on case insensitive fs
            if os.path.normcase(repository_dir) != os.path.normcase(self.name):
                self.log.info("'repository_dir' has changed from %r to %r"
                              % (repository_dir, self.name))
                raise TracError(_("The 'repository_dir' has changed, a "
                                  "'trac-admin resync' operation is needed."))
        elif repository_dir is None: # 
            self.log.info('Storing initial "repository_dir": %s' % self.name)
            cursor.execute("INSERT INTO system (name,value) VALUES (%s,%s)",
                           (CACHE_REPOSITORY_DIR, self.name,))
        else: # 'repository_dir' cleared by a resync
            self.log.info('Resetting "repository_dir": %s' % self.name)
            cursor.execute("UPDATE system SET value=%s WHERE name=%s",
                           (self.name, CACHE_REPOSITORY_DIR))

        db.commit() # save metadata changes made up to now

        # -- retrieve the youngest revision in the repository
        self.repos.clear()
        repos_youngest = self.repos.youngest_rev

        # -- retrieve the youngest revision cached so far
        if CACHE_YOUNGEST_REV not in metadata:
            raise TracError(_('Missing "youngest_rev" in cache metadata'))
        
        self.youngest = metadata[CACHE_YOUNGEST_REV]

        if self.youngest:
            self.youngest = self.repos.normalize_rev(self.youngest)
            if not self.youngest:
                self.log.debug('normalize_rev failed (youngest_rev=%r)' %
                               self.youngest_rev)
        else:
            self.log.debug('cache metadata undefined (youngest_rev=%r)' %
                           self.youngest_rev)
            self.youngest = None

        # -- compare them and try to resync if different
        if self.youngest != repos_youngest:
            self.log.info("repos rev [%s] != cached rev [%s]" %
                          (repos_youngest, self.youngest))
            if self.youngest:
                next_youngest = self.repos.next_rev(self.youngest)
            else:
                next_youngest = None
                try:
                    next_youngest = self.repos.oldest_rev
                    # Ugly hack needed because doing that everytime in 
                    # oldest_rev suffers from horrendeous performance (#5213)
                    if hasattr(self.repos, 'scope'):
                        if self.repos.scope != '/':
                            next_youngest = self.repos.next_rev(next_youngest, 
                                    find_initial_rev=True)
                    next_youngest = self.repos.normalize_rev(next_youngest)
                except TracError:
                    return # can't normalize oldest_rev: repository was empty

            if next_youngest is None: # nothing to cache yet
                return

            # 0. first check if there's no (obvious) resync in progress
            cursor.execute("SELECT rev FROM revision WHERE rev=%s",
                           (str(next_youngest),))
            for rev, in cursor:
                # already there, but in progress, so keep ''previous''
                # notion of 'youngest'
                self.repos.clear(youngest_rev=self.youngest)
                return

            # 1. prepare for resyncing
            #    (there still might be a race condition at this point)

            authz = self.repos.authz
            self.repos.authz = Authorizer() # remove permission checking

            kindmap = dict(zip(_kindmap.values(), _kindmap.keys()))
            actionmap = dict(zip(_actionmap.values(), _actionmap.keys()))

            try:
                while next_youngest is not None:
                    
                    # 1.1 Attempt to resync the 'revision' table
                    self.log.info("Trying to sync revision [%s]" %
                                  next_youngest)
                    cset = self.repos.get_changeset(next_youngest)
                    try:
                        cursor.execute("INSERT INTO revision "
                                       " (rev,time,author,message) "
                                       "VALUES (%s,%s,%s,%s)",
                                       (str(next_youngest),
                                        to_timestamp(cset.date),
                                        cset.author, cset.message))
                    except Exception, e: # *another* 1.1. resync attempt won 
                        self.log.warning('Revision %s already cached: %s' %
                                         (next_youngest, e))
                        # also potentially in progress, so keep ''previous''
                        # notion of 'youngest'
                        self.repos.clear(youngest_rev=self.youngest)
                        db.rollback()
                        return

                    # 1.2. now *only* one process was able to get there
                    #      (i.e. there *shouldn't* be any race condition here)

                    for path,kind,action,bpath,brev in cset.get_changes():
                        self.log.debug("Caching node change in [%s]: %s"
                                       % (next_youngest,
                                          (path,kind,action,bpath,brev)))
                        kind = kindmap[kind]
                        action = actionmap[action]
                        cursor.execute("INSERT INTO node_change "
                                       " (rev,path,node_type,change_type, "
                                       "  base_path,base_rev) "
                                       "VALUES (%s,%s,%s,%s,%s,%s)",
                                       (str(next_youngest),
                                        path, kind, action, bpath, brev))

                    # 1.3. iterate (1.1 should always succeed now)
                    self.youngest = next_youngest                    
                    next_youngest = self.repos.next_rev(next_youngest)

                    # 1.4. update 'youngest_rev' metadata 
                    #      (minimize possibility of failures at point 0.)
                    cursor.execute("UPDATE system SET value=%s WHERE name=%s",
                                   (str(self.youngest), CACHE_YOUNGEST_REV))
                    db.commit()

                    # 1.5. provide some feedback
                    if feedback:
                        feedback(self.youngest)
            finally:
                # 3. restore permission checking (after 1.)
                self.repos.authz = authz

    def get_node(self, path, rev=None):
        return self.repos.get_node(path, rev)

    def _get_node_revs(self, path, last=None, first=None):
        """Return the revisions affecting `path` between `first` and `last`
        revisions.
        """
        last = self.normalize_rev(last)
        node = self.get_node(path, last)    # Check node existence and perms
        db = self.getdb()
        cursor = db.cursor()
        rev_as_int = db.cast('rev', 'int')
        if first is None:
            cursor.execute("SELECT rev FROM node_change "
                           "WHERE path = %%s "
                           "  AND change_type IN ('A', 'C', 'M') "
                           "  AND %s <= %%s "
                           "ORDER BY %s DESC "
                           "LIMIT 1" % ((rev_as_int,) * 2),
                           (path, last))
            first = 0
            for row in cursor:
                first = int(row[0])
        cursor.execute("SELECT DISTINCT rev FROM node_change "
                       "WHERE (path = %%s OR path %s) "
                       " AND %s >= %%s AND %s <= %%s" % 
                       (db.like(), rev_as_int, rev_as_int),
                       (path, db.like_escape(path + '/') + '%', first, last))
        return [int(row[0]) for row in cursor]

    def has_node(self, path, rev=None):
        return self.repos.has_node(path, rev)

    def get_oldest_rev(self):
        return self.repos.oldest_rev

    def get_youngest_rev(self):
        if not hasattr(self, 'youngest'):
            self.sync()
        return self.youngest

    def previous_rev(self, rev, path=''):
        if self.has_linear_changesets:
            return self._next_prev_rev('<', rev, path)
        else:
            return self.repos.previous_rev(rev, path)

    def next_rev(self, rev, path=''):
        if self.has_linear_changesets:
            return self._next_prev_rev('>', rev, path)
        else:
            return self.repos.next_rev(rev, path)

    def _next_prev_rev(self, direction, rev, path=''):
        db = self.getdb()
        # the changeset revs are sequence of ints:
        sql = "SELECT rev FROM node_change WHERE " + \
              db.cast('rev', 'int') + " " + direction + " %s"
        args = [rev]

        if path:
            path = path.lstrip('/')
            sql += " AND ("
            # changes on path itself
            sql += "path=%s "
            args.append(path)
            sql += " OR "
            # changes on path children
            sql += "path "+db.like()
            args.append(db.like_escape(path+'/') + '%')
            sql += " OR "
            # deletion of path ancestors
            components = path.lstrip('/').split('/')
            for i in range(1, len(components)+1):
                args.append('/'.join(components[:i]))
            parent_insert = ','.join(('%s',) * len(components))
            sql += " (path in (" + parent_insert + ") and change_type='D')"
            sql += ")"

        sql += " ORDER BY " + db.cast('rev', 'int') + \
                (direction == '<' and " DESC" or "") + " LIMIT 1"
        
        cursor = db.cursor()
        cursor.execute(sql, args)
        for rev, in cursor:
            return rev

    def rev_older_than(self, rev1, rev2):
        return self.repos.rev_older_than(rev1, rev2)

    def get_path_history(self, path, rev=None, limit=None):
        return self.repos.get_path_history(path, rev, limit)

    def normalize_path(self, path):
        return self.repos.normalize_path(path)

    def normalize_rev(self, rev):
        return self.repos.normalize_rev(rev)

    def get_changes(self, old_path, old_rev, new_path, new_rev, 
            ignore_ancestry=1):
        return self.repos.get_changes(old_path, old_rev, new_path, new_rev, 
                ignore_ancestry)


class CachedChangeset(Changeset):

    def __init__(self, repos, rev, getdb, authz):
        self.repos = repos
        self.getdb = getdb
        self.authz = authz
        db = self.getdb()
        cursor = db.cursor()
        cursor.execute("SELECT time,author,message FROM revision "
                       "WHERE rev=%s", (str(rev),))
        row = cursor.fetchone()
        if row:
            _date, author, message = row
            date = datetime.fromtimestamp(_date, utc)
            Changeset.__init__(self, rev, message, author, date)
        else:
            raise NoSuchChangeset(rev)
        self.scope = getattr(repos, 'scope', '')

    def get_changes(self):
        db = self.getdb()
        cursor = db.cursor()
        cursor.execute("SELECT path,node_type,change_type,base_path,base_rev "
                       "FROM node_change WHERE rev=%s "
                       "ORDER BY path", (str(self.rev),))
        for path, kind, change, base_path, base_rev in cursor:
            if not self.authz.has_permission(posixpath.join(self.scope,
                                                            path.strip('/'))):
                # FIXME: what about the base_path?
                continue
            kind = _kindmap[kind]
            change = _actionmap[change]
            yield path, kind, change, base_path, base_rev

    def get_properties(self):
        return self.repos.get_changeset(self.rev).get_properties()
