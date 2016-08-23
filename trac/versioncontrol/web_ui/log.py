# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2014 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2005-2006 Christian Boos <cboos@edgewall.org>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.
#
# Author: Jonas Borgström <jonas@edgewall.com>
#         Christian Boos <cboos@edgewall.org>

import re

from genshi.builder import tag
from genshi.core import Markup

from trac.config import IntOption, ListOption
from trac.core import *
from trac.perm import IPermissionRequestor
from trac.resource import ResourceNotFound
from trac.util import Ranges
from trac.util.text import to_unicode, wrap
from trac.util.translation import _
from trac.versioncontrol.api import (Changeset, NoSuchChangeset,
                                     RepositoryManager)
from trac.versioncontrol.web_ui.changeset import ChangesetModule
from trac.versioncontrol.web_ui.util import *
from trac.web.api import IRequestHandler
from trac.web.chrome import (INavigationContributor, add_ctxtnav, add_link,
                             add_script, add_script_data, add_stylesheet,
                             auth_link, web_context)
from trac.wiki import IWikiSyntaxProvider, WikiParser


class LogModule(Component):

    implements(INavigationContributor, IPermissionRequestor, IRequestHandler,
               IWikiSyntaxProvider)

    realm = RepositoryManager.changeset_realm

    default_log_limit = IntOption('revisionlog', 'default_log_limit', 100,
        """Default value for the limit argument in the TracRevisionLog.
        """)

    graph_colors = ListOption('revisionlog', 'graph_colors',
        ['#cc0', '#0c0', '#0cc', '#00c', '#c0c', '#c00'],
        doc="""Comma-separated list of colors to use for the TracRevisionLog
        graph display. (''since 1.0'')""")

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'browser'

    def get_navigation_items(self, req):
        return []

    # IPermissionRequestor methods

    def get_permission_actions(self):
        return ['LOG_VIEW']

    # IRequestHandler methods

    def match_request(self, req):
        match = re.match(r'/log(/.*)?$', req.path_info)
        if match:
            req.args['path'] = match.group(1) or '/'
            return True

    def process_request(self, req):
        req.perm.require('LOG_VIEW')

        mode = req.args.get('mode', 'stop_on_copy')
        path = req.args.get('path', '/')
        rev = req.args.getfirst('rev')
        stop_rev = req.args.get('stop_rev')
        revs = req.args.get('revs')
        format = req.args.get('format')
        verbose = req.args.get('verbose')
        limit = req.args.getint('limit', self.default_log_limit)

        rm = RepositoryManager(self.env)
        reponame, repos, path = rm.get_repository_by_path(path)

        if not repos:
            if path == '/':
                raise TracError(_("No repository specified and no default"
                                  " repository configured."))
            else:
                raise ResourceNotFound(_("Repository '%(repo)s' not found",
                                         repo=reponame or path.strip('/')))

        if reponame != repos.reponame:  # Redirect alias
            qs = req.query_string
            req.redirect(req.href.log(repos.reponame or None, path)
                         + ('?' + qs if qs else ''))

        normpath = repos.normalize_path(path)

        # if `revs` parameter is given, then we're restricted to the
        # corresponding revision ranges.
        # If not, then we're considering all revisions since `rev`,
        # on that path, in which case `revranges` will be None.
        if revs:
            revranges = RevRanges(repos, revs, resolve=True)
            rev = revranges.b
        else:
            revranges = None
            rev = repos.normalize_rev(rev)

        # The `history()` method depends on the mode:
        #  * for ''stop on copy'' and ''follow copies'', it's `Node.history()`
        #    unless explicit ranges have been specified
        #  * for ''show only add, delete'' we're using
        #   `Repository.get_path_history()`
        cset_resource = repos.resource.child(self.realm)
        show_graph = False
        curr_revrange = []
        if mode == 'path_history':
            def history():
                for h in repos.get_path_history(path, rev):
                    if 'CHANGESET_VIEW' in req.perm(cset_resource(id=h[1])):
                        yield h

        elif revranges:
            show_graph = path == '/' and not verbose \
                         and not repos.has_linear_changesets \
                         and len(revranges) == 1

            def history():
                separator = False
                for a, b in reversed(revranges.pairs):
                    curr_revrange[:] = (a, b)
                    node = get_existing_node(req, repos, path, b)
                    for p, rev, chg in node.get_history():
                        if repos.rev_older_than(rev, a):
                            break
                        if 'CHANGESET_VIEW' in req.perm(cset_resource(id=rev)):
                            separator = True
                            yield p, rev, chg
                    else:
                        separator = False
                    if separator:
                        yield p, rev, None
        else:
            show_graph = path == '/' and not verbose \
                         and not repos.has_linear_changesets

            def history():
                node = get_existing_node(req, repos, path, rev)
                for h in node.get_history():
                    if 'CHANGESET_VIEW' in req.perm(cset_resource(id=h[1])):
                        yield h

        # -- retrieve history, asking for limit+1 results
        info = []
        depth = 1
        previous_path = normpath
        count = 0
        history_remaining = True
        for old_path, old_rev, old_chg in history():
            if stop_rev and repos.rev_older_than(old_rev, stop_rev):
                break
            old_path = repos.normalize_path(old_path)

            item = {
                'path': old_path, 'rev': old_rev, 'existing_rev': old_rev,
                'change': old_chg, 'depth': depth,
            }

            if old_chg == Changeset.DELETE:
                item['existing_rev'] = repos.previous_rev(old_rev, old_path)
            if not (mode == 'path_history' and old_chg == Changeset.EDIT):
                info.append(item)
            if old_path and old_path != previous_path and \
                    not (mode == 'path_history' and old_path == normpath):
                depth += 1
                item['depth'] = depth
                item['copyfrom_path'] = old_path
                if mode == 'stop_on_copy':
                    break
                elif mode == 'path_history':
                    depth -= 1
            if old_chg is None:  # separator entry
                stop_limit = limit
            else:
                count += 1
                stop_limit = limit + 1
            if count >= stop_limit:
                break
            previous_path = old_path
        else:
            history_remaining = False
        if not info:
            node = get_existing_node(req, repos, path, rev)
            if repos.rev_older_than(stop_rev, node.created_rev):
                # FIXME: we should send a 404 error here
                raise TracError(_("The file or directory '%(path)s' doesn't "
                                  "exist at revision %(rev)s or at any "
                                  "previous revision.", path=path,
                                  rev=repos.display_rev(rev)),
                                _('Nonexistent path'))

        # Generate graph data
        graph = {}
        if show_graph:
            threads, vertices, columns = \
                make_log_graph(repos, (item['rev'] for item in info))
            graph.update(threads=threads, vertices=vertices, columns=columns,
                         colors=self.graph_colors,
                         line_width=0.04, dot_radius=0.1)
            add_script(req, 'common/js/excanvas.js', ie_if='IE')
            add_script(req, 'common/js/log_graph.js')
            add_script_data(req, graph=graph)

        def make_log_href(path, **args):
            link_rev = rev
            if rev == str(repos.youngest_rev):
                link_rev = None
            params = {'rev': link_rev, 'mode': mode, 'limit': limit}
            params.update(args)
            if verbose:
                params['verbose'] = verbose
            return req.href.log(repos.reponame or None, path, **params)

        if format in ('rss', 'changelog'):
            info = [i for i in info if i['change']]  # drop separators
            if info and count > limit:
                del info[-1]
        elif info and history_remaining and count >= limit:
            # stop_limit reached, there _might_ be some more
            next_rev = info[-1]['rev']
            next_path = info[-1]['path']
            next_revranges = None
            if curr_revrange:
                new_revrange = (curr_revrange[0], next_rev) \
                               if info[-1]['change'] else None
                next_revranges = revranges.truncate(curr_revrange,
                                                    new_revrange)
                next_revranges = unicode(next_revranges) or None
            if next_revranges or not revranges:
                older_revisions_href = make_log_href(
                    next_path, rev=next_rev, revs=next_revranges)
                add_link(req, 'next', older_revisions_href,
                         _('Revision Log (restarting at %(path)s, rev. '
                           '%(rev)s)', path=next_path,
                           rev=repos.display_rev(next_rev)))
            # only show fully 'limit' results, use `change == None` as a marker
            info[-1]['change'] = None

        revisions = [i['rev'] for i in info]
        changes = get_changes(repos, revisions, self.log)
        extra_changes = {}

        if format == 'changelog':
            for rev in revisions:
                changeset = changes[rev]
                cs = {}
                cs['message'] = wrap(changeset.message, 70,
                                     initial_indent='\t',
                                     subsequent_indent='\t')
                files = []
                actions = []
                for cpath, kind, chg, bpath, brev in changeset.get_changes():
                    files.append(bpath if chg == Changeset.DELETE else cpath)
                    actions.append(chg)
                cs['files'] = files
                cs['actions'] = actions
                extra_changes[rev] = cs

        data = {
            'context': web_context(req, 'source', path, parent=repos.resource),
            'reponame': repos.reponame or None, 'repos': repos,
            'path': path, 'rev': rev, 'stop_rev': stop_rev,
            'display_rev': repos.display_rev, 'revranges': revranges,
            'mode': mode, 'verbose': verbose, 'limit': limit,
            'items': info, 'changes': changes, 'extra_changes': extra_changes,
            'graph': graph,
            'wiki_format_messages': self.config['changeset']
                                    .getbool('wiki_format_messages')
        }

        if format == 'changelog':
            return 'revisionlog.txt', data, 'text/plain'
        elif format == 'rss':
            data['context'] = web_context(req, 'source',
                                          path, parent=repos.resource,
                                          absurls=True)
            return 'revisionlog.rss', data, 'application/rss+xml'

        item_ranges = []
        range = []
        for item in info:
            if item['change'] is None:  # separator
                if range:  # start new range
                    range.append(item)
                    item_ranges.append(range)
                    range = []
            else:
                range.append(item)
        if range:
            item_ranges.append(range)
        data['item_ranges'] = item_ranges

        add_stylesheet(req, 'common/css/diff.css')
        add_stylesheet(req, 'common/css/browser.css')

        path_links = get_path_links(req.href, repos.reponame, path, rev)
        if path_links:
            data['path_links'] = path_links
        if path != '/':
            add_link(req, 'up', path_links[-2]['href'], _('Parent directory'))

        rss_href = make_log_href(path, format='rss', revs=revs,
                                 stop_rev=stop_rev)
        add_link(req, 'alternate', auth_link(req, rss_href), _('RSS Feed'),
                 'application/rss+xml', 'rss')
        changelog_href = make_log_href(path, format='changelog', revs=revs,
                                       stop_rev=stop_rev)
        add_link(req, 'alternate', changelog_href, _('ChangeLog'),
                 'text/plain')

        add_ctxtnav(req, _('View Latest Revision'),
                    href=req.href.browser(repos.reponame or None, path))
        if 'next' in req.chrome['links']:
            next = req.chrome['links']['next'][0]
            add_ctxtnav(req, tag.span(tag.a(_('Older Revisions'),
                                            href=next['href']),
                                      Markup(' &rarr;')))

        return 'revisionlog.html', data, None

    # IWikiSyntaxProvider methods

    # int rev ranges or any kind of rev range
    REV_RANGE = r"(?:%(int)s|%(cset)s(?:[:-]%(cset)s)?)" % \
                {'int': Ranges.RE_STR, 'cset': ChangesetModule.CHANGESET_ID}

    def get_wiki_syntax(self):
        yield (
            # [...] form, starts with optional intertrac: [T... or [trac ...
            r"!?\[(?P<it_log>%s\s*)" % WikiParser.INTERTRAC_SCHEME +
            # <from>:<to> + optional path restriction
            r"(?P<log_revs>%s)(?P<log_path>[/?][^\]]*)?\]" % self.REV_RANGE,
            lambda x, y, z: self._format_link(x, 'log1', y[1:-1], y, z))
        yield (
            # r<from>:<to> form + optional path restriction (no intertrac)
            r"(?:\b|!)r%s\b(?:/[a-zA-Z0-9_/+-]+)?" % Ranges.RE_STR,
            lambda x, y, z: self._format_link(x, 'log2', '@' + y[1:], y))

    def get_link_resolvers(self):
        yield ('log', self._format_link)

    LOG_LINK_RE = re.compile(r"([^@:]*)[@:]%s?" % REV_RANGE)

    def _format_link(self, formatter, ns, match, label, fullmatch=None):
        if ns == 'log1':
            groups = fullmatch.groupdict()
            it_log = groups.get('it_log')
            revs = groups.get('log_revs')
            path = groups.get('log_path') or '/'
            target = '%s%s@%s' % (it_log, path, revs)
            # prepending it_log is needed, as the helper expects it there
            intertrac = formatter.shorthand_intertrac_helper(
                'log', target, label, fullmatch)
            if intertrac:
                return intertrac
            path, query, fragment = formatter.split_link(path)
        else:
            assert ns in ('log', 'log2')
            if ns == 'log':
                match, query, fragment = formatter.split_link(match)
            else:
                query = fragment = ''
                match = ''.join(reversed(match.split('/', 1)))
            path = match
            revs = ''
            if self.LOG_LINK_RE.match(match):
                indexes = [sep in match and match.index(sep) for sep in ':@']
                idx = min([i for i in indexes if i is not False])
                path, revs = match[:idx], match[idx+1:]

        rm = RepositoryManager(self.env)
        try:
            reponame, repos, path = rm.get_repository_by_path(path)
            if not reponame:
                reponame = rm.get_default_repository(formatter.context)
                if reponame is not None:
                    repos = rm.get_repository(reponame)

            if repos:
                if 'LOG_VIEW' in formatter.perm(repos.resource):
                    reponame = repos.reponame or None
                    path = path or '/'
                    revranges = RevRanges(repos, revs)
                    if revranges.has_ranges():
                        href = formatter.href.log(reponame, path,
                                                  revs=unicode(revranges))
                    else:
                        # try to resolve if single rev
                        repos.normalize_rev(revs)
                        href = formatter.href.log(reponame, path,
                                                  rev=revs or None)
                    if query and '?' in href:
                        query = '&' + query[1:]
                    return tag.a(label, class_='source',
                                 href=href + query + fragment)
                errmsg = _("No permission to view change log")
            elif reponame:
                errmsg = _("Repository '%(repo)s' not found", repo=reponame)
            else:
                errmsg = _("No default repository defined")
        except TracError as e:
            errmsg = to_unicode(e)
        return tag.a(label, class_='missing source', title=errmsg)


class RevRanges(object):

    def __init__(self, repos, revs=None, resolve=False):
        self.repos = repos
        self.resolve = resolve
        self.pairs = []
        self.a = self.b = None
        if revs:
            self._append(revs)

    def has_ranges(self):
        n = len(self.pairs)
        return n > 1 or n == 1 and self.a != self.b

    def truncate(self, curr_pair, new_pair=None):
        curr_pair = tuple(curr_pair)
        if new_pair:
            new_pair = tuple(new_pair)
        revranges = RevRanges(self.repos, resolve=self.resolve)
        pairs = revranges.pairs
        for pair in self.pairs:
            if pair == curr_pair:
                if new_pair:
                    pairs.append(new_pair)
                break
            pairs.append(pair)
        if pairs:
            revranges.a = pairs[0][0]
            revranges.b = pairs[-1][1]
        revranges._reduce()
        return revranges

    def _normrev(self, rev):
        if not rev:
            raise NoSuchChangeset(rev)
        if self.resolve:
            return self.repos.normalize_rev(rev)
        elif self.repos.has_linear_changesets:
            try:
                return int(rev)
            except (ValueError, TypeError):
                return rev
        else:
            return rev

    _cset_range_re = re.compile(r"""(?:
        %(cset)s[:-]%(cset)s    |  # int or hexa revs
        [0-9]+[:-][A-Za-z_0-9]+ |  # e.g. 42-head
        [A-Za-z_0-9]+[:-][0-9]+ |  # e.g. head-42
        [^:]+:[^:]+                # e.g. master:dev-42
        )\Z
        """ % {'cset': ChangesetModule.CHANGESET_ID}, re.VERBOSE)

    def _append(self, revs):
        if not revs:
            return

        pairs = []
        for rev in re.split(u',\u200b?', revs):
            a = b = None
            if self._cset_range_re.match(rev):
                for sep in ':-':
                    if sep in rev:
                        a, b = rev.split(sep)
                        break
            if a is None:
                a = b = self._normrev(rev)
            elif a == b:
                a = b = self._normrev(a)
            else:
                a = self._normrev(a)
                b = self._normrev(b)
            pairs.append((a, b))
        self.pairs.extend(pairs)
        self._reduce()

    def _reduce(self):
        if all(isinstance(pair[0], (int, long)) and
               isinstance(pair[1], (int, long))
               for pair in self.pairs):
            try:
                ranges = Ranges(unicode(self), reorder=True)
            except:
                pass
            else:
                self.pairs[:] = ranges.pairs
        else:
            seen = set()
            pairs = self.pairs[:]
            for idx, pair in enumerate(pairs):
                if pair in seen:
                    pairs[idx] = None
                else:
                    seen.add(pair)
            if len(pairs) != len(seen):
                self.pairs[:] = filter(None, pairs)
        if self.pairs:
            self.a = self.pairs[0][0]
            self.b = self.pairs[-1][1]
        else:
            self.a = self.b = None

    def __len__(self):
        return len(self.pairs)

    def __unicode__(self):
        sep = '-' if self.repos.has_linear_changesets else ':'
        return ','.join(sep.join(map(unicode, pair)) if pair[0] != pair[1]
                                                     else unicode(pair[0])
                        for pair in self.pairs)
