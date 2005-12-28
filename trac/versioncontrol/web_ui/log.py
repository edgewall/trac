# -*- coding: iso-8859-1 -*-
#
# Copyright (C) 2003-2005 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgström <jonas@edgewall.com>
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

from trac import util
from trac.core import *
from trac.perm import IPermissionRequestor
from trac.web import IRequestHandler
from trac.web.chrome import add_link, add_stylesheet, INavigationContributor
from trac.wiki import IWikiSyntaxProvider
from trac.versioncontrol import Changeset
from trac.versioncontrol.web_ui.util import *

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
            return 1

    def process_request(self, req):
        req.perm.assert_permission('LOG_VIEW')

        mode = req.args.get('mode', 'stop_on_copy')
        path = req.args.get('path', '/')
        rev = req.args.get('rev')
        format = req.args.get('format')
        stop_rev = req.args.get('stop_rev')
        verbose = req.args.get('verbose')
        limit = LOG_LIMIT

        req.hdf['title'] = path + ' (log)'
        req.hdf['log'] = {
            'mode': mode,
            'path': path,
            'rev': rev,
            'verbose': verbose,
            'stop_rev': stop_rev,
            'browser_href': self.env.href.browser(path),
            'log_href': self.env.href.log(path, rev=rev)
        }

        path_links = get_path_links(self.env.href, path, rev)
        req.hdf['log.path'] = path_links
        if path_links:
            add_link(req, 'up', path_links[-1]['href'], 'Parent directory')

        repos = self.env.get_repository(req.authname)
        normpath = repos.normalize_path(path)
        rev = str(repos.normalize_rev(rev))

        # ''Node history'' uses `Node.history()`,
        # ''Path history'' uses `Repository.get_path_history()`
        if mode == 'path_history':
            def history(limit):
                for h in repos.get_path_history(path, rev, limit):
                    yield h
        else:
            history = get_existing_node(self.env, repos, path, rev).get_history

        # -- retrieve history, asking for limit+1 results
        info = []
        previous_path = repos.normalize_path(path)
        for old_path, old_rev, old_chg in history(limit+1):
            if stop_rev and repos.rev_older_than(old_rev, stop_rev):
                break
            old_path = repos.normalize_path(old_path)
            item = {
                'rev': str(old_rev),
                'path': str(old_path),
                'log_href': self.env.href.log(old_path, rev=old_rev),
                'browser_href': self.env.href.browser(old_path, rev=old_rev),
                'changeset_href': self.env.href.changeset(old_rev),
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
            return self.env.href.log(path, **params)

        if len(info) == limit+1: # limit+1 reached, there _might_ be some more
            next_rev = info[-1]['rev']
            next_path = info[-1]['path']
            add_link(req, 'next', make_log_href(next_path, rev=next_rev),
                     'Revision Log (restarting at %s, rev. %s)'
                     % (next_path, next_rev))
            # now, only show 'limit' results
            del info[-1]
        
        req.hdf['log.items'] = info

        changes = get_changes(self.env, repos, [i['rev'] for i in info],
                              verbose, req, format)
        if format == 'rss':
            # Get the email addresses of all known users
            email_map = {}
            for username,name,email in self.env.get_known_users():
                if email:
                    email_map[username] = email
            for cs in changes.values():
                cs['shortlog'] = cs['shortlog'].replace('\n', ' ')
                # For RSS, author must be an email address
                author = cs['author']
                author_email = ''
                if '@' in author:
                    author_email = author
                elif email_map.has_key(author):
                    author_email = email_map[author]
                cs['author'] = author_email
                cs['date'] = util.http_date(cs['date_seconds'])
        elif format == 'changelog':
            for cs in changes.values():
                cs['message'] = '\n'.join(['\t' + m for m in
                                           cs['message'].split('\n')])
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
    
    def get_wiki_syntax(self):
        yield (r"!?\[\d+:\d+\]|(?:\b|!)r\d+:\d+\b",
               lambda x, y, z: self._format_link(x, 'log',
                                                 '#'+(y[0] == 'r' and y[1:]
                                                      or y[1:-1]), y))

    def get_link_resolvers(self):
        yield ('log', self._format_link)

    def _format_link(self, formatter, ns, path, label):
        path, rev, line = get_path_rev_line(path)
        stop_rev = None
        if rev and ':' in rev:
            stop_rev, rev = rev.split(':', 1)
        label = urllib.unquote(label)
        return '<a class="source" href="%s">%s</a>' \
               % (formatter.href.log(path, rev=rev, stop_rev=stop_rev), label)
