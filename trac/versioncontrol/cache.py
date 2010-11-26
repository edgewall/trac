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

import os

from trac.cache import cached
from trac.core import TracError
from trac.util.datefmt import from_utimestamp, to_utimestamp
from trac.util.translation import _
from trac.versioncontrol import Changeset, Node, Repository, NoSuchChangeset


_kindmap = {'D': Node.DIRECTORY, 'F': Node.FILE}
_actionmap = {'A': Changeset.ADD, 'C': Changeset.COPY,
              'D': Changeset.DELETE, 'E': Changeset.EDIT,
              'M': Changeset.MOVE}

CACHE_REPOSITORY_DIR = 'repository_dir'
CACHE_YOUNGEST_REV = 'youngest_rev'

CACHE_METADATA_KEYS = (CACHE_REPOSITORY_DIR, CACHE_YOUNGEST_REV)


class CachedRepository(Repository):

    has_linear_changesets = False

    scope = property(lambda self: self.repos.scope)
    
    def __init__(self, env, repos, log):
        self.env = env
        self.repos = repos
        self._metadata_id = (CachedRepository.__module__ + '.'
                             + CachedRepository.__name__ + '.metadata:'
                             + str(self.repos.id))
        Repository.__init__(self, repos.name, repos.params, log)

    def close(self):
        self.repos.close()

    def get_base(self):
        return self.repos.get_base()
        
    def get_quickjump_entries(self, rev):
        return self.repos.get_quickjump_entries(self.normalize_rev(rev))

    def get_path_url(self, path, rev):
        return self.repos.get_path_url(path, rev)

    def get_changeset(self, rev):
        return CachedChangeset(self, self.normalize_rev(rev), self.env)

    def get_changeset_uid(self, rev):
        return self.repos.get_changeset_uid(rev)

    def get_changesets(self, start, stop):
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT rev FROM revision "
                       "WHERE repos=%s AND time >= %s AND time < %s "
                       "ORDER BY time DESC, rev DESC",
                       (self.id, to_utimestamp(start), to_utimestamp(stop)))
        for rev, in cursor:
            try:
                yield self.get_changeset(rev)
            except NoSuchChangeset:
                pass # skip changesets currently being resync'ed

    def sync_changeset(self, rev):
        cset = self.repos.get_changeset(rev)
        srev = self.db_rev(cset.rev)
        old_cset = [None]

        @self.env.with_transaction()
        def do_sync(db):
            cursor = db.cursor()
            cursor.execute("""
                SELECT time,author,message FROM revision
                WHERE repos=%s AND rev=%s
                """, (self.id, srev))
            for time, author, message in cursor:
                old_cset[0] = Changeset(self.repos, cset.rev, message, author,
                                        from_utimestamp(time))
            cursor.execute("""
                UPDATE revision SET time=%s, author=%s, message=%s
                WHERE repos=%s AND rev=%s
                """, (to_utimestamp(cset.date), cset.author, cset.message,
                      self.id, srev))
        return old_cset[0]

    @cached('_metadata_id')
    def metadata(self, db):
        """Retrieve data for the cached `metadata` attribute."""
        cursor = db.cursor()
        cursor.execute("SELECT name, value FROM repository "
                       "WHERE id=%%s AND name IN (%s)" % 
                       ','.join(['%s'] * len(CACHE_METADATA_KEYS)),
                       (self.id,) + CACHE_METADATA_KEYS)
        return dict(cursor)

    def sync(self, feedback=None, clean=False):
        if clean:
            self.log.info('Cleaning cache')
            @self.env.with_transaction()
            def do_clean(db):
                cursor = db.cursor()
                cursor.execute("DELETE FROM revision WHERE repos=%s",
                               (self.id,))
                cursor.execute("DELETE FROM node_change WHERE repos=%s",
                               (self.id,))
                cursor.executemany("""
                    DELETE FROM repository WHERE id=%s AND name=%s
                    """, [(self.id, k) for k in CACHE_METADATA_KEYS])
                cursor.executemany("""
                    INSERT INTO repository (id,name,value) VALUES (%s,%s,%s)
                    """, [(self.id, k, '') for k in CACHE_METADATA_KEYS])
                del self.metadata

        metadata = self.metadata
        
        @self.env.with_transaction()
        def do_transaction(db):
            cursor = db.cursor()
            invalidate = False
    
            # -- check that we're populating the cache for the correct
            #    repository
            repository_dir = metadata.get(CACHE_REPOSITORY_DIR)
            if repository_dir:
                # directory part of the repo name can vary on case insensitive
                # fs
                if os.path.normcase(repository_dir) \
                        != os.path.normcase(self.name):
                    self.log.info("'repository_dir' has changed from %r to %r",
                                  repository_dir, self.name)
                    raise TracError(_("The repository directory has changed, "
                                      "you should resynchronize the "
                                      "repository with: trac-admin $ENV "
                                      "repository resync '%(reponame)s'",
                                      reponame=self.reponame or '(default)'))
            elif repository_dir is None: # 
                self.log.info('Storing initial "repository_dir": %s',
                              self.name)
                cursor.execute("""
                    INSERT INTO repository (id,name,value) VALUES (%s,%s,%s)
                    """, (self.id, CACHE_REPOSITORY_DIR, self.name))
                invalidate = True
            else: # 'repository_dir' cleared by a resync
                self.log.info('Resetting "repository_dir": %s', self.name)
                cursor.execute("""
                    UPDATE repository SET value=%s WHERE id=%s AND name=%s
                    """, (self.name, self.id, CACHE_REPOSITORY_DIR))
                invalidate = True
    
            # -- insert a 'youngeset_rev' for the repository if necessary
            if metadata.get(CACHE_YOUNGEST_REV) is None:
                cursor.execute("""
                    INSERT INTO repository (id,name,value) VALUES (%s,%s,%s)
                    """, (self.id, CACHE_YOUNGEST_REV, ''))
                invalidate = True
    
            if invalidate:
                del self.metadata

        # -- retrieve the youngest revision in the repository and the youngest
        #    revision cached so far
        self.repos.clear()
        repos_youngest = self.repos.youngest_rev
        youngest = metadata.get(CACHE_YOUNGEST_REV)

        # -- verify and normalize youngest revision
        if youngest:
            youngest = self.repos.normalize_rev(youngest)
            if not youngest:
                self.log.debug('normalize_rev failed (youngest_rev=%r)',
                               self.youngest_rev)
        else:
            self.log.debug('cache metadata undefined (youngest_rev=%r)',
                           self.youngest_rev)
            youngest = None

        # -- compare them and try to resync if different
        next_youngest = None
        if youngest != repos_youngest:
            self.log.info("repos rev [%s] != cached rev [%s]",
                          repos_youngest, youngest)
            if youngest:
                next_youngest = self.repos.next_rev(youngest)
            else:
                try:
                    next_youngest = self.repos.oldest_rev
                    # Ugly hack needed because doing that everytime in 
                    # oldest_rev suffers from horrendeous performance (#5213)
                    if self.repos.scope != '/' and not \
                            self.repos.has_node('/', next_youngest):
                        next_youngest = self.repos.next_rev(next_youngest,
                                find_initial_rev=True)
                    next_youngest = self.repos.normalize_rev(next_youngest)
                except TracError:
                    # can't normalize oldest_rev: repository was empty
                    return

            if next_youngest is None: # nothing to cache yet
                return
            srev = self.db_rev(next_youngest)

            # 0. first check if there's no (obvious) resync in progress
            db = self.env.get_read_db()
            cursor = db.cursor()
            cursor.execute("""
               SELECT rev FROM revision WHERE repos=%s AND rev=%s
               """, (self.id, srev))
            for rev, in cursor:
                # already there, but in progress, so keep ''previous''
                # notion of 'youngest'
                self.repos.clear(youngest_rev=youngest)
                return

            # 1. prepare for resyncing
            #    (there still might be a race condition at this point)

            kindmap = dict(zip(_kindmap.values(), _kindmap.keys()))
            actionmap = dict(zip(_actionmap.values(), _actionmap.keys()))

            while next_youngest is not None:
                srev = self.db_rev(next_youngest)
                exit = [False]
                
                @self.env.with_transaction()
                def do_transaction(db):
                    cursor = db.cursor()
                    
                    # 1.1 Attempt to resync the 'revision' table
                    self.log.info("Trying to sync revision [%s]",
                                  next_youngest)
                    cset = self.repos.get_changeset(next_youngest)
                    try:
                        cursor.execute("""
                            INSERT INTO revision
                                (repos,rev,time,author,message)
                            VALUES (%s,%s,%s,%s,%s)
                            """, (self.id, srev, to_utimestamp(cset.date),
                                  cset.author, cset.message))
                    except Exception, e: # *another* 1.1. resync attempt won 
                        self.log.warning('Revision %s already cached: %r',
                                         next_youngest, e)
                        # also potentially in progress, so keep ''previous''
                        # notion of 'youngest'
                        self.repos.clear(youngest_rev=youngest)
                        # FIXME: This aborts a containing transaction
                        db.rollback()
                        exit[0] = True
                        return
    
                    # 1.2. now *only* one process was able to get there
                    #      (i.e. there *shouldn't* be any race condition here)
    
                    for path, kind, action, bpath, brev in cset.get_changes():
                        self.log.debug("Caching node change in [%s]: %r",
                                       next_youngest,
                                       (path, kind, action, bpath, brev))
                        kind = kindmap[kind]
                        action = actionmap[action]
                        cursor.execute("""
                            INSERT INTO node_change
                                (repos,rev,path,node_type,
                                 change_type,base_path,base_rev)
                            VALUES (%s,%s,%s,%s,%s,%s,%s)
                            """, (self.id, srev, path, kind, action, bpath,
                                  brev))
    
                    # 1.3. update 'youngest_rev' metadata 
                    #      (minimize possibility of failures at point 0.)
                    cursor.execute("""
                        UPDATE repository SET value=%s WHERE id=%s AND name=%s
                        """, (str(next_youngest), self.id, CACHE_YOUNGEST_REV))
                    del self.metadata

                if exit[0]:
                    return
                
                # 1.4. iterate (1.1 should always succeed now)
                youngest = next_youngest
                next_youngest = self.repos.next_rev(next_youngest)

                # 1.5. provide some feedback
                if feedback:
                    feedback(youngest)

    def get_node(self, path, rev=None):
        return self.repos.get_node(path, self.normalize_rev(rev))

    def _get_node_revs(self, path, last=None, first=None):
        """Return the revisions affecting `path` between `first` and `last`
        revisions.
        """
        last = self.normalize_rev(last)
        slast = self.db_rev(last)
        node = self.get_node(path, last)    # Check node existence
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        if first is None:
            cursor.execute("SELECT rev FROM node_change "
                           "WHERE repos=%s AND rev<=%s "
                           "  AND path=%s "
                           "  AND change_type IN ('A', 'C', 'M') "
                           "ORDER BY rev DESC LIMIT 1",
                           (self.id, slast, path))
            first = 0
            for row in cursor:
                first = int(row[0])
        sfirst = self.db_rev(first)
        cursor.execute("SELECT DISTINCT rev FROM node_change "
                       "WHERE repos=%%s AND rev>=%%s AND rev<=%%s "
                       " AND (path=%%s OR path %s)" % db.like(),
                       (self.id, sfirst, slast, path,
                        db.like_escape(path + '/') + '%'))
        return [int(row[0]) for row in cursor]

    def has_node(self, path, rev=None):
        return self.repos.has_node(path, self.normalize_rev(rev))

    def get_oldest_rev(self):
        return self.repos.oldest_rev

    def get_youngest_rev(self):
        return self.rev_db(self.metadata.get(CACHE_YOUNGEST_REV))

    def previous_rev(self, rev, path=''):
        if self.has_linear_changesets:
            return self._next_prev_rev('<', rev, path)
        else:
            return self.repos.previous_rev(self.normalize_rev(rev), path)

    def next_rev(self, rev, path=''):
        if self.has_linear_changesets:
            return self._next_prev_rev('>', rev, path)
        else:
            return self.repos.next_rev(self.normalize_rev(rev), path)

    def _next_prev_rev(self, direction, rev, path=''):
        srev = self.db_rev(rev)
        db = self.env.get_db_cnx()
        # the changeset revs are sequence of ints:
        sql = "SELECT rev FROM node_change WHERE repos=%s AND " + \
              "rev" + direction + "%s"
        args = [self.id, srev]

        if path:
            path = path.lstrip('/')
            # changes on path itself or its children
            sql += " AND (path=%s OR path " + db.like()
            args.extend((path, db.like_escape(path + '/') + '%'))
            # deletion of path ancestors
            components = path.lstrip('/').split('/')
            parents = ','.join(('%s',) * len(components))
            sql += " OR (path IN (" + parents + ") AND change_type='D'))"
            for i in range(1, len(components) + 1):
                args.append('/'.join(components[:i]))

        sql += " ORDER BY rev" + (direction == '<' and " DESC" or "") \
               + " LIMIT 1"
        
        cursor = db.cursor()
        cursor.execute(sql, args)
        for rev, in cursor:
            return int(rev)

    def rev_older_than(self, rev1, rev2):
        return self.repos.rev_older_than(self.normalize_rev(rev1),
                                         self.normalize_rev(rev2))

    def get_path_history(self, path, rev=None, limit=None):
        return self.repos.get_path_history(path, self.normalize_rev(rev),
                                           limit)

    def normalize_path(self, path):
        return self.repos.normalize_path(path)

    def normalize_rev(self, rev):
        if rev is None or isinstance(rev, basestring) and \
               rev.lower() in ('', 'head', 'latest', 'youngest'):
            return self.rev_db(self.youngest_rev or 0)
        else:
            try:
                rev = int(rev)
                if rev <= self.youngest_rev:
                    return rev
            except (ValueError, TypeError):
                pass
            raise NoSuchChangeset(rev)

    def db_rev(self, rev):
        """Convert a revision to its representation in the database."""
        return str(rev)

    def rev_db(self, rev):
        """Convert a revision from its representation in the database."""
        return rev

    def get_changes(self, old_path, old_rev, new_path, new_rev, 
                    ignore_ancestry=1):
        return self.repos.get_changes(old_path, self.normalize_rev(old_rev),
                                      new_path, self.normalize_rev(new_rev), 
                                      ignore_ancestry)


class CachedChangeset(Changeset):

    def __init__(self, repos, rev, env):
        self.env = env
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT time,author,message FROM revision "
                       "WHERE repos=%s AND rev=%s",
                       (repos.id, repos.db_rev(rev)))
        row = cursor.fetchone()
        if row:
            _date, author, message = row
            date = from_utimestamp(_date)
            Changeset.__init__(self, repos, repos.rev_db(rev), message, author,
                               date)
        else:
            raise NoSuchChangeset(rev)

    def get_changes(self):
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT path,node_type,change_type,base_path,base_rev "
                       "FROM node_change WHERE repos=%s AND rev=%s "
                       "ORDER BY path",
                       (self.repos.id, self.repos.db_rev(self.rev)))
        for path, kind, change, base_path, base_rev in sorted(cursor):
            kind = _kindmap[kind]
            change = _actionmap[change]
            yield path, kind, change, base_path, self.repos.rev_db(base_rev)

    def get_properties(self):
        return self.repos.repos.get_changeset(self.rev).get_properties()
