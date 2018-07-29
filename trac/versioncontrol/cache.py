# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2018 Edgewall Software
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

def _invert_dict(d):
    return dict(zip(d.values(), d.keys()))

_inverted_kindmap = _invert_dict(_kindmap)
_inverted_actionmap = _invert_dict(_actionmap)

CACHE_REPOSITORY_DIR = 'repository_dir'
CACHE_YOUNGEST_REV = 'youngest_rev'

CACHE_METADATA_KEYS = (CACHE_REPOSITORY_DIR, CACHE_YOUNGEST_REV)


def _norm_reponame(repos):
    return repos.reponame or '(default)'


class CachedRepository(Repository):

    has_linear_changesets = False

    scope = property(lambda self: self.repos.scope)

    def __init__(self, env, repos, log):
        self.env = env
        self.repos = repos
        self._metadata_id = str(self.repos.id)
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
        for rev, in self.env.db_query("""
                SELECT rev FROM revision
                WHERE repos=%s AND time >= %s AND time < %s
                ORDER BY time DESC, rev DESC
                """, (self.id, to_utimestamp(start), to_utimestamp(stop))):
            try:
                yield self.get_changeset(rev)
            except NoSuchChangeset:
                pass # skip changesets currently being resync'ed

    def sync_changeset(self, rev):
        cset = self.repos.get_changeset(rev)
        srev = self.db_rev(cset.rev)
        old_cset = None

        with self.env.db_transaction as db:
            try:
                old_cset = CachedChangeset(self, cset.rev, self.env)
            except NoSuchChangeset:
                old_cset = None
            if old_cset:
                db("""UPDATE revision SET time=%s, author=%s, message=%s
                      WHERE repos=%s AND rev=%s
                      """, (to_utimestamp(cset.date), cset.author,
                            cset.message, self.id, srev))
            else:
                self.insert_changeset(cset.rev, cset)
        return old_cset

    @cached('_metadata_id')
    def metadata(self):
        """Retrieve data for the cached `metadata` attribute."""
        return dict(self.env.db_query("""
                SELECT name, value FROM repository
                WHERE id=%%s AND name IN (%s)
                """ % ','.join(['%s'] * len(CACHE_METADATA_KEYS)),
                (self.id,) + CACHE_METADATA_KEYS))

    def sync(self, feedback=None, clean=False):
        if clean:
            self.remove_cache()

        metadata = self.metadata
        self.save_metadata(metadata)

        # -- retrieve the youngest revision in the repository and the youngest
        #    revision cached so far
        self.repos.clear()
        repos_youngest = self.repos.youngest_rev
        youngest = metadata.get(CACHE_YOUNGEST_REV)

        # -- verify and normalize youngest revision
        if youngest:
            youngest = self.repos.normalize_rev(youngest)
            if not youngest:
                self.log.debug("normalize_rev failed (youngest_rev=%r, "
                               "reponame=%s)",
                               self.youngest_rev, _norm_reponame(self))
        else:
            self.log.debug("cache metadata undefined (youngest_rev=%r, "
                           "reponame=%s)",
                           self.youngest_rev, _norm_reponame(self))
            youngest = None

        # -- compare them and try to resync if different
        next_youngest = None
        if youngest != repos_youngest:
            self.log.info("repos rev [%s] != cached rev [%s] in '%s'",
                          repos_youngest, youngest, _norm_reponame(self))
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
            with self.env.db_query as db:
                for rev, in db(
                        "SELECT rev FROM revision WHERE repos=%s AND rev=%s",
                        (self.id, srev)):
                    # already there, but in progress, so keep ''previous''
                    # notion of 'youngest'
                    self.repos.clear(youngest_rev=youngest)
                    return

            # prepare for resyncing (there might still be a race
            # condition at this point)
            while next_youngest is not None:
                srev = self.db_rev(next_youngest)

                with self.env.db_transaction as db:
                    self.log.info("Trying to sync revision [%s] in '%s'",
                                  next_youngest, _norm_reponame(self))
                    cset = self.repos.get_changeset(next_youngest)
                    try:
                        # steps 1. and 2.
                        self.insert_changeset(next_youngest, cset)
                    except Exception as e: # *another* 1.1. resync attempt won
                        if isinstance(e, self.env.db_exc.IntegrityError):
                            self.log.warning("Revision %s in '%s' already "
                                             "cached: %r", next_youngest,
                                             _norm_reponame(self), e)
                        else:
                            self.log.error("Unable to create cache records "
                                           "for revision %s in '%s': %r",
                                           next_youngest, _norm_reponame(self),
                                           e)
                        # the other resync attempts is also
                        # potentially still in progress, so for our
                        # process/thread, keep ''previous'' notion of
                        # 'youngest'
                        self.repos.clear(youngest_rev=youngest)
                        # FIXME: This aborts a containing transaction
                        db.rollback()
                        return

                    # 3. update 'youngest_rev' metadata (minimize
                    # possibility of failures at point 0.)
                    db("""
                        UPDATE repository SET value=%s WHERE id=%s AND name=%s
                        """, (str(next_youngest), self.id, CACHE_YOUNGEST_REV))
                    del self.metadata

                # 4. iterate (1. should always succeed now)
                youngest = next_youngest
                next_youngest = self.repos.next_rev(next_youngest)

                # 5. provide some feedback
                if feedback:
                    feedback(youngest)

    def remove_cache(self):
        """Remove the repository cache."""
        self.log.info("Cleaning cache in '%s'", _norm_reponame(self))
        with self.env.db_transaction as db:
            db("DELETE FROM revision WHERE repos=%s",
               (self.id,))
            db("DELETE FROM node_change WHERE repos=%s",
               (self.id,))
            db.executemany("DELETE FROM repository WHERE id=%s AND name=%s",
                           [(self.id, k) for k in CACHE_METADATA_KEYS])
            db.executemany("""
                  INSERT INTO repository (id, name, value)
                  VALUES (%s, %s, %s)
                  """, [(self.id, k, '') for k in CACHE_METADATA_KEYS])
            del self.metadata

    def save_metadata(self, metadata):
        """Save the repository metadata."""
        with self.env.db_transaction as db:
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
                                      reponame=_norm_reponame(self)))
            elif repository_dir is None: #
                self.log.info('Storing initial "repository_dir": %s',
                              self.name)
                db("""INSERT INTO repository (id, name, value)
                      VALUES (%s, %s, %s)
                      """, (self.id, CACHE_REPOSITORY_DIR, self.name))
                invalidate = True
            else: # 'repository_dir' cleared by a resync
                self.log.info('Resetting "repository_dir": %s', self.name)
                db("UPDATE repository SET value=%s WHERE id=%s AND name=%s",
                   (self.name, self.id, CACHE_REPOSITORY_DIR))
                invalidate = True

            # -- insert a 'youngeset_rev' for the repository if necessary
            if CACHE_YOUNGEST_REV not in metadata:
                db("""INSERT INTO repository (id, name, value)
                      VALUES (%s, %s, %s)
                      """, (self.id, CACHE_YOUNGEST_REV, ''))
                invalidate = True

            if invalidate:
                del self.metadata

    def insert_changeset(self, rev, cset):
        """Create revision and node_change records for the given changeset
        instance."""
        with self.env.db_transaction as db:
            self._insert_changeset(db, rev, cset)

    def _insert_changeset(self, db, rev, cset):
        """:deprecated: since 1.1.2, use `insert_changeset` instead. Will
                        be removed in 1.3.1.
        """
        srev = self.db_rev(rev)
        # 1. Attempt to resync the 'revision' table.  In case of
        # concurrent syncs, only such insert into the `revision` table
        # will succeed, the others will fail and raise an exception.
        db("""
            INSERT INTO revision (repos,rev,time,author,message)
            VALUES (%s,%s,%s,%s,%s)
            """, (self.id, srev, to_utimestamp(cset.date),
                  cset.author, cset.message))
        # 2. now *only* one process was able to get there (i.e. there
        # *shouldn't* be any race condition here)
        for path, kind, action, bpath, brev in cset.get_changes():
            self.log.debug("Caching node change in [%s] in '%s': %r",
                           rev, _norm_reponame(self.repos),
                           (path, kind, action, bpath, brev))
            kind = _inverted_kindmap[kind]
            action = _inverted_actionmap[action]
            db("""
                INSERT INTO node_change
                    (repos,rev,path,node_type,change_type,base_path,
                     base_rev)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                """, (self.id, srev, path, kind, action, bpath, brev))

    def get_node(self, path, rev=None):
        return self.repos.get_node(path, self.normalize_rev(rev))

    def _get_node_revs(self, path, last=None, first=None):
        """Return the revisions affecting `path` between `first` and `last`
        revisions.
        """
        last = self.normalize_rev(last)
        slast = self.db_rev(last)
        node = self.get_node(path, last)    # Check node existence
        with self.env.db_query as db:
            if first is None:
                first = db("""
                    SELECT MAX(rev) FROM node_change
                    WHERE repos=%s AND rev<=%s AND path=%s
                      AND change_type IN ('A', 'C', 'M')
                    """, (self.id, slast, path))
                first = int(first[0][0]) if first[0][0] is not None else 0
            sfirst = self.db_rev(first)
            return [int(rev) for rev, in db("""
                    SELECT DISTINCT rev FROM node_change
                    WHERE repos=%%s AND rev>=%%s AND rev<=%%s
                      AND (path=%%s OR path %s)""" % db.prefix_match(),
                    (self.id, sfirst, slast, path,
                     db.prefix_match_value(path + '/')))]

    def _get_changed_revs(self, node_infos):
        if not node_infos:
            return {}

        node_infos = [(node, self.normalize_rev(first)) for node, first
                                                        in node_infos]
        sfirst = self.db_rev(min(first for node, first in node_infos))
        slast = self.db_rev(max(node.rev for node, first in node_infos))
        path_infos = dict((node.path, (node, first)) for node, first
                                                     in node_infos)
        path_revs = dict((node.path, []) for node, first in node_infos)

        # Prevent "too many SQL variables" since max number of parameters is
        # 999 on SQLite. No limitation on PostgreSQL and MySQL.
        idx = 0
        delta = (999 - 3) // 5
        with self.env.db_query as db:
            prefix_match = db.prefix_match()
            while idx < len(node_infos):
                subset = node_infos[idx:idx + delta]
                idx += delta
                count = len(subset)

                holders = ','.join(('%s',) * count)
                query = """\
                    SELECT DISTINCT
                      rev, (CASE WHEN path IN (%s) THEN path %s END) AS path
                    FROM node_change
                    WHERE repos=%%s AND rev>=%%s AND rev<=%%s
                      AND (path IN (%s) %s)
                    """ % \
                    (holders,
                     ' '.join(('WHEN path ' + prefix_match + ' THEN %s',)
                              * count),
                     holders,
                     ' '.join(('OR path ' + prefix_match,)
                              * count))
                args = []
                args.extend(node.path for node, first in subset)
                for node, first in subset:
                    args.append(db.prefix_match_value(node.path + '/'))
                    args.append(node.path)
                args.extend((self.id, sfirst, slast))
                args.extend(node.path for node, first in subset)
                args.extend(db.prefix_match_value(node.path + '/')
                            for node, first in subset)

                for srev, path in db(query, args):
                    rev = self.rev_db(srev)
                    node, first = path_infos[path]
                    if first <= rev <= node.rev:
                        path_revs[path].append(rev)

        return path_revs

    def has_node(self, path, rev=None):
        return self.repos.has_node(path, self.normalize_rev(rev))

    def get_oldest_rev(self):
        return self.repos.oldest_rev

    def get_youngest_rev(self):
        return self.rev_db(self.metadata.get(CACHE_YOUNGEST_REV))

    def previous_rev(self, rev, path=''):
        # Hitting the repository directly is faster than searching the
        # database.  When there is a long stretch of inactivity on a file (in
        # particular, when a file is added late in the history) the database
        # query can take a very long time to determine that there is no
        # previous revision in the node_changes table.  However, the repository
        # will have a datastructure that will allow it to find the previous
        # version of a node fairly directly.
        #if self.has_linear_changesets:
        #    return self._next_prev_rev('<', rev, path)
        return self.repos.previous_rev(self.normalize_rev(rev), path)

    def next_rev(self, rev, path=''):
        if self.has_linear_changesets:
            return self._next_prev_rev('>', rev, path)
        else:
            return self.repos.next_rev(self.normalize_rev(rev), path)

    def _next_prev_rev(self, direction, rev, path=''):
        srev = self.db_rev(rev)
        with self.env.db_query as db:
            # the changeset revs are sequence of ints:
            sql = "SELECT %(aggr)s(rev) FROM %(tab)s " \
                  "WHERE repos=%%s AND rev%(dir)s%%s"
            aggr = 'MAX' if direction == '<' else 'MIN'
            args = [self.id, srev]

            if path:
                path = path.lstrip('/')
                sql %= {'aggr': aggr, 'dir': direction, 'tab': 'node_change'}
                # changes on path itself or its children
                sql += " AND (path=%s OR path " + db.prefix_match()
                args.extend((path, db.prefix_match_value(path + '/')))
                # deletion of path ancestors
                components = path.lstrip('/').split('/')
                parents = ','.join(('%s',) * len(components))
                sql += " OR (path IN (" + parents + ") AND change_type='D'))"
                for i in range(1, len(components) + 1):
                    args.append('/'.join(components[:i]))
            else:
                sql %= {'aggr': aggr, 'dir': direction, 'tab': 'revision'}

            for rev, in db(sql, args):
                if rev is not None:
                    return int(rev)

    def parent_revs(self, rev):
        if self.has_linear_changesets:
            return Repository.parent_revs(self, rev)
        else:
            return self.repos.parent_revs(rev)

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
        drev = repos.db_rev(rev)
        for _date, author, message in self.env.db_query("""
                SELECT time, author, message FROM revision
                WHERE repos=%s AND rev=%s
                """, (repos.id, drev)):
            date = from_utimestamp(_date)
            Changeset.__init__(self, repos, repos.rev_db(rev), message, author,
                               date)
            break
        else:
            repos.log.debug("Missing revision record (%r, %r) in '%s'",
                            repos.id, drev, _norm_reponame(repos))
            raise NoSuchChangeset(rev)

    def get_changes(self):
        for path, kind, change, base_path, base_rev in sorted(
                self.env.db_query("""
                SELECT path, node_type, change_type, base_path, base_rev
                FROM node_change WHERE repos=%s AND rev=%s
                ORDER BY path
                """, (self.repos.id, self.repos.db_rev(self.rev)))):
            kind = _kindmap[kind]
            change = _actionmap[change]
            yield path, kind, change, base_path, self.repos.rev_db(base_rev)

    def get_properties(self):
        return self.repos.repos.get_changeset(self.rev).get_properties()
