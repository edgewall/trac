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

import unittest

from trac.test import locate
from tracopt.versioncontrol.git.PyGIT import GitCore, Storage


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
    else:
        print("SKIP: tracopt/versioncontrol/git/tests/PyGIT.py (git cli "
              "binary, 'git', not found)")
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
