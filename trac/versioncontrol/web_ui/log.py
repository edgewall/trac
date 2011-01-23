# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2009 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2005-2006 Christian Boos <cboos@neuf.fr>
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
#         Christian Boos <cboos@neuf.fr>

import re

from genshi.core import Markup
from genshi.builder import tag

from trac.config import IntOption
from trac.core import *
from trac.mimeview import Context
from trac.perm import IPermissionRequestor
from trac.resource import ResourceNotFound
from trac.util import Ranges
from trac.util.compat import any
from trac.util.text import to_unicode, wrap
from trac.util.translation import _
from trac.versioncontrol.api import RepositoryManager, Changeset, \
                                    NoSuchChangeset
from trac.versioncontrol.web_ui.changeset import ChangesetModule
from trac.versioncontrol.web_ui.util import *
from trac.web import IRequestHandler
from trac.web.chrome import add_ctxtnav, add_link, add_stylesheet, \
                            INavigationContributor, Chrome
from trac.wiki import IWikiSyntaxProvider, WikiParser 

class LogModule(Component):

    implements(INavigationContributor, IPermissionRequestor, IRequestHandler,
               IWikiSyntaxProvider)

    default_log_limit = IntOption('revisionlog', 'default_log_limit', 100,
        """Default value for the limit argument in the TracRevisionLog
        (''since 0.11'').""")

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
        rev = req.args.get('rev')
        stop_rev = req.args.get('stop_rev')
        revs = req.args.get('revs')
        format = req.args.get('format')
        verbose = req.args.get('verbose')
        limit = int(req.args.get('limit') or self.default_log_limit)

        rm = RepositoryManager(self.env)
        reponame, repos, path = rm.get_repository_by_path(path)
        
        if not repos:
            raise ResourceNotFound(_("Repository '%(repo)s' not found",
                                   repo=reponame))

        if reponame != repos.reponame:  # Redirect alias
            qs = req.query_string
            req.redirect(req.href.log(repos.reponame or None, path)
                         + (qs and '?' + qs or ''))

        normpath = repos.normalize_path(path)
        # if `revs` parameter is given, then we're restricted to the 
        # corresponding revision ranges.
        # If not, then we're considering all revisions since `rev`, 
        # on that path, in which case `revranges` will be None.
        revranges = None
        if revs:
            try:
                revranges = Ranges(revs)
                rev = revranges.b
            except ValueError:
                pass
        rev = unicode(repos.normalize_rev(rev))
        display_rev = repos.display_rev

        # The `history()` method depends on the mode:
        #  * for ''stop on copy'' and ''follow copies'', it's `Node.history()`
        #    unless explicit ranges have been specified
        #  * for ''show only add, delete'' we're using
        #   `Repository.get_path_history()` 
        cset_resource = repos.resource.child('changeset')
        if mode == 'path_history':
            def history():
                for h in repos.get_path_history(path, rev):
                    if 'CHANGESET_VIEW' in req.perm(cset_resource(id=h[1])):
                        yield h
        elif revranges:
            def history():
                prevpath = path
                expected_next_item = None
                ranges = list(revranges.pairs)
                ranges.reverse()
                for (a, b) in ranges:
                    a = repos.normalize_rev(a)
                    b = repos.normalize_rev(b)
                    while not repos.rev_older_than(b, a):
                        node = get_existing_node(req, repos, prevpath, b)
                        node_history = list(node.get_history(2))
                        p, rev, chg = node_history[0]
                        if repos.rev_older_than(rev, a):
                            break # simply skip, no separator
                        if 'CHANGESET_VIEW' in req.perm(cset_resource(id=rev)):
                            if expected_next_item:
                                # check whether we're continuing previous range
                                np, nrev, nchg = expected_next_item
                                if rev != nrev: # no, we need a separator
                                    yield (np, nrev, None)
                            yield node_history[0]
                        prevpath = node_history[-1][0] # follow copy
                        b = repos.previous_rev(rev)
                        if len(node_history) > 1:
                            expected_next_item = node_history[-1]
                        else:
                            expected_next_item = None
                if expected_next_item:
                    yield (expected_next_item[0], expected_next_item[1], None)
        else:
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
            if old_chg is None: # separator entry
                stop_limit = limit
            else:
                count += 1
                stop_limit = limit + 1
            if count >= stop_limit:
                break
            previous_path = old_path
        if info == []:
            node = get_existing_node(req, repos, path, rev)
            if repos.rev_older_than(stop_rev, node.created_rev):
                # FIXME: we should send a 404 error here
                raise TracError(_("The file or directory '%(path)s' doesn't "
                    "exist at revision %(rev)s or at any previous revision.", 
                    path=path, rev=display_rev(rev)), _('Nonexistent path'))

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
            info = [i for i in info if i['change']] # drop separators
            if info and count > limit:
                del info[-1]
        elif info and count >= limit:
            # stop_limit reached, there _might_ be some more
            next_rev = info[-1]['rev']
            next_path = info[-1]['path']
            next_revranges = None
            if revranges:
                next_revranges = str(revranges.truncate(next_rev))
            if next_revranges or not revranges:
                older_revisions_href = make_log_href(next_path, rev=next_rev,
                                                     revs=next_revranges)
                add_link(req, 'next', older_revisions_href,
                    _('Revision Log (restarting at %(path)s, rev. %(rev)s)',
                    path=next_path, rev=display_rev(next_rev)))
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
                    files.append(chg == Changeset.DELETE and bpath or cpath)
                    actions.append(chg)
                cs['files'] = files
                cs['actions'] = actions
                extra_changes[rev] = cs

        data = {
            'context': Context.from_request(req, 'source', path,
                                            parent=repos.resource),
            'reponame': repos.reponame or None, 'repos': repos,
            'path': path, 'rev': rev, 'stop_rev': stop_rev,
            'display_rev': display_rev, 'revranges': revranges,
            'mode': mode, 'verbose': verbose, 'limit' : limit,
            'items': info, 'changes': changes, 'extra_changes': extra_changes,
            'wiki_format_messages':
            self.config['changeset'].getbool('wiki_format_messages')
        }

        if format == 'changelog':
            return 'revisionlog.txt', data, 'text/plain'
        elif format == 'rss':
            data['email_map'] = Chrome(self.env).get_email_map()
            data['context'] = Context.from_request(req, 'source', 
                                                   path, parent=repos.resource,
                                                   absurls=True)
            return 'revisionlog.rss', data, 'application/rss+xml'

        item_ranges = []
        range = []
        for item in info:
            if item['change'] is None: # separator
                if range: # start new range
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
        add_link(req, 'alternate', rss_href, _('RSS Feed'),
                 'application/rss+xml', 'rss')
        changelog_href = make_log_href(path, format='changelog', revs=revs,
                                       stop_rev=stop_rev)
        add_link(req, 'alternate', changelog_href, _('ChangeLog'), 'text/plain')

        add_ctxtnav(req, _('View Latest Revision'), 
                    href=req.href.browser(repos.reponame or None, path))
        if 'next' in req.chrome['links']:
            next = req.chrome['links']['next'][0]
            add_ctxtnav(req, tag.span(tag.a(_('Older Revisions'), 
                                            href=next['href']),
                                      Markup(' &rarr;')))

        return 'revisionlog.html', data, None

    # IWikiSyntaxProvider methods

    REV_RANGE = r"(?:%s|%s)" % (Ranges.RE_STR, ChangesetModule.CHANGESET_ID)
    #                          int rev ranges or any kind of rev
    
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
                revranges = None
                if any(c for c in ':-,' if c in revs):
                    revranges = self._normalize_ranges(repos, path, revs)
                    revs = None
                if 'LOG_VIEW' in formatter.perm:
                    if revranges:
                        href = formatter.href.log(repos.reponame or None,
                                                  path or '/', 
                                                  revs=str(revranges))
                    else:
                        try:
                            rev = repos.normalize_rev(revs)
                        except NoSuchChangeset:
                            rev = None
                        href = formatter.href.log(repos.reponame or None,
                                                  path or '/', rev=rev)
                    if query and (revranges or revs):
                        query = '&' + query[1:]
                    return tag.a(label, class_='source',
                                 href=href + query + fragment)
                errmsg = _("No permission to view change log")
            elif reponame:
                errmsg = _("Repository '%(repo)s' not found", repo=reponame)
            else:
                errmsg = _("No default repository defined")
        except TracError, e:
            errmsg = to_unicode(e)
        return tag.a(label, class_='missing source', title=errmsg)

    LOG_LINK_RE = re.compile(r"([^@:]*)[@:]%s?" % REV_RANGE)

    def _normalize_ranges(self, repos, path, revs):
        ranges = revs.replace(':', '-')
        try:
            # fast path; only numbers
            return Ranges(ranges, reorder=True) 
        except ValueError:
            # slow path, normalize each rev
            splitted_ranges = re.split(r'([-,])', ranges)
            try:
                revs = [repos.normalize_rev(r) for r in splitted_ranges[::2]]
            except NoSuchChangeset:
                return None
            seps = splitted_ranges[1::2] + ['']
            ranges = ''.join([str(rev)+sep for rev, sep in zip(revs, seps)])
            return Ranges(ranges)
