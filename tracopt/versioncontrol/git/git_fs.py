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

from datetime import datetime
import itertools
import os

from genshi.builder import tag
from genshi.core import Markup

from trac.cache import cached
from trac.config import BoolOption, IntOption, ListOption, PathOption, Option
from trac.core import Component, TracError, implements
from trac.env import ISystemInfoProvider
from trac.util import shorten_line
from trac.util.datefmt import FixedOffset, to_timestamp, format_datetime
from trac.util.text import to_unicode, exception_to_unicode
from trac.util.translation import _
from trac.versioncontrol.api import Changeset, Node, Repository, \
                                    IRepositoryConnector, InvalidRepository,\
                                    NoSuchChangeset, NoSuchNode, \
                                    IRepositoryProvider
from trac.versioncontrol.cache import CACHE_YOUNGEST_REV, CachedRepository, \
                                      CachedChangeset
from trac.versioncontrol.web_ui import IPropertyRenderer
from trac.web.chrome import Chrome
from trac.wiki import IWikiSyntaxProvider

from tracopt.versioncontrol.git import PyGIT


class GitCachedRepository(CachedRepository):
    """Git-specific cached repository."""

    def display_rev(self, rev):
        return self.short_rev(rev)

    def short_rev(self, path):
        return self.repos.short_rev(path)

    def normalize_rev(self, rev):
        if not rev:
            return self.get_youngest_rev()
        normrev = self.repos.git.verifyrev(rev)
        if normrev is None:
            raise NoSuchChangeset(rev)
        return normrev

    def get_youngest_rev(self):
        # return None if repository is empty
        return CachedRepository.get_youngest_rev(self) or None

    def child_revs(self, rev):
        return self.repos.child_revs(rev)

    def get_changesets(self, start, stop):
        for key, csets in itertools.groupby(
                CachedRepository.get_changesets(self, start, stop),
                key=lambda cset: cset.date):
            csets = list(csets)
            if len(csets) == 1:
                yield csets[0]
                continue
            rev_csets = dict((cset.rev, cset) for cset in csets)
            while rev_csets:
                revs = [rev for rev in rev_csets
                            if not any(r in rev_csets
                                       for r in self.repos.child_revs(rev))]
                for rev in sorted(revs):
                    yield rev_csets.pop(rev)

    def get_changeset(self, rev):
        return GitCachedChangeset(self, self.normalize_rev(rev), self.env)

    def sync(self, feedback=None, clean=False):
        if clean:
            self.remove_cache()

        metadata = self.metadata
        self.save_metadata(metadata)
        meta_youngest = metadata.get(CACHE_YOUNGEST_REV, '')
        repos = self.repos

        def is_synced(rev):
            for count, in self.env.db_query("""
                    SELECT COUNT(*) FROM revision WHERE repos=%s AND rev=%s
                    """, (self.id, rev)):
                return count > 0
            return False

        def needs_sync():
            max_holders = 999
            revs = sorted(set(rev for refname, rev in repos.git.get_refs()))
            step = max_holders - 1
            for idx in xrange(0, len(revs), step):
                revs_ = revs[idx:idx + step]
                holders = ','.join(('%s',) * len(revs_))
                args = [self.id]
                args.extend(revs_)
                query = """SELECT COUNT(*) FROM revision
                           WHERE repos=%%s AND rev IN (%s)""" % holders
                for count, in self.env.db_query(query, args):
                    if count < len(revs_):
                        return True
            return False

        def traverse(rev, seen):
            revs = []
            merge_revs = []
            while True:
                if rev in seen:
                    break
                seen.add(rev)
                if is_synced(rev):
                    break
                revs.append(rev)
                parent_revs = repos.parent_revs(rev)
                if not parent_revs:  # root commit?
                    break
                rev = parent_revs[0]
                if len(parent_revs) > 1:
                    merge_revs.append((len(revs), parent_revs[1:]))
            for idx, parent_revs in reversed(merge_revs):
                for rev in parent_revs:
                    revs[idx:idx] = traverse(rev, seen)
            return revs

        def sync_revs():
            updated = False
            seen = set()

            for rev in repos.git.all_revs():
                if repos.child_revs(rev):
                    continue
                revs = traverse(rev, seen)  # topology ordered
                while revs:
                    # sync revision from older revision to newer revision
                    rev = revs.pop()
                    self.log.info("Trying to sync revision [%s]", rev)
                    cset = repos.get_changeset(rev)
                    try:
                        self.insert_changeset(rev, cset)
                        updated = True
                    except self.env.db_exc.IntegrityError as e:
                        self.log.info('Revision %s already cached: %r', rev, e)
                        continue
                    if feedback:
                        feedback(rev)

            return updated

        with self.env.db_query:
            while True:
                repos.sync()
                if needs_sync() and sync_revs():
                    continue  # sync again
                repos_youngest = repos.youngest_rev or ''
                if meta_youngest != repos_youngest:
                    with self.env.db_transaction as db:
                        db("""
                            UPDATE repository SET value=%s
                            WHERE id=%s AND name=%s
                            """, (repos_youngest, self.id, CACHE_YOUNGEST_REV))
                        del self.metadata
                return


class GitCachedChangeset(CachedChangeset):
    """Git-specific cached changeset."""

    def get_branches(self):
        _rev = self.rev

        return [(k, v == _rev) for k, v in
                 self.repos.repos.git.get_branch_contains(_rev, resolve=True)]

    def get_tags(self):
        return self.repos.repos.git.get_tags(self.rev)


def _last_iterable(iterable):
    """helper for detecting last iteration in for-loop"""
    i = iter(iterable)
    v = i.next()
    for nextv in i:
        yield False, v
        v = nextv
    yield True, v

def intersperse(sep, iterable):
    """The 'intersperse' generator takes an element and an iterable and
    intersperses that element between the elements of the iterable.

    inspired by Haskell's ``Data.List.intersperse``
    """

    for i, item in enumerate(iterable):
        if i: yield sep
        yield item

# helper
def _parse_user_time(s):
    """Parse author or committer attribute lines and return
    corresponding ``(user, timestamp)`` pair.
    """

    user, time, tz_str = s.rsplit(None, 2)
    tz = FixedOffset((int(tz_str) * 6) / 10, tz_str)
    time = datetime.fromtimestamp(float(time), tz)
    return user, time


_file_type_mask = 0170000


def _is_dir(mode):
    if mode is None:
        return False
    return (mode & _file_type_mask) in (0040000, 0160000)


def _is_submodule(mode):
    if mode is None:
        return False
    return (mode & _file_type_mask) == 0160000


class GitConnector(Component):

    implements(IRepositoryConnector, ISystemInfoProvider, IWikiSyntaxProvider)

    def __init__(self):
        self._version = None

        try:
            self._version = PyGIT.Storage.git_version(git_bin=self.git_bin)
        except PyGIT.GitError as e:
            self.log.error("GitError: %s", e)

        if self._version:
            self.log.info("detected GIT version %s", self._version['v_str'])
            if not self._version['v_compatible']:
                self.log.error("GIT version %s installed not compatible"
                               "(need >= %s)", self._version['v_str'],
                               self._version['v_min_str'])

    # ISystemInfoProvider methods

    def get_system_info(self):
        if self._version:
            yield 'GIT', self._version['v_str']

    # IWikiSyntaxProvider methods

    def _format_sha_link(self, formatter, sha, label):
        # FIXME: this function needs serious rethinking...

        reponame = ''

        context = formatter.context
        while context:
            if context.resource.realm in ('source', 'changeset'):
                reponame = context.resource.parent.id
                break
            context = context.parent

        try:
            repos = self.env.get_repository(reponame)

            if not repos:
                raise Exception("Repository '%s' not found" % reponame)

            sha = repos.normalize_rev(sha) # in case it was abbreviated
            changeset = repos.get_changeset(sha)
            return tag.a(label, class_='changeset',
                         title=shorten_line(changeset.message),
                         href=formatter.href.changeset(sha, repos.reponame))
        except Exception as e:
            return tag.a(label, class_='missing changeset',
                         title=to_unicode(e), rel='nofollow')

    def get_wiki_syntax(self):
        yield (r'(?:\b|!)r?[0-9a-fA-F]{%d,40}\b' % self.wiki_shortrev_len,
               lambda fmt, sha, match:
                    self._format_sha_link(fmt, sha.startswith('r')
                                          and sha[1:] or sha, sha))

    def get_link_resolvers(self):
        yield ('sha', lambda fmt, _, sha, label, match=None:
                        self._format_sha_link(fmt, sha, label))

    # IRepositoryConnector methods

    persistent_cache = BoolOption('git', 'persistent_cache', 'false',
        """Enable persistent caching of commit tree.""")

    cached_repository = BoolOption('git', 'cached_repository', 'false',
        """Wrap `GitRepository` in `CachedRepository`.""")

    shortrev_len = IntOption('git', 'shortrev_len', 7,
        """The length at which a sha1 should be abbreviated to (must
        be >= 4 and <= 40).
        """)

    wiki_shortrev_len = IntOption('git', 'wikishortrev_len', 40,
        """The minimum length of an hex-string for which
        auto-detection as sha1 is performed (must be >= 4 and <= 40).
        """)

    trac_user_rlookup = BoolOption('git', 'trac_user_rlookup', 'false',
        """Enable reverse mapping of git email addresses to trac user ids.
        Performance will be reduced if there are many users and the
        `cached_repository` option is `disabled`.

        A repository resync is required after changing the value of this
        option.
        """)

    use_committer_id = BoolOption('git', 'use_committer_id', 'true',
        """Use git-committer id instead of git-author id for the
        changeset ''Author'' field.
        """)

    use_committer_time = BoolOption('git', 'use_committer_time', 'true',
        """Use git-committer timestamp instead of git-author timestamp
        for the changeset ''Timestamp'' field.
        """)

    git_fs_encoding = Option('git', 'git_fs_encoding', 'utf-8',
        """Define charset encoding of paths within git repositories.""")

    git_bin = Option('git', 'git_bin', 'git',
        """Path to the git executable.""")


    def get_supported_types(self):
        yield ('git', 8)

    def get_repository(self, type, dir, params):
        """GitRepository factory method"""
        assert type == 'git'

        if not (4 <= self.shortrev_len <= 40):
            raise TracError(_("%(option)s must be in the range [4..40]",
                              option="[git] shortrev_len"))

        if not (4 <= self.wiki_shortrev_len <= 40):
            raise TracError(_("%(option)s must be in the range [4..40]",
                              option="[git] wikishortrev_len"))

        if not self._version:
            raise TracError(_("GIT backend not available"))
        elif not self._version['v_compatible']:
            raise TracError(_("GIT version %(hasver)s installed not "
                              "compatible (need >= %(needsver)s)",
                              hasver=self._version['v_str'],
                              needsver=self._version['v_min_str']))

        if self.trac_user_rlookup:
            def rlookup_uid(email):
                """Reverse map 'real name <user@domain.tld>' addresses to trac
                user ids.

                :return: `None` if lookup failed
                """

                try:
                    _, email = email.rsplit('<', 1)
                    email, _ = email.split('>', 1)
                    email = email.lower()
                except Exception:
                    return None

                for _uid, _name, _email in self.env.get_known_users():
                    try:
                        if email == _email.lower():
                            return _uid
                    except Exception:
                        continue

        else:
            def rlookup_uid(_):
                return None

        repos = GitRepository(self.env, dir, params, self.log,
                              persistent_cache=self.persistent_cache,
                              git_bin=self.git_bin,
                              git_fs_encoding=self.git_fs_encoding,
                              shortrev_len=self.shortrev_len,
                              rlookup_uid=rlookup_uid,
                              use_committer_id=self.use_committer_id,
                              use_committer_time=self.use_committer_time,
                              )

        if self.cached_repository:
            repos = GitCachedRepository(self.env, repos, self.log)
            self.log.debug("enabled CachedRepository for '%s'", dir)
        else:
            self.log.debug("disabled CachedRepository for '%s'", dir)

        return repos


class CsetPropertyRenderer(Component):

    implements(IPropertyRenderer)

    # relied upon by GitChangeset
    def match_property(self, name, mode):
        # default renderer has priority 1
        return (name in ('Parents',
                         'Children',
                         'Branches',
                         'git-committer',
                         'git-author',
                         ) and mode == 'revprop') and 4 or 0

    def render_property(self, name, mode, context, props):

        def sha_link(sha, label=None):
            # sha is assumed to be a non-abbreviated 40-chars sha id
            try:
                reponame = context.resource.parent.id
                repos = self.env.get_repository(reponame)
                cset = repos.get_changeset(sha)
                if label is None:
                    label = repos.display_rev(sha)

                return tag.a(label, class_='changeset',
                             title=shorten_line(cset.message),
                             href=context.href.changeset(sha, repos.reponame))

            except Exception as e:
                return tag.a(sha, class_='missing changeset',
                             title=to_unicode(e), rel='nofollow')

        if name == 'Branches':
            branches = props[name]

            # simple non-merge commit
            return tag(*intersperse(', ', (sha_link(rev, label)
                                           for label, rev in branches)))

        elif name in ('Parents', 'Children'):
            revs = props[name] # list of commit ids

            if name == 'Parents' and len(revs) > 1:
                # we got a merge...
                current_sha = context.resource.id
                reponame = context.resource.parent.id

                parent_links = intersperse(', ', \
                    ((sha_link(rev),
                      ' (',
                      tag.a(_("diff"),
                            title=_("Diff against this parent (show the "
                                    "changes merged from the other parents)"),
                            href=context.href.changeset(current_sha, reponame,
                                                        old=rev)),
                      ')')
                     for rev in revs))

                return tag(list(parent_links),
                           tag.br(),
                           tag.span(Markup(_("Note: this is a <strong>merge"
                                             "</strong> changeset, the "
                                             "changes displayed below "
                                             "correspond to the merge "
                                             "itself.")),
                                    class_='hint'),
                           tag.br(),
                           tag.span(Markup(_("Use the <code>(diff)</code> "
                                             "links above to see all the "
                                             "changes relative to each "
                                             "parent.")),
                                    class_='hint'))

            # simple non-merge commit
            return tag(*intersperse(', ', map(sha_link, revs)))

        elif name in ('git-committer', 'git-author'):
            user_, time_ = props[name]
            _str = "%s (%s)" % (
                Chrome(self.env).format_author(context.req, user_),
                format_datetime(time_, tzinfo=context.req.tz))
            return unicode(_str)

        raise TracError(_("Internal error"))


class GitRepository(Repository):
    """Git repository"""

    def __init__(self, env, path, params, log,
                 persistent_cache=False,
                 git_bin='git',
                 git_fs_encoding='utf-8',
                 shortrev_len=7,
                 rlookup_uid=lambda _: None,
                 use_committer_id=False,
                 use_committer_time=False,
                 ):

        self.env = env
        self.logger = log
        self.gitrepo = path
        self.params = params
        self.persistent_cache = persistent_cache
        self.shortrev_len = max(4, min(shortrev_len, 40))
        self.rlookup_uid = rlookup_uid
        self.use_committer_time = use_committer_time
        self.use_committer_id = use_committer_id

        try:
            factory = PyGIT.StorageFactory(path, log, not persistent_cache,
                                           git_bin=git_bin,
                                           git_fs_encoding=git_fs_encoding)
            self._git = factory.getInstance()
        except PyGIT.GitError as e:
            log.error(exception_to_unicode(e))
            raise InvalidRepository(
                _('"%(name)s" is not readable or not a Git repository.',
                  name=params.get('name') or '(default)'))

        Repository.__init__(self, 'git:' + path, self.params, log)
        self._cached_git_id = str(self.id)

    def close(self):
        self._git = None

    @property
    def git(self):
        if self.persistent_cache:
            return self._cached_git
        else:
            return self._git

    @cached('_cached_git_id')
    def _cached_git(self):
        self._git.invalidate_rev_cache()
        return self._git

    def get_youngest_rev(self):
        return self.git.youngest_rev()

    def get_path_history(self, path, rev=None, limit=None):
        raise TracError(_("Unsupported \"Show only adds and deletes\""))

    def get_oldest_rev(self):
        return self.git.oldest_rev()

    def normalize_path(self, path):
        return path and path.strip('/') or '/'

    def normalize_rev(self, rev):
        if not rev:
            return self.get_youngest_rev()
        normrev = self.git.verifyrev(rev)
        if normrev is None:
            raise NoSuchChangeset(rev)
        return normrev

    def display_rev(self, rev):
        return self.short_rev(rev)

    def short_rev(self, rev):
        return self.git.shortrev(self.normalize_rev(rev),
                                 min_len=self.shortrev_len)

    def get_node(self, path, rev=None):
        return self._get_node(path, rev)

    def _get_node(self, path, rev, ls_tree_info=None, historian=None):
        return GitNode(self, path, rev, self.log, ls_tree_info, historian)

    def get_quickjump_entries(self, rev):
        for bname, bsha in self.git.get_branches():
            yield 'branches', bname, '/', bsha
        for t in self.git.get_tags():
            yield 'tags', t, '/', t

    def get_path_url(self, path, rev):
        return self.params.get('url')

    def get_changesets(self, start, stop):
        for rev in self.git.history_timerange(to_timestamp(start),
                                              to_timestamp(stop)):
            yield self.get_changeset(rev)

    def get_changeset(self, rev):
        """GitChangeset factory method"""
        return GitChangeset(self, rev)

    def get_changeset_uid(self, rev):
        return self.normalize_rev(rev)

    def get_changes(self, old_path, old_rev, new_path, new_rev,
                    ignore_ancestry=0):
        # TODO: handle renames/copies, ignore_ancestry
        old_path = self.normalize_path(old_path)
        new_path = self.normalize_path(new_path)
        if old_path != new_path:
            raise TracError(_("Not supported in git_fs"))

        old_rev = self.normalize_rev(old_rev)
        new_rev = self.normalize_rev(new_rev)
        if old_rev == new_rev:
            return

        def get_tree(rev):
            results = self.git.ls_tree(rev, target_path, recursive=True)
            return dict((result[4], result) for result in results)

        target_path = old_path.strip('/')
        old_tree = get_tree(old_rev)
        new_tree = get_tree(new_rev)

        with self.git.get_historian(old_rev, target_path) as old_historian:
            with self.git.get_historian(new_rev, target_path) as new_historian:
                for chg in self.git.diff_tree(old_rev, new_rev, target_path):
                    mode1, mode2, obj1, obj2, action, path, path2 = chg
                    kind = Node.DIRECTORY \
                           if _is_dir(mode2) or _is_dir(mode1) \
                           else Node.FILE

                    change = GitChangeset.action_map[action]
                    old_node = self._get_node(path, old_rev,
                                              old_tree.get(path, False),
                                              old_historian) \
                               if change != Changeset.ADD else None
                    new_node = self._get_node(path, new_rev,
                                              new_tree.get(path, False),
                                              new_historian) \
                               if change != Changeset.DELETE else None

                    yield old_node, new_node, kind, change

    def next_rev(self, rev, path=''):
        return self.git.hist_next_revision(rev)

    def previous_rev(self, rev, path=''):
        return self.git.hist_prev_revision(rev)

    def parent_revs(self, rev):
        return self.git.parents(rev)

    def child_revs(self, rev):
        return self.git.children(rev)

    def rev_older_than(self, rev1, rev2):
        return self.git.rev_is_anchestor_of(self.normalize_rev(rev1),
                                            self.normalize_rev(rev2))

    # def clear(self, youngest_rev=None):
    #     self.youngest = None
    #     if youngest_rev is not None:
    #         self.youngest = self.normalize_rev(youngest_rev)
    #     self.oldest = None

    def clear(self, youngest_rev=None):
        self.sync()

    def sync(self, rev_callback=None, clean=None):
        if rev_callback:
            revs = set(self.git.all_revs())

        if self.persistent_cache:
            del self._cached_git  # invalidate persistent cache
        if not self.git.sync():
            return None # nothing expected to change

        if rev_callback:
            revs = set(self.git.all_revs()) - revs
            for rev in revs:
                rev_callback(rev)


class GitNode(Node):

    def __init__(self, repos, path, rev, log, ls_tree_info=None,
                 historian=None):
        self.log = log
        self.repos = repos
        self.fs_sha = None # points to either tree or blobs
        self.fs_perm = None
        self.fs_type = None
        self.fs_size = None
        if rev:
            rev = repos.normalize_rev(to_unicode(rev))
        else:
            rev = repos.youngest_rev
        created_rev = rev

        kind = Node.DIRECTORY
        p = path.strip('/')
        if p:  # ie. not the root-tree
            if not rev:
                raise NoSuchNode(path, rev)
            if ls_tree_info is None:
                ls_tree_info = repos.git.ls_tree(rev, p)
                if ls_tree_info:
                    ls_tree_info = ls_tree_info[0]
            if not ls_tree_info:
                raise NoSuchNode(path, rev)
            self.fs_perm, self.fs_type, self.fs_sha, self.fs_size, fname = \
                ls_tree_info

            # fix-up to the last commit-rev that touched this node
            created_rev = repos.git.last_change(rev, p, historian)

            if self.fs_type == 'tree':
                kind = Node.DIRECTORY
            elif self.fs_type == 'blob':
                kind = Node.FILE
            elif _is_submodule(self.fs_perm):
                # FIXME: this is a workaround for missing git submodule
                #        support in the plugin
                kind = Node.DIRECTORY
            else:
                self.log.warning('Got unexpected object %r', ls_tree_info)
                raise TracError(_("Internal error (got unexpected object "
                                  "kind '%(kind)s')", kind=self.fs_type))

        self.created_path = path
        self.created_rev = created_rev

        Node.__init__(self, repos, path, rev, kind)

    def __git_path(self):
        """return path as expected by PyGIT"""
        p = self.path.strip('/')
        if self.isfile:
            assert p
            return p
        if self.isdir:
            return p and (p + '/')

        raise TracError(_("Internal error"))

    def get_content(self):
        if not self.isfile:
            return None
        return self.repos.git.get_file(self.fs_sha)

    def get_properties(self):
        if self.fs_perm is None:
            return {}
        props = {'mode': '%06o' % self.fs_perm}
        if _is_submodule(self.fs_perm):
            props['commit'] = self.fs_sha
        return props

    def get_annotations(self):
        if not self.isfile:
            return

        return [rev for rev, lineno in \
                self.repos.git.blame(self.rev,self.__git_path())]

    def get_entries(self):
        if not self.rev:  # if empty repository
            return
        if not self.isdir:
            return
        if _is_submodule(self.fs_perm):
            return

        with self.repos.git.get_historian(self.rev,
                                          self.path.strip('/')) as historian:
            for ent in self.repos.git.ls_tree(self.rev, self.__git_path()):
                yield GitNode(self.repos, ent[-1], self.rev, self.log, ent,
                              historian)

    def get_content_type(self):
        if self.isdir:
            return None

        return ''

    def get_content_length(self):
        if not self.isfile:
            return None

        if self.fs_size is None:
            self.fs_size = self.repos.git.get_obj_size(self.fs_sha)

        return self.fs_size

    def get_history(self, limit=None):
        if not self.rev:  # if empty repository
            return
        # TODO: find a way to follow renames/copies
        for is_last, rev in _last_iterable(self.repos.git.history(self.rev,
                                                self.__git_path(), limit)):
            yield (self.path, rev, Changeset.EDIT if not is_last else
                                   Changeset.ADD)

    def get_last_modified(self):
        if not self.isfile:
            return None

        try:
            msg, props = self.repos.git.read_commit(self.rev)
            user, ts = _parse_user_time(props['committer'][0])
        except:
            self.log.error("internal error (could not get timestamp from "
                           "commit '%s')", self.rev)
            return None

        return ts


class GitChangeset(Changeset):
    """A Git changeset in the Git repository.

    Corresponds to a Git commit blob.
    """

    action_map = { # see also git-diff-tree(1) --diff-filter
        'A': Changeset.ADD,
        'M': Changeset.EDIT, # modified
        'T': Changeset.EDIT, # file type (mode) change
        'D': Changeset.DELETE,
        'R': Changeset.MOVE, # renamed
        'C': Changeset.COPY
        } # TODO: U, X, B

    def __init__(self, repos, sha):
        if sha is None:
            raise NoSuchChangeset(sha)

        try:
            msg, props = repos.git.read_commit(sha)
        except PyGIT.GitErrorSha:
            raise NoSuchChangeset(sha)

        self.props = props

        assert 'children' not in props
        _children = list(repos.git.children(sha))
        if _children:
            props['children'] = _children

        committer, author = self._get_committer_and_author()
        # use 1st author/committer as changeset owner/timestamp
        c_user = a_user = c_time = a_time = None
        if committer:
            c_user, c_time = _parse_user_time(committer)
        if author:
            a_user, a_time = _parse_user_time(author)

        if repos.use_committer_time:
            time = c_time or a_time
        else:
            time = a_time or c_time

        if repos.use_committer_id:
            user = c_user or a_user
        else:
            user = a_user or c_user

        # try to resolve email address to trac uid
        user = repos.rlookup_uid(user) or user

        Changeset.__init__(self, repos, rev=sha, message=msg, author=user,
                           date=time)

    def _get_committer_and_author(self):
        committer = author = None
        if 'committer' in self.props:
            committer = self.props['committer'][0]
        if 'author' in self.props:
            author = self.props['author'][0]
        return committer, author

    def get_properties(self):
        properties = {}

        if 'parent' in self.props:
            properties['Parents'] = self.props['parent']

        if 'children' in self.props:
            properties['Children'] = self.props['children']

        committer, author = self._get_committer_and_author()
        if author != committer:
            properties['git-committer'] = _parse_user_time(committer)
            properties['git-author'] = _parse_user_time(author)

        branches = list(self.repos.git.get_branch_contains(self.rev,
                                                           resolve=True))
        if branches:
            properties['Branches'] = branches

        return properties

    def get_changes(self):
        # Returns the differences against the first parent
        parent = self.props.get('parent')
        parent = parent[0] if parent else None

        for mode1, mode2, obj1, obj2, action, path1, path2 in \
                self.repos.git.diff_tree(parent, self.rev, find_renames=True):
            path = path2 or path1
            p_path, p_rev = path1, parent

            kind = Node.DIRECTORY \
                   if _is_dir(mode2) or _is_dir(mode1) else \
                   Node.FILE

            action = GitChangeset.action_map[action]

            if action == Changeset.ADD:
                p_path = p_rev = None

            yield path, kind, action, p_path, p_rev

    def get_branches(self):
        _rev = self.rev

        return [(k, v == _rev)
                for k, v in self.repos.git.get_branch_contains(_rev,
                                                               resolve=True)]

    def get_tags(self):
        return self.repos.git.get_tags(self.rev)


class GitwebProjectsRepositoryProvider(Component):

    implements(IRepositoryProvider)

    projects_list = PathOption('gitweb-repositories', 'projects_list', doc=
        """Path to a gitweb-formatted projects.list""")

    projects_base = PathOption('gitweb-repositories', 'projects_base', doc=
        """Path to the base of your git projects""")

    projects_url = Option('gitweb-repositories', 'projects_url', doc=
        """Template for project URLs. `%s` will be replaced with the repo
        name""")

    sync_per_request = ListOption('gitweb-repositories',
        'sync_per_request', '', doc="""Repositories to sync on every request
        (not recommended).""")

    def get_repositories(self):
        """Retrieve repositories specified in a `projects_list` file."""
        if not self.projects_list:
            return

        if not os.path.exists(self.projects_list):
            self.log.warn("The [git] projects_list file was not found at "
                          "'%s'", self.projects_list)
            return

        with open(self.projects_list, 'r') as fp:
            for line in fp:
                entries = line.strip().split()
                if entries:
                    name = entries[0]
                    reponame = name.rstrip('.git')
                    info = {
                        'dir': os.path.join(self.projects_base, name),
                        'sync_per_request': reponame in self.sync_per_request,
                        'type': 'git',
                    }
                    description_path = \
                        os.path.join(info['dir'], 'description')
                    if os.path.exists(description_path):
                        with open(description_path, 'r') as fd:
                            info['description'] = fd.read().strip()
                    if self.projects_url:
                        info['url'] = self.projects_url % reponame
                    yield reponame, info
