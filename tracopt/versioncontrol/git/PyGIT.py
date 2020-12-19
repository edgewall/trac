# -*- coding: utf-8 -*-
#
# Copyright (C) 2012-2020 Edgewall Software
# Copyright (C) 2006-2011, Herbert Valerio Riedel <hvr@gnu.org>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

import codecs
import contextlib
import io
import os
import re
import subprocess
import weakref
from collections import deque
from functools import partial
from subprocess import DEVNULL, PIPE
from threading import Lock

from trac.core import TracBaseError
from trac.util import terminate
from trac.util.compat import close_fds
from trac.util.datefmt import time_now
from trac.util.text import to_unicode

__all__ = ['GitError', 'GitErrorSha', 'Storage', 'StorageFactory']


class GitError(TracBaseError):
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


_unquote_re = re.compile(r'\\(?:[abtnvfr"\\]|[0-7]{3})'.encode('utf-8'))
_unquote_chars = bytearray(128)
for _key, _val in zip(b'abtnvfr"\\', b'\a\b\t\n\v\f\r"\\'):
    _unquote_chars[_key] = _val
del _key, _val
_unquote_chars = bytes(_unquote_chars)


def _unquote(path):
    if path.startswith(b'"') and path.endswith(b'"'):
        def replace(match):
            match = match.group(0)
            if len(match) == 4:
                code = int(match[1:], 8)  # \ooo
            else:
                code = _unquote_chars[match[1]]
            return b'%c' % code
        path = _unquote_re.sub(replace, path[1:-1])
    return path


def _rev_u(rev):
    if rev is not None:
        rev = str(rev, 'ascii')
    return rev


def _rev_b(rev):
    if rev is not None:
        rev = rev.encode('ascii')
    return rev


class GitCore(object):
    """Low-level wrapper around git executable"""

    def __init__(self, git_dir=None, git_bin='git', log=None,
                 fs_encoding=None):
        self.__git_bin = git_bin
        self.__git_dir = git_dir
        self.__log = log
        self.__fs_encoding = fs_encoding

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

        fs_encoding = self.__fs_encoding
        if fs_encoding is not None:
            if os.name == 'nt':
                # If Python 3 for Windows, Popen() accepts only str instances
                def to_cmd_encoding(arg):
                    if isinstance(arg, bytes):
                        arg = arg.decode(fs_encoding, 'replace')
                    return arg
            else:
                def to_cmd_encoding(arg):
                    if isinstance(arg, str):
                        arg = arg.encode(fs_encoding, 'replace')
                    return arg
            cmd = list(map(to_cmd_encoding, cmd))
        return cmd

    def __pipe(self, git_cmd, *cmd_args, **kw):
        kw.setdefault('stdin', PIPE)
        kw.setdefault('stdout', PIPE)
        kw.setdefault('stderr', PIPE)
        return subprocess.Popen(self.__build_git_cmd(git_cmd, *cmd_args),
                                close_fds=close_fds, **kw)

    def __execute(self, *args):
        """execute git command and return file-like object of stdout"""

        #print("DEBUG:", args, file=sys.stderr)

        with self.__pipe(*args, stdin=DEVNULL) as p:
            stdout_data, stderr_data = p.communicate()
        if self.__log and (p.returncode != 0 or stderr_data):
            self.__log.debug('%s exits with %d, dir: %r, args: %r, stderr: %r',
                             self.__git_bin, p.returncode, self.__git_dir,
                             args, stderr_data)

        return stdout_data

    def cat_file_batch(self):
        return self.__pipe('cat-file', '--batch')

    def log_pipe(self, *cmd_args):
        return self.__pipe('log', *cmd_args)

    def diff_tree_pipe(self):
        return self.__pipe('diff-tree', '--stdin', '--root', '-z', '-r', '-M')

    def __getattr__(self, name):
        if name.startswith('_') or \
                name in ('cat_file_batch', 'log_pipe', 'diff_tree_pipe'):
            raise AttributeError(name)
        return partial(self.__execute, name.replace('_','-'))

    __is_sha_pat = re.compile(b'[0-9A-Fa-f]{4,40}$')

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
        raise NotImplementedError("SizedDict has no setdefault() method")


class StorageFactory(object):
    __dict = weakref.WeakValueDictionary()
    __dict_nonweak = {}
    __dict_rev_cache = {}
    __dict_lock = Lock()

    def __init__(self, repo, log, weak=True, git_bin='git',
                 git_fs_encoding=None):
        self.logger = log

        with self.__dict_lock:
            if weak:
                # remove additional reference which is created
                # with non-weak argument
                try:
                    del self.__dict_nonweak[repo]
                except KeyError:
                    pass
            try:
                i = self.__dict[repo]
            except KeyError:
                rev_cache = self.__dict_rev_cache.get(repo)
                i = Storage(repo, log, git_bin, git_fs_encoding, rev_cache)
                self.__dict[repo] = i

            # create additional reference depending on 'weak' argument
            if not weak:
                self.__dict_nonweak[repo] = i

        self.__inst = i
        self.logger.debug("requested %s PyGIT.Storage instance for '%s'",
                          'weak' if weak else 'non-weak', repo)

    def getInstance(self):
        return self.__inst

    @classmethod
    def set_rev_cache(cls, repo, rev_cache):
        with cls.__dict_lock:
            cls.__dict_rev_cache[repo] = rev_cache

    @classmethod
    def _clean(cls):
        """For testing purpose only"""
        with cls.__dict_lock:
            cls.__dict.clear()
            cls.__dict_nonweak.clear()
            cls.__dict_rev_cache.clear()


class Storage(object):
    """High-level wrapper around GitCore with in-memory caching"""

    __SREV_MIN = 4 # minimum short-rev length

    class RevCache(object):

        __slots__ = ('youngest_rev', 'oldest_rev', 'rev_dict', 'refs_dict',
                     'srev_dict')

        def __init__(self, youngest_rev, oldest_rev, rev_dict, refs_dict,
                     srev_dict):
            self.youngest_rev = youngest_rev
            self.oldest_rev = oldest_rev
            self.rev_dict = rev_dict
            self.refs_dict = refs_dict
            self.srev_dict = srev_dict
            if youngest_rev is not None and oldest_rev is not None and \
                    rev_dict and refs_dict and srev_dict:
                pass  # all fields are not empty
            elif not youngest_rev and not oldest_rev and \
                    not rev_dict and not refs_dict and not srev_dict:
                pass  # all fields are empty
            else:
                raise ValueError('Invalid RevCache fields: %r' % self)

        @classmethod
        def empty(cls):
            return cls(None, None, {}, {}, {})

        def __repr__(self):
            return 'RevCache(youngest_rev=%r, oldest_rev=%r, ' \
                   'rev_dict=%d entries, refs_dict=%d entries, ' \
                   'srev_dict=%d entries)' % \
                   (self.youngest_rev, self.oldest_rev, len(self.rev_dict),
                    len(self.refs_dict), len(self.srev_dict))

        def iter_branches(self):
            head = self.refs_dict.get(b'HEAD')
            for refname, rev in self.refs_dict.items():
                if refname.startswith(b'refs/heads/'):
                    yield refname[11:], rev, refname == head

        def iter_tags(self):
            for refname, rev in self.refs_dict.items():
                if refname.startswith(b'refs/tags/'):
                    yield refname[10:], rev

    @staticmethod
    def __rev_key(rev):
        assert len(rev) >= 4
        #assert GitCore.is_sha(rev)
        srev_key = int(rev[:4], 16)
        assert 0 <= srev_key <= 0xffff
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

            split_version = tuple(map(try_int, version.split(b'.')))

            result = {}
            result['v_str'] = version
            result['v_tuple'] = split_version
            result['v_min_tuple'] = GIT_VERSION_MIN_REQUIRED
            result['v_min_str'] = ".".join(map(str, GIT_VERSION_MIN_REQUIRED))
            result['v_compatible'] = split_version >= GIT_VERSION_MIN_REQUIRED
            return result

        except Exception as e:
            raise GitError("Could not retrieve GIT version (tried to "
                           "execute/parse '%s --version' but got %s)"
                           % (git_bin, repr(e)))

    def __init__(self, git_dir, log, git_bin='git', git_fs_encoding=None,
                 rev_cache=None):
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
        self.__rev_cache = rev_cache or self.RevCache.empty()
        self.__rev_cache_refresh = True
        self.__rev_cache_lock = Lock()

        # cache the last 200 commit messages
        self.__commit_msg_cache = SizedDict(200)
        self.__commit_msg_lock = Lock()

        self.__cat_file_pipe = None
        self.__cat_file_pipe_lock = Lock()
        self.__diff_tree_pipe = None
        self.__diff_tree_pipe_lock = Lock()

        if git_fs_encoding is not None:
            # validate encoding name
            codecs.lookup(git_fs_encoding)

            # setup conversion functions
            self._fs_to_unicode = lambda s: s.decode(git_fs_encoding,
                                                     'replace')
            self._fs_from_unicode = lambda s: s.encode(git_fs_encoding)
        else:
            # pass bytestrings as-is w/o any conversion
            self._fs_to_unicode = self._fs_from_unicode = lambda s: s

        # simple sanity checking
        try:
            os.listdir(git_dir)
        except EnvironmentError as e:
            self._raise_not_readable(git_dir, e)
        if not self._control_files_exist(git_dir):
            dot_git_dir = os.path.join(git_dir, '.git')
            try:
                os.listdir(dot_git_dir)
            except EnvironmentError:
                missing = True
            else:
                if self._control_files_exist(dot_git_dir):
                    missing = False
                    git_dir = dot_git_dir
                else:
                    missing = True
            if missing:
                raise GitError("Git control files not found in '%s'" % git_dir)

        # at least, check that the HEAD file is readable
        try:
            with open(os.path.join(git_dir, 'HEAD'), 'rb'):
                pass
        except EnvironmentError as e:
            self._raise_not_readable(git_dir, e)

        self.repo = GitCore(git_dir, git_bin, log, git_fs_encoding)
        self.repo_path = git_dir

        self.logger.debug("PyGIT.Storage instance for '%s' is constructed",
                          git_dir)

    def _cleanup_proc(self, proc):
        if proc:
            for f in (proc.stdin, proc.stdout, proc.stderr):
                if f:
                    f.close()
            terminate(proc)
            proc.wait()

    def __del__(self):
        with self.__cat_file_pipe_lock:
            self._cleanup_proc(self.__cat_file_pipe)
        with self.__diff_tree_pipe_lock:
            self._cleanup_proc(self.__diff_tree_pipe)

    #
    # cache handling
    #

    def invalidate_rev_cache(self):
        with self.__rev_cache_lock:
            self.__rev_cache_refresh = True

    @property
    def rev_cache(self):
        """Retrieve revision cache

        may rebuild cache on the fly if required

        returns RevCache tuple
        """
        with self.__rev_cache_lock:
            self._refresh_rev_cache()
            return self.__rev_cache

    def _refresh_rev_cache(self, force=False):
        refreshed = False
        if force or self.__rev_cache_refresh:
            self.__rev_cache_refresh = False
            refs = self._get_refs()
            if self.__rev_cache.refs_dict != refs:
                self.logger.debug("Detected changes in git repository "
                                  "'%s'", self.repo_path)
                rev_cache = self._build_rev_cache(refs)
                self.__rev_cache = rev_cache
                StorageFactory.set_rev_cache(self.repo_path, rev_cache)
                refreshed = True
            else:
                self.logger.debug("Detected no changes in git repository "
                                  "'%s'", self.repo_path)
        return refreshed

    def _build_rev_cache(self, refs):
        self.logger.debug("triggered rebuild of commit tree db for '%s'",
                          self.repo_path)
        ts0 = time_now()

        new_db = {} # db
        new_sdb = {} # short_rev db

        # helper for reusing strings
        revs_seen = {}
        def _rev_reuse(rev):
            return revs_seen.setdefault(rev, rev)

        refs = {refname: _rev_reuse(rev) for refname, rev in refs.items()}
        head_revs = {rev for refname, rev in refs.items()
                         if refname.startswith(b'refs/heads/')}
        rev_list = [list(map(_rev_reuse, line.split()))
                    for line in self.repo.rev_list('--parents', '--topo-order',
                                                   '--all').splitlines()]
        revs_seen = None

        if rev_list:
            # first rev seen is assumed to be the youngest one
            youngest = rev_list[0][0]
            # last rev seen is assumed to be the oldest one
            oldest = rev_list[-1][0]
        else:
            youngest = oldest = None

        rheads_seen = {}
        def _rheads_reuse(rheads):
            rheads = frozenset(rheads)
            return rheads_seen.setdefault(rheads, rheads)

        __rev_key = self.__rev_key
        for ord_rev, revs in enumerate(rev_list):
            rev = revs[0]
            parents = revs[1:]

            # shortrev "hash" map
            new_sdb.setdefault(__rev_key(rev), []).append(rev)

            # new_db[rev] = (children(rev), parents(rev),
            #                ordinal_id(rev), rheads(rev))
            if rev in new_db:
                # (incomplete) entry was already created by children
                _children, _parents, _ord_rev, _rheads = new_db[rev]
                assert _children
                assert not _parents
                assert _ord_rev == 0
            else: # new entry
                _children = set()
                _rheads = set()
            if rev in head_revs:
                _rheads.add(rev)

            # create/update entry
            # transform into frozenset and tuple since entry will be final
            new_db[rev] = (frozenset(_children), tuple(parents), ord_rev + 1,
                           _rheads_reuse(_rheads))

            # update parents(rev)s
            for parent in parents:
                # by default, a dummy ordinal_id is used for the mean-time
                _children, _parents, _ord_rev, _rheads2 = \
                    new_db.setdefault(parent, (set(), [], 0, set()))

                # update parent(rev)'s children
                _children.add(rev)

                # update parent(rev)'s rheads
                _rheads2.update(_rheads)

        rheads_seen = None

        # convert sdb either to dict or array depending on size
        tmp = [()] * (max(new_sdb) + 1) if len(new_sdb) > 5000 else {}
        try:
            while True:
                k, v = new_sdb.popitem()
                tmp[k] = tuple(v)
        except KeyError:
            pass
        assert len(new_sdb) == 0
        new_sdb = tmp

        rev_cache = self.RevCache(youngest, oldest, new_db, refs, new_sdb)
        self.logger.debug("rebuilt commit tree db for '%s' with %d entries "
                          "(took %.1f ms)", self.repo_path, len(new_db),
                          1000 * (time_now() - ts0))
        return rev_cache

    def _get_refs(self):
        refs = {}
        tags = {}

        for line in self.repo.show_ref('--dereference').splitlines():
            if b' ' not in line:
                continue
            rev, refname = line.split(b' ', 1)
            if refname.endswith(b'^{}'):  # derefered tag
                tags[refname[:-3]] = rev
            else:
                refs[refname] = rev
        refs.update(iter(tags.items()))

        if refs:
            refname = (self.repo.symbolic_ref('-q', 'HEAD') or '').strip()
            if refname in refs:
                refs[b'HEAD'] = refname

        return refs

    def get_branches(self):
        """returns list of (local) branches, with active (= HEAD) one being
        the first item
        """
        def fn(args):
            name, rev, head = args
            return not head, name
        _fs_to_unicode = self._fs_to_unicode
        branches = sorted(((_fs_to_unicode(name), _rev_u(rev), head)
                           for name, rev, head
                           in self.rev_cache.iter_branches()), key=fn)
        return [(name, rev) for name, rev, head in branches]

    def get_refs(self):
        _fs_to_unicode = self._fs_to_unicode
        for refname, rev in self.rev_cache.refs_dict.items():
            if refname != b'HEAD':
                yield _fs_to_unicode(refname), _rev_u(rev)

    def get_commits(self):
        return self.rev_cache.rev_dict

    def oldest_rev(self):
        return _rev_u(self.rev_cache.oldest_rev)

    def youngest_rev(self):
        return _rev_u(self.rev_cache.youngest_rev)

    def get_branch_contains(self, sha, resolve=False):
        """return list of reachable head sha ids or (names, sha) pairs if
        resolve is true

        see also get_branches()
        """

        sha = _rev_b(sha)
        _rev_cache = self.rev_cache

        try:
            rheads = _rev_cache.rev_dict[sha][3]
        except KeyError:
            return []

        if resolve:
            _fs_to_unicode = self._fs_to_unicode
            rv = [(_fs_to_unicode(name), _rev_u(rev))
                  for name, rev, head in _rev_cache.iter_branches()
                  if rev in rheads]
            rv.sort(key=lambda v: v[0])
            return rv
        else:
            return list(map(_rev_u, rheads))

    def history_relative_rev(self, sha, rel_pos):

        def get_history_relative_rev(sha, rel_pos):
            rev_dict = self.get_commits()

            if sha not in rev_dict:
                raise GitErrorSha()

            if rel_pos == 0:
                return sha

            lin_rev = rev_dict[sha][2] + rel_pos

            if lin_rev < 1 or lin_rev > len(rev_dict):
                return None

            for k, v in rev_dict.items():
                if v[2] == lin_rev:
                    return k

            # should never be reached if rev_dict is consistent
            raise GitError("internal inconsistency detected")

        result = get_history_relative_rev(_rev_b(sha), rel_pos)
        return _rev_u(result)

    def hist_next_revision(self, sha):
        return self.history_relative_rev(sha, -1)

    def hist_prev_revision(self, sha):
        return self.history_relative_rev(sha, +1)

    def get_commit_encoding(self):
        if self.commit_encoding is None:
            self.commit_encoding = \
                self.repo.config('--get', 'i18n.commitEncoding').strip() or \
                'utf-8'

        return self.commit_encoding

    def head(self):
        """get current HEAD commit id"""
        return self.verifyrev('HEAD')

    def cat_file(self, kind, sha):
        with self.__cat_file_pipe_lock:
            if self.__cat_file_pipe is None:
                self.__cat_file_pipe = self.repo.cat_file_batch()

            try:
                self.__cat_file_pipe.stdin.write(sha + b'\n')
                self.__cat_file_pipe.stdin.flush()

                split_stdout_line = self.__cat_file_pipe.stdout.readline() \
                                                               .split()
                if len(split_stdout_line) != 3:
                    raise GitError("internal error (could not split line %s)" %
                                   repr(split_stdout_line))

                _sha, _type, _size = split_stdout_line

                if _type != kind:
                    raise GitError("internal error (got unexpected object "
                                   "kind %r, expected %r)" % (_type, kind))

                size = int(_size)
                return self.__cat_file_pipe.stdout.read(size + 1)[:size]
            except EnvironmentError:
                # There was an error, we should close the pipe to get to a
                # consistent state (Otherwise it happens that next time we
                # call cat_file we get payload from previous call)
                self.logger.debug("closing cat_file pipe")
                self._cleanup_proc(self.__cat_file_pipe)
                self.__cat_file_pipe = None

    def verifyrev(self, rev):
        """verify/lookup given revision object and return a sha id or None
        if lookup failed
        """

        def get_verifyrev(rev):
            _rev_cache = self.rev_cache

            if GitCore.is_sha(rev):
                # maybe it's a short or full rev
                fullrev = self.fullrev(rev)
                if fullrev:
                    return fullrev

            refs = _rev_cache.refs_dict
            if rev == b'HEAD':  # resolve HEAD
                refname = refs.get(rev)
                if refname in refs:
                    return refs[refname]
            resolved = refs.get(b'refs/heads/' + rev)  # resolve branch
            if resolved:
                return resolved
            resolved = refs.get(b'refs/tags/' + rev)  # resolve tag
            if resolved:
                return resolved

            # fall back to external git calls
            rc = self.repo.rev_parse('--verify', rev).strip()
            if not rc:
                return None
            if rc in _rev_cache.rev_dict:
                return rc

            return None

        result = get_verifyrev(self._fs_from_unicode(rev))
        return _rev_u(result)

    def shortrev(self, rev, min_len=7):

        def get_shortrev(rev, min_len):
            """try to shorten sha id"""
            #try to emulate the following:
            #return self.repo.rev_parse("--short", rev).strip()

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
            crevs = srevs - {rev}

            for l in range(min_len+1, 40):
                srev = rev[:l]
                if srev not in [ r[:l] for r in crevs ]:
                    return srev

            return rev # worst-case, all except the last character match

        return _rev_u(get_shortrev(_rev_b(rev), min_len))


    def fullrev(self, rev):
        """try to reverse shortrev()"""

        _rev_cache = self.rev_cache

        # short-cut
        if len(rev) == 40 and rev in _rev_cache.rev_dict:
            return rev

        if not GitCore.is_sha(rev):
            return None

        try:
            srevs = _rev_cache.srev_dict[self.__rev_key(rev)]
        except KeyError:
            return None

        resolved = None
        for s in srevs:
            if s.startswith(rev):
                if resolved is not None:
                    return None
                resolved = s
        return resolved

    def get_tags(self, rev=None):
        if rev is not None:
            rev = _rev_b(rev)
        return sorted(self._fs_to_unicode(name)
                      for name, rev_ in self.rev_cache.iter_tags()
                      if rev is None or rev == rev_)

    def ls_tree(self, rev, path='', recursive=False):
        rev = self._fs_from_unicode(rev) if rev else b'HEAD'  # paranoia
        path = self._fs_from_unicode(path).lstrip(b'/') or b'.'
        tree = self.repo.ls_tree('-zlr' if recursive else '-zl',
                                 rev, '--', path).split(b'\0')

        def split_ls_tree_line(l):
            """split according to '<mode> <type> <sha> <size>\t<fname>'"""

            meta, fname = l.split(b'\t', 1)
            _mode, _type, _sha, _size = meta.split()
            _type = str(_type, 'utf-8')
            _sha = _rev_u(_sha)
            _mode = int(_mode, 8)
            _size = None if _size == b'-' else int(_size)
            fname = self._fs_to_unicode(fname)
            return _mode, _type, _sha, _size, fname

        return [split_ls_tree_line(e) for e in tree if e]

    def read_commit(self, commit_id):
        if not commit_id:
            raise GitError("read_commit called with empty commit_id")

        commit_id_orig = commit_id
        commit_id = self.fullrev(_rev_b(commit_id))

        rev_dict = self.get_commits()
        if commit_id not in rev_dict:
            self.logger.info("read_commit failed for %r (%r)",
                             commit_id, commit_id_orig)
            raise GitErrorSha

        with self.__commit_msg_lock:
            if commit_id in self.__commit_msg_cache:
                # cache hit
                result = self.__commit_msg_cache[commit_id]
                return result[0], dict(result[1])

        # cache miss
        raw = self.cat_file(b'commit', commit_id)
        raw = str(raw, self.get_commit_encoding(), 'replace')
        result = parse_commit(raw)
        with self.__commit_msg_lock:
            self.__commit_msg_cache[commit_id] = result
        return result[0], dict(result[1])

    def get_file(self, sha):
        sha = _rev_b(sha)
        content = self.cat_file(b'blob', sha)
        return io.BytesIO(content)

    def get_obj_size(self, sha):
        sha = _rev_b(sha)
        try:
            obj_size = int(self.repo.cat_file('-s', sha).strip())
        except ValueError:
            raise GitErrorSha("object '%s' not found" % sha)
        return obj_size

    def children(self, sha):
        sha = _rev_b(sha)
        rev_dict = self.get_commits()
        try:
            item = rev_dict[sha]
        except KeyError:
            return ()
        return sorted(map(_rev_u, item[0]))

    def children_recursive(self, sha, rev_dict=None):
        """Recursively traverse children in breadth-first order"""

        if rev_dict is None:
            rev_dict = self.get_commits()

        work_list = deque()
        seen = set()

        _children = rev_dict[sha][0]
        seen.update(_children)
        work_list.extend(_children)

        while work_list:
            p = work_list.popleft()
            yield p

            _children = rev_dict[p][0] - seen
            seen.update(_children)
            work_list.extend(_children)

        assert len(work_list) == 0

    def parents(self, sha):
        sha = _rev_b(sha)
        rev_dict = self.get_commits()
        try:
            item = rev_dict[sha]
        except KeyError:
            return []
        return list(map(_rev_u, item[1]))

    def all_revs(self):
        for rev in self.get_commits():
            yield _rev_u(rev)

    def sync(self):
        with self.__rev_cache_lock:
            return self._refresh_rev_cache(force=True)

    @contextlib.contextmanager
    def get_historian(self, sha, base_path):
        p = []
        change = {}
        next_path = []
        base_path = self._fs_from_unicode(base_path) or '.'

        def name_status_gen():
            p[:] = [self.repo.log_pipe('--pretty=format:%n%H', '--no-renames',
                                       '--name-status', sha, '--', base_path)]
            f = p[0].stdout
            for l in f:
                if l == b'\n':
                    continue
                old_sha = l.rstrip(b'\n')
                for l in f:
                    if l == b'\n':
                        break
                    _, path = l.rstrip(b'\n').split(b'\t', 1)
                    # git-log without -z option quotes each pathname
                    path = _unquote(path)
                    while path not in change:
                        change[path] = old_sha
                        if next_path == [path]:
                            yield old_sha
                        try:
                            path, _ = path.rsplit(b'/', 1)
                        except ValueError:
                            break
            if p:
                self._cleanup_proc(p[0])
            p[:] = []
            while True:
                yield None
        gen = name_status_gen()

        def historian(path):
            path = self._fs_from_unicode(path)
            try:
                rev = change[path]
            except KeyError:
                next_path[:] = [path]
                rev = next(gen)
            return _rev_u(rev)

        try:
            yield historian
        finally:
            if p:
                self._cleanup_proc(p[0])

    def last_change(self, sha, path, historian=None):
        if historian is not None:
            return historian(path)
        for entry in self.history(sha, path, limit=1):
            return entry
        return None

    def history(self, sha, path, limit=None):
        if limit is None:
            limit = -1

        args = ['--max-count=%d' % limit, str(sha)]
        if path:
            args.extend(('--', self._fs_from_unicode(path)))
        tmp = self.repo.rev_list(*args)
        for rev in tmp.splitlines():
            yield _rev_u(rev)

    def history_timerange(self, start, stop):
        # retrieve start <= committer-time < stop,
        # see CachedRepository.get_changesets()
        output = self.repo.rev_list('--all', '--date-order',
                                    '--max-age=%d' % start,
                                    '--min-age=%d' % (stop - 1))
        return [_rev_u(rev) for rev in output.splitlines()]

    def rev_is_anchestor_of(self, rev1, rev2):
        """return True if rev2 is successor of rev1"""

        rev1 = _rev_b(rev1)
        rev2 = _rev_b(rev2)
        rev_dict = self.get_commits()
        return (rev2 in rev_dict and
                rev2 in self.children_recursive(rev1, rev_dict))

    def blame(self, commit_sha, path):
        in_metadata = False

        commit_sha = _rev_b(commit_sha)
        path = self._fs_from_unicode(path)

        for line in self.repo.blame('-p', '--', path, commit_sha) \
                             .splitlines():
            assert line
            if in_metadata:
                in_metadata = not line.startswith(b'\t')
            else:
                split_line = line.split()
                if len(split_line) == 4:
                    (sha, orig_lineno, lineno, group_size) = split_line
                else:
                    (sha, orig_lineno, lineno) = split_line

                assert len(sha) == 40
                yield _rev_u(sha), lineno
                in_metadata = True

        assert not in_metadata

    def get_changes(self, tree1, tree2):
        with self.__diff_tree_pipe_lock:
            if self.__diff_tree_pipe is None:
                self.__diff_tree_pipe = self.repo.diff_tree_pipe()
            proc = self.__diff_tree_pipe
            try:
                proc.stdin.write(b'%s %s\n\n' % (_rev_b(tree2), _rev_b(tree1))
                                 if tree1 else
                                 b'%s\n\n' % _rev_b(tree2))
                proc.stdin.flush()
                read = proc.stdout.read
                entries = []
                c = read(1)
                if not c:
                    raise EOFError()
                while c != b'\n':
                    entry = bytearray()
                    while c != b'\0':
                        entry.append(c[0])
                        c = read(1)
                        if not c:
                            raise EOFError()
                    entries.append(bytes(entry))
                    c = read(1)
                    if not c:
                        raise EOFError()
            except:
                self.__diff_tree_pipe = None
                self._cleanup_proc(proc)
                raise
        if not entries:
            return
        # skip first entry as a sha
        assert not entries[0].startswith(b':')
        entries = entries[1:]

        yield from self._iter_diff_tree(entries)

    def diff_tree(self, tree1, tree2, path='', find_renames=False):
        """calls `git diff-tree` and returns tuples of the kind
        (mode1,mode2,obj1,obj2,action,path1,path2)"""

        # diff-tree returns records with the following structure:
        # :<old-mode> <new-mode> <old-sha> <new-sha> <change> NUL <old-path> NUL [ <new-path> NUL ]

        path = self._fs_from_unicode(path).strip(b'/') or b'.'
        diff_tree_args = ['-z', '-r']
        if find_renames:
            diff_tree_args.append('-M')
        diff_tree_args.extend([tree1 if tree1 else '--root',
                               tree2, '--', path])
        result = self.repo.diff_tree(*diff_tree_args)
        if not result:
            return

        def iter_entry(result):
            start = 0
            while True:
                idx = result.find(b'\0', start)
                if idx == -1:
                    return
                yield result[start:idx]
                start = idx + 1

        entries = list(iter_entry(result))
        if not tree1:
            # if only one tree-sha is given on commandline,
            # the first line is just the redundant tree-sha itself...
            entry = entries.pop(0)
            assert not entry.startswith(b':')

        yield from self._iter_diff_tree(entries)

    def _iter_diff_tree(self, entries):

        def next_entry():
            return next(iter_entry)

        iter_entry = iter(entries)
        while True:
            try:
                entry = next_entry()
            except StopIteration:
                return
            assert entry.startswith(b':')
            values = entry[1:].split(b' ')
            assert len(values) == 5
            old_mode, new_mode, old_sha, new_sha, change = values
            old_mode = int(old_mode, 8)
            new_mode = int(new_mode, 8)
            old_sha = _rev_u(old_sha)
            new_sha = _rev_u(new_sha)
            change = str(change[:1], 'utf-8')
            old_path = self._fs_to_unicode(next_entry())
            new_path = None
            if change in ('R', 'C'):  # renamed or copied
                new_path = self._fs_to_unicode(next_entry())
            yield (old_mode, new_mode, old_sha, new_sha, change, old_path,
                   new_path)

    def _raise_not_readable(self, git_dir, e):
        raise GitError("Make sure the Git repository '%s' is readable: %s"
                       % (git_dir, to_unicode(e)))

    def _control_files_exist(self, git_dir):
        for name in ('HEAD', 'objects', 'refs'):
            if not os.path.exists(os.path.join(git_dir, name)):
                self.logger.debug("Missing Git control file '%s' in '%s'",
                                  name, git_dir)
                return False
        return True
