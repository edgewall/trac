# -*- coding: utf-8 -*-
#
# Copyright (C) 2012 Edgewall Software
# Copyright (C) 2006-2011, Herbert Valerio Riedel <hvr@gnu.org>
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
import codecs
from collections import deque
from contextlib import contextmanager
import cStringIO
from functools import partial
from operator import itemgetter
import re
from subprocess import Popen, PIPE
import sys
from threading import Lock
import time
import weakref


__all__ = ['GitError', 'GitErrorSha', 'Storage', 'StorageFactory']


def terminate(process):
    """Python 2.5 compatibility method.
    os.kill is not available on Windows before Python 2.7.
    In Python 2.6 subprocess.Popen has a terminate method.
    (It also seems to have some issues on Windows though.)
    """

    def terminate_win(process):
        import ctypes
        PROCESS_TERMINATE = 1
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_TERMINATE,
                                                    False,
                                                    process.pid)
        ctypes.windll.kernel32.TerminateProcess(handle, -1)
        ctypes.windll.kernel32.CloseHandle(handle)

    def terminate_nix(process):
        import os
        import signal
        return os.kill(process.pid, signal.SIGTERM)

    if sys.platform == 'win32':
        return terminate_win(process)
    return terminate_nix(process)


class GitError(Exception):
    pass

class GitErrorSha(GitError):
    pass

# Helper functions

def parse_commit(raw):
    """Parse the raw content of a commit (as given by `git cat-file -p <rev>`).

    Return the commit message and a dict of properties.
    """
    if not raw:
        raise GitErrorSha
    lines = raw.splitlines()
    if not lines:
        raise GitErrorSha
    line = lines.pop(0)
    props = {}
    multiline = multiline_key = None
    while line:
        if line[0] == ' ':
            if not multiline:
                multiline_key = key
                multiline = [props[multiline_key][-1]]
            multiline.append(line[1:])
        else:
            key, value = line.split(None, 1)
            props.setdefault(key, []).append(value.strip())
        line = lines.pop(0)
        if multiline and (not line or key != multiline_key):
            props[multiline_key][-1] = '\n'.join(multiline)
            multiline = None
    return '\n'.join(lines), props


class GitCore(object):
    """Low-level wrapper around git executable"""

    def __init__(self, git_dir=None, git_bin='git'):
        self.__git_bin = git_bin
        self.__git_dir = git_dir

    def __repr__(self):
        return '<GitCore bin="%s" dir="%s">' % (self.__git_bin,
                                                self.__git_dir)

    def __build_git_cmd(self, gitcmd, *args):
        """construct command tuple for git call suitable for Popen()"""

        cmd = [self.__git_bin]
        if self.__git_dir:
            cmd.append('--git-dir=%s' % self.__git_dir)
        cmd.append(gitcmd)
        cmd.extend(args)

        return cmd

    def __pipe(self, git_cmd, *cmd_args, **kw):
        if sys.platform == 'win32':
            return Popen(self.__build_git_cmd(git_cmd, *cmd_args), **kw)
        else:
            return Popen(self.__build_git_cmd(git_cmd, *cmd_args),
                         close_fds=True, **kw)

    def __execute(self, git_cmd, *cmd_args):
        """execute git command and return file-like object of stdout"""

        #print >>sys.stderr, "DEBUG:", git_cmd, cmd_args

        p = self.__pipe(git_cmd, stdout=PIPE, stderr=PIPE, *cmd_args)

        stdout_data, stderr_data = p.communicate()
        #TODO, do something with p.returncode, e.g. raise exception

        return stdout_data

    def cat_file_batch(self):
        return self.__pipe('cat-file', '--batch', stdin=PIPE, stdout=PIPE)

    def log_pipe(self, *cmd_args):
        return self.__pipe('log', stdout=PIPE, *cmd_args)

    def __getattr__(self, name):
        if name[0] == '_' or name in ['cat_file_batch', 'log_pipe']:
            raise AttributeError, name
        return partial(self.__execute, name.replace('_','-'))

    __is_sha_pat = re.compile(r'[0-9A-Fa-f]*$')

    @classmethod
    def is_sha(cls, sha):
        """returns whether sha is a potential sha id
        (i.e. proper hexstring between 4 and 40 characters)
        """

        # quick test before starting up regexp matcher
        if not (4 <= len(sha) <= 40):
            return False

        return bool(cls.__is_sha_pat.match(sha))


class SizedDict(dict):
    """Size-bounded dictionary with FIFO replacement strategy"""

    def __init__(self, max_size=0):
        dict.__init__(self)
        self.__max_size = max_size
        self.__key_fifo = deque()
        self.__lock = Lock()

    def __setitem__(self, name, value):
        with self.__lock:
            assert len(self) == len(self.__key_fifo) # invariant

            if not self.__contains__(name):
                self.__key_fifo.append(name)

            rc = dict.__setitem__(self, name, value)

            while len(self.__key_fifo) > self.__max_size:
                self.__delitem__(self.__key_fifo.popleft())

            assert len(self) == len(self.__key_fifo) # invariant

            return rc

    def setdefault(self, *_):
        raise NotImplemented("SizedDict has no setdefault() method")


class StorageFactory(object):
    __dict = weakref.WeakValueDictionary()
    __dict_nonweak = dict()
    __dict_lock = Lock()

    def __init__(self, repo, log, weak=True, git_bin='git',
                 git_fs_encoding=None):
        self.logger = log

        with StorageFactory.__dict_lock:
            try:
                i = StorageFactory.__dict[repo]
            except KeyError:
                i = Storage(repo, log, git_bin, git_fs_encoding)
                StorageFactory.__dict[repo] = i

                # create or remove additional reference depending on 'weak'
                # argument
                if weak:
                    try:
                        del StorageFactory.__dict_nonweak[repo]
                    except KeyError:
                        pass
                else:
                    StorageFactory.__dict_nonweak[repo] = i

        self.__inst = i
        self.__repo = repo

    def getInstance(self):
        is_weak = self.__repo not in StorageFactory.__dict_nonweak
        self.logger.debug("requested %sPyGIT.Storage instance %d for '%s'"
                          % (("","weak ")[is_weak], id(self.__inst),
                             self.__repo))
        return self.__inst


class Storage(object):
    """High-level wrapper around GitCore with in-memory caching"""

    __SREV_MIN = 4 # minimum short-rev length


    class RevCache(tuple):
        """RevCache(youngest_rev, oldest_rev, rev_dict, tag_set, srev_dict,
                    branch_dict)

        In Python 2.7 this class could be defined by:
            from collections import namedtuple
            RevCache = namedtuple('RevCache', 'youngest_rev oldest_rev '
                                              'rev_dict tag_set srev_dict '
                                              'branch_dict')
        This implementation is what that code generator would produce.
        """

        __slots__ = ()

        _fields = ('youngest_rev', 'oldest_rev', 'rev_dict', 'tag_set',
                   'srev_dict', 'branch_dict')

        def __new__(cls, youngest_rev, oldest_rev, rev_dict, tag_set,
                    srev_dict, branch_dict):
            return tuple.__new__(cls, (youngest_rev, oldest_rev, rev_dict,
                                 tag_set, srev_dict, branch_dict))

        @classmethod
        def _make(cls, iterable, new=tuple.__new__, len=len):
            """Make a new RevCache object from a sequence or iterable"""
            result = new(cls, iterable)
            if len(result) != 6:
                raise TypeError('Expected 6 arguments, got %d' % len(result))
            return result

        def __repr__(self):
            return 'RevCache(youngest_rev=%r, oldest_rev=%r, rev_dict=%r, ' \
                   'tag_set=%r, srev_dict=%r, branch_dict=%r)' % self

        def _asdict(t):
            """Return a new dict which maps field names to their values"""
            return {'youngest_rev': t[0], 'oldest_rev': t[1],
                    'rev_dict': t[2], 'tag_set': t[3], 'srev_dict': t[4],
                    'branch_dict': t[5]}

        def _replace(self, **kwds):
            """Return a new RevCache object replacing specified fields with
            new values
            """
            result = self._make(map(kwds.pop, ('youngest_rev', 'oldest_rev',
                'rev_dict', 'tag_set', 'srev_dict', 'branch_dict'), self))
            if kwds:
                raise ValueError("Got unexpected field names: %r"
                                 % kwds.keys())
            return result

        def __getnewargs__(self):
            return tuple(self)

        youngest_rev = property(itemgetter(0))
        oldest_rev = property(itemgetter(1))
        rev_dict = property(itemgetter(2))
        tag_set = property(itemgetter(3))
        srev_dict = property(itemgetter(4))
        branch_dict = property(itemgetter(5))


    @staticmethod
    def __rev_key(rev):
        assert len(rev) >= 4
        #assert GitCore.is_sha(rev)
        srev_key = int(rev[:4], 16)
        assert srev_key >= 0 and srev_key <= 0xffff
        return srev_key

    @staticmethod
    def git_version(git_bin='git'):
        GIT_VERSION_MIN_REQUIRED = (1, 5, 6)
        try:
            g = GitCore(git_bin=git_bin)
            [v] = g.version().splitlines()
            version = v.strip().split()[2]
            # 'version' has usually at least 3 numeric version
            # components, e.g.::
            #  1.5.4.2
            #  1.5.4.3.230.g2db511
            #  1.5.4.GIT

            def try_int(s):
                try:
                    return int(s)
                except ValueError:
                    return s

            split_version = tuple(map(try_int, version.split('.')))

            result = {}
            result['v_str'] = version
            result['v_tuple'] = split_version
            result['v_min_tuple'] = GIT_VERSION_MIN_REQUIRED
            result['v_min_str'] = ".".join(map(str, GIT_VERSION_MIN_REQUIRED))
            result['v_compatible'] = split_version >= GIT_VERSION_MIN_REQUIRED
            return result

        except Exception, e:
            raise GitError("Could not retrieve GIT version (tried to "
                           "execute/parse '%s --version' but got %s)"
                           % (git_bin, repr(e)))

    def __init__(self, git_dir, log, git_bin='git', git_fs_encoding=None):
        """Initialize PyGit.Storage instance

        `git_dir`: path to .git folder;
                this setting is not affected by the `git_fs_encoding` setting

        `log`: logger instance

        `git_bin`: path to executable
                this setting is not affected by the `git_fs_encoding` setting

        `git_fs_encoding`: encoding used for paths stored in git repository;
                if `None`, no implicit decoding/encoding to/from
                unicode objects is performed, and bytestrings are
                returned instead
        """

        self.logger = log

        self.commit_encoding = None

        # caches
        self.__rev_cache = None
        self.__rev_cache_lock = Lock()

        # cache the last 200 commit messages
        self.__commit_msg_cache = SizedDict(200)
        self.__commit_msg_lock = Lock()

        self.__cat_file_pipe = None
        self.__cat_file_pipe_lock = Lock()

        if git_fs_encoding is not None:
            # validate encoding name
            codecs.lookup(git_fs_encoding)

            # setup conversion functions
            self._fs_to_unicode = lambda s: s.decode(git_fs_encoding)
            self._fs_from_unicode = lambda s: s.encode(git_fs_encoding)
        else:
            # pass bytestrings as-is w/o any conversion
            self._fs_to_unicode = self._fs_from_unicode = lambda s: s

        # simple sanity checking
        __git_file_path = partial(os.path.join, git_dir)
        if not all(map(os.path.exists,
                       map(__git_file_path,
                           ['HEAD','objects','refs']))):
            self.logger.error("GIT control files missing in '%s'" % git_dir)
            if os.path.exists(__git_file_path('.git')):
                self.logger.error("entry '.git' found in '%s'"
                                  " -- maybe use that folder instead..."
                                  % git_dir)
            raise GitError("GIT control files not found, maybe wrong "
                           "directory?")

        self.repo = GitCore(git_dir, git_bin=git_bin)

        self.logger.debug("PyGIT.Storage instance %d constructed" % id(self))

    def __del__(self):
        with self.__cat_file_pipe_lock:
            if self.__cat_file_pipe is not None:
                self.__cat_file_pipe.stdin.close()
                terminate(self.__cat_file_pipe)
                self.__cat_file_pipe.wait()

    #
    # cache handling
    #

    # called by Storage.sync()
    def __rev_cache_sync(self, youngest_rev=None):
        """invalidates revision db cache if necessary"""

        with self.__rev_cache_lock:
            need_update = False
            if self.__rev_cache:
                last_youngest_rev = self.__rev_cache.youngest_rev
                if last_youngest_rev != youngest_rev:
                    self.logger.debug("invalidated caches (%s != %s)"
                                      % (last_youngest_rev, youngest_rev))
                    need_update = True
            else:
                need_update = True # almost NOOP

            if need_update:
                self.__rev_cache = None

            return need_update

    def get_rev_cache(self):
        """Retrieve revision cache

        may rebuild cache on the fly if required

        returns RevCache tuple
        """

        with self.__rev_cache_lock:
            if self.__rev_cache is None:
                # can be cleared by Storage.__rev_cache_sync()
                self.logger.debug("triggered rebuild of commit tree db "
                                  "for %d" % id(self))
                ts0 = time.time()

                youngest = None
                oldest = None
                new_db = {} # db
                new_sdb = {} # short_rev db

                # helper for reusing strings
                __rev_seen = {}
                def __rev_reuse(rev):
                    rev = str(rev)
                    return __rev_seen.setdefault(rev, rev)

                new_tags = set(__rev_reuse(rev.strip())
                               for rev in self.repo.rev_parse('--tags')
                                                   .splitlines())

                new_branches = [(k, __rev_reuse(v))
                                for k, v in self._get_branches()]
                head_revs = set(v for _, v in new_branches)

                rev = ord_rev = 0
                for ord_rev, revs in enumerate(
                                        self.repo.rev_list('--parents',
                                                           '--topo-order',
                                                           '--all')
                                                 .splitlines()):
                    revs = map(__rev_reuse, revs.strip().split())

                    rev = revs[0]

                    # first rev seen is assumed to be the youngest one
                    if not ord_rev:
                        youngest = rev

                    # shortrev "hash" map
                    srev_key = self.__rev_key(rev)
                    new_sdb.setdefault(srev_key, []).append(rev)

                    # parents
                    parents = tuple(revs[1:])

                    # new_db[rev] = (children(rev), parents(rev),
                    #                ordinal_id(rev), rheads(rev))
                    if rev in new_db:
                        # (incomplete) entry was already created by children
                        _children, _parents, _ord_rev, _rheads = new_db[rev]
                        assert _children
                        assert not _parents
                        assert _ord_rev == 0

                        if rev in head_revs and rev not in _rheads:
                            _rheads.append(rev)

                    else: # new entry
                        _children = []
                        _rheads = [rev] if rev in head_revs else []

                    # create/update entry
                    # transform lists into tuples since entry will be final
                    new_db[rev] = tuple(_children), tuple(parents), \
                                  ord_rev + 1, tuple(_rheads)

                    # update parents(rev)s
                    for parent in parents:
                        # by default, a dummy ordinal_id is used
                        # for the mean-time
                        _children, _parents, _ord_rev, _rheads2 = \
                            new_db.setdefault(parent, ([], [], 0, []))

                        # update parent(rev)'s children
                        if rev not in _children:
                            _children.append(rev)

                        # update parent(rev)'s rheads
                        for rev in _rheads:
                            if rev not in _rheads2:
                                _rheads2.append(rev)

                # last rev seen is assumed to be the oldest
                # one (with highest ord_rev)
                oldest = rev

                __rev_seen = None

                # convert sdb either to dict or array depending on size
                tmp = [()]*(max(new_sdb.keys())+1) \
                      if len(new_sdb) > 5000 else {}

                try:
                    while True:
                        k, v = new_sdb.popitem()
                        tmp[k] = tuple(v)
                except KeyError:
                    pass

                assert len(new_sdb) == 0
                new_sdb = tmp

                # atomically update self.__rev_cache
                self.__rev_cache = Storage.RevCache(youngest, oldest, new_db,
                                                    new_tags, new_sdb,
                                                    new_branches)
                ts1 = time.time()
                self.logger.debug("rebuilt commit tree db for %d with %d "
                                  "entries (took %.1f ms)"
                                  % (id(self), len(new_db), 1000*(ts1-ts0)))

            assert all(e is not None for e in self.__rev_cache) \
                   or not any(self.__rev_cache)

            return self.__rev_cache
        # with self.__rev_cache_lock

    # see RevCache namedtuple
    rev_cache = property(get_rev_cache)

    def _get_branches(self):
        """returns list of (local) branches, with active (= HEAD) one being
        the first item
        """

        result = []
        for e in self.repo.branch('-v', '--no-abbrev').splitlines():
            bname, bsha = e[1:].strip().split()[:2]
            if e.startswith('*'):
                result.insert(0, (bname, bsha))
            else:
                result.append((bname, bsha))

        return result

    def get_branches(self):
        """returns list of (local) branches, with active (= HEAD) one being
        the first item
        """
        return ((self._fs_to_unicode(name), sha)
                for name, sha in self.rev_cache.branch_dict)

    def get_commits(self):
        return self.rev_cache.rev_dict

    def oldest_rev(self):
        return self.rev_cache.oldest_rev

    def youngest_rev(self):
        return self.rev_cache.youngest_rev

    def get_branch_contains(self, sha, resolve=False):
        """return list of reachable head sha ids or (names, sha) pairs if
        resolve is true

        see also get_branches()
        """

        _rev_cache = self.rev_cache

        try:
            rheads = _rev_cache.rev_dict[sha][3]
        except KeyError:
            return []

        if resolve:
            return ((self._fs_to_unicode(k), v)
                    for k, v in _rev_cache.branch_dict if v in rheads)

        return rheads

    def history_relative_rev(self, sha, rel_pos):
        db = self.get_commits()

        if sha not in db:
            raise GitErrorSha()

        if rel_pos == 0:
            return sha

        lin_rev = db[sha][2] + rel_pos

        if lin_rev < 1 or lin_rev > len(db):
            return None

        for k, v in db.iteritems():
            if v[2] == lin_rev:
                return k

        # should never be reached if db is consistent
        raise GitError("internal inconsistency detected")

    def hist_next_revision(self, sha):
        return self.history_relative_rev(sha, -1)

    def hist_prev_revision(self, sha):
        return self.history_relative_rev(sha, +1)

    def get_commit_encoding(self):
        if self.commit_encoding is None:
            self.commit_encoding = \
                self.repo.repo_config("--get", "i18n.commitEncoding") \
                    .strip() or 'utf-8'

        return self.commit_encoding

    def head(self):
        """get current HEAD commit id"""
        return self.verifyrev('HEAD')

    def cat_file(self, kind, sha):
        with self.__cat_file_pipe_lock:
            if self.__cat_file_pipe is None:
                self.__cat_file_pipe = self.repo.cat_file_batch()

            try:
                self.__cat_file_pipe.stdin.write(sha + '\n')
                self.__cat_file_pipe.stdin.flush()

                split_stdout_line = self.__cat_file_pipe.stdout.readline() \
                                                               .split()
                if len(split_stdout_line) != 3:
                    raise GitError("internal error (could not split line "
                                   "'%s')" % (split_stdout_line,))

                _sha, _type, _size = split_stdout_line

                if _type != kind:
                    raise GitError("internal error (got unexpected object "
                                   "kind '%s', expected '%s')"
                                   % (_type, kind))

                size = int(_size)
                return self.__cat_file_pipe.stdout.read(size + 1)[:size]
            except:
                # There was an error, we should close the pipe to get to a
                # consistent state (Otherwise it happens that next time we
                # call cat_file we get payload from previous call)
                self.logger.debug("closing cat_file pipe")
                self.__cat_file_pipe.stdin.close()
                terminate(self.__cat_file_pipe)
                self.__cat_file_pipe.wait()
                self.__cat_file_pipe = None

    def verifyrev(self, rev):
        """verify/lookup given revision object and return a sha id or None
        if lookup failed
        """
        rev = self._fs_from_unicode(rev)

        _rev_cache = self.rev_cache

        if GitCore.is_sha(rev):
            # maybe it's a short or full rev
            fullrev = self.fullrev(rev)
            if fullrev:
                return fullrev

        # fall back to external git calls
        rc = self.repo.rev_parse('--verify', rev).strip()
        if not rc:
            return None

        if rc in _rev_cache.rev_dict:
            return rc

        if rc in _rev_cache.tag_set:
            sha = self.cat_file('tag', rc).split(None, 2)[:2]
            if sha[0] != 'object':
                self.logger.debug("unexpected result from 'git-cat-file tag "
                                  "%s'" % rc)
                return None
            return sha[1]

        return None

    def shortrev(self, rev, min_len=7):
        """try to shorten sha id"""
        #try to emulate the following:
        #return self.repo.rev_parse("--short", str(rev)).strip()
        rev = str(rev)

        if min_len < self.__SREV_MIN:
            min_len = self.__SREV_MIN

        _rev_cache = self.rev_cache

        if rev not in _rev_cache.rev_dict:
            return None

        srev = rev[:min_len]
        srevs = set(_rev_cache.srev_dict[self.__rev_key(rev)])

        if len(srevs) == 1:
            return srev # we already got a unique id

        # find a shortened id for which rev doesn't conflict with
        # the other ones from srevs
        crevs = srevs - set([rev])

        for l in range(min_len+1, 40):
            srev = rev[:l]
            if srev not in [ r[:l] for r in crevs ]:
                return srev

        return rev # worst-case, all except the last character match

    def fullrev(self, srev):
        """try to reverse shortrev()"""
        srev = str(srev)

        _rev_cache = self.rev_cache

        # short-cut
        if len(srev) == 40 and srev in _rev_cache.rev_dict:
            return srev

        if not GitCore.is_sha(srev):
            return None

        try:
            srevs = _rev_cache.srev_dict[self.__rev_key(srev)]
        except KeyError:
            return None

        srevs = filter(lambda s: s.startswith(srev), srevs)
        if len(srevs) == 1:
            return srevs[0]

        return None

    def get_tags(self):
        return (self._fs_to_unicode(e.strip())
                for e in self.repo.tag('-l').splitlines())

    def ls_tree(self, rev, path=''):
        rev = rev and str(rev) or 'HEAD' # paranoia

        path = self._fs_from_unicode(path)

        if path.startswith('/'):
            path = path[1:]

        tree = self.repo.ls_tree('-z', '-l', rev, '--', path).split('\0')

        def split_ls_tree_line(l):
            """split according to '<mode> <type> <sha> <size>\t<fname>'"""

            meta, fname = l.split('\t', 1)
            _mode, _type, _sha, _size = meta.split()

            if _size == '-':
                _size = None
            else:
                _size = int(_size)

            return _mode, _type, _sha, _size, self._fs_to_unicode(fname)

        return [ split_ls_tree_line(e) for e in tree if e ]

    def read_commit(self, commit_id):
        if not commit_id:
            raise GitError("read_commit called with empty commit_id")

        commit_id, commit_id_orig = self.fullrev(commit_id), commit_id

        db = self.get_commits()
        if commit_id not in db:
            self.logger.info("read_commit failed for '%s' ('%s')" %
                             (commit_id, commit_id_orig))
            raise GitErrorSha

        with self.__commit_msg_lock:
            if self.__commit_msg_cache.has_key(commit_id):
                # cache hit
                result = self.__commit_msg_cache[commit_id]
                return result[0], dict(result[1])

            # cache miss
            raw = self.cat_file('commit', commit_id)
            raw = unicode(raw, self.get_commit_encoding(), 'replace')
            result = parse_commit(raw)

            self.__commit_msg_cache[commit_id] = result

            return result[0], dict(result[1])

    def get_file(self, sha):
        return cStringIO.StringIO(self.cat_file('blob', str(sha)))

    def get_obj_size(self, sha):
        sha = str(sha)

        try:
            obj_size = int(self.repo.cat_file('-s', sha).strip())
        except ValueError:
            raise GitErrorSha("object '%s' not found" % sha)

        return obj_size

    def children(self, sha):
        db = self.get_commits()

        try:
            return list(db[sha][0])
        except KeyError:
            return []

    def children_recursive(self, sha, rev_dict=None):
        """Recursively traverse children in breadth-first order"""

        if rev_dict is None:
            rev_dict = self.get_commits()

        work_list = deque()
        seen = set()

        seen.update(rev_dict[sha][0])
        work_list.extend(rev_dict[sha][0])

        while work_list:
            p = work_list.popleft()
            yield p

            _children = set(rev_dict[p][0]) - seen

            seen.update(_children)
            work_list.extend(_children)

        assert len(work_list) == 0

    def parents(self, sha):
        db = self.get_commits()

        try:
            return list(db[sha][1])
        except KeyError:
            return []

    def all_revs(self):
        return self.get_commits().iterkeys()

    def sync(self):
        rev = self.repo.rev_list('--max-count=1', '--topo-order', '--all') \
                       .strip()
        return self.__rev_cache_sync(rev)

    @contextmanager
    def get_historian(self, sha, base_path):
        p = []
        change = {}
        next_path = []

        def name_status_gen():
            p[:] = [self.repo.log_pipe('--pretty=format:%n%H',
                                       '--name-status', sha, '--', base_path)]
            f = p[0].stdout
            for l in f:
                if l == '\n':
                    continue
                old_sha = l.rstrip('\n')
                for l in f:
                    if l == '\n':
                        break
                    _, path = l.rstrip('\n').split('\t', 1)
                    while path not in change:
                        change[path] = old_sha
                        if next_path == [path]:
                            yield old_sha
                        try:
                            path, _ = path.rsplit('/', 1)
                        except ValueError:
                            break
            f.close()
            terminate(p[0])
            p[0].wait()
            p[:] = []
            while True:
                yield None
        gen = name_status_gen()

        def historian(path):
            try:
                return change[path]
            except KeyError:
                next_path[:] = [path]
                return gen.next()
        yield historian

        if p:
            p[0].stdout.close()
            terminate(p[0])
            p[0].wait()

    def last_change(self, sha, path, historian=None):
        if historian is not None:
            return historian(path)
        return self.repo.rev_list('--max-count=1',
                                  sha, '--',
                                  self._fs_from_unicode(path)).strip() or None

    def history(self, sha, path, limit=None):
        if limit is None:
            limit = -1

        tmp = self.repo.rev_list('--max-count=%d' % limit, str(sha), '--',
                                 self._fs_from_unicode(path))

        return [ rev.strip() for rev in tmp.splitlines() ]

    def history_timerange(self, start, stop):
        return [ rev.strip() for rev in \
                     self.repo.rev_list('--reverse',
                                        '--max-age=%d' % start,
                                        '--min-age=%d' % stop,
                                        '--all').splitlines() ]

    def rev_is_anchestor_of(self, rev1, rev2):
        """return True if rev2 is successor of rev1"""

        rev1 = rev1.strip()
        rev2 = rev2.strip()

        rev_dict = self.get_commits()

        return (rev2 in rev_dict and
                rev2 in self.children_recursive(rev1, rev_dict))

    def blame(self, commit_sha, path):
        in_metadata = False

        path = self._fs_from_unicode(path)

        for line in self.repo.blame('-p', '--', path, str(commit_sha)) \
                             .splitlines():
            assert line
            if in_metadata:
                in_metadata = not line.startswith('\t')
            else:
                split_line = line.split()
                if len(split_line) == 4:
                    (sha, orig_lineno, lineno, group_size) = split_line
                else:
                    (sha, orig_lineno, lineno) = split_line

                assert len(sha) == 40
                yield (sha, lineno)
                in_metadata = True

        assert not in_metadata

    def diff_tree(self, tree1, tree2, path='', find_renames=False):
        """calls `git diff-tree` and returns tuples of the kind
        (mode1,mode2,obj1,obj2,action,path1,path2)"""

        # diff-tree returns records with the following structure:
        # :<old-mode> <new-mode> <old-sha> <new-sha> <change> NUL <old-path> NUL [ <new-path> NUL ]

        path = self._fs_from_unicode(path).strip('/')
        diff_tree_args = ['-z', '-r']
        if find_renames:
            diff_tree_args.append('-M')
        diff_tree_args.extend([str(tree1) if tree1 else '--root',
                               str(tree2),
                               '--', path])

        lines = self.repo.diff_tree(*diff_tree_args).split('\0')

        assert lines[-1] == ''
        del lines[-1]

        if tree1 is None and lines:
            # if only one tree-sha is given on commandline,
            # the first line is just the redundant tree-sha itself...
            assert not lines[0].startswith(':')
            del lines[0]

        # FIXME: the following code is ugly, needs rewrite

        chg = None

        def __chg_tuple():
            if len(chg) == 6:
                chg.append(None)
            else:
                chg[6] = self._fs_to_unicode(chg[6])
            chg[5] = self._fs_to_unicode(chg[5])

            assert len(chg) == 7
            return tuple(chg)

        for line in lines:
            if line.startswith(':'):
                if chg:
                    yield __chg_tuple()

                chg = line[1:].split()
                assert len(chg) == 5
            else:
                chg.append(line)

        # handle left-over chg entry
        if chg:
            yield __chg_tuple()
