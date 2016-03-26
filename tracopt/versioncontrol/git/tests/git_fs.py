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
import sys
import tempfile
import unittest
from cStringIO import StringIO
from datetime import datetime, timedelta
from subprocess import Popen, PIPE

from trac.core import TracError
from trac.test import EnvironmentStub, MockRequest, locate
from trac.tests.compat import rmtree
from trac.util import create_file
from trac.util.compat import close_fds
from trac.util.datefmt import to_timestamp, utc
from trac.util.text import to_utf8
from trac.versioncontrol.api import Changeset, DbRepositoryProvider, \
                                    InvalidRepository, Node, \
                                    NoSuchChangeset, NoSuchNode, \
                                    RepositoryManager
from trac.versioncontrol.web_ui.browser import BrowserModule
from trac.versioncontrol.web_ui.log import LogModule
from tracopt.versioncontrol.git.PyGIT import StorageFactory
from tracopt.versioncontrol.git.git_fs import GitCachedRepository, \
                                              GitConnector, GitRepository


class GitCommandMixin(object):

    git_bin = locate('git')

    def _git_commit(self, *args, **kwargs):
        env = kwargs.get('env') or os.environ.copy()
        if 'date' in kwargs:
            self._set_committer_date(env, kwargs.pop('date'))
        args = ('commit',) + args
        kwargs['env'] = env
        return self._git(*args, **kwargs)

    def _spawn_git(self, *args, **kwargs):
        args = map(to_utf8, (self.git_bin,) + args)
        kwargs.setdefault('stdin', PIPE)
        kwargs.setdefault('stdout', PIPE)
        kwargs.setdefault('stderr', PIPE)
        kwargs.setdefault('cwd', self.repos_path)
        return Popen(args, close_fds=close_fds, **kwargs)

    def _git(self, *args, **kwargs):
        proc = self._spawn_git(*args, **kwargs)
        stdout, stderr = proc.communicate()
        self.assertEqual(0, proc.returncode,
                         'git exits with %r, args %r, kwargs %r, stdout %r, '
                         'stderr %r' %
                         (proc.returncode, args, kwargs, stdout, stderr))
        return proc

    def _git_fast_import(self, data):
        if isinstance(data, unicode):
            data = data.encode('utf-8')
        proc = self._spawn_git('fast-import', stdin=PIPE)
        stdout, stderr = proc.communicate(input=data)
        self.assertEqual(0, proc.returncode,
                         'git exits with %r, stdout %r, stderr %r' %
                         (proc.returncode, stdout, stderr))

    def _git_date_format(self, dt):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=utc)
        offset = dt.utcoffset()
        secs = offset.days * 3600 * 24 + offset.seconds
        hours, rem = divmod(abs(secs), 3600)
        return '%d %c%02d:%02d' % (to_timestamp(dt), '-' if secs < 0 else '+',
                                   hours, rem / 60)

    def _set_committer_date(self, env, dt):
        if not isinstance(dt, basestring):
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=utc)
            dt = self._git_date_format(dt)
        env['GIT_COMMITTER_DATE'] = dt
        env['GIT_AUTHOR_DATE'] = dt


class BaseTestCase(unittest.TestCase, GitCommandMixin):

    def setUp(self):
        self.env = EnvironmentStub()
        self.repos_path = tempfile.mkdtemp(prefix='trac-gitrepos-')
        if self.git_bin:
            self.env.config.set('git', 'git_bin', self.git_bin)

    def tearDown(self):
        for repos in self._repomgr.get_real_repositories():
            repos.close()
        self._repomgr.reload_repositories()
        StorageFactory._clean()
        self.env.reset_db()
        if os.path.isdir(self.repos_path):
            rmtree(self.repos_path)

    @property
    def _repomgr(self):
        return RepositoryManager(self.env)

    @property
    def _dbrepoprov(self):
        return DbRepositoryProvider(self.env)

    def _add_repository(self, reponame='gitrepos', bare=False):
        path = self.repos_path \
               if bare else os.path.join(self.repos_path, '.git')
        self._dbrepoprov.add_repository(reponame, path, 'git')

    def _git_init(self, data=True, bare=False):
        if bare:
            self._git('init', '--bare')
        else:
            self._git('init')
        if not bare and data:
            self._git('config', 'user.name', 'Joe')
            self._git('config', 'user.email', 'joe@example.com')
            create_file(os.path.join(self.repos_path, '.gitignore'))
            self._git('add', '.gitignore')
            self._git_commit('-a', '-m', 'test',
                             date=datetime(2001, 1, 29, 16, 39, 56))


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

        self._commit(datetime(2014, 1, 29, 16, 44, 54, 0, utc))
        self.assertEqual(youngest, self._repository.youngest_rev)
        self._repository.sync()
        self.assertNotEqual(youngest, self._repository.youngest_rev)

    def test_non_persistent(self):
        self.env.config.set('git', 'persistent_cache', 'disabled')
        self._git_init()
        self._add_repository()
        youngest = self._repository.youngest_rev
        self._repomgr.reload_repositories()  # clear repository cache

        self._commit(datetime(2014, 1, 29, 16, 44, 54, 0, utc))
        youngest_2 = self._repository.youngest_rev
        self.assertNotEqual(youngest, youngest_2)
        self._repository.sync()
        self.assertNotEqual(youngest, self._repository.youngest_rev)
        self.assertEqual(youngest_2, self._repository.youngest_rev)

    def _commit(self, date):
        gitignore = os.path.join(self.repos_path, '.gitignore')
        create_file(gitignore, date.isoformat())
        self._git_commit('-a', '-m', date.isoformat(), date=date)

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
        for idx in xrange(3):
            create_file(filename, 'commit-%d.txt' % idx)
            self._git_commit('-a', '-m', 'commit %d' % idx, date=ts)
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


class GitNormalTestCase(BaseTestCase):

    def test_get_node(self):
        self.env.config.set('git', 'persistent_cache', 'false')
        self.env.config.set('git', 'cached_repository', 'false')

        self._git_init()
        self._add_repository()
        repos = self._repomgr.get_repository('gitrepos')
        rev = repos.youngest_rev
        self.assertNotEqual(None, rev)
        self.assertEqual(40, len(rev))

        self.assertEqual(rev, repos.get_node('/').rev)
        self.assertEqual(rev, repos.get_node('/', rev[:7]).rev)
        self.assertEqual(rev, repos.get_node('/.gitignore').rev)
        self.assertEqual(rev, repos.get_node('/.gitignore', rev[:7]).rev)

        self.assertRaises(NoSuchNode, repos.get_node, '/non-existent')
        self.assertRaises(NoSuchNode, repos.get_node, '/non-existent', rev[:7])
        self.assertRaises(NoSuchNode, repos.get_node, '/non-existent', rev)
        self.assertRaises(NoSuchChangeset,
                          repos.get_node, '/', 'invalid-revision')
        self.assertRaises(NoSuchChangeset,
                          repos.get_node, '/.gitignore', 'invalid-revision')
        self.assertRaises(NoSuchChangeset,
                          repos.get_node, '/non-existent', 'invalid-revision')

        # git_fs doesn't support non-ANSI strings on Windows
        if os.name != 'nt':
            self._git('branch', u'tïckét10605', 'master')
            repos.sync()
            self.assertEqual(rev, repos.get_node('/', u'tïckét10605').rev)
            self.assertEqual(rev, repos.get_node('/.gitignore',
                                                 u'tïckét10605').rev)

    def _test_on_empty_repos(self, cached_repository):
        self.env.config.set('git', 'persistent_cache', 'false')
        self.env.config.set('git', 'cached_repository',
                            'true' if cached_repository else 'false')

        self._git_init(data=False, bare=True)
        self._add_repository(bare=True)
        repos = self._repomgr.get_repository('gitrepos')
        if cached_repository:
            # call sync() thrice with empty repository (#11851)
            for i in xrange(3):
                repos.sync()
                rows = self.env.db_query("SELECT value FROM repository "
                                         "WHERE id=%s AND name=%s",
                                         (repos.id, 'youngest_rev'))
                self.assertEqual('', rows[0][0])
        else:
            repos.sync()
        youngest_rev = repos.youngest_rev
        self.assertEqual(None, youngest_rev)
        self.assertEqual(None, repos.oldest_rev)
        self.assertEqual(None, repos.normalize_rev(''))
        self.assertEqual(None, repos.normalize_rev(None))

        node = repos.get_node('/', youngest_rev)
        self.assertEqual([], list(node.get_entries()))
        self.assertEqual([], list(node.get_history()))
        self.assertRaises(NoSuchNode, repos.get_node, '/path', youngest_rev)

        req = MockRequest(self.env, path_info='/browser/gitrepos')
        browser_mod = BrowserModule(self.env)
        self.assertTrue(browser_mod.match_request(req))
        rv = browser_mod.process_request(req)
        self.assertEqual('browser.html', rv[0])
        self.assertEqual(None, rv[1]['rev'])

        req = MockRequest(self.env, path_info='/log/gitrepos')
        log_mod = LogModule(self.env)
        self.assertTrue(log_mod.match_request(req))
        rv = log_mod.process_request(req)
        self.assertEqual('revisionlog.html', rv[0])
        self.assertEqual([], rv[1]['items'])

    def test_on_empty_and_cached_repos(self):
        self._test_on_empty_repos(True)

    def test_on_empty_and_non_cached_repos(self):
        self._test_on_empty_repos(False)


class GitRepositoryTestCase(BaseTestCase):

    cached_repository = 'disabled'

    def setUp(self):
        BaseTestCase.setUp(self)
        self.env.config.set('git', 'cached_repository', self.cached_repository)

    def _create_merge_commit(self):
        for idx, branch in enumerate(('alpha', 'beta')):
            self._git('checkout', '-b', branch, 'master')
            for n in xrange(2):
                filename = 'file-%s-%d.txt' % (branch, n)
                create_file(os.path.join(self.repos_path, filename))
                self._git('add', filename)
                self._git_commit('-a', '-m', filename,
                                 date=datetime(2014, 2, 2, 17, 12,
                                               n * 2 + idx))
        self._git('checkout', 'alpha')
        self._git('merge', '-m', 'Merge branch "beta" to "alpha"', 'beta')

    def test_invalid_path_raises(self):
        self.assertRaises(InvalidRepository, GitRepository, self.env,
                          '/the/invalid/path', [], self.env.log)

    def test_repository_instance(self):
        self._git_init()
        self._add_repository('gitrepos')
        self.assertEqual(GitRepository,
                         type(self._repomgr.get_repository('gitrepos')))

    def test_reset_head(self):
        self._git_init()
        create_file(os.path.join(self.repos_path, 'file.txt'), 'text')
        self._git('add', 'file.txt')
        self._git_commit('-a', '-m', 'test',
                         date=datetime(2014, 2, 2, 17, 12, 18))
        self._add_repository('gitrepos')
        repos = self._repomgr.get_repository('gitrepos')
        repos.sync()
        youngest_rev = repos.youngest_rev
        entries = list(repos.get_node('').get_history())
        self.assertEqual(2, len(entries))
        self.assertEqual('', entries[0][0])
        self.assertEqual(Changeset.EDIT, entries[0][2])
        self.assertEqual('', entries[1][0])
        self.assertEqual(Changeset.ADD, entries[1][2])

        self._git('reset', '--hard', 'HEAD~')
        repos.sync()
        new_entries = list(repos.get_node('').get_history())
        self.assertEqual(1, len(new_entries))
        self.assertEqual(new_entries[0], entries[1])
        self.assertNotEqual(youngest_rev, repos.youngest_rev)

    def test_tags(self):
        self._git_init()
        self._add_repository('gitrepos')
        repos = self._repomgr.get_repository('gitrepos')
        repos.sync()
        self.assertEqual(['master'], self._get_quickjump_names(repos))
        self._git('tag', 'v1.0', 'master')  # add tag
        repos.sync()
        self.assertEqual(['master', 'v1.0'], self._get_quickjump_names(repos))
        self._git('tag', '-d', 'v1.0')  # delete tag
        repos.sync()
        self.assertEqual(['master'], self._get_quickjump_names(repos))

    def test_branchs(self):
        self._git_init()
        self._add_repository('gitrepos')
        repos = self._repomgr.get_repository('gitrepos')
        repos.sync()
        self.assertEqual(['master'], self._get_quickjump_names(repos))
        self._git('branch', 'alpha', 'master')  # add branch
        repos.sync()
        self.assertEqual(['master', 'alpha'], self._get_quickjump_names(repos))
        self._git('branch', '-m', 'alpha', 'beta')  # rename branch
        repos.sync()
        self.assertEqual(['master', 'beta'], self._get_quickjump_names(repos))
        self._git('branch', '-D', 'beta')  # delete branch
        repos.sync()
        self.assertEqual(['master'], self._get_quickjump_names(repos))

    def test_changeset_branches_tags(self):
        self._git_init()
        self._git('tag', '0.0.1', 'master')
        self._git('tag', '-m', 'Root commit', 'initial', 'master')
        self._git('branch', 'root', 'master')
        self._git('checkout', '-b', 'dev', 'master')
        self._git_commit('-m', 'Summary', '--allow-empty')
        self._git('tag', '0.1.0dev', 'dev')
        self._git('tag', '0.1.0a', 'dev')
        self._add_repository('gitrepos')
        repos = self._repomgr.get_repository('gitrepos')
        repos.sync()

        def get_branches(repos, rev):
            rev = repos.normalize_rev(rev)
            return list(repos.get_changeset(rev).get_branches())

        def get_tags(repos, rev):
            rev = repos.normalize_rev(rev)
            return list(repos.get_changeset(rev).get_tags())

        self.assertEqual([('dev', False), ('master', True), ('root', True)],
                         get_branches(repos, '0.0.1'))
        self.assertEqual([('dev', True)], get_branches(repos, '0.1.0dev'))
        self.assertEqual(['0.0.1', 'initial'], get_tags(repos, '0.0.1'))
        self.assertEqual(['0.0.1', 'initial'], get_tags(repos, 'initial'))
        self.assertEqual(['0.1.0a', '0.1.0dev'], get_tags(repos, '0.1.0dev'))

    def test_parent_child_revs(self):
        self._git_init()
        self._git('branch', 'initial')  # root commit
        self._create_merge_commit()
        self._git('branch', 'latest')

        self._add_repository('gitrepos')
        repos = self._repomgr.get_repository('gitrepos')
        repos.sync()

        rev = repos.normalize_rev('initial')
        children = repos.child_revs(rev)
        self.assertEqual(2, len(children), 'child_revs: %r' % children)
        parents = repos.parent_revs(rev)
        self.assertEqual(0, len(parents), 'parent_revs: %r' % parents)
        self.assertEqual(1, len(repos.child_revs(children[0])))
        self.assertEqual(1, len(repos.child_revs(children[1])))
        self.assertEqual([('.gitignore', Node.FILE, Changeset.ADD, None,
                           None)],
                         sorted(repos.get_changeset(rev).get_changes()))

        rev = repos.normalize_rev('latest')
        cset = repos.get_changeset(rev)
        children = repos.child_revs(rev)
        self.assertEqual(0, len(children), 'child_revs: %r' % children)
        parents = repos.parent_revs(rev)
        self.assertEqual(2, len(parents), 'parent_revs: %r' % parents)
        self.assertEqual(1, len(repos.parent_revs(parents[0])))
        self.assertEqual(1, len(repos.parent_revs(parents[1])))

        # check the differences against the first parent
        def fn_repos_changes(entry):
            old_node, new_node, kind, change = entry
            if old_node:
                old_path, old_rev = old_node.path, old_node.rev
            else:
                old_path, old_rev = None, None
            return new_node.path, kind, change, old_path, old_rev
        self.assertEqual(sorted(map(fn_repos_changes,
                                    repos.get_changes('/', parents[0], '/',
                                                      rev))),
                         sorted(cset.get_changes()))

    def _get_quickjump_names(self, repos):
        return list(name for type, name, path, rev
                         in repos.get_quickjump_entries('HEAD'))


class GitCachedRepositoryTestCase(GitRepositoryTestCase):

    cached_repository = 'enabled'

    def test_repository_instance(self):
        self._git_init()
        self._add_repository('gitrepos')
        self.assertEqual(GitCachedRepository,
                         type(self._repomgr.get_repository('gitrepos')))

    def test_sync(self):
        self._git_init()
        for idx in xrange(3):
            filename = 'file%d.txt' % idx
            create_file(os.path.join(self.repos_path, filename))
            self._git('add', filename)
            self._git_commit('-a', '-m', filename,
                             date=datetime(2014, 2, 2, 17, 12, idx))
        self._add_repository('gitrepos')
        repos = self._repomgr.get_repository('gitrepos')
        revs = [entry[1] for entry in repos.repos.get_node('').get_history()]
        revs.reverse()
        revs2 = []
        def feedback(rev):
            revs2.append(rev)
        repos.sync(feedback=feedback)
        self.assertEqual(revs, revs2)
        self.assertEqual(4, len(revs2))

        revs2 = []
        def feedback_1(rev):
            revs2.append(rev)
            if len(revs2) == 2:
                raise StopSync
        def feedback_2(rev):
            revs2.append(rev)
        try:
            repos.sync(feedback=feedback_1, clean=True)
        except StopSync:
            self.assertEqual(revs[:2], revs2)
            repos.sync(feedback=feedback_2)  # restart sync
        self.assertEqual(revs, revs2)

    def test_sync_merge(self):
        self._git_init()
        self._create_merge_commit()

        self._add_repository('gitrepos')
        repos = self._repomgr.get_repository('gitrepos')
        youngest_rev = repos.repos.youngest_rev
        oldest_rev = repos.repos.oldest_rev

        revs = []
        def feedback(rev):
            revs.append(rev)
        repos.sync(feedback=feedback)
        self.assertEqual(6, len(revs))
        self.assertEqual(youngest_rev, revs[-1])
        self.assertEqual(oldest_rev, revs[0])

        revs2 = []
        def feedback_1(rev):
            revs2.append(rev)
            if len(revs2) == 3:
                raise StopSync
        def feedback_2(rev):
            revs2.append(rev)
        try:
            repos.sync(feedback=feedback_1, clean=True)
        except StopSync:
            self.assertEqual(revs[:3], revs2)
            repos.sync(feedback=feedback_2)  # restart sync
        self.assertEqual(revs, revs2)

    def test_sync_too_many_merges(self):
        data = self._generate_data_many_merges(100)
        self._git_init(data=False, bare=True)
        self._git_fast_import(data)
        self._add_repository('gitrepos', bare=True)
        repos = self._repomgr.get_repository('gitrepos')

        reclimit = sys.getrecursionlimit()
        try:
            sys.setrecursionlimit(80)
            repos.sync()
        finally:
            sys.setrecursionlimit(reclimit)

        rows = self.env.db_query("SELECT COUNT(*) FROM revision "
                                 "WHERE repos=%s", (repos.id,))
        self.assertEqual(202, rows[0][0])

    def _generate_data_many_merges(self, n, timestamp=1400000000):
        init = """\
blob
mark :1
data 0

reset refs/heads/dev
commit refs/heads/dev
mark :2
author Joe <joe@example.com> %(timestamp)d +0000
committer Joe <joe@example.com> %(timestamp)d +0000
data 5
root
M 100644 :1 .gitignore

commit refs/heads/master
mark :3
author Joe <joe@example.com> %(timestamp)d +0000
committer Joe <joe@example.com> %(timestamp)d +0000
data 7
master
from :2
M 100644 :1 master.txt

"""
        merge = """\
commit refs/heads/dev
mark :%(dev)d
author Joe <joe@example.com> %(timestamp)d +0000
committer Joe <joe@example.com> %(timestamp)d +0000
data 4
dev
from :2
M 100644 :1 dev%(dev)08d.txt

commit refs/heads/master
mark :%(merge)d
author Joe <joe@example.com> %(timestamp)d +0000
committer Joe <joe@example.com> %(timestamp)d +0000
data 19
Merge branch 'dev'
from :%(from)d
merge :%(dev)d
M 100644 :1 dev%(dev)08d.txt

"""
        data = StringIO()
        data.write(init % {'timestamp': timestamp})
        for idx in xrange(n):
            data.write(merge % {'timestamp': timestamp,
                                'dev': 4 + idx * 2,
                                'merge': 5 + idx * 2,
                                'from': 3 + idx * 2})
        return data.getvalue()


class StopSync(Exception):
    pass


def suite():
    suite = unittest.TestSuite()
    if GitCommandMixin.git_bin:
        suite.addTest(unittest.makeSuite(SanityCheckingTestCase))
        suite.addTest(unittest.makeSuite(PersistentCacheTestCase))
        suite.addTest(unittest.makeSuite(HistoryTimeRangeTestCase))
        suite.addTest(unittest.makeSuite(GitNormalTestCase))
        suite.addTest(unittest.makeSuite(GitRepositoryTestCase))
        suite.addTest(unittest.makeSuite(GitCachedRepositoryTestCase))
    else:
        print("SKIP: tracopt/versioncontrol/git/tests/git_fs.py (git cli "
              "binary, 'git', not found)")
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
