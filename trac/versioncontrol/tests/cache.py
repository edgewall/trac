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

from trac.log import logger_factory
from trac.test import Mock, InMemoryDatabase
from trac.versioncontrol import Repository, Changeset, Node
from trac.versioncontrol.cache import CachedRepository

import time
import unittest


class CacheTestCase(unittest.TestCase):

    def setUp(self):
        self.db = InMemoryDatabase()
        self.log = logger_factory('test')

    def test_initial_sync_with_empty_repos(self):
        changeset = Mock(Changeset, 0, '', '', 42000,
                         get_changes=lambda: [])
        repos = Mock(Repository, 'test-repos', None, self.log,
                     get_changeset=lambda x: changeset,
                     get_oldest_rev=lambda: 0,
                     get_youngest_rev=lambda: 0,
                     normalize_rev=lambda x: x,
                     next_rev=lambda x: None)
        cache = CachedRepository(self.db, repos, None, self.log)
        cache.sync()

        cursor = self.db.cursor()
        cursor.execute("SELECT rev,time,author,message FROM revision")
        self.assertEquals(('0', 42000, '', ''), cursor.fetchone())
        cursor.execute("SELECT COUNT(*) FROM node_change")
        self.assertEquals(0, cursor.fetchone()[0])

    def test_initial_sync(self):
        changes = [('trunk', Node.DIRECTORY, Changeset.ADD, None, None),
                   ('trunk/README', Node.FILE, Changeset.ADD, None, None)]
        changesets = [Mock(Changeset, 0, '', '', 41000,
                           get_changes=lambda: []),
                      Mock(Changeset, 1, 'Import', 'joe', 42000,
                           get_changes=lambda: iter(changes))]
        repos = Mock(Repository, 'test-repos', None, self.log,
                     get_changeset=lambda x: changesets[int(x)],
                     get_oldest_rev=lambda: 0,
                     get_youngest_rev=lambda: 1,
                     normalize_rev=lambda x: x,
                     next_rev=lambda x: int(x) == 0 and 1 or None)
        cache = CachedRepository(self.db, repos, None, self.log)
        cache.sync()

        cursor = self.db.cursor()
        cursor.execute("SELECT rev,time,author,message FROM revision")
        self.assertEquals(('0', 41000, '', ''), cursor.fetchone())
        self.assertEquals(('1', 42000, 'joe', 'Import'), cursor.fetchone())
        self.assertEquals(None, cursor.fetchone())
        cursor.execute("SELECT rev,path,node_type,change_type,base_path,"
                       "base_rev FROM node_change")
        self.assertEquals(('1', 'trunk', 'D', 'A', None, None),
                          cursor.fetchone())
        self.assertEquals(('1', 'trunk/README', 'F', 'A', None, None),
                          cursor.fetchone())
        self.assertEquals(None, cursor.fetchone())

    def test_update_sync(self):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO revision (rev,time,author,message) "
                       "VALUES (0,41000,'','')")
        cursor.execute("INSERT INTO revision (rev,time,author,message) "
                       "VALUES (1,42000,'joe','Import')")
        cursor.executemany("INSERT INTO node_change (rev,path,node_type,"
                           "change_type,base_path,base_rev) "
                           "VALUES ('1',%s,%s,%s,%s,%s)",
                           [('trunk', 'D', 'A', None, None),
                            ('trunk/README', 'F', 'A', None, None)])

        changes = [('trunk/README', Node.FILE, Changeset.EDIT, 'trunk/README', 1)]
        changeset = Mock(Changeset, 2, 'Update', 'joe', 42042,
                         get_changes=lambda: iter(changes))
        repos = Mock(Repository, 'test-repos', None, self.log,
                     get_changeset=lambda x: changeset,
                     get_youngest_rev=lambda: 2,
                     next_rev=lambda x: int(x) == 1 and 2 or None)
        cache = CachedRepository(self.db, repos, None, self.log)
        cache.sync()

        cursor = self.db.cursor()
        cursor.execute("SELECT time,author,message FROM revision WHERE rev='2'")
        self.assertEquals((42042, 'joe', 'Update'), cursor.fetchone())
        self.assertEquals(None, cursor.fetchone())
        cursor.execute("SELECT path,node_type,change_type,base_path,base_rev "
                       "FROM node_change WHERE rev='2'")
        self.assertEquals(('trunk/README', 'F', 'E', 'trunk/README', '1'),
                          cursor.fetchone())
        self.assertEquals(None, cursor.fetchone())

    def test_get_changes(self):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO revision (rev,time,author,message) "
                       "VALUES (0,41000,'','')")
        cursor.execute("INSERT INTO revision (rev,time,author,message) "
                       "VALUES (1,42000,'joe','Import')")
        cursor.executemany("INSERT INTO node_change (rev,path,node_type,"
                           "change_type,base_path,base_rev) "
                           "VALUES ('1',%s,%s,%s,%s,%s)",
                           [('trunk', 'D', 'A', None, None),
                            ('trunk/README', 'F', 'A', None, None)])

        repos = Mock(Repository, 'test-repos', None, self.log,
                     get_changeset=lambda x: None,
                     get_youngest_rev=lambda: 1,
                     next_rev=lambda x: None, normalize_rev=lambda rev: rev)
        cache = CachedRepository(self.db, repos, None, self.log)
        self.assertEqual(1, cache.youngest_rev)
        changeset = cache.get_changeset(1)
        self.assertEqual('joe', changeset.author)
        self.assertEqual('Import', changeset.message)
        self.assertEqual(42000, changeset.date)
        changes = changeset.get_changes()
        self.assertEqual(('trunk', Node.DIRECTORY, Changeset.ADD, None, None),
                         changes.next())
        self.assertEqual(('trunk/README', Node.FILE, Changeset.ADD, None, None),
                         changes.next())
        self.assertRaises(StopIteration, changes.next)


def suite():
    return unittest.makeSuite(CacheTestCase, 'test')

if __name__ == '__main__':
    unittest.main()
