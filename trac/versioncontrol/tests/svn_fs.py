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

import os.path
import shutil
import sys
import tempfile
import unittest

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from svn import core, repos

from trac.Logging import logger_factory
from trac.test import TestSetup
from trac.versioncontrol import Changeset, Node
from trac.versioncontrol.svn_fs import SubversionRepository

REPOS_PATH = os.path.join(tempfile.gettempdir(), 'trac-svnrepos')


class SubversionRepositoryTestSetup(TestSetup):

    def setUp(self):
        dumpfile = open(os.path.join(os.path.split(__file__)[0], 'svndump.txt'))

        core.apr_initialize()
        pool = core.svn_pool_create(None)
        dumpstream = None
        try:
            r = repos.svn_repos_create(REPOS_PATH, '', '', None, None, pool)
            if hasattr(repos, 'svn_repos_load_fs2'):
                repos.svn_repos_load_fs2(r, dumpfile, StringIO(),
                                        repos.svn_repos_load_uuid_default, '',
                                        0, 0, None, pool)
            else:
                dumpstream = core.svn_stream_from_aprfile(dumpfile, pool)
                repos.svn_repos_load_fs(r, dumpstream, None,
                                        repos.svn_repos_load_uuid_default, '', None,
                                        None, pool)
        finally:
            if dumpstream:
                core.svn_stream_close(dumpstream)
            core.svn_pool_destroy(pool)
            core.apr_terminate()

    def tearDown(self):
        shutil.rmtree(REPOS_PATH)


class SubversionRepositoryTestCase(unittest.TestCase):

    def setUp(self):
        self.repos = SubversionRepository(REPOS_PATH, None,
                                          logger_factory('test'))

    def tearDown(self):
        self.repos = None

    def test_rev_navigation(self):
        self.assertEqual(0, self.repos.oldest_rev)
        self.assertEqual(None, self.repos.previous_rev(0))
        self.assertEqual(0, self.repos.previous_rev(1))
        self.assertEqual(6, self.repos.youngest_rev)
        self.assertEqual(6, self.repos.next_rev(5))
        self.assertEqual(None, self.repos.next_rev(6))

    def test_get_node(self):
        node = self.repos.get_node('/trunk')
        self.assertEqual('trunk', node.name)
        self.assertEqual('/trunk', node.path)
        self.assertEqual(Node.DIRECTORY, node.kind)
        self.assertEqual(6, node.rev)
        self.assertEqual(1112381806, node.last_modified)
        node = self.repos.get_node('/trunk/README.txt')
        self.assertEqual('README.txt', node.name)
        self.assertEqual('/trunk/README.txt', node.path)
        self.assertEqual(Node.FILE, node.kind)
        self.assertEqual(3, node.rev)
        self.assertEqual(1112361898, node.last_modified)

    def test_get_node_specific_rev(self):
        node = self.repos.get_node('/trunk', 1)
        self.assertEqual('trunk', node.name)
        self.assertEqual('/trunk', node.path)
        self.assertEqual(Node.DIRECTORY, node.kind)
        self.assertEqual(1, node.rev)
        self.assertEqual(1112349652, node.last_modified)
        node = self.repos.get_node('/trunk/README.txt', 2)
        self.assertEqual('README.txt', node.name)
        self.assertEqual('/trunk/README.txt', node.path)
        self.assertEqual(Node.FILE, node.kind)
        self.assertEqual(2, node.rev)
        self.assertEqual(1112361138, node.last_modified)

    def test_get_dir_entries(self):
        node = self.repos.get_node('/trunk')
        entries = node.get_entries()
        self.assertEqual('README2.txt', entries.next().name)
        self.assertEqual('dir1', entries.next().name)
        self.assertEqual('README.txt', entries.next().name)
        self.assertRaises(StopIteration, entries.next)

    def test_get_file_entries(self):
        node = self.repos.get_node('/trunk/README.txt')
        entries = node.get_entries()
        self.assertRaises(StopIteration, entries.next)

    def test_get_dir_content(self):
        node = self.repos.get_node('/trunk')
        self.assertEqual(None, node.content_length)
        self.assertEqual(None, node.content_type)
        self.assertEqual(None, node.get_content())

    def test_get_file_content(self):
        node = self.repos.get_node('/trunk/README.txt')
        self.assertEqual(8, node.content_length)
        self.assertEqual('text/plain', node.content_type)
        self.assertEqual('A test.\n', node.get_content().read())

    def test_get_dir_properties(self):
        f = self.repos.get_node('/trunk')
        props = f.get_properties()
        self.assertEqual(0, len(props))

    def test_get_file_properties(self):
        f = self.repos.get_node('/trunk/README.txt')
        props = f.get_properties()
        self.assertEqual('native', props['svn:eol-style'])
        self.assertEqual('text/plain', props['svn:mime-type'])

    def test_get_node_history(self):
        node = self.repos.get_node('/trunk/README2.txt')
        history = node.get_history()
        self.assertEqual(('trunk/README2.txt', 6), history.next())
        self.assertEqual(('trunk/README.txt', 3), history.next())
        self.assertEqual(('trunk/README.txt', 2), history.next())
        self.assertRaises(StopIteration, history.next)

    def test_changeset_repos_creation(self):
        chgset = self.repos.get_changeset(0)
        self.assertEqual(0, chgset.rev)
        self.assertEqual(None, chgset.message)
        self.assertEqual(None, chgset.author)
        self.assertEqual(1112349461, chgset.date)
        self.assertRaises(StopIteration, chgset.get_changes().next)

    def test_changeset_added_dirs(self):
        chgset = self.repos.get_changeset(1)
        self.assertEqual(1, chgset.rev)
        self.assertEqual('Initial directory layout.', chgset.message)
        self.assertEqual('john', chgset.author)
        self.assertEqual(1112349652, chgset.date)

        changes = chgset.get_changes()
        self.assertEqual(('trunk', Node.DIRECTORY, Changeset.ADD, None, -1),
                         changes.next())
        self.assertEqual(('branches', Node.DIRECTORY, Changeset.ADD, None, -1),
                         changes.next())
        self.assertEqual(('tags', Node.DIRECTORY, Changeset.ADD, None, -1),
                         changes.next())
        self.assertRaises(StopIteration, changes.next)

    def test_changeset_file_edit(self):
        chgset = self.repos.get_changeset(3)
        self.assertEqual(3, chgset.rev)
        self.assertEqual('Fixed README.\n', chgset.message)
        self.assertEqual('kate', chgset.author)
        self.assertEqual(1112361898, chgset.date)

        changes = chgset.get_changes()
        self.assertEqual(('trunk/README.txt', Node.FILE, Changeset.EDIT,
                          'trunk/README.txt', 2), changes.next())
        self.assertRaises(StopIteration, changes.next)

    def test_changeset_dir_moves(self):
        chgset = self.repos.get_changeset(5)
        self.assertEqual(5, chgset.rev)
        self.assertEqual('Moved directories.', chgset.message)
        self.assertEqual('kate', chgset.author)
        self.assertEqual(1112372739, chgset.date)

        changes = chgset.get_changes()
        self.assertEqual(('trunk/dir1/dir2', Node.DIRECTORY, Changeset.MOVE,
                          'trunk/dir2', 4), changes.next())
        self.assertEqual(('trunk/dir1/dir3', Node.DIRECTORY, Changeset.MOVE,
                          'trunk/dir3', 4), changes.next())
        self.assertRaises(StopIteration, changes.next)

    def test_changeset_file_copy(self):
        chgset = self.repos.get_changeset(6)
        self.assertEqual(6, chgset.rev)
        self.assertEqual('More things to read', chgset.message)
        self.assertEqual('john', chgset.author)
        self.assertEqual(1112381806, chgset.date)

        changes = chgset.get_changes()
        self.assertEqual(('trunk/README2.txt', Node.FILE, Changeset.COPY,
                          'trunk/README.txt', 3), changes.next())
        self.assertRaises(StopIteration, changes.next)


def suite():
    return unittest.makeSuite(SubversionRepositoryTestCase, 'test',
                              suiteClass=SubversionRepositoryTestSetup)

if __name__ == '__main__':
    runner = unittest.TextTestRunner()
    runner.run(suite())
