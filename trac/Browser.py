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

from trac import perm, util
from trac.Module import Module
from trac.web.main import add_link
from trac.WikiFormatter import wiki_to_html, wiki_to_oneliner
from trac.versioncontrol import Changeset

import time
import urllib

CHUNK_SIZE = 4096
DISP_MAX_FILE_SIZE = 256 * 1024

def _get_changes(env, db, repos, revs, full=None, req=None, format=None):
    changes = {}
    files = None
    for rev in filter(lambda x: x in revs, revs):
        changeset = repos.get_changeset(rev)
        message = changeset.message
        if format == 'changelog':
            files = [c[0] for c in changeset.get_changes()]
        elif message:
            message = changeset.message
            if not full:
                message = util.shorten_line(message)
                message = wiki_to_oneliner(message, env, db)
            else:
                message = wiki_to_html(message, req.hdf, env, db,
                                       absurls=(format == 'rss'),
                                       escape_newlines=True)
        if not message:
            message = '--'
        changes[rev] = {
            'date_seconds': changeset.date,
            'date': time.strftime('%x %X', time.localtime(changeset.date)),
            'age': util.pretty_timedelta(changeset.date),
            'author': changeset.author or 'anonymous',
            'message': message,
            'files': files,
        }
    return changes

def _get_path_links(href, path, rev):
    links = []
    parts = path.split('/')
    if not parts[-1]:
        parts.pop()
    path = '/'
    for i,part in util.enum(parts):
        path = path + part + '/'
        links.append({
            'name': part or 'root',
            'href': href.browser(path, rev=rev)
        })
    return links


class BrowserModule(Module):

    def render(self, req):
        rev = req.args.get('rev')
        path = req.args.get('path', '/')

        req.hdf['title'] = path
        req.hdf['browser'] = {'path': path, 'log_href': self.env.href.log(path)}

        path_links = _get_path_links(self.env.href, path, rev)
        req.hdf['browser.path'] = path_links
        if len(path_links) > 1:
            add_link(req, 'up', path_links[-2]['href'], 'Parent directory')

        repos = self.env.get_repository(req.authname)
        req.hdf['browser.revision'] = rev or repos.youngest_rev

        node = repos.get_node(path, rev)
        if node.isdir:
            req.hdf['browser.is_dir'] = 1
            self.render_directory(req, repos, node, rev)
        else:
            self.render_file(req, repos, node, rev)

    def render_directory(self, req, repos, node, rev=None):
        self.perm.assert_permission(perm.BROWSER_VIEW)

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
        changes = _get_changes(self.env, self.db, repos,
                               [i['rev'] for i in info])

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
        req.display('browser.cs')

    def render_file(self, req, repos, node, rev=None):
        self.perm.assert_permission(perm.FILE_VIEW)

        changeset = repos.get_changeset(node.rev)
        req.hdf['file'] = {
            'rev': node.rev,
            'changeset_href': self.env.href.changeset(node.rev),
            'date': time.strftime('%x %X', time.localtime(changeset.date)),
            'age': util.pretty_timedelta(changeset.date),
            'author': changeset.author or 'anonymous',
            'message': wiki_to_html(changeset.message or '--',
                                    req.hdf, self.env, self.db,
                                    escape_newlines=True),
            }

        mime_type = node.content_type
        if not mime_type or mime_type == 'application/octet-stream':
            mime_type = self.env.mimeview.get_mimetype(node.name) \
                        or mime_type or 'text/plain'

        # We don't have to guess if the charset is specified in the
        # svn:mime-type property
        ctpos = mime_type.find('charset=')
        if ctpos >= 0:
            charset = mime_type[ctpos + 8:]
        else:
            charset = self.config.get('trac', 'default_charset')

        if req.args.get('format') == 'raw':
            req.send_response(200)
            req.send_header('Content-Type', node.content_type)
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
            content = util.to_utf8(node.get_content().read(DISP_MAX_FILE_SIZE),
                                   charset)
            if len(content) == DISP_MAX_FILE_SIZE:
                req.hdf['file.max_file_size_reached'] = 1
                req.hdf['file.max_file_size'] = DISP_MAX_FILE_SIZE
                preview = ' '
            else:
                preview = self.env.mimeview.display(content, filename=node.name,
                                                    rev=node.rev,
                                                    mimetype=mime_type)
            req.hdf['file.preview'] = preview

            raw_href = self.env.href.browser(node.path, rev=rev and node.rev,
                                             format='raw')
            req.hdf['file.raw_href'] = raw_href
            add_link(req, 'alternate', raw_href, 'Original Format', mime_type)

            req.display('browser.cs')


class FileModule(Module):
    """
    Legacy module that redirects to the browser for URI backwards compatibility.
    """

    def render(self, req):
        path = req.args.get('path', '/')
        rev = req.args.get('rev')
        # FIXME: This should be a permanent redirect
        req.redirect(self.env.href.browser(path, rev))


class LogModule(Module):
    template_name = 'log.cs'
    template_rss_name = 'log_rss.cs'

    def render(self, req):
        self.perm.assert_permission(perm.LOG_VIEW)

        path = req.args.get('path', '/')
        rev = req.args.get('rev')
        format = req.args.get('format')
        stop_rev = req.args.get('stop_rev')
        log_mode = req.args.get('log_mode', 'stop_on_copy')
        full_messages = req.args.get('full_messages', '')
        page = int(req.args.get('page', '1'))
        limit = int(req.args.get('limit') or self.config.get('log', 'limit', '100'))
        # (Note: 100 has often been suggested as a reasonable default)
        pages = urllib.unquote_plus(req.args.get('pages', '')).split(' ')

        if page and page > 0 and page * 2 - 1 < len(pages):
            page_rev = pages[page * 2 - 2]
            page_path = pages[page * 2 - 1]
        else:
            page = 1
            page_rev = rev
            page_path = path
            pages = None
            
        repos = self.env.get_repository(req.authname)
        normpath = repos.normalize_path(path)
        rev = str(repos.normalize_rev(rev))
        page_rev = str(repos.normalize_rev(page_rev))
        if pages == None:
            pages = [page_rev, page_path]

#       self.authzperm.assert_permission(self.path)

        req.hdf['title'] = path + ' (log)'
        req.hdf['log.path'] = path
        req.hdf['log.rev'] = rev
        req.hdf['log.page'] = page
        req.hdf['log.limit'] = limit
        req.hdf['log.mode'] = log_mode
        req.hdf['log.full_messages'] = full_messages
        if stop_rev:
            req.hdf['log.stop_rev'] = stop_rev
        req.hdf['log.browser_href'] = self.env.href.browser(path, rev=rev)
        req.hdf['log.log_href'] = self.env.href.log(path, rev=rev)

        path_links = _get_path_links(self.env.href, path, rev)
        req.hdf['log.path'] = path_links
        if path_links:
            add_link(req, 'up', path_links[-1]['href'], 'Parent directory')

        # 'node' or 'path' history: use get_node()/get_history() or get_path_history()
        if log_mode != 'path_history':
            try:
                node = repos.get_node(page_path or path, page_rev)
            except util.TracError:
                node = None
            if not node:
                log_mode = 'path_history' # show 'path' history instead of 'node' history
            else:
                history = node.get_history

        if log_mode == 'path_history':
            def history():
                for h in repos.get_path_history(path, page_rev):
                    yield h

        # -- retrieve history, asking for limit+1 results
        info = []
        previous_path = repos.normalize_path(path)
        for old_path, old_rev, old_chg in history():
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
            # we optimize for the case old_path is the log.path:
            if old_path == normpath:
                item['path'] = ''
            if not (log_mode == 'path_history' and old_chg == Changeset.EDIT):
                info.append(item)
            if old_path and old_path != previous_path \
               and not (log_mode == 'path_history' and old_path == normpath):
                item['copyfrom_path'] = old_path
                if log_mode == 'stop_on_copy':
                    break
            if len(info) > limit: # we want limit+1 entries
                break
            previous_path = old_path
        if info == [] and rev == page_rev:
            # FIXME: we should send a 404 error here
            raise util.TracError("The file or directory '%s' doesn't exist "
                                 "at revision %s or at any previous revision." % (path, rev),
                                 'Nonexistent path')

        # -- first, previous and next page links:
        #    The page "history" information is encoded in the URL, not optimal
        #    but still better than putting that information in the session or
        #    recomputing the full history each time.
        def make_log_href(**args):
            args.update({
                'rev': rev,
                'log_mode': log_mode,
                'limit': limit,
                })
            if full_messages:
                args['full_messages'] = full_messages
            return self.env.href.log(path, **args)
        
        def add_page_link(what, page):
            add_link(req, what, make_log_href(page=page,
                                              pages=urllib.quote_plus(' '.join(pages))),
                     'Revision Log (Page %d)' % (page))

        if page > 1: # then, one needs to be able to go to previous page
            if page > 2: # then one can directly jump to the first page
                add_page_link('first', 1)
            add_page_link('prev', page - 1)

        if len(info) == limit+1: # limit+1 reached, there _might_ be some more
            if page * 2  == len(pages):
                pages.append(info[-1]['rev'])
                pages.append(info[-1]['path'])
            add_page_link('next', page + 1)
            # now, only show 'limit' results
            del info[-1]
        
        req.hdf['log.items'] = info

        changes = _get_changes(self.env, self.db, repos,
                               [i['rev'] for i in info],
                               full_messages, req, format)
        if format == 'rss':
            for cs in changes.values():
                cs['message'] = util.escape(cs['message'])
        elif format == 'changelog':
            for cs in changes.values():
                cs['message'] = '\n'.join(['\t' + m for m in cs['message'].split('\n')])
        req.hdf['log.changes'] = changes
        
        add_link(req, 'alternate', make_log_href(format='rss', stop_rev=stop_rev),
                 'RSS Feed', 'application/rss+xml', 'rss')
        add_link(req, 'alternate', make_log_href(format='changelog', stop_rev=stop_rev),
                 'ChangeLog', 'text/plain')

        if format == 'rss':
            req.display('log_rss.cs', 'application/rss+xml')
        elif format == 'changelog':
            req.display('log_changelog.cs', 'text/plain')
        else:
            req.display('log.cs')
