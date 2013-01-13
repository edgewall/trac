# -*- coding: utf-8 -*-
#
# Copyright (C) 2012 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import os
import shutil
import tempfile
import unittest
from subprocess import Popen, PIPE

from trac.test import locate, EnvironmentStub
from trac.util import create_file
from trac.util.compat import close_fds
from tracopt.versioncontrol.git.PyGIT import GitCore, Storage, parse_commit


class GitTestCase(unittest.TestCase):

    def test_is_sha(self):
        self.assertTrue(not GitCore.is_sha('123'))
        self.assertTrue(GitCore.is_sha('1a3f'))
        self.assertTrue(GitCore.is_sha('f' * 40))
        self.assertTrue(not GitCore.is_sha('x' + 'f' * 39))
        self.assertTrue(not GitCore.is_sha('f' * 41))

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
        self.assertEquals(
            ['30aaca4582eac20a52ac7b2ec35bdb908133e5b1',
             '5a0dc7365c240795bf190766eba7a27600be3b3e'],
            props['parent'])
        self.assertEquals(
            ['Linus Torvalds <torvalds@linux-foundation.org> 1323915958 -0800'],
            props['author'])
        self.assertEquals(props['author'], props['committer'])

        # Merge tag
        self.assertEquals(['''\
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
        self.assertEquals("""Merge tag 'tytso-for-linus-20111214' of git://git.kernel.org/pub/scm/linux/kernel/git/tytso/ext4

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


class UnicodeNameTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.repos_path = tempfile.mkdtemp(prefix='trac-gitrepos')
        self.git_bin = locate('git')
        # create git repository and master branch
        self._git('init', self.repos_path)
        create_file(os.path.join(self.repos_path, '.gitignore'))
        self._git('add', '.gitignore')
        self._git('commit', '-a', '-m', 'test')

    def tearDown(self):
        if os.path.isdir(self.repos_path):
            shutil.rmtree(self.repos_path)

    def _git(self, *args):
        args = [self.git_bin] + list(args)
        proc = Popen(args, stdout=PIPE, stderr=PIPE, close_fds=close_fds,
                     cwd=self.repos_path)
        proc.wait()
        assert proc.returncode == 0
        return proc

    def _storage(self):
        path = os.path.join(self.repos_path, '.git')
        return Storage(path, self.env.log, self.git_bin, 'utf-8')

    def test_unicode_verifyrev(self):
        storage = self._storage()
        self.assertNotEqual(None, storage.verifyrev(u'master'))
        self.assertEquals(None, storage.verifyrev(u'tété'))

    def test_unicode_filename(self):
        create_file(os.path.join(self.repos_path, 'tickét.txt'))
        self._git('add', 'tickét.txt')
        self._git('commit', '-m', 'unicode-filename')
        storage = self._storage()
        filenames = sorted(fname for mode, type, sha, size, fname
                                 in storage.ls_tree('HEAD'))
        self.assertEquals(unicode, type(filenames[0]))
        self.assertEquals(unicode, type(filenames[1]))
        self.assertEquals(u'.gitignore', filenames[0])
        self.assertEquals(u'tickét.txt', filenames[1])

    def test_unicode_branches(self):
        self._git('checkout', '-b', 'tickét10980', 'master')
        storage = self._storage()
        branches = sorted(storage.get_branches())
        self.assertEquals(unicode, type(branches[0][0]))
        self.assertEquals(unicode, type(branches[1][0]))
        self.assertEquals(u'master', branches[0][0])
        self.assertEquals(u'tickét10980', branches[1][0])

        contains = sorted(storage.get_branch_contains(branches[1][1],
                                                      resolve=True))
        self.assertEquals(unicode, type(contains[0][0]))
        self.assertEquals(unicode, type(contains[1][0]))
        self.assertEquals(u'master', contains[0][0])
        self.assertEquals(u'tickét10980', contains[1][0])

    def test_unicode_tags(self):
        self._git('tag', 'täg-t10980', 'master')
        storage = self._storage()
        tags = tuple(storage.get_tags())
        self.assertEquals(unicode, type(tags[0]))
        self.assertEquals(u'täg-t10980', tags[0])
        self.assertNotEqual(None, storage.verifyrev(u'täg-t10980'))


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
#                self.assertEquals(g.fullrev(s), i)
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
#                    assert len(result) == 7
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
    git = locate("git")
    if git:
        suite.addTest(unittest.makeSuite(GitTestCase, 'test'))
        suite.addTest(unittest.makeSuite(TestParseCommit, 'test'))
        if os.name != 'nt':
            # Popen doesn't accept unicode path and arguments on Windows
            suite.addTest(unittest.makeSuite(UnicodeNameTestCase, 'test'))
    else:
        print("SKIP: tracopt/versioncontrol/git/tests/PyGIT.py (git cli "
              "binary, 'git', not found)")
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
