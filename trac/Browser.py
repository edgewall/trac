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

from trac import perm, util
from trac.Module import Module
from trac.web.main import add_link
from trac.WikiFormatter import wiki_to_html, wiki_to_oneliner

import time

CHUNK_SIZE = 4096
DISP_MAX_FILE_SIZE = 256 * 1024

def _get_changes(env, db, repos, revs):
    changes = {}
    for rev in filter(lambda x: x in revs, revs):
        changeset = repos.get_changeset(rev)
        changes[rev] = {
            'date_seconds': changeset.date,
            'date': time.strftime('%x %X', time.localtime(changeset.date)),
            'age': util.pretty_timedelta(changeset.date),
            'author': changeset.author or 'anonymous',
            'message': wiki_to_oneliner(util.shorten_line(util.wiki_escape_newline(changeset.message)),
                                        env, db)
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
            'message': wiki_to_html(util.wiki_escape_newline(changeset.message),
                                    req.hdf, self.env, self.db)
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

#       self.authzperm.assert_permission(self.path)

        req.hdf['title'] = path + ' (log)'
        req.hdf['log.path'] = path
        req.hdf['log.browser_href'] = self.env.href.browser(path)

        path_links = _get_path_links(self.env.href, path, rev)
        req.hdf['log.path'] = path_links
        if path_links:
            add_link(req, 'up', path_links[-1]['href'], 'Parent directory')

        repos = self.env.get_repository(req.authname)
        node = repos.get_node(path, rev)
        if not node:
            # FIXME: we should send a 404 error here
            raise util.TracError("The file or directory '%s' doesn't exist in "
                                 "the repository at revision %d." % (path, rev),
                                 'Nonexistent path')
        info = []
        for old_path, old_rev in node.get_history():
            info.append({
                'rev': old_rev,
                'browser_href': self.env.href.browser(old_path, rev=old_rev),
                'changeset_href': self.env.href.changeset(old_rev)
            })
        req.hdf['log.items'] = info
        req.hdf['log.changes'] = _get_changes(self.env, self.db, repos,
                                              [i['rev'] for i in info])

        rss_href = self.env.href.log(path, rev=rev, format='rss')
        add_link(req, 'alternate', rss_href, 'RSS Feed', 'application/rss+xml',
                 'rss')

        if req.args.get('format') == 'rss':
            req.display('log_rss.cs', 'application/rss+xml')
        else:
            req.display('log.cs')
