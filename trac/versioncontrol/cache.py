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
from trac.versioncontrol import Changeset, Node, Repository, Authorizer


_kindmap = {'D': Node.DIRECTORY, 'F': Node.FILE}
_actionmap = {'A': Changeset.ADD, 'C': Changeset.COPY,
              'D': Changeset.DELETE, 'E': Changeset.EDIT,
              'M': Changeset.MOVE}


class CachedRepository(Repository):

    def __init__(self, db, repos, authz, log):
        Repository.__init__(self, authz, log)
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

    def sync(self):
        self.log.debug("Checking whether sync with repository is needed")
        youngest_stored = self.repos.get_youngest_rev_in_cache(self.db)
        if youngest_stored != str(self.repos.youngest_rev):
            authz = self.repos.authz
            self.repos.authz = Authorizer() # remove permission checking

            kindmap = dict(zip(_kindmap.values(), _kindmap.keys()))
            actionmap = dict(zip(_actionmap.values(), _actionmap.keys()))
            self.log.info("Syncing with repository (%s to %s)"
                          % (youngest_stored, self.repos.youngest_rev))
            cursor = self.db.cursor()
            if youngest_stored:
                current_rev = self.repos.next_rev(youngest_stored)
            else:
                current_rev = self.repos.oldest_rev
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
                    cursor.execute("INSERT INTO node_change (rev,path,kind,"
                                   "change,base_path,base_rev) "
                                   "VALUES (%s,%s,%s,%s,%s,%s)",
                                   (str(current_rev), path, kind, action,
                                   base_path, base_rev))
                current_rev = self.repos.next_rev(current_rev)
            self.db.commit()
            self.repos.authz = authz # restore permission checking

    def get_node(self, path, rev=None):
        return self.repos.get_node(path, rev)

    def get_oldest_rev(self):
        return self.repos.oldest_rev

    def get_youngest_rev(self):
        return self.repos.youngest_rev

    def previous_rev(self, rev):
        return self.repos.previous_rev(rev)

    def next_rev(self, rev):
        return self.repos.next_rev(rev)

    def rev_older_than(self, rev1, rev2):
        return self.repos.rev_older_than(rev1, rev2)

    def get_path_history(self, path, rev=None, limit=None):
        return self.repos.get_path_history(path, rev, limit)

    def normalize_path(self, path):
        return self.repos.normalize_path(path)

    def normalize_rev(self, rev):
        return self.repos.normalize_rev(rev)


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
            raise TracError, "No changeset %s in the repository" % rev

    def get_changes(self):
        cursor = self.db.cursor()
        cursor.execute("SELECT path,kind,change,base_path,base_rev "
                       "FROM node_change WHERE rev=%s", (self.rev,))
        for path, kind, change, base_path, base_rev in cursor:
            if not self.authz.has_permission(path):
                # FIXME: what about the base_path?
                continue
            kind = _kindmap[kind]
            change = _actionmap[change]
            yield path, kind, change, base_path, base_rev
