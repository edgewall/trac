# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2006 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2005-2006 Christian Boos <cboos@neuf.fr>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://projects.edgewall.com/trac/.
#
# Author: Jonas Borgström <jonas@edgewall.com>
#         Christian Boos <cboos@neuf.fr>

import re
import urllib

from trac.core import *
from trac.perm import IPermissionRequestor
from trac.util.datefmt import http_date
from trac.util.markup import html
from trac.versioncontrol import Changeset
from trac.versioncontrol.web_ui.changeset import ChangesetModule
from trac.versioncontrol.web_ui.util import *
from trac.web import IRequestHandler
from trac.web.chrome import add_link, add_stylesheet, INavigationContributor
from trac.wiki import IWikiSyntaxProvider, Formatter

LOG_LIMIT = 100

class LogModule(Component):

    implements(INavigationContributor, IPermissionRequestor, IRequestHandler,
               IWikiSyntaxProvider)

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
        import re
        match = re.match(r'/log(?:(/.*)|$)', req.path_info)
        if match:
            req.args['path'] = match.group(1) or '/'
            return True

    def process_request(self, req):
        req.perm.assert_permission('LOG_VIEW')

        mode = req.args.get('mode', 'stop_on_copy')
        path = req.args.get('path', '/')
        rev = req.args.get('rev')
        stop_rev = req.args.get('stop_rev')
        format = req.args.get('format')
        verbose = req.args.get('verbose')
        limit = LOG_LIMIT

        repos = self.env.get_repository(req.authname)
        normpath = repos.normalize_path(path)
        rev = unicode(repos.normalize_rev(rev))
        if stop_rev:
            stop_rev = unicode(repos.normalize_rev(stop_rev))
            if repos.rev_older_than(rev, stop_rev):
                rev, stop_rev = stop_rev, rev
            
        req.hdf['title'] = path + ' (log)'
        req.hdf['log'] = {
            'mode': mode,
            'path': path,
            'rev': rev,
            'verbose': verbose,
            'stop_rev': stop_rev,
            'browser_href': req.href.browser(path),
            'changeset_href': req.href.changeset(),
            'log_href': req.href.log(path, rev=rev)
        }

        path_links = get_path_links(req.href, path, rev)
        req.hdf['log.path'] = path_links
        if path_links:
            add_link(req, 'up', path_links[-1]['href'], 'Parent directory')

        # The `history()` method depends on the mode:
        #  * for ''stop on copy'' and ''follow copies'', it's `Node.history()` 
        #  * for ''show only add, delete'' it's`Repository.get_path_history()` 
        if mode == 'path_history':
            def history(limit):
                for h in repos.get_path_history(path, rev, limit):
                    yield h
        else:
            history = get_existing_node(req, repos, path, rev).get_history

        # -- retrieve history, asking for limit+1 results
        info = []
        previous_path = repos.normalize_path(path)
        for old_path, old_rev, old_chg in history(limit+1):
            if stop_rev and repos.rev_older_than(old_rev, stop_rev):
                break
            old_path = repos.normalize_path(old_path)
            item = {
                'rev': str(old_rev),
                'path': old_path,
                'log_href': req.href.log(old_path, rev=old_rev),
                'browser_href': req.href.browser(old_path, rev=old_rev),
                'changeset_href': req.href.changeset(old_rev),
                'restricted_href': req.href.changeset(old_rev, new_path=old_path),
                'change': old_chg
            }
            if not (mode == 'path_history' and old_chg == Changeset.EDIT):
                info.append(item)
            if old_path and old_path != previous_path \
               and not (mode == 'path_history' and old_path == normpath):
                item['copyfrom_path'] = old_path
                if mode == 'stop_on_copy':
                    break
            if len(info) > limit: # we want limit+1 entries
                break
            previous_path = old_path
        if info == []:
            # FIXME: we should send a 404 error here
            raise TracError("The file or directory '%s' doesn't exist "
                            "at revision %s or at any previous revision."
                            % (path, rev), 'Nonexistent path')

        def make_log_href(path, **args):
            link_rev = rev
            if rev == str(repos.youngest_rev):
                link_rev = None
            params = {'rev': link_rev, 'mode': mode, 'limit': limit}
            params.update(args)
            if verbose:
                params['verbose'] = verbose
            return req.href.log(path, **params)

        if len(info) == limit+1: # limit+1 reached, there _might_ be some more
            next_rev = info[-1]['rev']
            next_path = info[-1]['path']
            add_link(req, 'next', make_log_href(next_path, rev=next_rev),
                     'Revision Log (restarting at %s, rev. %s)'
                     % (next_path, next_rev))
            # now, only show 'limit' results
            del info[-1]
        
        req.hdf['log.items'] = info

        revs = [i['rev'] for i in info]
        changes = get_changes(self.env, repos, revs, verbose, req, format)
        if format == 'rss':
            # Get the email addresses of all known users
            email_map = {}
            for username,name,email in self.env.get_known_users():
                if email:
                    email_map[username] = email
            for cs in changes.values():
                # For RSS, author must be an email address
                author = cs['author']
                author_email = ''
                if '@' in author:
                    author_email = author
                elif email_map.has_key(author):
                    author_email = email_map[author]
                cs['author'] = author_email
                cs['date'] = http_date(cs['date_seconds'])
        elif format == 'changelog':
            for rev in revs:
                changeset = repos.get_changeset(rev)
                cs = changes[rev]
                cs['message'] = '\n'.join(['\t' + m for m in
                                           changeset.message.split('\n')])
                files = []
                actions = []
                for path, kind, chg, bpath, brev in changeset.get_changes():
                    files.append(chg == Changeset.DELETE and bpath or path)
                    actions.append(chg)
                cs['files'] = files
                cs['actions'] = actions
        req.hdf['log.changes'] = changes

        if req.args.get('format') == 'changelog':
            return 'log_changelog.cs', 'text/plain'
        elif req.args.get('format') == 'rss':
            return 'log_rss.cs', 'application/rss+xml'

        add_stylesheet(req, 'common/css/browser.css')
        add_stylesheet(req, 'common/css/diff.css')

        rss_href = make_log_href(path, format='rss', stop_rev=stop_rev)
        add_link(req, 'alternate', rss_href, 'RSS Feed', 'application/rss+xml',
                 'rss')
        changelog_href = make_log_href(path, format='changelog',
                                       stop_rev=stop_rev)
        add_link(req, 'alternate', changelog_href, 'ChangeLog', 'text/plain')

        return 'log.cs', None

    # IWikiSyntaxProvider methods

    REV_RANGE = "%s[-:]%s" % ((ChangesetModule.CHANGESET_ID,)*2)
    
    def get_wiki_syntax(self):
        yield (
            # [...] form, starts with optional intertrac: [T... or [trac ...
            r"!?\[(?P<it_log>%s\s*)" % Formatter.INTERTRAC_SCHEME +
            # <from>:<to> + optional path restriction
            r"(?P<log_rev>%s)(?P<log_path>/[^\]]*)?\]" % self.REV_RANGE,
            lambda x, y, z: self._format_link(x, 'log1', y[1:-1], y, z))
        yield (
            # r<from>:<to> form (no intertrac and no path restriction)
            r"(?:\b|!)r%s\b" % self.REV_RANGE,
            lambda x, y, z: self._format_link(x, 'log2', '@' + y[1:], y))

    def get_link_resolvers(self):
        yield ('log', self._format_link)

    def _format_link(self, formatter, ns, match, label, fullmatch=None):
        if ns == 'log1':
            it_log = fullmatch.group('it_log')
            rev = fullmatch.group('log_rev')
            path = fullmatch.group('log_path')
        else: # ns == 'log2'
            path, rev, line = get_path_rev_line(match)
        stop_rev = None
        for sep in ':-':
            if not stop_rev and rev and sep in rev:
                stop_rev, rev = rev.split(sep, 1)
        href = formatter.href.log(path or '/', rev=rev, stop_rev=stop_rev)
        if ns == 'log1':
            target = it_log + href[len(formatter.href.log('/')):]
            # prepending it_log is needed, as the helper expects it there
            intertrac = formatter.shorthand_intertrac_helper('log', target,
                                                             label, fullmatch)
            if intertrac:
                return intertrac
        return html.A(label, href=href, class_='source')
