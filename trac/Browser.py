
# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2003, 2004, 2005 Edgewall Software
# Copyright (C) 2003, 2004, 2005 Jonas Borgström <jonas@edgewall.com>
#
# Trac is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version.
#
# Trac is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#
# Author: Jonas Borgström <jonas@edgewall.com>

from __future__ import generators
import re
import time
import urllib

from trac import util
from trac.core import *
from trac.mimeview import get_mimetype, is_binary, detect_unicode, Mimeview
from trac.perm import IPermissionRequestor
from trac.web.chrome import add_link, add_stylesheet, INavigationContributor
from trac.web.main import IRequestHandler
from trac.wiki import wiki_to_html, wiki_to_oneliner, IWikiSyntaxProvider
from trac.versioncontrol import Changeset

CHUNK_SIZE = 4096
DISP_MAX_FILE_SIZE = 256 * 1024

rev_re = re.compile(r"([^#]+)#(.+)")
img_re = re.compile(r"\.(gif|jpg|jpeg|png)(\?.*)?$", re.IGNORECASE)


def _get_changes(env, repos, revs, full=None, req=None, format=None):
    db = env.get_db_cnx()
    changes = {}
    for rev in revs:
        changeset = repos.get_changeset(rev)
        message = changeset.message
        shortlog = util.shorten_line(message)        
        files = None
        if format == 'changelog':
            files = [change[0] for change in changeset.get_changes()]
        elif message:
            if not full:
                message = wiki_to_oneliner(shortlog, env, db)
            else:
                message = wiki_to_html(message, env, req, db,
                                       absurls=(format == 'rss'),
                                       escape_newlines=True)
        if not message:
            message = '--'
        changes[rev] = {
            'date_seconds': changeset.date,
            'date': time.strftime('%x %X', time.localtime(changeset.date)),
            'age': util.pretty_timedelta(changeset.date),
            'author': changeset.author or 'anonymous',
            'shortlog': shortlog,
            'message': message,
            'files': files
        }
    return changes

def _get_path_links(href, path, rev):
    links = []
    parts = path.split('/')
    if not parts[-1]:
        parts.pop()
    path = '/'
    for part in parts:
        path = path + part + '/'
        links.append({
            'name': part or 'root',
            'href': href.browser(path, rev=rev)
        })
    return links

def _get_path_rev(path):
    rev = None
    match = rev_re.search(path)
    if match:
        path = match.group(1)
        rev = match.group(2)
    path = urllib.unquote(path)
    return (path, rev)


class BrowserModule(Component):

    implements(INavigationContributor, IPermissionRequestor, IRequestHandler,
               IWikiSyntaxProvider)

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'browser'

    def get_navigation_items(self, req):
        if not req.perm.has_permission('BROWSER_VIEW'):
            return
        yield 'mainnav', 'browser', '<a href="%s">Browse Source</a>' \
              % util.escape(self.env.href.browser())

    # IPermissionRequestor methods

    def get_permission_actions(self):
        return ['BROWSER_VIEW', 'FILE_VIEW']

    # IRequestHandler methods

    def match_request(self, req):
        import re
        match = re.match(r'/(browser|file)(?:(/.*))?', req.path_info)
        if match:
            req.args['path'] = match.group(2) or '/'
            if match.group(1) == 'file':
                # FIXME: This should be a permanent redirect
                req.redirect(self.env.href.browser(req.args.get('path'),
                                                   rev=req.args.get('rev')))
            return True

    def process_request(self, req):
        path = req.args.get('path', '/')
        rev = req.args.get('rev')

        repos = self.env.get_repository(req.authname)
        node = repos.get_node(path, rev)

        req.hdf['title'] = path
        req.hdf['browser'] = {
            'path': path,
            'revision': rev or repos.youngest_rev,
            'props': dict([(util.escape(name), util.escape(value))
                           for name, value in node.get_properties().items()]),
            'href': self.env.href.browser(path,rev=rev or repos.youngest_rev),
            'log_href': self.env.href.log(path)
        }

        path_links = _get_path_links(self.env.href, path, rev)
        if len(path_links) > 1:
            add_link(req, 'up', path_links[-2]['href'], 'Parent directory')
        req.hdf['browser.path'] = path_links

        if node.isdir:
            req.hdf['browser.is_dir'] = True
            self._render_directory(req, repos, node, rev)
        else:
            self._render_file(req, repos, node, rev)

        add_stylesheet(req, 'css/browser.css')
        return 'browser.cs', None

    # Internal methods

    def _render_directory(self, req, repos, node, rev=None):
        req.perm.assert_permission('BROWSER_VIEW')

        order = req.args.get('order', 'name').lower()
        req.hdf['browser.order'] = order
        desc = req.args.has_key('desc')
        req.hdf['browser.desc'] = desc and 1 or 0

        info = []
        for entry in node.get_entries():
            entry_rev = rev and entry.rev
            info.append({
                'name': entry.name,
                'fullpath': entry.path,
                'is_dir': int(entry.isdir),
                'content_length': entry.content_length,
                'size': util.pretty_size(entry.content_length),
                'rev': entry.rev,
                'permission': 1, # FIXME
                'log_href': self.env.href.log(entry.path, rev=rev),
                'browser_href': self.env.href.browser(entry.path, rev=rev)
            })
        changes = _get_changes(self.env, repos, [i['rev'] for i in info])

        def cmp_func(a, b):
            dir_cmp = (a['is_dir'] and -1 or 0) + (b['is_dir'] and 1 or 0)
            if dir_cmp:
                return dir_cmp
            neg = desc and -1 or 1
            if order == 'date':
                return neg * cmp(changes[b['rev']]['date_seconds'],
                                 changes[a['rev']]['date_seconds'])
            elif order == 'size':
                return neg * cmp(a['content_length'], b['content_length'])
            else:
                return neg * cmp(a['name'].lower(), b['name'].lower())
        info.sort(cmp_func)

        req.hdf['browser.items'] = info
        req.hdf['browser.changes'] = changes

    def _render_file(self, req, repos, node, rev=None):
        req.perm.assert_permission('FILE_VIEW')

        changeset = repos.get_changeset(node.rev)  
        req.hdf['file'] = {  
            'rev': node.rev,  
            'changeset_href': self.env.href.changeset(node.rev),  
            'date': time.strftime('%x %X', time.localtime(changeset.date)),  
            'age': util.pretty_timedelta(changeset.date),  
            'author': changeset.author or 'anonymous',  
            'message': wiki_to_html(changeset.message or '--', self.env, req,  
                                    escape_newlines=True)  
        } 
        mime_type = node.content_type
        if not mime_type or mime_type == 'application/octet-stream':
            mime_type = get_mimetype(node.name) or mime_type or 'text/plain'

        # We don't have to guess if the charset is specified in the
        # svn:mime-type property
        ctpos = mime_type.find('charset=')
        if ctpos >= 0:
            charset = mime_type[ctpos + 8:]
        else:
            charset = None

        format = req.args.get('format')
        if format in ['raw', 'txt']:
            req.send_response(200)
            req.send_header('Content-Type',
                            format == 'txt' and 'text/plain' or mime_type)
            req.send_header('Content-Length', node.content_length)
            req.send_header('Last-Modified', util.http_date(node.last_modified))
            req.end_headers()

            content = node.get_content()
            while 1:
                chunk = content.read(CHUNK_SIZE)
                if not chunk:
                    break
                req.write(chunk)

        else:
            # Generate HTML preview
            content = node.get_content().read(DISP_MAX_FILE_SIZE)
            if not charset:
                charset = detect_unicode(content) or \
                          self.config.get('trac', 'default_charset')
            if not is_binary(content):
                content = util.to_utf8(content, charset)
                if mime_type != 'text/plain':
                    plain_href = self.env.href.browser(node.path,
                                                       rev=rev and node.rev,
                                                       format='txt')
                    add_link(req, 'alternate', plain_href, 'Plain Text',
                             'text/plain')
            if len(content) == DISP_MAX_FILE_SIZE:
                req.hdf['file.max_file_size_reached'] = 1
                req.hdf['file.max_file_size'] = DISP_MAX_FILE_SIZE
                preview = ' '
            else:
                preview = Mimeview(self.env).render(req, mime_type, content,
                                                    node.name, node.rev,
                                                    annotations=['lineno'])
            req.hdf['file.preview'] = preview

            raw_href = self.env.href.browser(node.path, rev=rev and node.rev,
                                             format='raw')
            req.hdf['file.raw_href'] = raw_href
            add_link(req, 'alternate', raw_href, 'Original Format', mime_type)

            add_stylesheet(req, 'css/code.css')

    # IWikiSyntaxProvider methods
    
    def get_wiki_syntax(self):
        return []

    def get_link_resolvers(self):
        return [('repos', self._format_link),
                ('source', self._format_link),
                ('browser', self._format_link)]

    def _format_link(self, formatter, ns, path, label):
        match = img_re.search(path)
        if formatter.flavor != 'oneliner' and match:
            return '<img src="%s" alt="%s" />' % \
                   (formatter.href.file(path, format='raw'), label)
        path, rev = _get_path_rev(path)
        label = urllib.unquote(label)
        return '<a class="source" href="%s">%s</a>' \
               % (formatter.href.browser(path, rev=rev), label)


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
            req.args['path'] = match.group(1)
            return 1

    def process_request(self, req):
        req.perm.assert_permission('LOG_VIEW')

        mode = req.args.get('mode', 'stop_on_copy')
        path = req.args.get('path', '/')
        rev = req.args.get('rev')
        format = req.args.get('format')
        stop_rev = req.args.get('stop_rev')
        verbose = req.args.get('verbose')
        limit = int(req.args.get('limit') or 100)

        req.hdf['title'] = path + ' (log)'
        req.hdf['log'] = {
            'path': path,
            'rev': rev,
            'verbose': verbose,
            'stop_rev': stop_rev,
            'browser_href': self.env.href.browser(path, rev=rev),
            'log_href': self.env.href.log(path, rev=rev)
        }

        path_links = _get_path_links(self.env.href, path, rev)
        req.hdf['log.path'] = path_links
        if path_links:
            add_link(req, 'up', path_links[-1]['href'], 'Parent directory')

        repos = self.env.get_repository(req.authname)
        normpath = repos.normalize_path(path)
        rev = str(repos.normalize_rev(rev))

        # 'node' or 'path' history: use get_node()/get_history() or get_path_history()
        if mode != 'path_history':
            try:
                node = repos.get_node(path, rev)
            except TracError:
                node = None
            if not node:
                # show 'path' history instead of 'node' history
                mode = 'path_history'
            else:
                history = node.get_history

        req.hdf['log.mode'] = mode # mode might have change (see 3 lines above)

        if mode == 'path_history':
            def history(limit):
                for h in repos.get_path_history(path, rev, limit):
                    yield h

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

        changes = _get_changes(self.env, repos, [i['rev'] for i in info],
                               verbose, req, format)
        if format == 'rss':
            # Get the email addresses of all known users
            email_map = {}
            for username,name,email in self.env.get_known_users():
                if email:
                    email_map[username] = email
            for cs in changes.values():
                cs['message'] = util.escape(cs['message'])
                cs['shortlog'] = util.escape(cs['shortlog'].replace('\n', ' '))
                # For RSS, author must be an email address
                author = cs['author']
                author_email = ''
                if '@' in author:
                    author_email = author
                elif author in email_map.keys():
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

        add_stylesheet(req, 'css/browser.css')
        add_stylesheet(req, 'css/diff.css')

        rss_href = make_log_href(path, format='rss', stop_rev=stop_rev)
        add_link(req, 'alternate', rss_href, 'RSS Feed', 'application/rss+xml',
                 'rss')
        changelog_href = make_log_href(path, format='changelog',
                                       stop_rev=stop_rev)
        add_link(req, 'alternate', changelog_href, 'ChangeLog', 'text/plain')

        return 'log.cs', None

    # IWikiSyntaxProvider methods
    
    def get_wiki_syntax(self):
        return []

    def get_link_resolvers(self):
        yield ('log', self._format_link)

    def _format_link(self, formatter, ns, path, label):
        path, rev = _get_path_rev(path)
        stop_rev = None
        if rev and ':' in rev:
            stop_rev, rev = rev.split(':',1)
        label = urllib.unquote(label)
        return '<a class="source" href="%s">%s</a>' \
               % (formatter.href.log(path, rev=rev, stop_rev=stop_rev), label)
