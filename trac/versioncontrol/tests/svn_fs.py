# -*- coding: iso8859-1 -*-
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

import os.path
import stat
import shutil
import sys
import tempfile
import unittest

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from svn import core, repos

from trac.log import logger_factory
from trac.test import TestSetup
from trac.versioncontrol import Changeset, Node
from trac.versioncontrol.svn_fs import SubversionRepository

REPOS_PATH = os.path.join(tempfile.gettempdir(), 'trac-svnrepos')


class SubversionRepositoryTestSetup(TestSetup):

    def setUp(self):
        dumpfile = open(os.path.join(os.path.split(__file__)[0],
                                     'svnrepos.dump'))

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
                                        repos.svn_repos_load_uuid_default, '',
                                        None, None, pool)
        finally:
            if dumpstream:
                core.svn_stream_close(dumpstream)
            core.svn_pool_destroy(pool)
            core.apr_terminate()

    def tearDown(self):
        if os.name == 'nt':
            # The Windows version of 'shutil.rmtree' doesn't override the
            # permissions of read-only files, so we have to do it ourselves:
            format_file = os.path.join(REPOS_PATH, 'db', 'format')
            if os.path.isfile(format_file):
                os.chmod(format_file, stat.S_IRWXU)
            os.chmod(os.path.join(REPOS_PATH, 'format'), stat.S_IRWXU)
        shutil.rmtree(REPOS_PATH)


class SubversionRepositoryTestCase(unittest.TestCase):

    def setUp(self):
        self.repos = SubversionRepository(REPOS_PATH, None,
                                          logger_factory('test'))

    def tearDown(self):
        self.repos = None

    def test_repos_normalize_path(self):
        self.assertEqual('/', self.repos.normalize_path('/'))
        self.assertEqual('/', self.repos.normalize_path(''))
        self.assertEqual('/', self.repos.normalize_path(None))
        self.assertEqual('trunk', self.repos.normalize_path('trunk'))
        self.assertEqual('trunk', self.repos.normalize_path('/trunk'))
        self.assertEqual('trunk', self.repos.normalize_path('trunk/'))
        self.assertEqual('trunk', self.repos.normalize_path('/trunk/'))

    def test_repos_normalize_rev(self):
        self.assertEqual(13, self.repos.normalize_rev('latest'))
        self.assertEqual(13, self.repos.normalize_rev('head'))
        self.assertEqual(13, self.repos.normalize_rev(''))
        self.assertEqual(13, self.repos.normalize_rev(None))
        self.assertEqual(11, self.repos.normalize_rev('11'))
        self.assertEqual(11, self.repos.normalize_rev(11))

    def test_rev_navigation(self):
        self.assertEqual(0, self.repos.oldest_rev)
        self.assertEqual(None, self.repos.previous_rev(0))
        self.assertEqual(0, self.repos.previous_rev(1))
        self.assertEqual(13, self.repos.youngest_rev)
        self.assertEqual(6, self.repos.next_rev(5))
        self.assertEqual(7, self.repos.next_rev(6))
        # ...
        self.assertEqual(None, self.repos.next_rev(13))

    def test_has_node(self):
        self.assertEqual(False, self.repos.has_node('/trunk/dir1', 3))
        self.assertEqual(True, self.repos.has_node('/trunk/dir1', 4))
        
    def test_get_node(self):
        node = self.repos.get_node('/trunk')
        self.assertEqual('trunk', node.name)
        self.assertEqual('/trunk', node.path)
        self.assertEqual(Node.DIRECTORY, node.kind)
        self.assertEqual(13, node.rev)
        self.assertEqual(1132240396L, node.last_modified)
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
        self.assertEqual(1, len(props))

    def test_get_file_properties(self):
        f = self.repos.get_node('/trunk/README.txt')
        props = f.get_properties()
        self.assertEqual('native', props['svn:eol-style'])
        self.assertEqual('text/plain', props['svn:mime-type'])

    # Revision Log / node history 

    def test_get_node_history(self):
        node = self.repos.get_node('/trunk/README2.txt')
        history = node.get_history()
        self.assertEqual(('trunk/README2.txt', 6, 'copy'), history.next())
        self.assertEqual(('trunk/README.txt', 3, 'edit'), history.next())
        self.assertEqual(('trunk/README.txt', 2, 'add'), history.next())
        self.assertRaises(StopIteration, history.next)

    def test_get_node_history_follow_copy(self):
        node = self.repos.get_node('/tags/v1/README.txt')
        history = node.get_history()
        self.assertEqual(('tags/v1/README.txt', 7, 'copy'), history.next())
        self.assertEqual(('trunk/README.txt', 3, 'edit'), history.next())
        self.assertEqual(('trunk/README.txt', 2, 'add'), history.next())
        self.assertRaises(StopIteration, history.next)

    # Revision Log / path history 

    def test_get_path_history(self):
        history = self.repos.get_path_history('/trunk/README2.txt', None)
        self.assertEqual(('trunk/README2.txt', 6, 'copy'), history.next())
        self.assertEqual(('trunk/README.txt', 3, 'unknown'), history.next())
        self.assertRaises(StopIteration, history.next)

    def test_get_path_history_copied_file(self):
        history = self.repos.get_path_history('/tags/v1/README.txt', None)
        self.assertEqual(('tags/v1/README.txt', 7, 'copy'), history.next())
        self.assertEqual(('trunk/README.txt', 3, 'unknown'), history.next())
        self.assertRaises(StopIteration, history.next)
        
    def test_get_path_history_copied_dir(self):
        history = self.repos.get_path_history('/branches/v1x', None)
        self.assertEqual(('branches/v1x', 12, 'copy'), history.next())
        self.assertEqual(('tags/v1.1', 10, 'unknown'), history.next())
        self.assertEqual(('branches/v1x', 11, 'delete'), history.next())
        self.assertEqual(('branches/v1x', 9, 'edit'), history.next())
        self.assertEqual(('branches/v1x', 8, 'copy'), history.next())
        self.assertEqual(('tags/v1', 7, 'unknown'), history.next())
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
        self.assertEqual(('branches', Node.DIRECTORY, Changeset.ADD, None, -1),
                         changes.next())
        self.assertEqual(('tags', Node.DIRECTORY, Changeset.ADD, None, -1),
                         changes.next())
        self.assertEqual(('trunk', Node.DIRECTORY, Changeset.ADD, None, -1),
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


class ScopedSubversionRepositoryTestCase(unittest.TestCase):

    def setUp(self):
        self.repos = SubversionRepository(REPOS_PATH + '/trunk', None,
                                          logger_factory('test'))

    def tearDown(self):
        self.repos = None

    def test_repos_normalize_path(self):
        self.assertEqual('/', self.repos.normalize_path('/'))
        self.assertEqual('/', self.repos.normalize_path(''))
        self.assertEqual('/', self.repos.normalize_path(None))
        self.assertEqual('dir1', self.repos.normalize_path('dir1'))
        self.assertEqual('dir1', self.repos.normalize_path('/dir1'))
        self.assertEqual('dir1', self.repos.normalize_path('dir1/'))
        self.assertEqual('dir1', self.repos.normalize_path('/dir1/'))

    def test_repos_normalize_rev(self):
        self.assertEqual(13, self.repos.normalize_rev('latest'))
        self.assertEqual(13, self.repos.normalize_rev('head'))
        self.assertEqual(13, self.repos.normalize_rev(''))
        self.assertEqual(13, self.repos.normalize_rev(None))
        self.assertEqual(5, self.repos.normalize_rev('5'))
        self.assertEqual(5, self.repos.normalize_rev(5))

    def test_rev_navigation(self):
        self.assertEqual(1, self.repos.oldest_rev)
        self.assertEqual(None, self.repos.previous_rev(0))
        self.assertEqual(1, self.repos.previous_rev(2))
        self.assertEqual(13, self.repos.youngest_rev)
        self.assertEqual(2, self.repos.next_rev(1))
        self.assertEqual(3, self.repos.next_rev(2))
        # ...
        self.assertEqual(None, self.repos.next_rev(13))

    def test_has_node(self):
        self.assertEqual(False, self.repos.has_node('/dir1', 3))
        self.assertEqual(True, self.repos.has_node('/dir1', 4))

    def test_get_node(self):
        node = self.repos.get_node('/dir1')
        self.assertEqual('dir1', node.name)
        self.assertEqual('/dir1', node.path)
        self.assertEqual(Node.DIRECTORY, node.kind)
        self.assertEqual(5, node.rev)
        self.assertEqual(1112372739, node.last_modified)
        node = self.repos.get_node('/README.txt')
        self.assertEqual('README.txt', node.name)
        self.assertEqual('/README.txt', node.path)
        self.assertEqual(Node.FILE, node.kind)
        self.assertEqual(3, node.rev)
        self.assertEqual(1112361898, node.last_modified)

    def test_get_node_specific_rev(self):
        node = self.repos.get_node('/dir1', 4)
        self.assertEqual('dir1', node.name)
        self.assertEqual('/dir1', node.path)
        self.assertEqual(Node.DIRECTORY, node.kind)
        self.assertEqual(4, node.rev)
        self.assertEqual(1112370155, node.last_modified)
        node = self.repos.get_node('/README.txt', 2)
        self.assertEqual('README.txt', node.name)
        self.assertEqual('/README.txt', node.path)
        self.assertEqual(Node.FILE, node.kind)
        self.assertEqual(2, node.rev)
        self.assertEqual(1112361138, node.last_modified)

    def test_get_dir_entries(self):
        node = self.repos.get_node('/')
        entries = node.get_entries()
        self.assertEqual('README2.txt', entries.next().name)
        self.assertEqual('dir1', entries.next().name)
        self.assertEqual('README.txt', entries.next().name)
        self.assertRaises(StopIteration, entries.next)

    def test_get_file_entries(self):
        node = self.repos.get_node('/README.txt')
        entries = node.get_entries()
        self.assertRaises(StopIteration, entries.next)

    def test_get_dir_content(self):
        node = self.repos.get_node('/dir1')
        self.assertEqual(None, node.content_length)
        self.assertEqual(None, node.content_type)
        self.assertEqual(None, node.get_content())

    def test_get_file_content(self):
        node = self.repos.get_node('/README.txt')
        self.assertEqual(8, node.content_length)
        self.assertEqual('text/plain', node.content_type)
        self.assertEqual('A test.\n', node.get_content().read())

    def test_get_dir_properties(self):
        f = self.repos.get_node('/dir1')
        props = f.get_properties()
        self.assertEqual(0, len(props))

    def test_get_file_properties(self):
        f = self.repos.get_node('/README.txt')
        props = f.get_properties()
        self.assertEqual('native', props['svn:eol-style'])
        self.assertEqual('text/plain', props['svn:mime-type'])

    # Revision Log / node history 

    def test_get_node_history(self):
        node = self.repos.get_node('/README2.txt')
        history = node.get_history()
        self.assertEqual(('README2.txt', 6, 'copy'), history.next())
        self.assertEqual(('README.txt', 3, 'edit'), history.next())
        self.assertEqual(('README.txt', 2, 'add'), history.next())
        self.assertRaises(StopIteration, history.next)

    def test_get_node_history_follow_copy(self):
        node = self.repos.get_node('dir1/dir3', )
        history = node.get_history()
        self.assertEqual(('dir1/dir3', 5, 'copy'), history.next())
        self.assertEqual(('dir3', 4, 'add'), history.next())
        self.assertRaises(StopIteration, history.next)

    # Revision Log / path history 

    def test_get_path_history(self):
        history = self.repos.get_path_history('dir3', None)
        self.assertEqual(('dir3', 5, 'delete'), history.next())
        self.assertEqual(('dir3', 4, 'add'), history.next())
        self.assertRaises(StopIteration, history.next)

    def test_get_path_history_copied_file(self):
        history = self.repos.get_path_history('README2.txt', None)
        self.assertEqual(('README2.txt', 6, 'copy'), history.next())
        self.assertEqual(('README.txt', 3, 'unknown'), history.next())
        self.assertRaises(StopIteration, history.next)
        
    def test_get_path_history_copied_dir(self):
        history = self.repos.get_path_history('dir1/dir3', None)
        self.assertEqual(('dir1/dir3', 5, 'copy'), history.next())
        self.assertEqual(('dir3', 4, 'unknown'), history.next())
        self.assertRaises(StopIteration, history.next)

    def test_changeset_repos_creation(self):
        chgset = self.repos.get_changeset(0)
        self.assertEqual(0, chgset.rev)
        self.assertEqual(None, chgset.message)
        self.assertEqual(None, chgset.author)
        self.assertEqual(1112349461, chgset.date)
        self.assertRaises(StopIteration, chgset.get_changes().next)

    def test_changeset_added_dirs(self):
        chgset = self.repos.get_changeset(4)
        self.assertEqual(4, chgset.rev)
        self.assertEqual('More directories.', chgset.message)
        self.assertEqual('john', chgset.author)
        self.assertEqual(1112370155, chgset.date)

        changes = chgset.get_changes()
        self.assertEqual(('dir1', Node.DIRECTORY, 'add', None, -1),
                         changes.next())
        self.assertEqual(('dir2', Node.DIRECTORY, 'add', None, -1),
                         changes.next())
        self.assertEqual(('dir3', Node.DIRECTORY, 'add', None, -1),
                         changes.next())
        self.assertRaises(StopIteration, changes.next)

    def test_changeset_file_edit(self):
        chgset = self.repos.get_changeset(3)
        self.assertEqual(3, chgset.rev)
        self.assertEqual('Fixed README.\n', chgset.message)
        self.assertEqual('kate', chgset.author)
        self.assertEqual(1112361898, chgset.date)

        changes = chgset.get_changes()
        self.assertEqual(('README.txt', Node.FILE, Changeset.EDIT,
                          'README.txt', 2), changes.next())
        self.assertRaises(StopIteration, changes.next)

    def test_changeset_dir_moves(self):
        chgset = self.repos.get_changeset(5)
        self.assertEqual(5, chgset.rev)
        self.assertEqual('Moved directories.', chgset.message)
        self.assertEqual('kate', chgset.author)
        self.assertEqual(1112372739, chgset.date)

        changes = chgset.get_changes()
        self.assertEqual(('dir1/dir2', Node.DIRECTORY, Changeset.MOVE,
                          'dir2', 4), changes.next())
        self.assertEqual(('dir1/dir3', Node.DIRECTORY, Changeset.MOVE,
                          'dir3', 4), changes.next())
        self.assertRaises(StopIteration, changes.next)

    def test_changeset_file_copy(self):
        chgset = self.repos.get_changeset(6)
        self.assertEqual(6, chgset.rev)
        self.assertEqual('More things to read', chgset.message)
        self.assertEqual('john', chgset.author)
        self.assertEqual(1112381806, chgset.date)

        changes = chgset.get_changes()
        self.assertEqual(('README2.txt', Node.FILE, Changeset.COPY,
                          'README.txt', 3), changes.next())
        self.assertRaises(StopIteration, changes.next)


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(SubversionRepositoryTestCase, 'test',
                                     suiteClass=SubversionRepositoryTestSetup))
    suite.addTest(unittest.makeSuite(ScopedSubversionRepositoryTestCase, 'test',
                                     suiteClass=SubversionRepositoryTestSetup))
    return suite

if __name__ == '__main__':
    runner = unittest.TextTestRunner()
    runner.run(suite())
