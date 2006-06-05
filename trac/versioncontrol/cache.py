# -*- coding: utf-8 -*-
#
# Copyright (C) 2005 Edgewall Software
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://projects.edgewall.com/trac/.
#
# Author: Christopher Lenz <cmlenz@gmx.de>

from trac.core import TracError
from trac.versioncontrol import Changeset, Node, Repository, Authorizer, \
                                NoSuchChangeset


_kindmap = {'D': Node.DIRECTORY, 'F': Node.FILE}
_actionmap = {'A': Changeset.ADD, 'C': Changeset.COPY,
              'D': Changeset.DELETE, 'E': Changeset.EDIT,
              'M': Changeset.MOVE}


class CachedRepository(Repository):

    def __init__(self, db, repos, authz, log):
        Repository.__init__(self, repos.name, authz, log)
        self.db = db
        self.repos = repos
        self.synced = 0

    def close(self):
        self.repos.close()

    def get_changeset(self, rev):
        if not self.synced:
            self.sync()
            self.synced = 1
        return CachedChangeset(self.repos.normalize_rev(rev), self.db,
                               self.authz)

    def get_changesets(self, start, stop):
        if not self.synced:
            self.sync()
            self.synced = 1
        cursor = self.db.cursor()
        cursor.execute("SELECT rev FROM revision "
                       "WHERE time >= %s AND time < %s "
                       "ORDER BY time", (start, stop))
        for rev, in cursor:
            if self.authz.has_permission_for_changeset(rev):
                yield self.get_changeset(rev)

    def sync(self):
        self.log.debug("Checking whether sync with repository is needed")
        cursor = self.db.cursor()

        # -- repository used for populating the cache
        cursor.execute("SELECT value FROM system WHERE name='repository_dir'")
        row = cursor.fetchone()
        if row:
            previous_repository_dir = row[0]
        else: # no 'repository_dir' stored yet, assume everything's OK
            previous_repository_dir = self.name

        if self.name != previous_repository_dir:
            raise TracError, ("The 'repository_dir' has changed, "
                              "a 'trac-admin resync' operation is needed.")

        youngest_stored = self.repos.get_youngest_rev_in_cache(self.db)

        if youngest_stored != str(self.repos.youngest_rev):
            authz = self.repos.authz
            self.repos.authz = Authorizer() # remove permission checking

            kindmap = dict(zip(_kindmap.values(), _kindmap.keys()))
            actionmap = dict(zip(_actionmap.values(), _actionmap.keys()))
            self.log.info("Syncing with repository (%s to %s)"
                          % (youngest_stored, self.repos.youngest_rev))
            if youngest_stored:
                current_rev = self.repos.next_rev(youngest_stored)
            else:
                try:
                    current_rev = self.repos.oldest_rev
                    current_rev = self.repos.normalize_rev(current_rev)
                except TracError:
                    current_rev = None
            while current_rev is not None:
                changeset = self.repos.get_changeset(current_rev)
                cursor.execute("INSERT INTO revision (rev,time,author,message) "
                               "VALUES (%s,%s,%s,%s)", (str(current_rev),
                               changeset.date, changeset.author,
                               changeset.message))
                for path,kind,action,base_path,base_rev in changeset.get_changes():
                    self.log.debug("Caching node change in [%s]: %s"
                                   % (current_rev, (path, kind, action,
                                      base_path, base_rev)))
                    kind = kindmap[kind]
                    action = actionmap[action]
                    cursor.execute("INSERT INTO node_change (rev,path,"
                                   "node_type,change_type,base_path,base_rev) "
                                   "VALUES (%s,%s,%s,%s,%s,%s)",
                                   (str(current_rev), path, kind, action,
                                   base_path, base_rev))
                current_rev = self.repos.next_rev(current_rev)
            self.db.commit()
            self.repos.authz = authz # restore permission checking

    def get_node(self, path, rev=None):
        return self.repos.get_node(path, rev)

    def has_node(self, path, rev):
        return self.repos.has_node(path, rev)

    def get_oldest_rev(self):
        return self.repos.oldest_rev

    def get_youngest_rev(self):
        return self.repos.youngest_rev

    def previous_rev(self, rev):
        return self.repos.previous_rev(rev)

    def next_rev(self, rev, path=''):
        return self.repos.next_rev(rev, path)

    def rev_older_than(self, rev1, rev2):
        return self.repos.rev_older_than(rev1, rev2)

    def get_path_history(self, path, rev=None, limit=None):
        return self.repos.get_path_history(path, rev, limit)

    def normalize_path(self, path):
        return self.repos.normalize_path(path)

    def normalize_rev(self, rev):
        return self.repos.normalize_rev(rev)

    def get_changes(self, old_path, old_rev, new_path, new_rev, ignore_ancestry=1):
        return self.repos.get_changes(old_path, old_rev, new_path, new_rev, ignore_ancestry)


class CachedChangeset(Changeset):

    def __init__(self, rev, db, authz):
        self.db = db
        self.authz = authz
        cursor = self.db.cursor()
        cursor.execute("SELECT time,author,message FROM revision "
                       "WHERE rev=%s", (rev,))
        row = cursor.fetchone()
        if row:
            date, author, message = row
            Changeset.__init__(self, rev, message, author, int(date))
        else:
            raise NoSuchChangeset(rev)

    def get_changes(self):
        cursor = self.db.cursor()
        cursor.execute("SELECT path,node_type,change_type,base_path,base_rev "
                       "FROM node_change WHERE rev=%s "
                       "ORDER BY path", (self.rev,))
        for path, kind, change, base_path, base_rev in cursor:
            if not self.authz.has_permission(path):
                # FIXME: what about the base_path?
                continue
            kind = _kindmap[kind]
            change = _actionmap[change]
            yield path, kind, change, base_path, base_rev

    def get_properties(self):
        return []
