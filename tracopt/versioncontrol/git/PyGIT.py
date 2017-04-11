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
import re
from subprocess import Popen, PIPE
from threading import Lock
import weakref

from trac.util import terminate
from trac.util.compat import close_fds
from trac.util.datefmt import time_now
from trac.util.text import to_unicode

__all__ = ['GitError', 'GitErrorSha', 'Storage', 'StorageFactory']


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


_unquote_re = re.compile(r'\\(?:[abtnvfr"\\]|[0-7]{3})')
_unquote_chars = {'a': '\a', 'b': '\b', 't': '\t', 'n': '\n', 'v': '\v',
                  'f': '\f', 'r': '\r', '"': '"', '\\': '\\'}


def _unquote(path):
    if path.startswith('"') and path.endswith('"'):
        def replace(match):
            s = match.group(0)[1:]
            if len(s) == 3:
                return chr(int(s, 8))  # \ooo
            return _unquote_chars[s]
        path = _unquote_re.sub(replace, path[1:-1])
    return path


def _close_proc_pipes(proc):
    if proc:
        for f in (proc.stdin, proc.stdout, proc.stderr):
            if f:
                f.close()


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
                # For Windows, Popen() accepts only ANSI encoding
                def to_cmd_encoding(arg):
                    if not isinstance(arg, unicode):
                        arg = arg.decode(fs_encoding, 'replace')
                    return arg.encode('mbcs', 'replace')
            else:
                def to_cmd_encoding(arg):
                    if isinstance(arg, unicode):
                        arg = arg.encode(fs_encoding, 'replace')
                    return arg
            cmd = map(to_cmd_encoding, cmd)
        return cmd

    def __pipe(self, git_cmd, *cmd_args, **kw):
        kw.setdefault('stdin', PIPE)
        kw.setdefault('stdout', PIPE)
        kw.setdefault('stderr', PIPE)
        return Popen(self.__build_git_cmd(git_cmd, *cmd_args),
                     close_fds=close_fds, **kw)

    def __execute(self, git_cmd, *cmd_args):
        """execute git command and return file-like object of stdout"""

        #print >>sys.stderr, "DEBUG:", git_cmd, cmd_args

        p = self.__pipe(git_cmd, stdout=PIPE, stderr=PIPE, *cmd_args)
        stdout_data, stderr_data = p.communicate()
        _close_proc_pipes(p)
        if self.__log and (p.returncode != 0 or stderr_data):
            self.__log.debug('%s exits with %d, dir: %r, args: %s %r, '
                             'stderr: %r', self.__git_bin, p.returncode,
                             self.__git_dir, git_cmd, cmd_args, stderr_data)

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
            head = self.refs_dict.get('HEAD')
            for refname, rev in self.refs_dict.iteritems():
                if refname.startswith('refs/heads/'):
                    yield refname[11:], rev, refname == head

        def iter_tags(self):
            for refname, rev in self.refs_dict.iteritems():
                if refname.startswith('refs/tags/'):
                    yield refname[10:], rev

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
        __git_file_path = partial(os.path.join, git_dir)
        control_files = ['HEAD', 'objects', 'refs']
        control_files_exist = \
            lambda p: all(map(os.path.exists, map(p, control_files)))
        if not control_files_exist(__git_file_path):
            __git_file_path = partial(os.path.join, git_dir, '.git')
            if os.path.exists(__git_file_path()) and \
                    control_files_exist(__git_file_path):
                git_dir = __git_file_path()
            else:
                self.logger.error("GIT control files missing in '%s'"
                                  % git_dir)
                raise GitError("GIT control files not found, maybe wrong "
                               "directory?")
        # at least, check that the HEAD file is readable
        head_file = os.path.join(git_dir, 'HEAD')
        try:
            with open(head_file, 'rb'):
                pass
        except IOError, e:
            raise GitError("Make sure the Git repository '%s' is readable: %s"
                           % (git_dir, to_unicode(e)))

        self.repo = GitCore(git_dir, git_bin, log, git_fs_encoding)
        self.repo_path = git_dir

        self.logger.debug("PyGIT.Storage instance for '%s' is constructed",
                          git_dir)

    def _cleanup_proc(self, proc):
        if proc:
            _close_proc_pipes(proc)
            terminate(proc)
            proc.wait()

    def __del__(self):
        with self.__cat_file_pipe_lock:
            self._cleanup_proc(self.__cat_file_pipe)

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

        refs = dict((refname, _rev_reuse(rev))
                    for refname, rev in refs.iteritems())
        head_revs = set(rev for refname, rev in refs.iteritems()
                            if refname.startswith('refs/heads/'))
        rev_list = [map(_rev_reuse, line.split())
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
        tmp = [()] * (max(new_sdb.keys()) + 1) if len(new_sdb) > 5000 else {}
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
            if ' ' not in line:
                continue
            rev, refname = line.split(' ', 1)
            if refname.endswith('^{}'):  # derefered tag
                tags[refname[:-3]] = rev
            else:
                refs[refname] = rev
        refs.update(tags.iteritems())

        if refs:
            refname = (self.repo.symbolic_ref('-q', 'HEAD') or '').strip()
            if refname in refs:
                refs['HEAD'] = refname

        return refs

    def get_branches(self):
        """returns list of (local) branches, with active (= HEAD) one being
        the first item
        """
        branches = sorted(((self._fs_to_unicode(name), rev, head)
                           for name, rev, head
                           in self.rev_cache.iter_branches()),
                          key=lambda (name, rev, head): (not head, name))
        return [(name, rev) for name, rev, head in branches]

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
            return sorted((self._fs_to_unicode(name), rev)
                          for name, rev, head in _rev_cache.iter_branches()
                          if rev in rheads)
        else:
            return list(rheads)

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
                self._cleanup_proc(self.__cat_file_pipe)
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

        refs = _rev_cache.refs_dict
        if rev == 'HEAD':  # resolve HEAD
            refname = refs.get('HEAD')
            if refname in refs:
                return refs[refname]
        resolved = refs.get('refs/heads/' + rev)  # resolve branch
        if resolved:
            return resolved
        resolved = refs.get('refs/tags/' + rev)  # resolve tag
        if resolved:
            return resolved

        # fall back to external git calls
        rc = self.repo.rev_parse('--verify', rev).strip()
        if not rc:
            return None
        if rc in _rev_cache.rev_dict:
            return rc

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

    def get_tags(self, rev=None):
        return sorted(self._fs_to_unicode(name)
                      for name, rev_ in self.rev_cache.iter_tags()
                      if rev is None or rev == rev_)

    def ls_tree(self, rev, path='', recursive=False):
        rev = rev and str(rev) or 'HEAD' # paranoia
        path = self._fs_from_unicode(path).lstrip('/') or '.'
        tree = self.repo.ls_tree('-zlr' if recursive else '-zl',
                                 rev, '--', path).split('\0')

        def split_ls_tree_line(l):
            """split according to '<mode> <type> <sha> <size>\t<fname>'"""

            meta, fname = l.split('\t', 1)
            _mode, _type, _sha, _size = meta.split()
            _size = None if _size == '-' else int(_size)
            return _mode, _type, _sha, _size, self._fs_to_unicode(fname)

        return [ split_ls_tree_line(e) for e in tree if e ]

    def read_commit(self, commit_id):
        if not commit_id:
            raise GitError("read_commit called with empty commit_id")

        commit_id, commit_id_orig = self.fullrev(commit_id), commit_id

        db = self.get_commits()
        if commit_id not in db:
            self.logger.info("read_commit failed for '%s' ('%s')",
                             commit_id, commit_id_orig)
            raise GitErrorSha

        with self.__commit_msg_lock:
            if commit_id in self.__commit_msg_cache:
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
            return sorted(db[sha][0])
        except KeyError:
            return []

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
        db = self.get_commits()

        try:
            return list(db[sha][1])
        except KeyError:
            return []

    def all_revs(self):
        return self.get_commits().iterkeys()

    def sync(self):
        with self.__rev_cache_lock:
            return self._refresh_rev_cache(force=True)

    @contextmanager
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
                if l == '\n':
                    continue
                old_sha = l.rstrip('\n')
                for l in f:
                    if l == '\n':
                        break
                    _, path = l.rstrip('\n').split('\t', 1)
                    # git-log without -z option quotes each pathname
                    path = _unquote(path)
                    while path not in change:
                        change[path] = old_sha
                        if next_path == [path]:
                            yield old_sha
                        try:
                            path, _ = path.rsplit('/', 1)
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
                return change[path]
            except KeyError:
                next_path[:] = [path]
                return gen.next()

        try:
            yield historian
        finally:
            if p:
                self._cleanup_proc(p[0])

    def last_change(self, sha, path, historian=None):
        if historian is not None:
            return historian(path)
        tmp = self.history(sha, path, limit=1)
        return tmp[0] if tmp else None

    def history(self, sha, path, limit=None):
        if limit is None:
            limit = -1

        args = ['--max-count=%d' % limit, str(sha)]
        if path:
            args.extend(('--', self._fs_from_unicode(path)))
        tmp = self.repo.rev_list(*args)
        return [rev.strip() for rev in tmp.splitlines()]

    def history_timerange(self, start, stop):
        # retrieve start <= committer-time < stop,
        # see CachedRepository.get_changesets()
        return [ rev.strip() for rev in \
                     self.repo.rev_list('--date-order',
                                        '--max-age=%d' % start,
                                        '--min-age=%d' % (stop - 1),
                                        '--all').splitlines() ]

    def rev_is_anchestor_of(self, rev1, rev2):
        """return True if rev2 is successor of rev1"""

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

        path = self._fs_from_unicode(path).strip('/') or '.'
        diff_tree_args = ['-z', '-r']
        if find_renames:
            diff_tree_args.append('-M')
        diff_tree_args.extend([str(tree1) if tree1 else '--root',
                               str(tree2), '--', path])
        result = self.repo.diff_tree(*diff_tree_args)
        if not result:
            return

        def iter_entry(result):
            start = 0
            while True:
                idx = result.find('\0', start)
                if idx == -1:
                    return
                yield result[start:idx]
                start = idx + 1

        iterate = iter_entry(result)

        def next_entry():
            return iterate.next()

        if not tree1:
            # if only one tree-sha is given on commandline,
            # the first line is just the redundant tree-sha itself...
            entry = next_entry()
            assert not entry.startswith(':')

        while True:
            try:
                entry = next_entry()
            except StopIteration:
                return
            assert entry.startswith(':')
            values = entry[1:].split(' ')
            assert len(values) == 5
            old_mode, new_mode, old_sha, new_sha, change = values
            change = change[:1]
            old_path = self._fs_to_unicode(next_entry())
            new_path = None
            if change in ('R', 'C'):  # renamed or copied
                new_path = self._fs_to_unicode(next_entry())
            yield (old_mode, new_mode, old_sha, new_sha, change, old_path,
                   new_path)
