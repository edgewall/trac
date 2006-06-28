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

import re
import urllib
import os.path
from fnmatch import fnmatchcase

from trac import util
from trac.config import ListOption, Option
from trac.core import *
from trac.mimeview import Mimeview, is_binary, get_mimetype
from trac.perm import IPermissionRequestor
from trac.util import sorted, embedded_numbers
from trac.util.datefmt import http_date, format_datetime, pretty_timedelta
from trac.util.markup import escape, html, Markup
from trac.util.text import pretty_size
from trac.web import IRequestHandler, RequestDone
from trac.web.chrome import add_link, add_stylesheet, INavigationContributor
from trac.wiki import wiki_to_html, IWikiSyntaxProvider
from trac.versioncontrol.api import NoSuchChangeset
from trac.versioncontrol.web_ui.util import *


CHUNK_SIZE = 4096


class BrowserModule(Component):

    implements(INavigationContributor, IPermissionRequestor, IRequestHandler,
               IWikiSyntaxProvider)

    hidden_properties = Option('browser', 'hide_properties', 'svk:merge',
        """List of subversion properties to hide from the repository browser
        (''since 0.9'')""")

    downloadable_paths = ListOption('browser', 'downloadable_paths',
                                    '/trunk, /branches/*, /tags/*', doc=
        """List of repository paths that can be downloaded.
        
        Leave the option empty if you want to disable all downloads, otherwise
        set it to a comma-separated list of authorized paths (those paths are
        glob patterns, i.e. "*" can be used as a wild card)
        (''since 0.10'')""")

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'browser'

    def get_navigation_items(self, req):
        if not req.perm.has_permission('BROWSER_VIEW'):
            return
        yield ('mainnav', 'browser',
               html.A('Browse Source', href=req.href.browser()))

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
                req.redirect(req.href.browser(req.args.get('path'),
                                              rev=req.args.get('rev'),
                                              format=req.args.get('format')),
                             permanent=True)
            return True

    def process_request(self, req):
        path = req.args.get('path', '/')
        rev = req.args.get('rev') or None

        # Find node for the requested path/rev
        repos = self.env.get_repository(req.authname)
        if rev:
            rev = repos.normalize_rev(rev)
        # If `rev` is `None`, we'll try to reuse `None` consistently,
        # as a special shortcut to the latest revision.
        rev_or_latest = rev or repos.youngest_rev
        node = get_existing_node(req, repos, path, rev_or_latest)

        # Rendered list of node properties
        hidden_properties = self.hidden_properties
        properties = []
        for name, value in node.get_properties().items():
            if not name in hidden_properties:
                properties.append({
                    'name': name,
                    'value': render_node_property(self.env, name, value)})

        req.hdf['title'] = path
        req.hdf['browser'] = {
            'path': path,
            'revision': rev,
            'props': properties,
            'href': req.href.browser(path, rev=rev),
            'log_href': req.href.log(path, rev=rev),
            'restr_changeset_href': req.href.changeset(node.rev,
                                                       node.created_path),
            'anydiff_href': req.href.anydiff(),
        }

        path_links = get_path_links(req.href, path, rev)
        if len(path_links) > 1:
            add_link(req, 'up', path_links[-2]['href'], 'Parent directory')
        req.hdf['browser.path'] = path_links

        if node.isdir:
            req.hdf['browser.is_dir'] = True
            self._render_directory(req, repos, node, rev)
        else:
            self._render_file(req, repos, node, rev)

        add_stylesheet(req, 'common/css/browser.css')
        return 'browser.cs', None

    # Internal methods

    def _render_directory(self, req, repos, node, rev=None):
        req.perm.assert_permission('BROWSER_VIEW')

        # Entries metadata
        info = []
        for entry in node.get_entries():
            info.append({
                'name': entry.name,
                'fullpath': entry.path,
                'is_dir': entry.isdir,
                'content_length': entry.content_length,
                'size': pretty_size(entry.content_length),
                'rev': entry.rev,
                'permission': 1, # FIXME
                'log_href': req.href.log(entry.path, rev=rev),
                'browser_href': req.href.browser(entry.path, rev=rev)
            })
        changes = get_changes(self.env, repos, [i['rev'] for i in info])

        # Ordering of entries
        order = req.args.get('order', 'name').lower()
        desc = req.args.has_key('desc')

        if order == 'date':
            def file_order(a):
                return changes[a['rev']]['date_seconds']
        elif order == 'size':
            def file_order(a):
                return (a['content_length'],
                        embedded_numbers(a['name'].lower()))
        else:
            def file_order(a):
                return embedded_numbers(a['name'].lower())

        dir_order = desc and 1 or -1

        def browse_order(a):
            return a['is_dir'] and dir_order or 0, file_order(a)
        info = sorted(info, key=browse_order, reverse=desc)

        switch_ordering_hrefs = {}
        for col in ('name', 'size', 'date'):
            switch_ordering_hrefs[col] = req.href.browser(
                node.path, rev=rev, order=col,
                desc=(col == order and not desc and 1 or None))

        # ''Zip Archive'' alternate link
        patterns = self.downloadable_paths
        if node.path and patterns and \
               filter(None, [fnmatchcase(node.path, p) for p in patterns]):
            zip_href = req.href.changeset(rev or repos.youngest_rev, node.path,
                                          old=rev, old_path='/', format='zip')
            add_link(req, 'alternate', zip_href, 'Zip Archive',
                     'application/zip', 'zip')

        req.hdf['browser'] = {'order': order, 'desc': desc and 1 or 0,
                              'items': info, 'changes': changes,
                              'order_href': switch_ordering_hrefs}

    def _render_file(self, req, repos, node, rev=None):
        req.perm.assert_permission('FILE_VIEW')

        mimeview = Mimeview(self.env)

        # MIME type detection
        content = node.get_content()
        chunk = content.read(CHUNK_SIZE)
        mime_type = node.content_type
        if not mime_type or mime_type == 'application/octet-stream':
            mime_type = mimeview.get_mimetype(node.name, chunk) or \
                        mime_type or 'text/plain'

        # Eventually send the file directly
        format = req.args.get('format')
        if format in ['raw', 'txt']:
            req.send_response(200)
            req.send_header('Content-Type',
                            format == 'txt' and 'text/plain' or mime_type)
            req.send_header('Content-Length', node.content_length)
            req.send_header('Last-Modified', http_date(node.last_modified))
            req.end_headers()

            while 1:
                if not chunk:
                    raise RequestDone
                req.write(chunk)
                chunk = content.read(CHUNK_SIZE)
        else:
            # The changeset corresponding to the last change on `node` 
            # is more interesting than the `rev` changeset.
            changeset = repos.get_changeset(node.rev)

            message = changeset.message or '--'
            if self.config['changeset'].getbool('wiki_format_messages'):
                message = wiki_to_html(message, self.env, req,
                                       escape_newlines=True)
            else:
                message = html.PRE(message)

            req.hdf['file'] = {
                'rev': node.rev,
                'changeset_href': req.href.changeset(node.rev),
                'date': format_datetime(changeset.date),
                'age': pretty_timedelta(changeset.date),
                'size': pretty_size(node.content_length),
                'author': changeset.author or 'anonymous',
                'message': message
            } 

            # add ''Plain Text'' alternate link if needed
            if not is_binary(chunk) and mime_type != 'text/plain':
                plain_href = req.href.browser(node.path, rev=rev, format='txt')
                add_link(req, 'alternate', plain_href, 'Plain Text',
                         'text/plain')

            # add ''Original Format'' alternate link (always)
            raw_href = req.href.browser(node.path, rev=rev, format='raw')
            add_link(req, 'alternate', raw_href, 'Original Format', mime_type)

            self.log.debug("Rendering preview of node %s@%s with mime-type %s"
                           % (node.name, str(rev), mime_type))

            del content # the remainder of that content is not needed

            req.hdf['file'] = mimeview.preview_to_hdf(
                req, node.get_content(), node.get_content_length(), mime_type,
                node.created_path, raw_href, annotations=['lineno'])

            add_stylesheet(req, 'common/css/code.css')

    # IWikiSyntaxProvider methods

    def get_wiki_syntax(self):
        return []

    def get_link_resolvers(self):
        return [('repos', self._format_link),
                ('source', self._format_link),
                ('browser', self._format_link)]

    def _format_link(self, formatter, ns, path, label):
        path, rev, line = get_path_rev_line(path)
        fragment = ''
        if line is not None:
            fragment = '#L%d' % line
        return html.A(label, class_='source',
                      href=formatter.href.browser(path, rev=rev) + fragment)
