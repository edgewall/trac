# -*- coding: utf-8 -*-
#
# Copyright (C) 2012-2013 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

from __future__ import with_statement

import os
import tempfile
import unittest
from datetime import datetime
from subprocess import Popen, PIPE

import trac.tests.compat
from trac.test import EnvironmentStub, rmtree
from trac.util import create_file
from trac.util.compat import close_fds
from trac.versioncontrol.api import Changeset, DbRepositoryProvider, \
                                    RepositoryManager
from tracopt.versioncontrol.git.git_fs import GitConnector
from tracopt.versioncontrol.git.PyGIT import GitCore, GitError, Storage, \
                                             SizedDict, StorageFactory, \
                                             parse_commit
from tracopt.versioncontrol.git.tests.git_fs import GitCommandMixin


class GitTestCase(unittest.TestCase):

    def test_is_sha(self):
        self.assertFalse(GitCore.is_sha('123'))
        self.assertTrue(GitCore.is_sha('1a3f'))
        self.assertTrue(GitCore.is_sha('f' * 40))
        self.assertFalse(GitCore.is_sha('x' + 'f' * 39))
        self.assertFalse(GitCore.is_sha('f' * 41))

    def test_git_version(self):
        v = Storage.git_version()
        self.assertTrue(v)
        self.assertTrue(v['v_compatible'])


class TestParseCommit(unittest.TestCase):
    # The ''' ''' lines are intended to keep lines with trailing whitespace
    commit2240a7b = '''\
tree b19535236cfb6c64b798745dd3917dafc27bcd0a
parent 30aaca4582eac20a52ac7b2ec35bdb908133e5b1
parent 5a0dc7365c240795bf190766eba7a27600be3b3e
author Linus Torvalds <torvalds@linux-foundation.org> 1323915958 -0800
committer Linus Torvalds <torvalds@linux-foundation.org> 1323915958 -0800
mergetag object 5a0dc7365c240795bf190766eba7a27600be3b3e
 type commit
 tag tytso-for-linus-20111214A
 tagger Theodore Ts'o <tytso@mit.edu> 1323890113 -0500
 ''' '''
 tytso-for-linus-20111214
 -----BEGIN PGP SIGNATURE-----
 Version: GnuPG v1.4.10 (GNU/Linux)
 ''' '''
 iQIcBAABCAAGBQJO6PXBAAoJENNvdpvBGATwpuEP/2RCxmdWYZ8/6Z6pmTh3hHN5
 fx6HckTdvLQOvbQs72wzVW0JKyc25QmW2mQc5z3MjSymjf/RbEKihPUITRNbHrTD
 T2sP/lWu09AKLioEg4ucAKn/A7Do3UDIkXTszvVVP/t2psVPzLeJ1njQKra14Nyz
 o0+gSlnwuGx9WaxfR+7MYNs2ikdSkXIeYsiFAOY4YOxwwC99J/lZ0YaNkbI7UBtC
 yu2XLIvPboa5JZXANq2G3VhVIETMmOyRTCC76OAXjqkdp9nLFWDG0ydqQh0vVZwL
 xQGOmAj+l3BNTE0QmMni1w7A0SBU3N6xBA5HN6Y49RlbsMYG27aN54Fy5K2R41I3
 QXVhBL53VD6b0KaITcoz7jIGIy6qk9Wx+2WcCYtQBSIjL2YwlaJq0PL07+vRamex
 sqHGDejcNY87i6AV0DP6SNuCFCi9xFYoAoMi9Wu5E9+T+Vck0okFzW/luk/FvsSP
 YA5Dh+vISyBeCnWQvcnBmsUQyf8d9MaNnejZ48ath+GiiMfY8USAZ29RAG4VuRtS
 9DAyTTIBA73dKpnvEV9u4i8Lwd8hRVMOnPyOO785NwEXk3Ng08pPSSbMklW6UfCY
 4nr5UNB13ZPbXx4uoAvATMpCpYxMaLEdxmeMvgXpkekl0hHBzpVDey1Vu9fb/a5n
 dQpo6WWG9HIJ23hOGAGR
 =n3Lm
 -----END PGP SIGNATURE-----

Merge tag 'tytso-for-linus-20111214' of git://git.kernel.org/pub/scm/linux/kernel/git/tytso/ext4

* tag 'tytso-for-linus-20111214' of git://git.kernel.org/pub/scm/linux/kernel/git/tytso/ext4:
  ext4: handle EOF correctly in ext4_bio_write_page()
  ext4: remove a wrong BUG_ON in ext4_ext_convert_to_initialized
  ext4: correctly handle pages w/o buffers in ext4_discard_partial_buffers()
  ext4: avoid potential hang in mpage_submit_io() when blocksize < pagesize
  ext4: avoid hangs in ext4_da_should_update_i_disksize()
  ext4: display the correct mount option in /proc/mounts for [no]init_itable
  ext4: Fix crash due to getting bogus eh_depth value on big-endian systems
  ext4: fix ext4_end_io_dio() racing against fsync()

.. using the new signed tag merge of git that now verifies the gpg
signature automatically.  Yay.  The branchname was just 'dev', which is
prettier.  I'll tell Ted to use nicer tag names for future cases.
'''

    def test_parse(self):
        msg, props = parse_commit(self.commit2240a7b)
        self.assertTrue(msg)
        self.assertTrue(props)
        self.assertEqual(
            ['30aaca4582eac20a52ac7b2ec35bdb908133e5b1',
             '5a0dc7365c240795bf190766eba7a27600be3b3e'],
            props['parent'])
        self.assertEqual(
            ['Linus Torvalds <torvalds@linux-foundation.org> 1323915958 -0800'],
            props['author'])
        self.assertEqual(props['author'], props['committer'])

        # Merge tag
        self.assertEqual(['''\
object 5a0dc7365c240795bf190766eba7a27600be3b3e
type commit
tag tytso-for-linus-20111214A
tagger Theodore Ts\'o <tytso@mit.edu> 1323890113 -0500

tytso-for-linus-20111214
-----BEGIN PGP SIGNATURE-----
Version: GnuPG v1.4.10 (GNU/Linux)

iQIcBAABCAAGBQJO6PXBAAoJENNvdpvBGATwpuEP/2RCxmdWYZ8/6Z6pmTh3hHN5
fx6HckTdvLQOvbQs72wzVW0JKyc25QmW2mQc5z3MjSymjf/RbEKihPUITRNbHrTD
T2sP/lWu09AKLioEg4ucAKn/A7Do3UDIkXTszvVVP/t2psVPzLeJ1njQKra14Nyz
o0+gSlnwuGx9WaxfR+7MYNs2ikdSkXIeYsiFAOY4YOxwwC99J/lZ0YaNkbI7UBtC
yu2XLIvPboa5JZXANq2G3VhVIETMmOyRTCC76OAXjqkdp9nLFWDG0ydqQh0vVZwL
xQGOmAj+l3BNTE0QmMni1w7A0SBU3N6xBA5HN6Y49RlbsMYG27aN54Fy5K2R41I3
QXVhBL53VD6b0KaITcoz7jIGIy6qk9Wx+2WcCYtQBSIjL2YwlaJq0PL07+vRamex
sqHGDejcNY87i6AV0DP6SNuCFCi9xFYoAoMi9Wu5E9+T+Vck0okFzW/luk/FvsSP
YA5Dh+vISyBeCnWQvcnBmsUQyf8d9MaNnejZ48ath+GiiMfY8USAZ29RAG4VuRtS
9DAyTTIBA73dKpnvEV9u4i8Lwd8hRVMOnPyOO785NwEXk3Ng08pPSSbMklW6UfCY
4nr5UNB13ZPbXx4uoAvATMpCpYxMaLEdxmeMvgXpkekl0hHBzpVDey1Vu9fb/a5n
dQpo6WWG9HIJ23hOGAGR
=n3Lm
-----END PGP SIGNATURE-----'''], props['mergetag'])

        # Message
        self.assertEqual("""Merge tag 'tytso-for-linus-20111214' of git://git.kernel.org/pub/scm/linux/kernel/git/tytso/ext4

* tag 'tytso-for-linus-20111214' of git://git.kernel.org/pub/scm/linux/kernel/git/tytso/ext4:
  ext4: handle EOF correctly in ext4_bio_write_page()
  ext4: remove a wrong BUG_ON in ext4_ext_convert_to_initialized
  ext4: correctly handle pages w/o buffers in ext4_discard_partial_buffers()
  ext4: avoid potential hang in mpage_submit_io() when blocksize < pagesize
  ext4: avoid hangs in ext4_da_should_update_i_disksize()
  ext4: display the correct mount option in /proc/mounts for [no]init_itable
  ext4: Fix crash due to getting bogus eh_depth value on big-endian systems
  ext4: fix ext4_end_io_dio() racing against fsync()

.. using the new signed tag merge of git that now verifies the gpg
signature automatically.  Yay.  The branchname was just 'dev', which is
prettier.  I'll tell Ted to use nicer tag names for future cases.""", msg)


class NormalTestCase(unittest.TestCase, GitCommandMixin):

    def setUp(self):
        self.env = EnvironmentStub()
        self.repos_path = tempfile.mkdtemp(prefix='trac-gitrepos-')
        # create git repository and master branch
        self._git('init')
        self._git('config', 'core.quotepath', 'true')  # ticket:11198
        self._git('config', 'user.name', "Joe")
        self._git('config', 'user.email', "joe@example.com")
        create_file(os.path.join(self.repos_path, '.gitignore'))
        self._git('add', '.gitignore')
        self._git_commit('-a', '-m', 'test',
                         date=datetime(2013, 1, 1, 9, 4, 56))

    def tearDown(self):
        RepositoryManager(self.env).reload_repositories()
        StorageFactory._clean()
        self.env.reset_db()
        if os.path.isdir(self.repos_path):
            rmtree(self.repos_path)

    def _factory(self, weak, path=None):
        if path is None:
            path = os.path.join(self.repos_path, '.git')
        return StorageFactory(path, self.env.log, weak)

    def _storage(self, path=None):
        if path is None:
            path = os.path.join(self.repos_path, '.git')
        return Storage(path, self.env.log, self.git_bin, 'utf-8')

    def test_control_files_detection(self):
        # Exception not raised when path points to ctrl file dir
        self.assertIsInstance(self._storage().repo, GitCore)
        # Exception not raised when path points to parent of ctrl files dir
        self.assertIsInstance(self._storage(self.repos_path).repo, GitCore)
        # Exception raised when path points to dir with no ctrl files
        path = tempfile.mkdtemp(dir=self.repos_path)
        self.assertRaises(GitError, self._storage, path)
        # Exception raised if a ctrl file is missing
        os.remove(os.path.join(self.repos_path, '.git', 'HEAD'))
        self.assertRaises(GitError, self._storage, self.repos_path)

    def test_get_branches_with_cr_in_commitlog(self):
        # regression test for #11598
        message = 'message with carriage return'.replace(' ', '\r')

        create_file(os.path.join(self.repos_path, 'ticket11598.txt'))
        self._git('add', 'ticket11598.txt')
        self._git_commit('-m', message,
                         date=datetime(2013, 5, 9, 11, 5, 21))

        storage = self._storage()
        branches = sorted(storage.get_branches())
        self.assertEqual('master', branches[0][0])
        self.assertEqual(1, len(branches))

    if os.name == 'nt':
        del test_get_branches_with_cr_in_commitlog

    def test_rev_is_anchestor_of(self):
        # regression test for #11215
        path = os.path.join(self.repos_path, '.git')
        DbRepositoryProvider(self.env).add_repository('gitrepos', path, 'git')
        repos = self.env.get_repository('gitrepos')
        parent_rev = repos.youngest_rev

        create_file(os.path.join(self.repos_path, 'ticket11215.txt'))
        self._git('add', 'ticket11215.txt')
        self._git_commit('-m', 'ticket11215',
                         date=datetime(2013, 6, 27, 18, 26, 2))
        repos.sync()
        rev = repos.youngest_rev

        self.assertNotEqual(rev, parent_rev)
        self.assertFalse(repos.rev_older_than(None, None))
        self.assertFalse(repos.rev_older_than(None, rev[:7]))
        self.assertFalse(repos.rev_older_than(rev[:7], None))
        self.assertTrue(repos.rev_older_than(parent_rev, rev))
        self.assertTrue(repos.rev_older_than(parent_rev[:7], rev[:7]))
        self.assertFalse(repos.rev_older_than(rev, parent_rev))
        self.assertFalse(repos.rev_older_than(rev[:7], parent_rev[:7]))

    def test_node_get_history_with_empty_commit(self):
        # regression test for #11328
        path = os.path.join(self.repos_path, '.git')
        DbRepositoryProvider(self.env).add_repository('gitrepos', path, 'git')
        repos = self.env.get_repository('gitrepos')
        parent_rev = repos.youngest_rev

        self._git_commit('-m', 'ticket:11328', '--allow-empty',
                         date=datetime(2013, 10, 15, 9, 46, 27))
        repos.sync()
        rev = repos.youngest_rev

        node = repos.get_node('', rev)
        self.assertEqual(rev, repos.git.last_change(rev, ''))
        history = list(node.get_history())
        self.assertEqual(u'', history[0][0])
        self.assertEqual(rev, history[0][1])
        self.assertEqual(Changeset.EDIT, history[0][2])
        self.assertEqual(u'', history[1][0])
        self.assertEqual(parent_rev, history[1][1])
        self.assertEqual(Changeset.ADD, history[1][2])
        self.assertEqual(2, len(history))

    def test_sync_after_removing_branch(self):
        self._git('checkout', '-b', 'b1', 'master')
        self._git('checkout', 'master')
        create_file(os.path.join(self.repos_path, 'newfile.txt'))
        self._git('add', 'newfile.txt')
        self._git_commit('-m', 'added newfile.txt to master',
                         date=datetime(2013, 12, 23, 6, 52, 23))

        storage = self._storage()
        storage.sync()
        self.assertEqual(['b1', 'master'],
                         sorted(b[0] for b in storage.get_branches()))
        self._git('branch', '-D', 'b1')
        self.assertEqual(True, storage.sync())
        self.assertEqual(['master'],
                         sorted(b[0] for b in storage.get_branches()))
        self.assertEqual(False, storage.sync())

    def test_turn_off_persistent_cache(self):
        # persistent_cache is enabled
        parent_rev = self._factory(False).getInstance().youngest_rev()

        create_file(os.path.join(self.repos_path, 'newfile.txt'))
        self._git('add', 'newfile.txt')
        self._git_commit('-m', 'test_turn_off_persistent_cache',
                         date=datetime(2014, 1, 29, 13, 13, 25))

        # persistent_cache is disabled
        rev = self._factory(True).getInstance().youngest_rev()
        self.assertNotEqual(rev, parent_rev)


class UnicodeNameTestCase(unittest.TestCase, GitCommandMixin):

    def setUp(self):
        self.env = EnvironmentStub()
        self.repos_path = tempfile.mkdtemp(prefix='trac-gitrepos-')
        # create git repository and master branch
        self._git('init')
        self._git('config', 'core.quotepath', 'true')  # ticket:11198
        self._git('config', 'user.name', "Joé")  # passing utf-8 bytes
        self._git('config', 'user.email', "joe@example.com")
        create_file(os.path.join(self.repos_path, '.gitignore'))
        self._git('add', '.gitignore')
        self._git_commit('-a', '-m', 'test',
                         date=datetime(2013, 1, 1, 9, 4, 57))

    def tearDown(self):
        self.env.reset_db()
        if os.path.isdir(self.repos_path):
            rmtree(self.repos_path)

    def _storage(self):
        path = os.path.join(self.repos_path, '.git')
        return Storage(path, self.env.log, self.git_bin, 'utf-8')

    def test_unicode_verifyrev(self):
        storage = self._storage()
        self.assertNotEqual(None, storage.verifyrev(u'master'))
        self.assertIsNone(storage.verifyrev(u'tété'))

    def test_unicode_filename(self):
        create_file(os.path.join(self.repos_path, 'tickét.txt'))
        self._git('add', 'tickét.txt')
        self._git_commit('-m', 'unicode-filename', date='1359912600 +0100')
        storage = self._storage()
        filenames = sorted(fname for mode, type, sha, size, fname
                                 in storage.ls_tree('HEAD'))
        self.assertEqual(unicode, type(filenames[0]))
        self.assertEqual(unicode, type(filenames[1]))
        self.assertEqual(u'.gitignore', filenames[0])
        self.assertEqual(u'tickét.txt', filenames[1])
        # check commit author, for good measure
        self.assertEqual(u'Joé <joe@example.com> 1359912600 +0100',
                         storage.read_commit(storage.head())[1]['author'][0])

    def test_unicode_branches(self):
        self._git('checkout', '-b', 'tickɇt10980', 'master')
        storage = self._storage()
        branches = sorted(storage.get_branches())
        self.assertEqual(unicode, type(branches[0][0]))
        self.assertEqual(unicode, type(branches[1][0]))
        self.assertEqual(u'master', branches[0][0])
        self.assertEqual(u'tickɇt10980', branches[1][0])

        contains = sorted(storage.get_branch_contains(branches[1][1],
                                                      resolve=True))
        self.assertEqual(unicode, type(contains[0][0]))
        self.assertEqual(unicode, type(contains[1][0]))
        self.assertEqual(u'master', contains[0][0])
        self.assertEqual(u'tickɇt10980', contains[1][0])

    def test_unicode_tags(self):
        self._git('tag', 'tɐg-t10980', 'master')
        self._git_commit('-m', 'blah', '--allow-empty')
        self._git('tag', 'v0.42.1', 'master')
        storage = self._storage()

        tags = storage.get_tags()
        self.assertEqual(unicode, type(tags[0]))
        self.assertEqual([u'tɐg-t10980', 'v0.42.1'], tags)

        rev = storage.verifyrev(u'tɐg-t10980')
        self.assertNotEqual(None, rev)
        self.assertEqual([u'tɐg-t10980'], storage.get_tags(rev))

        rev = storage.verifyrev('v0.42.1')
        self.assertNotEqual(None, rev)
        self.assertEqual(['v0.42.1'], storage.get_tags(rev))

    def test_ls_tree(self):
        paths = [u'normal-path.txt',
                 u'tickét.tx\\t',
                 u'\a\b\t\n\v\f\r\x1b"\\.tx\\t']
        for path in paths:
            path_utf8 = path.encode('utf-8')
            create_file(os.path.join(self.repos_path, path_utf8))
            self._git('add', path_utf8)
        self._git_commit('-m', 'ticket:11180 and ticket:11198',
                         date=datetime(2013, 4, 30, 13, 48, 57))

        storage = self._storage()
        rev = storage.head()
        entries = storage.ls_tree(rev, '/')
        self.assertEqual(4, len(entries))
        self.assertEqual(u'\a\b\t\n\v\f\r\x1b"\\.tx\\t', entries[0][4])
        self.assertEqual(u'.gitignore', entries[1][4])
        self.assertEqual(u'normal-path.txt', entries[2][4])
        self.assertEqual(u'tickét.tx\\t', entries[3][4])

    def test_get_historian(self):
        paths = [u'normal-path.txt',
                 u'tickét.tx\\t',
                 u'\a\b\t\n\v\f\r\x1b"\\.tx\\t']

        for path in paths:
            path_utf8 = path.encode('utf-8')
            create_file(os.path.join(self.repos_path, path_utf8))
            self._git('add', path_utf8)
        self._git_commit('-m', 'ticket:11180 and ticket:11198',
                         date=datetime(2013, 4, 30, 17, 48, 57))

        def validate(path, quotepath):
            self._git('config', 'core.quotepath', quotepath)
            storage = self._storage()
            rev = storage.head()
            with storage.get_historian('HEAD', path) as historian:
                hrev = storage.last_change('HEAD', path, historian)
                self.assertEquals(rev, hrev)

        validate(paths[0], 'true')
        validate(paths[0], 'false')
        validate(paths[1], 'true')
        validate(paths[1], 'false')
        validate(paths[2], 'true')
        validate(paths[2], 'false')


class SizedDictTestCase(unittest.TestCase):

    def test_setdefault_raises(self):
        """`setdefault` raises NotImplementedError."""
        self.assertRaises(NotImplementedError, SizedDict().setdefault)


#class GitPerformanceTestCase(unittest.TestCase):
#    """Performance test. Not really a unit test.
#    Not self-contained: Needs a git repository and prints performance result
#    instead of testing anything.
#    TODO: Move to a profiling script?"""
#
#    def test_performance(self):
#        import logging
#        import timeit
#
#        g = Storage(path_to_repo, logging) # Need a git repository path here
#        revs = g.get_commits().keys()
#
#        def shortrev_test():
#            for i in revs:
#                i = str(i)
#                s = g.shortrev(i, min_len=4)
#                self.assertTrue(i.startswith(s))
#                self.assertEqual(g.fullrev(s), i)
#
#        iters = 1
#        t = timeit.Timer("shortrev_test()",
#                         "from __main__ import shortrev_test")
#        usec_per_rev = (1000000 * t.timeit(number=iters)/len(revs))
#        print "%.2f usec/rev" % usec_per_rev # Print instead of testing

#class GitMemoryUsageTestCase(unittest.TestCase):
#    """Memory test. Not really a unit test.
#    Not self-contained: Needs a git repository and prints memory usage
#    instead of testing anything.
#    TODO: Move to a profiling script?"""
#
#    def test_memory_usage(self):
#        import logging
#        import sys
#
#        # custom linux hack reading `/proc/<PID>/statm`
#        if sys.platform == 'linux2':
#            __pagesize = os.sysconf('SC_PAGESIZE')
#
#            def proc_statm(pid = os.getpid()):
#                __proc_statm = '/proc/%d/statm' % pid
#                try:
#                    t = open(__proc_statm)
#                    result = t.read().split()
#                    t.close()
#                    self.assertEqual(7, len(result))
#                    return tuple([ __pagesize*int(p) for p in result ])
#                except:
#                    raise RuntimeError("failed to get memory stats")
#
#        else: # not linux2
#            print "WARNING - meminfo.proc_statm() not available"
#            def proc_statm():
#                return (0,)*7
#
#        print "statm =", proc_statm()
#        __data_size = proc_statm()[5]
#        __data_size_last = [__data_size]
#
#        def print_data_usage():
#            __tmp = proc_statm()[5]
#            print "DATA: %6d %+6d" % (__tmp - __data_size,
#                                    __tmp - __data_size_last[0])
#            __data_size_last[0] = __tmp
#
#        print_data_usage()
#
#        g = Storage(path_to_repo, logging) # Need a git repository path here
#
#        print_data_usage()
#
#        print "[%s]" % g.head()
#        print g.ls_tree(g.head())
#        print "--------------"
#        print_data_usage()
#        print g.read_commit(g.head())
#        print "--------------"
#        print_data_usage()
#        p = g.parents(g.head())
#        print list(p)
#        print "--------------"
#        print list(g.children(list(p)[0]))
#        print list(g.children(list(p)[0]))
#        print "--------------"
#        print g.get_commit_encoding()
#        print "--------------"
#        print g.get_branches()
#        print "--------------"
#        print g.hist_prev_revision(g.oldest_rev()), g.oldest_rev(), \
#                                g.hist_next_revision(g.oldest_rev())
#        print_data_usage()
#        print "--------------"
#        p = g.youngest_rev()
#        print g.hist_prev_revision(p), p, g.hist_next_revision(p)
#        print "--------------"
#
#        p = g.head()
#        for i in range(-5, 5):
#            print i, g.history_relative_rev(p, i)
#
#        # check for loops
#        def check4loops(head):
#            print "check4loops", head
#            seen = set([head])
#            for _sha in g.children_recursive(head):
#                if _sha in seen:
#                    print "dupe detected :-/", _sha, len(seen)
#                seen.add(_sha)
#            return seen
#
#        print len(check4loops(g.parents(g.head())[0]))
#
#        #p = g.head()
#        #revs = [ g.history_relative_rev(p, i) for i in range(0,10) ]
#        print_data_usage()
#        revs = g.get_commits().keys()
#        print_data_usage()
#
#        #print len(check4loops(g.oldest_rev()))
#        #print len(list(g.children_recursive(g.oldest_rev())))
#
#        print_data_usage()
#
#        # perform typical trac operations:
#
#        if 1:
#            print "--------------"
#            rev = g.head()
#            for mode, _type, sha, _size, name in g.ls_tree(rev):
#                [last_rev] = g.history(rev, name, limit=1)
#                s = g.get_obj_size(sha) if _type == 'blob' else 0
#                msg = g.read_commit(last_rev)
#
#                print "%s %s %10d [%s]" % (_type, last_rev, s, name)
#
#        print "allocating 2nd instance"
#        print_data_usage()
#        g2 = Storage(path_to_repo, logging) # Need a git repository path here
#        g2.head()
#        print_data_usage()
#
#        print "allocating 3rd instance"
#        g3 = Storage(path_to_repo, logging) # Need a git repository path here
#        g3.head()
#        print_data_usage()


def suite():
    suite = unittest.TestSuite()
    if GitCommandMixin.git_bin:
        suite.addTest(unittest.makeSuite(GitTestCase))
        suite.addTest(unittest.makeSuite(TestParseCommit))
        suite.addTest(unittest.makeSuite(NormalTestCase))
        if os.name != 'nt':
            # Popen doesn't accept unicode path and arguments on Windows
            suite.addTest(unittest.makeSuite(UnicodeNameTestCase))
    else:
        print("SKIP: tracopt/versioncontrol/git/tests/PyGIT.py (git cli "
              "binary, 'git', not found)")
    suite.addTest(unittest.makeSuite(SizedDictTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
