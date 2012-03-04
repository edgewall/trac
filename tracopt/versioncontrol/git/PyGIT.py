# -*- coding: iso-8859-1 -*-
#
# Copyright (C) 2006-2011, Herbert Valerio Riedel <hvr@gnu.org>
#
# See COPYING for distribution information

from __future__ import with_statement

from future27 import namedtuple

import os, re, sys, time, weakref
from collections import deque
from functools import partial
from threading import Lock
from subprocess import Popen, PIPE
from operator import itemgetter
from contextlib import contextmanager
import cStringIO
import codecs

__all__ = ["git_version", "GitError", "GitErrorSha", "Storage", "StorageFactory"]

class GitError(Exception):
    pass

class GitErrorSha(GitError):
    pass

class GitCore(object):
    """
    Low-level wrapper around git executable
    """

    def __init__(self, git_dir=None, git_bin="git"):
        self.__git_bin = git_bin
        self.__git_dir = git_dir

    def __repr__(self):
        return '<GitCore bin="%s" dir="%s">' % (self.__git_bin, self.__git_dir)

    def __build_git_cmd(self, gitcmd, *args):
        "construct command tuple for git call suitable for Popen()"

        cmd = [self.__git_bin]
        if self.__git_dir:
            cmd.append('--git-dir=%s' % self.__git_dir)
        cmd.append(gitcmd)
        cmd.extend(args)

        return cmd

    def __pipe(self, git_cmd, *cmd_args, **kw):
        if sys.platform == "win32":
            return Popen(self.__build_git_cmd(git_cmd, *cmd_args), **kw)
        else:
            return Popen(self.__build_git_cmd(git_cmd, *cmd_args),
                         close_fds=True, **kw)

    def __execute(self, git_cmd, *cmd_args):
        "execute git command and return file-like object of stdout"

        #print >>sys.stderr, "DEBUG:", git_cmd, cmd_args

        p = self.__pipe(git_cmd, *cmd_args, stdout=PIPE, stderr=PIPE)

        stdout_data, stderr_data = p.communicate()
        #TODO, do something with p.returncode, e.g. raise exception

        return stdout_data

    def cat_file_batch(self):
        return self.__pipe('cat-file', '--batch', stdin=PIPE, stdout=PIPE)

    def log_pipe(self, *cmd_args):
        return self.__pipe('log', *cmd_args, stdout=PIPE)

    def __getattr__(self, name):
        if name[0] == '_' or name in ['cat_file_batch', 'log_pipe']:
            raise AttributeError, name
        return partial(self.__execute, name.replace('_','-'))

    __is_sha_pat = re.compile(r'[0-9A-Fa-f]*$')

    @classmethod
    def is_sha(cls, sha):
        """
        returns whether sha is a potential sha id
        (i.e. proper hexstring between 4 and 40 characters)
        """

        # quick test before starting up regexp matcher
        if not (4 <= len(sha) <= 40):
            return False

        return bool(cls.__is_sha_pat.match(sha))

class SizedDict(dict):
    """
    Size-bounded dictionary with FIFO replacement strategy
    """

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

    def __init__(self, repo, log, weak=True, git_bin='git', git_fs_encoding=None):
        self.logger = log

        with StorageFactory.__dict_lock:
            try:
                i = StorageFactory.__dict[repo]
            except KeyError:
                i = Storage(repo, log, git_bin, git_fs_encoding)
                StorageFactory.__dict[repo] = i

                # create or remove additional reference depending on 'weak' argument
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
                          % (("","weak ")[is_weak], id(self.__inst), self.__repo))
        return self.__inst


class Storage(object):
    """
    High-level wrapper around GitCore with in-memory caching
    """

    __SREV_MIN = 4 # minimum short-rev length

    RevCache = namedtuple('RevCache', 'youngest_rev oldest_rev rev_dict tag_set srev_dict branch_dict')

    @staticmethod
    def __rev_key(rev):
        assert len(rev) >= 4
        #assert GitCore.is_sha(rev)
        srev_key = int(rev[:4], 16)
        assert srev_key >= 0 and srev_key <= 0xffff
        return srev_key

    @staticmethod
    def git_version(git_bin="git"):
        GIT_VERSION_MIN_REQUIRED = (1, 5, 6)
        try:
            g = GitCore(git_bin=git_bin)
            [v] = g.version().splitlines()
            _, _, version = v.strip().split()
            # 'version' has usually at least 3 numeric version components, e.g.::
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
            raise GitError("Could not retrieve GIT version"
                           " (tried to execute/parse '%s --version' but got %s)"
                           % (git_bin, repr(e)))

    def __init__(self, git_dir, log, git_bin='git', git_fs_encoding=None):
        """
        Initialize PyGit.Storage instance

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
                                  " -- maybe use that folder instead..." % git_dir)
            raise GitError("GIT control files not found, maybe wrong directory?")

        self.logger.debug("PyGIT.Storage instance %d constructed" % id(self))

        self.repo = GitCore(git_dir, git_bin=git_bin)

        self.commit_encoding = None

        # caches
        self.__rev_cache = None
        self.__rev_cache_lock = Lock()

        # cache the last 200 commit messages
        self.__commit_msg_cache = SizedDict(200)
        self.__commit_msg_lock = Lock()

        self.__cat_file_pipe = None

    def __del__(self):
        if self.__cat_file_pipe is not None:
            self.__cat_file_pipe.stdin.close()
            self.__cat_file_pipe.wait()

    #
    # cache handling
    #

    # called by Storage.sync()
    def __rev_cache_sync(self, youngest_rev=None):
        "invalidates revision db cache if necessary"

        with self.__rev_cache_lock:
            need_update = False
            if self.__rev_cache:
                last_youngest_rev = self.__rev_cache.youngest_rev
                if last_youngest_rev != youngest_rev:
                    self.logger.debug("invalidated caches (%s != %s)" % (last_youngest_rev, youngest_rev))
                    need_update = True
            else:
                need_update = True # almost NOOP

            if need_update:
                self.__rev_cache = None

            return need_update

    def get_rev_cache(self):
        """
        Retrieve revision cache

        may rebuild cache on the fly if required

        returns RevCache tuple
        """

        with self.__rev_cache_lock:
            if self.__rev_cache is None: # can be cleared by Storage.__rev_cache_sync()
                self.logger.debug("triggered rebuild of commit tree db for %d" % id(self))
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

                new_tags = set(__rev_reuse(rev.strip()) for rev in self.repo.rev_parse("--tags").splitlines())

                new_branches = [(k, __rev_reuse(v)) for k, v in self._get_branches()]
                head_revs = set(v for _, v in new_branches)

                rev = ord_rev = 0
                for ord_rev, revs in enumerate(self.repo.rev_list("--parents",
                                                                  "--topo-order",
                                                                  "--all").splitlines()):
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

                    # new_db[rev] = (children(rev), parents(rev), ordinal_id(rev), rheads(rev))
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

                    # create/update entry -- transform lists into tuples since entry will be final
                    new_db[rev] = tuple(_children), tuple(parents), ord_rev + 1, tuple(_rheads)

                    # update parents(rev)s
                    for parent in parents:
                        # by default, a dummy ordinal_id is used for the mean-time
                        _children, _parents, _ord_rev, _rheads2 = new_db.setdefault(parent, ([], [], 0, []))

                        # update parent(rev)'s children
                        if rev not in _children:
                            _children.append(rev)

                        # update parent(rev)'s rheads
                        for rev in _rheads:
                            if rev not in _rheads2:
                                _rheads2.append(rev)

                # last rev seen is assumed to be the oldest one (with highest ord_rev)
                oldest = rev

                __rev_seen = None

                # convert sdb either to dict or array depending on size
                tmp = [()]*(max(new_sdb.keys())+1) if len(new_sdb) > 5000 else {}

                try:
                    while True:
                        k, v = new_sdb.popitem()
                        tmp[k] = tuple(v)
                except KeyError:
                    pass

                assert len(new_sdb) == 0
                new_sdb = tmp

                # atomically update self.__rev_cache
                self.__rev_cache = Storage.RevCache(youngest, oldest, new_db, new_tags, new_sdb, new_branches)
                ts1 = time.time()
                self.logger.debug("rebuilt commit tree db for %d with %d entries (took %.1f ms)"
                                  % (id(self), len(new_db), 1000*(ts1-ts0)))

            assert all(e is not None for e in self.__rev_cache) or not any(self.__rev_cache)

            return self.__rev_cache
        # with self.__rev_cache_lock

    # see RevCache namedtuple
    rev_cache = property(get_rev_cache)

    def _get_branches(self):
        "returns list of (local) branches, with active (= HEAD) one being the first item"

        result = []
        for e in self.repo.branch("-v", "--no-abbrev").splitlines():
            bname, bsha = e[1:].strip().split()[:2]
            if e.startswith('*'):
                result.insert(0, (bname, bsha))
            else:
                result.append((bname, bsha))

        return result

    def get_branches(self):
        "returns list of (local) branches, with active (= HEAD) one being the first item"
        return self.rev_cache.branch_dict

    def get_commits(self):
        return self.rev_cache.rev_dict

    def oldest_rev(self):
        return self.rev_cache.oldest_rev

    def youngest_rev(self):
        return self.rev_cache.youngest_rev

    def get_branch_contains(self, sha, resolve=False):
        """
        return list of reachable head sha ids or (names, sha) pairs if resolve is true

        see also get_branches()
        """

        _rev_cache = self.rev_cache

        try:
            rheads = _rev_cache.rev_dict[sha][3]
        except KeyError:
            return []

        if resolve:
            return [ (k, v) for k, v in _rev_cache.branch_dict if v in rheads ]

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
                self.repo.repo_config("--get", "i18n.commitEncoding").strip() or 'utf-8'

        return self.commit_encoding

    def head(self):
        "get current HEAD commit id"
        return self.verifyrev("HEAD")

    def cat_file(self, kind, sha):
        if self.__cat_file_pipe is None:
            self.__cat_file_pipe = self.repo.cat_file_batch()

        self.__cat_file_pipe.stdin.write(sha + '\n')
        self.__cat_file_pipe.stdin.flush()
        _sha, _type, _size = self.__cat_file_pipe.stdout.readline().split()

        if _type != kind:
            raise TracError("internal error (got unexpected object kind '%s')" % k)

        size = int(_size)
        return self.__cat_file_pipe.stdout.read(size + 1)[:size]

    def verifyrev(self, rev):
        "verify/lookup given revision object and return a sha id or None if lookup failed"
        rev = str(rev)

        _rev_cache = self.rev_cache

        if GitCore.is_sha(rev):
            # maybe it's a short or full rev
            fullrev = self.fullrev(rev)
            if fullrev:
                return fullrev

        # fall back to external git calls
        rc = self.repo.rev_parse("--verify", rev).strip()
        if not rc:
            return None

        if rc in _rev_cache.rev_dict:
            return rc

        if rc in _rev_cache.tag_set:
            sha = self.cat_file("tag", rc).split(None, 2)[:2]
            if sha[0] != 'object':
                self.logger.debug("unexpected result from 'git-cat-file tag %s'" % rc)
                return None
            return sha[1]

        return None

    def shortrev(self, rev, min_len=7):
        "try to shorten sha id"
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
        "try to reverse shortrev()"
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
        return [ e.strip() for e in self.repo.tag("-l").splitlines() ]

    def ls_tree(self, rev, path=""):
        rev = rev and str(rev) or 'HEAD' # paranoia

        path = self._fs_from_unicode(path)

        if path.startswith('/'):
            path = path[1:]

        tree = self.repo.ls_tree("-z", "-l", rev, "--", path).split('\0')

        def split_ls_tree_line(l):
            "split according to '<mode> <type> <sha> <size>\t<fname>'"

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
            raw = self.cat_file("commit", commit_id)
            raw = unicode(raw, self.get_commit_encoding(), 'replace')
            lines = raw.splitlines()

            if not lines:
                raise GitErrorSha

            line = lines.pop(0)
            props = {}
            while line:
                key, value = line.split(None, 1)
                props.setdefault(key, []).append(value.strip())
                line = lines.pop(0)

            result = ("\n".join(lines), props)

            self.__commit_msg_cache[commit_id] = result

            return result[0], dict(result[1])

    def get_file(self, sha):
        return cStringIO.StringIO(self.cat_file("blob", str(sha)))

    def get_obj_size(self, sha):
        sha = str(sha)

        try:
            obj_size = int(self.repo.cat_file("-s", sha).strip())
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
        """
        Recursively traverse children in breadth-first order
        """

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
        rev = self.repo.rev_list("--max-count=1", "--topo-order", "--all").strip()
        return self.__rev_cache_sync(rev)

    @contextmanager
    def get_historian(self, sha, base_path):
        p = []
        change = {}
        next_path = []

        def name_status_gen():
            p[:] = [self.repo.log_pipe('--pretty=format:%n%H', '--name-status',
                                       sha, '--', base_path)]
            f = p[0].stdout
            for l in f:
                if l == '\n': continue
                old_sha = l.rstrip('\n')
                for l in f:
                    if l == '\n': break
                    _, path = l.rstrip('\n').split('\t', 1)
                    while path not in change:
                        change[path] = old_sha
                        if next_path == [path]: yield old_sha
                        try:
                            path, _ = path.rsplit('/', 1)
                        except ValueError:
                            break
            f.close()
            p[0].terminate()
            p[0].wait()
            p[:] = []
            while True: yield None
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
            p[0].terminate()
            p[0].wait()

    def last_change(self, sha, path, historian=None):
        if historian is not None:
            return historian(path)
        return self.repo.rev_list("--max-count=1",
                                  sha, "--",
                                  self._fs_from_unicode(path)).strip() or None

    def history(self, sha, path, limit=None):
        if limit is None:
            limit = -1

        tmp = self.repo.rev_list("--max-count=%d" % limit, str(sha), "--",
                                 self._fs_from_unicode(path))

        return [ rev.strip() for rev in tmp.splitlines() ]

    def history_timerange(self, start, stop):
        return [ rev.strip() for rev in \
                     self.repo.rev_list("--reverse",
                                        "--max-age=%d" % start,
                                        "--min-age=%d" % stop,
                                        "--all").splitlines() ]

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

        for line in self.repo.blame("-p", "--", path, str(commit_sha)).splitlines():
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

    def diff_tree(self, tree1, tree2, path="", find_renames=False):
        """calls `git diff-tree` and returns tuples of the kind
        (mode1,mode2,obj1,obj2,action,path1,path2)"""

        # diff-tree returns records with the following structure:
        # :<old-mode> <new-mode> <old-sha> <new-sha> <change> NUL <old-path> NUL [ <new-path> NUL ]

        path = self._fs_from_unicode(path).strip("/")
        diff_tree_args = ["-z", "-r"]
        if find_renames:
            diff_tree_args.append("-M")
        diff_tree_args.extend([str(tree1) if tree1 else "--root",
                               str(tree2),
                               "--", path])

        lines = self.repo.diff_tree(*diff_tree_args).split('\0')

        assert lines[-1] == ""
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

############################################################################
############################################################################
############################################################################

def main():
    import logging, timeit

    assert not GitCore.is_sha("123")
    assert GitCore.is_sha("1a3f")
    assert GitCore.is_sha("f"*40)
    assert not GitCore.is_sha("x"+"f"*39)
    assert not GitCore.is_sha("f"*41)

    print "git version [%s]" % str(Storage.git_version())

    # custom linux hack reading `/proc/<PID>/statm`
    if sys.platform == "linux2":
        __pagesize = os.sysconf('SC_PAGESIZE')

        def proc_statm(pid = os.getpid()):
            __proc_statm = '/proc/%d/statm' % pid
            try:
                t = open(__proc_statm)
                result = t.read().split()
                t.close()
                assert len(result) == 7
                return tuple([ __pagesize*int(p) for p in result ])
            except:
                raise RuntimeError("failed to get memory stats")

    else: # not linux2
        print "WARNING - meminfo.proc_statm() not available"
        def proc_statm():
            return (0,)*7

    print "statm =", proc_statm()
    __data_size = proc_statm()[5]
    __data_size_last = [__data_size]

    def print_data_usage():
        __tmp = proc_statm()[5]
        print "DATA: %6d %+6d" % (__tmp - __data_size, __tmp - __data_size_last[0])
        __data_size_last[0] = __tmp

    print_data_usage()

    g = Storage(sys.argv[1], logging)

    print_data_usage()

    print "[%s]" % g.head()
    print g.ls_tree(g.head())
    print "--------------"
    print_data_usage()
    print g.read_commit(g.head())
    print "--------------"
    print_data_usage()
    p = g.parents(g.head())
    print list(p)
    print "--------------"
    print list(g.children(list(p)[0]))
    print list(g.children(list(p)[0]))
    print "--------------"
    print g.get_commit_encoding()
    print "--------------"
    print g.get_branches()
    print "--------------"
    print g.hist_prev_revision(g.oldest_rev()), g.oldest_rev(), g.hist_next_revision(g.oldest_rev())
    print_data_usage()
    print "--------------"
    p = g.youngest_rev()
    print g.hist_prev_revision(p), p, g.hist_next_revision(p)
    print "--------------"

    p = g.head()
    for i in range(-5, 5):
        print i, g.history_relative_rev(p, i)

    # check for loops
    def check4loops(head):
        print "check4loops", head
        seen = set([head])
        for _sha in g.children_recursive(head):
            if _sha in seen:
                print "dupe detected :-/", _sha, len(seen)
            seen.add(_sha)
        return seen

    print len(check4loops(g.parents(g.head())[0]))

    #p = g.head()
    #revs = [ g.history_relative_rev(p, i) for i in range(0,10) ]
    print_data_usage()
    revs = g.get_commits().keys()
    print_data_usage()

    def shortrev_test():
        for i in revs:
            i = str(i)
            s = g.shortrev(i, min_len=4)
            assert i.startswith(s)
            assert g.fullrev(s) == i

    # iters = 1
    # print "timing %d*shortrev_test()..." % len(revs)
    # t = timeit.Timer("shortrev_test()", "from __main__ import shortrev_test")
    # print "%.2f usec/rev" % (1000000 * t.timeit(number=iters)/len(revs))

    #print len(check4loops(g.oldest_rev()))
    #print len(list(g.children_recursive(g.oldest_rev())))

    print_data_usage()

    # perform typical trac operations:

    if 1:
        print "--------------"
        rev = g.head()
        for mode, _type, sha, _size, name in g.ls_tree(rev):
            [last_rev] = g.history(rev, name, limit=1)
            s = g.get_obj_size(sha) if _type == "blob" else 0
            msg = g.read_commit(last_rev)

            print "%s %s %10d [%s]" % (_type, last_rev, s, name)

    print "allocating 2nd instance"
    print_data_usage()
    g2 = Storage(sys.argv[1], logging)
    g2.head()
    print_data_usage()

    print "allocating 3rd instance"
    g3 = Storage(sys.argv[1], logging)
    g3.head()
    print_data_usage()

if __name__ == '__main__':
    main()
