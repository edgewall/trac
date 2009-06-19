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

import bisect
from datetime import datetime
import os
import posixpath

from trac.cache import CacheProxy
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

    def __init__(self, env, repos, authz, log):
        self.env = env
        self.repos = repos
        self.metadata = CacheProxy(self.__class__.__module__ + '.'
                                   + self.__class__.__name__ + '.metadata:'
                                   + self.repos.reponame, self._metadata,
                                   self.env)
        Repository.__init__(self, repos.name, authz, log)

    def _set_reponame(self, value):
        self.repos.reponame = value
        self.metadata.id = self.__class__.__module__ + '.' \
                           + self.__class__.__name__ + '.metadata:' \
                           + value
    
    reponame = property(fget=lambda self: self.repos.reponame,
                        fset=_set_reponame)
    
    def close(self):
        self.repos.close()

    def get_base(self):
        return self.repos.get_base()
        
    def get_quickjump_entries(self, rev):
        for category, name, path, rev in self.repos.get_quickjump_entries(rev):
            yield category, name, path, rev

    def get_changeset(self, rev):
        return CachedChangeset(self.repos, self.repos.normalize_rev(rev),
                               self.env, self.authz)

    def get_changesets(self, start, stop):
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT rev FROM revision "
                       "WHERE repos=%s AND time >= %s AND time < %s "
                       "ORDER BY time DESC, rev DESC",
                       (self.reponame, to_timestamp(start),
                        to_timestamp(stop)))
        for rev, in cursor:
            try:
                if self.authz.has_permission_for_changeset(rev):
                    yield self.get_changeset(rev)
            except NoSuchChangeset:
                pass # skip changesets currently being resync'ed

    def sync_changeset(self, rev):
        cset = self.repos.get_changeset(rev)
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT time,author,message FROM revision "
                       "WHERE repos=%s AND rev=%s",
                       (self.reponame, str(cset.rev)))
        old_changeset = None
        for time, author, message in cursor:
            date = datetime.fromtimestamp(time, utc)
            old_changeset = Changeset(cset.rev, message, author, date)
        
        cursor.execute("UPDATE revision SET time=%s, author=%s, message=%s "
                       "WHERE repos=%s AND rev=%s",
                       (to_timestamp(cset.date), cset.author, cset.message,
                        self.reponame, str(cset.rev)))
        db.commit()
        return old_changeset
        
    def _metadata(self, db):
        """Retrieve data for the cached `metadata` attribute."""
        cursor = db.cursor()
        cursor.execute("SELECT name, value FROM repository "
                       "WHERE id=%%s AND name IN (%s)" % 
                       ','.join(['%s'] * len(CACHE_METADATA_KEYS)),
                       (self.reponame,) + CACHE_METADATA_KEYS)
        return dict(cursor)

    def sync(self, feedback=None):
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        metadata = self.metadata.get(db)
        do_commit = False
        
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
            cursor.execute("INSERT INTO repository (id,name,value) "
                           "VALUES (%s,%s,%s)",
                           (self.reponame, CACHE_REPOSITORY_DIR, self.name))
            do_commit = True
        else: # 'repository_dir' cleared by a resync
            self.log.info('Resetting "repository_dir": %s' % self.name)
            cursor.execute("UPDATE repository SET value=%s "
                           "WHERE id=%s AND name=%s",
                           (self.name, self.reponame, CACHE_REPOSITORY_DIR))
            do_commit = True

        # -- retrieve the youngest revision in the repository
        self.repos.clear()
        repos_youngest = self.repos.youngest_rev

        # -- retrieve the youngest revision cached so far
        youngest = metadata.get(CACHE_YOUNGEST_REV)
        if youngest is None:
            cursor.execute("INSERT INTO repository (id,name,value) "
                           "VALUES (%s,%s,%s)",
                           (self.reponame, CACHE_YOUNGEST_REV, ''))
            do_commit = True

        if do_commit:
            self.metadata.invalidate(db)
            db.commit() # save metadata changes made up to now

        if youngest:
            youngest = self.repos.normalize_rev(youngest)
            if not youngest:
                self.log.debug('normalize_rev failed (youngest_rev=%r)' %
                               self.youngest_rev)
        else:
            self.log.debug('cache metadata undefined (youngest_rev=%r)' %
                           self.youngest_rev)
            youngest = None

        # -- compare them and try to resync if different
        if youngest != repos_youngest:
            self.log.info("repos rev [%s] != cached rev [%s]" %
                          (repos_youngest, youngest))
            if youngest:
                next_youngest = self.repos.next_rev(youngest)
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
                    # can't normalize oldest_rev: repository was empty
                    return

            if next_youngest is None: # nothing to cache yet
                return

            # 0. first check if there's no (obvious) resync in progress
            cursor.execute("SELECT rev FROM revision "
                           "WHERE repos=%s AND rev=%s",
                           (self.reponame, str(next_youngest)))
            for rev, in cursor:
                # already there, but in progress, so keep ''previous''
                # notion of 'youngest'
                self.repos.clear(youngest_rev=youngest)
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
                                       " (repos,rev,time,author,message) "
                                       "VALUES (%s,%s,%s,%s,%s)",
                                       (self.reponame, str(next_youngest),
                                        to_timestamp(cset.date),
                                        cset.author, cset.message))
                    except Exception, e: # *another* 1.1. resync attempt won 
                        self.log.warning('Revision %s already cached: %s' %
                                         (next_youngest, e))
                        # also potentially in progress, so keep ''previous''
                        # notion of 'youngest'
                        self.repos.clear(youngest_rev=youngest)
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
                                       " (repos,rev,path,node_type,"
                                       "  change_type,base_path,base_rev) "
                                       "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                                       (self.reponame, str(next_youngest),
                                        path, kind, action, bpath, brev))

                    # 1.3. iterate (1.1 should always succeed now)
                    youngest = next_youngest                    
                    next_youngest = self.repos.next_rev(next_youngest)

                    # 1.4. update 'youngest_rev' metadata 
                    #      (minimize possibility of failures at point 0.)
                    cursor.execute("UPDATE repository SET value=%s "
                                   "WHERE id=%s AND name=%s",
                                   (str(youngest), self.reponame,
                                    CACHE_YOUNGEST_REV))
                    self.metadata.invalidate(db)
                    db.commit()

                    # 1.5. provide some feedback
                    if feedback:
                        feedback(youngest)
            finally:
                # 3. restore permission checking (after 1.)
                self.repos.authz = authz

    def get_node(self, path, rev=None):
        return self.repos.get_node(path, rev)

    def _get_node_revs(self, path, rev=None):
        """Return the revisions affecting `path` between its creation and
        `rev`.
        """
        rev = self.normalize_rev(rev)
        node = self.get_node(path, rev)     # Check node existence and perms
        db = self.getdb()
        cursor = db.cursor()
        cursor.execute("SELECT DISTINCT rev FROM node_change "
                       "WHERE (path = %%s OR path %s) "
                       "  AND %s <= %%s" % (db.like(), db.cast('rev', 'int')),
                       (path, db.like_escape(path + '/') + '%', rev))
        revs = list(int(row[0]) for row in cursor)
        revs.sort()
        cursor.execute("SELECT rev FROM node_change "
                       "WHERE path = %%s "
                       "  AND change_type IN ('A', 'C', 'M') "
                       "  AND %s <= %%s "
                       "ORDER BY %s DESC "
                       "LIMIT 1" % ((db.cast('rev', 'int'),) * 2),
                       (path, rev))
        created = 0
        for row in cursor:
            created = int(row[0])
        return revs[bisect.bisect_left(revs, created):]

    def has_node(self, path, rev=None):
        return self.repos.has_node(path, rev)

    def get_oldest_rev(self):
        return self.repos.oldest_rev

    def get_youngest_rev(self):
        return self.metadata.get().get(CACHE_YOUNGEST_REV)

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
        db = self.env.get_db_cnx()
        # the changeset revs are sequence of ints:
        sql = "SELECT rev FROM node_change WHERE repos=%s AND " + \
              db.cast('rev', 'int') + " " + direction + " %s"
        args = [self.reponame, rev]

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

    def __init__(self, repos, rev, env, authz):
        self.repos = repos
        self.env = env
        self.authz = authz
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT time,author,message FROM revision "
                       "WHERE repos=%s AND rev=%s",
                       (self.repos.reponame, str(rev)))
        row = cursor.fetchone()
        if row:
            _date, author, message = row
            date = datetime.fromtimestamp(_date, utc)
            Changeset.__init__(self, rev, message, author, date)
        else:
            raise NoSuchChangeset(rev)
        self.scope = getattr(repos, 'scope', '')

    def get_changes(self):
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT path,node_type,change_type,base_path,base_rev "
                       "FROM node_change WHERE repos=%s AND rev=%s "
                       "ORDER BY path", (self.repos.reponame, str(self.rev)))
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
