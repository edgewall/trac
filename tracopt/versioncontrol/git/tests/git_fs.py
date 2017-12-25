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

import trac.tests.compat
from trac.core import TracError
from trac.test import EnvironmentStub, MockRequest, locate, rmtree
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
                                              GitRepository, \
                                              GitwebProjectsRepositoryProvider


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
        self._close_proc_pipes(proc)
        self.assertEqual(0, proc.returncode,
                         'git exits with %r, args %r, kwargs %r, stdout %r, '
                         'stderr %r' %
                         (proc.returncode, args, kwargs, stdout, stderr))
        return proc

    def _git_fast_import(self, data, **kwargs):
        if isinstance(data, unicode):
            data = data.encode('utf-8')
        proc = self._spawn_git('fast-import', stdin=PIPE, **kwargs)
        stdout, stderr = proc.communicate(input=data)
        self._close_proc_pipes(proc)
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

    def _close_proc_pipes(self, proc):
        for f in (proc.stdin, proc.stdout, proc.stderr):
            if f:
                f.close()


class BaseTestCase(unittest.TestCase, GitCommandMixin):

    def setUp(self):
        self.env = EnvironmentStub()
        self.tmpdir = tempfile.mkdtemp(prefix='trac-tempdir-')
        self.repos_path = os.path.join(self.tmpdir, 'gitrepos')
        os.mkdir(self.repos_path)
        if self.git_bin:
            self.env.config.set('git', 'git_bin', self.git_bin)

    def tearDown(self):
        for repos in self._repomgr.get_real_repositories():
            repos.close()
        self._repomgr.reload_repositories()
        StorageFactory._clean()
        self.env.reset_db()
        if os.path.isdir(self.tmpdir):
            rmtree(self.tmpdir)

    @property
    def _repomgr(self):
        return RepositoryManager(self.env)

    @property
    def _dbrepoprov(self):
        return DbRepositoryProvider(self.env)

    def _add_repository(self, reponame='gitrepos', bare=False, path=None):
        if path is None:
            path = self.repos_path
        if not bare:
            path = os.path.join(path, '.git')
        self._dbrepoprov.add_repository(reponame, path, 'git')

    def _git_init(self, data=True, bare=False, **kwargs):
        if bare:
            self._git('init', '--bare', **kwargs)
        else:
            self._git('init', **kwargs)
        if not bare and data:
            self._git('config', 'user.name', 'Joe', **kwargs)
            self._git('config', 'user.email', 'joe@example.com', **kwargs)
            create_file(os.path.join(self.repos_path, '.gitignore'))
            self._git('add', '.gitignore', **kwargs)
            self._git_commit('-a', '-m', 'test',
                             date=datetime(2001, 1, 29, 16, 39, 56), **kwargs)


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
        self.assertEqual(None, repos.display_rev(''))
        self.assertEqual(None, repos.display_rev(None))
        self.assertEqual(None, repos.short_rev(''))
        self.assertEqual(None, repos.short_rev(None))

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
        def try_init(reponame):
            params = {'name': reponame}
            try:
                GitRepository(self.env, '/the/invalid/path', params,
                              self.env.log)
                self.fail('InvalidRepository not raised')
            except InvalidRepository as e:
                return e

        e = try_init('')
        self.assertEqual('"(default)" is not readable or not a Git '
                         'repository.', unicode(e))

        e = try_init('therepos')
        self.assertEqual('"therepos" is not readable or not a Git repository.',
                         unicode(e))

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

    _data_annotations = """\
blob
mark :1
data 14
one
two
three

reset refs/heads/master
commit refs/heads/master
mark :2
author Joe <joe@example.com> 1467172510 +0000
committer Joe <joe@example.com> 1467172510 +0000
data 6
blame
M 100644 :1 test.txt

blob
mark :3
data 49
one
two
three
four
five
six
seven
eight
nine
ten

commit refs/heads/master
mark :4
author Joe <joe@example.com> 1467172511 +0000
committer Joe <joe@example.com> 1467172511 +0000
data 10
add lines
from :2
M 100644 :3 test.txt

blob
mark :5
data 40
one
two
3
four
five
6
seven
eight
9
ten

commit refs/heads/master
mark :6
author Joe <joe@example.com> 1467172512 +0000
committer Joe <joe@example.com> 1467172512 +0000
data 13
modify lines
from :4
M 100644 :5 test.txt

reset refs/heads/master
from :6

"""

    def test_get_annotations(self):
        self._git_init(data=False)
        self._git_fast_import(self._data_annotations)
        self._add_repository('gitrepos')
        repos = self._repomgr.get_repository('gitrepos')
        repos.sync()

        rev1 = 'a7efe353630d02139f255220d71b76fa68eb7132'  # root commit
        rev2 = 'f928d1b36b8bedf64bcf08667428fdcccf36b21b'
        rev3 = '279a097f111c7cb1ef0b9da39735188051fd4f69'  # HEAD

        self.assertEqual([rev1] * 3,
                         repos.get_node('test.txt', rev1).get_annotations())
        self.assertEqual([rev1] * 3 + [rev2] * 7,
                         repos.get_node('test.txt', rev2).get_annotations())

        expected = [rev1, rev1, rev3, rev2, rev2, rev3, rev2, rev2, rev3, rev2]
        self.assertEqual(expected,
                         repos.get_node('test.txt', rev3).get_annotations())
        self.assertEqual(expected,
                         repos.get_node('test.txt', 'HEAD').get_annotations())
        self.assertEqual(expected,
                         repos.get_node('test.txt').get_annotations())

    # *   79dff4ccf842f8e2d2da2ee3e7a2149df63b099b Merge branch 'A'
    # |\
    # | *   86387120095e9e43573bce61b9da70a8c5d1c1b9 Merge branch 'B' into A
    # | |\
    # | | * 64e12f96b6b3040cd9edc225734ab2b26a03758b Changed a1
    # | * | 67fdcf11e2d083b123b9a79be4fce0600f313f81 Changed a2
    # * | | 42fbe758709b2a65aba33e56b2f53cd126c190e3 Changed b2
    # | |/
    # |/|
    # * | 24d94dc08eb77438e4ead192b3f7d1c7bdf1a9e1 Changed b2
    # * | 998bf23843c8fd982bbc23f88ec33c4d08114557 Changed b1
    # |/
    # * c5b01c74e125aa034a1d4ae31dc16f1897a73779 First commit
    _data_iter_nodes = """\
blob
mark :1
data 2
a1
blob
mark :2
data 2
a2
blob
mark :3
data 2
b1
blob
mark :4
data 2
b2
reset refs/heads/A
commit refs/heads/A
mark :5
author Joe <joe@example.com> 1470744252 +0000
committer Joe <joe@example.com> 1470744252 +0000
data 13
First commit
M 100644 :1 A/a1.txt
M 100644 :2 A/a2.txt
M 100644 :3 B/b1.txt
M 100644 :4 B/b2.txt

blob
mark :6
data 4
b1-1
commit refs/heads/master
mark :7
author Joe <joe@example.com> 1470744253 +0000
committer Joe <joe@example.com> 1470744253 +0000
data 11
Changed b1
from :5
M 100644 :6 B/b1.txt

blob
mark :8
data 4
b2-1
commit refs/heads/master
mark :9
author Joe <joe@example.com> 1470744254 +0000
committer Joe <joe@example.com> 1470744254 +0000
data 11
Changed b2
from :7
M 100644 :8 B/b2.txt

blob
mark :10
data 4
b2-2
commit refs/heads/master
mark :11
author Joe <joe@example.com> 1470744255 +0000
committer Joe <joe@example.com> 1470744255 +0000
data 11
Changed b2
from :9
M 100644 :10 B/b2.txt

blob
mark :12
data 4
a2-1
commit refs/heads/A
mark :13
author Joe <joe@example.com> 1470744256 +0000
committer Joe <joe@example.com> 1470744256 +0000
data 11
Changed a2
from :5
M 100644 :12 A/a2.txt

blob
mark :14
data 4
a1-1
commit refs/heads/B
mark :15
author Joe <joe@example.com> 1470744257 +0000
committer Joe <joe@example.com> 1470744257 +0000
data 11
Changed a1
from :9
M 100644 :14 A/a1.txt

commit refs/heads/A
mark :16
author Joe <joe@example.com> 1470744258 +0000
committer Joe <joe@example.com> 1470744258 +0000
data 24
Merge branch 'B' into A
from :13
merge :15
M 100644 :14 A/a1.txt
M 100644 :6 B/b1.txt
M 100644 :8 B/b2.txt

commit refs/heads/master
mark :17
author Joe <joe@example.com> 1470744259 +0000
committer Joe <joe@example.com> 1470744259 +0000
data 17
Merge branch 'A'
from :11
merge :16
M 100644 :14 A/a1.txt
M 100644 :12 A/a2.txt

reset refs/heads/master
from :17

"""

    def test_iter_nodes(self):
        self._git_init(data=False)
        self._git_fast_import(self._data_iter_nodes)
        self._add_repository('gitrepos')
        repos = self._repomgr.get_repository('gitrepos')
        repos.sync()
        mod = BrowserModule(self.env)

        root_node = repos.get_node('')
        nodes = list(mod._iter_nodes(root_node))
        self.assertEqual(['79dff4ccf842f8e2d2da2ee3e7a2149df63b099b'] * 7,
                         [node.rev for node in nodes])
        self.assertEqual([
            ('79dff4ccf842f8e2d2da2ee3e7a2149df63b099b', ''),
            ('64e12f96b6b3040cd9edc225734ab2b26a03758b', 'A'),
            ('64e12f96b6b3040cd9edc225734ab2b26a03758b', 'A/a1.txt'),
            ('67fdcf11e2d083b123b9a79be4fce0600f313f81', 'A/a2.txt'),
            ('42fbe758709b2a65aba33e56b2f53cd126c190e3', 'B'),
            ('998bf23843c8fd982bbc23f88ec33c4d08114557', 'B/b1.txt'),
            ('42fbe758709b2a65aba33e56b2f53cd126c190e3', 'B/b2.txt'),
            ], [(node.created_rev, node.path) for node in nodes])

        root_node = repos.get_node('',
                                   '86387120095e9e43573bce61b9da70a8c5d1c1b9')
        nodes = list(mod._iter_nodes(root_node))
        self.assertEqual(['86387120095e9e43573bce61b9da70a8c5d1c1b9'] * 7,
                         [node.rev for node in nodes])
        self.assertEqual([
            ('86387120095e9e43573bce61b9da70a8c5d1c1b9', ''),
            ('64e12f96b6b3040cd9edc225734ab2b26a03758b', 'A'),
            ('64e12f96b6b3040cd9edc225734ab2b26a03758b', 'A/a1.txt'),
            ('67fdcf11e2d083b123b9a79be4fce0600f313f81', 'A/a2.txt'),
            ('24d94dc08eb77438e4ead192b3f7d1c7bdf1a9e1', 'B'),
            ('998bf23843c8fd982bbc23f88ec33c4d08114557', 'B/b1.txt'),
            ('24d94dc08eb77438e4ead192b3f7d1c7bdf1a9e1', 'B/b2.txt'),
            ], [(node.created_rev, node.path) for node in nodes])

        root_commit = 'c5b01c74e125aa034a1d4ae31dc16f1897a73779'
        root_node = repos.get_node('', root_commit)
        nodes = list(mod._iter_nodes(root_node))
        self.assertEqual([root_commit] * 7, [node.rev for node in nodes])
        self.assertEqual([
            (root_commit, ''),
            (root_commit, 'A'),
            (root_commit, 'A/a1.txt'),
            (root_commit, 'A/a2.txt'),
            (root_commit, 'B'),
            (root_commit, 'B/b1.txt'),
            (root_commit, 'B/b2.txt'),
            ], [(node.created_rev, node.path) for node in nodes])

    def test_colon_character_in_filename(self):
        self._git_init(data=False)
        self._git_fast_import(self._data_colon_character_in_filename)
        self._add_repository('gitrepos')
        repos = self._repomgr.get_repository('gitrepos')
        repos.sync()
        rev1 = '382e1e6b85ba20ce8a84af1a875eaa50b8e1e092'  # root commit
        rev2 = 'd8001832aad079f85a39a54a388a8b15fe31093d'
        ADD = Changeset.ADD
        MOVE = Changeset.MOVE
        FILE = Node.FILE

        cset = repos.get_changeset(rev1)
        self.assertEqual(set([('0100644',     FILE, ADD, None, None),
                              ('0100644.txt', FILE, ADD, None, None),
                              (':100644',     FILE, ADD, None, None),
                              (':100644.txt', FILE, ADD, None, None),
                              ('a100644',     FILE, ADD, None, None),
                              ('a100644.txt', FILE, ADD, None, None)
                             ]),
                         set(cset.get_changes()))

        cset = repos.get_changeset(rev2)
        self.assertEqual(set([(':100666', FILE, MOVE, ':100644', rev1)]),
                         set(cset.get_changes()))

    _data_colon_character_in_filename = """\
blob
mark :1
data 0

blob
mark :2
data 16
...............

reset refs/heads/master
commit refs/heads/master
mark :3
author Joe <joe@example.com> 1491387182 +0000
committer Joe <joe@example.com> 1491387182 +0000
data 9
(#12758)
M 100644 :1 0100644.txt
M 100644 :1 0100644
M 100644 :1 :100644.txt
M 100644 :2 :100644
M 100644 :1 a100644.txt
M 100644 :1 a100644

commit refs/heads/master
mark :4
author Joe <joe@example.com> 1491387183 +0000
committer Joe <joe@example.com> 1491387183 +0000
data 16
(#12758) rename
from :3
D :100644
M 100644 :2 :100666

reset refs/heads/master
from :4
"""

    def test_submodule(self):
        subrepos_path = os.path.join(self.tmpdir, 'subrepos')
        submodule_dir = os.path.join(self.repos_path, 'sub')
        os.mkdir(subrepos_path)
        self._git_init(data=False, bare=True, cwd=subrepos_path)
        self._git_fast_import(self._data_submodule, cwd=subrepos_path)

        submodule_rev1 = '3e733d786b3529d750ee39edacea2f1c4daadca4'
        self._git_init()
        self._git('submodule', 'add', subrepos_path, 'sub')
        self._git('checkout', submodule_rev1, cwd=submodule_dir)
        self._git('add', '.gitmodules')
        self._git_commit('-a', '-m', 'init submodule')
        self._git('tag', 'v1', 'master')
        self._add_repository('gitrepos')
        repos = self._repomgr.get_repository('gitrepos')
        repos.sync()

        ADD = Changeset.ADD
        EDIT = Changeset.EDIT
        FILE = Node.FILE
        DIRECTORY = Node.DIRECTORY

        rev1 = repos.normalize_rev('v1')
        cset1 = repos.get_changeset(rev1)
        self.assertEqual([('.gitmodules', FILE,      ADD, None, None),
                          ('sub',         DIRECTORY, ADD, None, None)],
                         sorted(cset1.get_changes()))
        node1 = repos.get_node('sub', rev1)
        self.assertEqual(None, node1.get_content())
        self.assertEqual(None, node1.get_content_length())
        self.assertEqual(DIRECTORY, node1.kind)
        self.assertEqual({'mode': '160000', 'commit': submodule_rev1},
                         node1.get_properties())
        self.assertEqual([], list(node1.get_entries()))

        submodule_rev2 = '409058dc98500b5685c52a091cc9f44f3975113e'
        self._git('checkout', submodule_rev2, cwd=submodule_dir)
        self._git_commit('-a', '-m', 'change rev of the submodule')
        self._git('tag', 'v2', 'master')
        repos.sync()
        rev2 = repos.normalize_rev('v2')
        cset2 = repos.get_changeset(rev2)
        self.assertEqual([('sub', DIRECTORY, EDIT, 'sub', rev1)],
                         sorted(cset2.get_changes()))
        node2 = repos.get_node('sub', rev2)
        self.assertEqual({'mode': '160000', 'commit': submodule_rev2},
                         node2.get_properties())

    _data_submodule = """\
blob
mark :1
data 0

blob
mark :2
data 16
...............

# <= 3e733d786b3529d750ee39edacea2f1c4daadca4
reset refs/heads/master
commit refs/heads/master
mark :3
author Joe <joe@example.com> 1512643825 +0000
committer Joe <joe@example.com> 1512643825 +0000
data 12
root commit
M 100644 :1 001-001.txt
M 100644 :2 001-002.txt
M 100644 :2 001-003.txt

# <= 409058dc98500b5685c52a091cc9f44f3975113e
commit refs/heads/master
mark :4
author Joe <joe@example.com> 1512643826 +0000
committer Joe <joe@example.com> 1512643826 +0000
data 10
2nd commit
from :3
M 100644 :1 002-001.txt
M 100644 :2 002-002.txt

reset refs/heads/master
from :4
"""

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

    def test_sync_file_with_invalid_byte_sequence(self):
        self._git_init(data=False)
        self._git_fast_import("""\
blob
mark :1
data 0

reset refs/heads/master
commit refs/heads/master
mark :2
author Ryan Ollos <rjollos@edgewall.com> 1463639119 +0200
committer Ryan Ollos <rjollos@edgewall.com> 1463639119 +0200
data 9
(#12322)
M 100644 :1 "\312\326\267\347\307\331.txt"

reset refs/heads/master
from :2

""")
        self._add_repository('gitrepos')
        repos = self._repomgr.get_repository('gitrepos')

        revs = []
        def feedback(rev):
            revs.append(rev)
        repos.sync(feedback=feedback)

        changes = list(repos.repos.get_changeset(revs[0]).get_changes())
        self.assertEqual(1, len(changes))
        self.assertEqual(u'\ufffd\u05b7\ufffd\ufffd\ufffd.txt', changes[0][0])

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

    def test_sync_many_refs(self):
        n_refs = 1500
        data = self._generate_data_many_refs(n_refs)
        self._git_init(data=False, bare=True)
        self._git_fast_import(data)
        self._add_repository('gitrepos', bare=True)
        repos = self._repomgr.get_repository('gitrepos')

        revs = []
        def feedback(rev):
            revs.append(rev)
        repos.sync(feedback)  # create cache
        self.assertEqual(n_refs + 1, len(revs))

        revs[:] = ()
        repos.sync(feedback)  # check whether all refs are cached
        self.assertEqual(0, len(revs))

        rows = self.env.db_query("SELECT COUNT(*) FROM revision "
                                 "WHERE repos=%s", (repos.id,))
        self.assertEqual(n_refs + 1, rows[0][0])

    def _generate_data_many_refs(self, n, timestamp=1400000000):
        root_commit = """\
blob
mark :1
data 0

reset refs/heads/master
commit refs/heads/master
mark :2
author Joe <joe@example.com> %(timestamp)d +0000
committer Joe <joe@example.com> %(timestamp)d +0000
data 12
root commit
M 100644 :1 .gitignore
"""
        ref_commit = """
commit refs/heads/ref-%(ref)08d
mark :%(mark)d
author Joe <joe@example.com> %(timestamp)d +0000
committer Joe <joe@example.com> %(timestamp)d +0000
data 13
ref-%(ref)08d
from :2
"""
        data = StringIO()
        data.write(root_commit % {'timestamp': timestamp})
        for idx in xrange(n):
            data.write(ref_commit % {'timestamp': timestamp + idx,
                                     'mark': idx + 3, 'ref': idx})
        return data.getvalue()


class GitwebProjectsRepositoryProviderTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub()
        self.projects_base = os.path.realpath(tempfile.mkdtemp())
        self.projects_list = os.path.join(self.projects_base, 'projects_list')
        with open(self.projects_list, 'w') as f:
            f.write("""
            repos1 user1
            repos2.git user+2+<user@example.com>

            repos3
            """)
        self.env.config.set('gitweb-repositories', 'projects_list',
                            self.projects_list)
        self.env.config.set('gitweb-repositories', 'projects_base',
                            self.projects_base)
        self.env.config.set('gitweb-repositories', 'projects_url',
                            'https://example.com/%s')

    def tearDown(self):
        self.env.shutdown()
        rmtree(self.projects_base)

    def test_project_list_path_not_found(self):
        """Warning is logged when projects_list file is not found, but
        exception is not raised.
        """
        os.remove(self.projects_list)
        provider = GitwebProjectsRepositoryProvider(self.env)
        repositories = list(provider.get_repositories())

        self.assertEqual([], repositories)

    def test_get_repositories(self):
        provider = GitwebProjectsRepositoryProvider(self.env)
        repositories = list(provider.get_repositories())

        self.assertEqual(3, len(repositories))
        self.assertEqual('repos1', repositories[0][0])
        self.assertEqual('git', repositories[0][1]['type'])
        self.assertEqual(os.path.join(self.projects_base, 'repos1'),
                         repositories[0][1]['dir'])
        self.assertEqual('https://example.com/repos1',
                         repositories[0][1]['url'])
        self.assertEqual('repos2', repositories[1][0])
        self.assertEqual('git', repositories[1][1]['type'])
        self.assertEqual(os.path.join(self.projects_base, 'repos2.git'),
                         repositories[1][1]['dir'])
        self.assertEqual('https://example.com/repos2',
                         repositories[1][1]['url'])
        self.assertEqual('repos3', repositories[2][0])
        self.assertEqual('git', repositories[2][1]['type'])
        self.assertEqual(os.path.join(self.projects_base, 'repos3'),
                         repositories[2][1]['dir'])
        self.assertEqual('https://example.com/repos3',
                         repositories[2][1]['url'])



class StopSync(Exception):
    pass


class GitConnectorTestCase(BaseTestCase):

    def _git_version_from_system_info(self):
        git_version = None
        for name, version in self.env.get_systeminfo():
            if name == 'GIT':
                git_version = version
        return git_version

    def test_get_system_info(self):
        self.assertIsNotNone(self._git_version_from_system_info())


def test_suite():
    suite = unittest.TestSuite()
    if GitCommandMixin.git_bin:
        suite.addTest(unittest.makeSuite(SanityCheckingTestCase))
        suite.addTest(unittest.makeSuite(PersistentCacheTestCase))
        suite.addTest(unittest.makeSuite(HistoryTimeRangeTestCase))
        suite.addTest(unittest.makeSuite(GitNormalTestCase))
        suite.addTest(unittest.makeSuite(GitRepositoryTestCase))
        suite.addTest(unittest.makeSuite(GitCachedRepositoryTestCase))
        suite.addTest(unittest.makeSuite(GitConnectorTestCase))
        suite.addTest(unittest.makeSuite(GitwebProjectsRepositoryProviderTestCase))
    else:
        print("SKIP: tracopt/versioncontrol/git/tests/git_fs.py (git cli "
              "binary, 'git', not found)")
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
