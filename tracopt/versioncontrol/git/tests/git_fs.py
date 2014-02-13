# -*- coding: utf-8 -*-
#
# Copyright (C) 2014 Edgewall Software
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
import tempfile
import unittest
from datetime import datetime, timedelta
from subprocess import Popen, PIPE

from trac.core import TracError
from trac.test import EnvironmentStub, locate
from trac.tests.compat import rmtree
from trac.util import create_file
from trac.util.compat import close_fds
from trac.util.datefmt import utc
from trac.versioncontrol.api import DbRepositoryProvider, RepositoryManager
from tracopt.versioncontrol.git.git_fs import GitConnector


git_bin = None


class BaseTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(enable=['trac.*','tracopt.versioncontrol.git.*'])
        self.repos_path = tempfile.mkdtemp(prefix='trac-gitrepos-')
        if git_bin:
            self.env.config.set('git', 'git_bin', git_bin)

    def tearDown(self):
        self.env.reset_db()
        if os.path.isdir(self.repos_path):
            rmtree(self.repos_path)

    @property
    def _repomgr(self):
        return RepositoryManager(self.env)

    @property
    def _dbrepoprov(self):
        return DbRepositoryProvider(self.env)

    def _add_repository(self, reponame='gitrepos'):
        path = os.path.join(self.repos_path, '.git')
        self._dbrepoprov.add_repository(reponame, path, 'git')

    def _git_init(self, data=True, bare=False):
        if bare:
            self._git('init', '--bare', self.repos_path)
        else:
            self._git('init', self.repos_path)
        if not bare and data:
            self._git('config', 'user.name', 'Joe')
            self._git('config', 'user.email', 'joe@example.com')
            create_file(os.path.join(self.repos_path, '.gitignore'))
            self._git('add', '.gitignore')
            env = os.environ.copy()
            env['GIT_COMMITTER_DATE'] = '2001-01-29T16:39:56+00:00'
            env['GIT_AUTHOR_DATE'] = '2001-01-29T16:39:56+00:00'
            self._git('commit', '-a', '-m', 'test', env=env)

    def _git(self, *args, **kwargs):
        args = (git_bin,) + args
        proc = Popen(args, stdout=PIPE, stderr=PIPE, close_fds=close_fds,
                     cwd=self.repos_path, **kwargs)
        stdout, stderr = proc.communicate()
        self.assertEqual(0, proc.returncode,
               'git exits with %r, stdout %r, stderr %r' % (proc.returncode,
                                                            stdout, stderr))
        return proc


class SanityCheckingTestCase(BaseTestCase):

    def test_bare(self):
        self._git_init(bare=True)
        self._dbrepoprov.add_repository('gitrepos', self.repos_path, 'git')
        self._repomgr.get_repository('gitrepos')

    def test_non_bare(self):
        self._git_init(bare=False)
        self._dbrepoprov.add_repository('gitrepos.1',
                                        os.path.join(self.repos_path, '.git'),
                                        'git')
        self._repomgr.get_repository('gitrepos.1')
        self._dbrepoprov.add_repository('gitrepos.2', self.repos_path, 'git')
        self._repomgr.get_repository('gitrepos.2')

    def test_no_head_file(self):
        self._git_init(bare=True)
        os.unlink(os.path.join(self.repos_path, 'HEAD'))
        self._dbrepoprov.add_repository('gitrepos', self.repos_path, 'git')
        self.assertRaises(TracError, self._repomgr.get_repository, 'gitrepos')

    def test_no_objects_dir(self):
        self._git_init(bare=True)
        rmtree(os.path.join(self.repos_path, 'objects'))
        self._dbrepoprov.add_repository('gitrepos', self.repos_path, 'git')
        self.assertRaises(TracError, self._repomgr.get_repository, 'gitrepos')

    def test_no_refs_dir(self):
        self._git_init(bare=True)
        rmtree(os.path.join(self.repos_path, 'refs'))
        self._dbrepoprov.add_repository('gitrepos', self.repos_path, 'git')
        self.assertRaises(TracError, self._repomgr.get_repository, 'gitrepos')


class PersistentCacheTestCase(BaseTestCase):

    def test_persistent(self):
        self.env.config.set('git', 'persistent_cache', 'enabled')
        self._git_init()
        self._add_repository()
        youngest = self._repository.youngest_rev
        self._repomgr.reload_repositories()  # clear repository cache

        self._commit('2014-01-29T16:44:54+09:00')
        self.assertEqual(youngest, self._repository.youngest_rev)
        self._repository.sync()
        self.assertNotEqual(youngest, self._repository.youngest_rev)

    def test_non_persistent(self):
        self.env.config.set('git', 'persistent_cache', 'disabled')
        self._git_init()
        self._add_repository()
        youngest = self._repository.youngest_rev
        self._repomgr.reload_repositories()  # clear repository cache

        self._commit('2014-01-29T16:44:54+09:00')
        youngest_2 = self._repository.youngest_rev
        self.assertNotEqual(youngest, youngest_2)
        self._repository.sync()
        self.assertNotEqual(youngest, self._repository.youngest_rev)
        self.assertEqual(youngest_2, self._repository.youngest_rev)

    def _commit(self, date):
        gitignore = os.path.join(self.repos_path, '.gitignore')
        create_file(gitignore, date)
        self._git('commit', '-a', '-m', date, '--date', date)

    @property
    def _repository(self):
        return self._repomgr.get_repository('gitrepos')


class HistoryTimeRangeTestCase(BaseTestCase):

    def test_without_cache(self):
        self._test_timerange('disabled')

    def test_with_cache(self):
        self._test_timerange('enabled')

    def _test_timerange(self, cached_repository):
        self.env.config.set('git', 'cached_repository', cached_repository)

        self._git_init()
        filename = os.path.join(self.repos_path, '.gitignore')
        start = datetime(2000, 1, 1, 0, 0, 0, 0, utc)
        ts = datetime(2014, 2, 5, 15, 24, 6, 0, utc)
        env = os.environ.copy()
        env['GIT_COMMITTER_DATE'] = ts.isoformat()
        env['GIT_AUTHOR_DATE'] = ts.isoformat()
        for idx in xrange(3):
            create_file(filename, 'commit-%d.txt' % idx)
            self._git('commit', '-a', '-m', 'commit %d' % idx, env=env)
        self._add_repository()
        repos = self._repomgr.get_repository('gitrepos')
        repos.sync()

        revs = [repos.youngest_rev]
        while True:
            parents = repos.parent_revs(revs[-1])
            if not parents:
                break
            revs.extend(parents)
        self.assertEqual(4, len(revs))

        csets = list(repos.get_changesets(start, ts))
        self.assertEqual(1, len(csets))
        self.assertEqual(revs[-1], csets[0].rev)  # is oldest rev

        csets = list(repos.get_changesets(start, ts + timedelta(seconds=1)))
        self.assertEqual(revs, [cset.rev for cset in csets])


def suite():
    global git_bin
    suite = unittest.TestSuite()
    git_bin = locate('git')
    if git_bin:
        suite.addTest(unittest.makeSuite(SanityCheckingTestCase))
        suite.addTest(unittest.makeSuite(PersistentCacheTestCase))
        suite.addTest(unittest.makeSuite(HistoryTimeRangeTestCase))
    else:
        print("SKIP: tracopt/versioncontrol/git/tests/git_fs.py (git cli "
              "binary, 'git', not found)")
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
