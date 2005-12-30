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

import re
import urllib

from trac import util
from trac.core import *
from trac.mimeview import Mimeview, is_binary, get_mimetype
from trac.perm import IPermissionRequestor
from trac.web import IRequestHandler, RequestDone
from trac.web.chrome import add_link, add_stylesheet, INavigationContributor
from trac.wiki import wiki_to_html, wiki_to_oneliner, IWikiSyntaxProvider
from trac.versioncontrol.web_ui.util import *


IMG_RE = re.compile(r"\.(gif|jpg|jpeg|png)(\?.*)?$", re.IGNORECASE)

CHUNK_SIZE = 4096

DIGITS = re.compile(r'[0-9]+')
def _natural_order(x, y):
    """Comparison function for natural order sorting based on
    http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/214202."""
    nx = ny = 0
    while True:
        a = DIGITS.search(x, nx)
        b = DIGITS.search(y, ny)
        if None in (a, b):
            return cmp(x[nx:], y[ny:])
        r = (cmp(x[nx:a.start()], y[ny:b.start()]) or
             cmp(int(x[a.start():a.end()]), int(y[b.start():b.end()])))
        if r:
            return r
        nx, ny = a.end(), b.end()


class BrowserModule(Component):

    implements(INavigationContributor, IPermissionRequestor, IRequestHandler,
               IWikiSyntaxProvider)

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'browser'

    def get_navigation_items(self, req):
        if not req.perm.has_permission('BROWSER_VIEW'):
            return
        yield ('mainnav', 'browser',
               util.Markup('<a href="%s">Browse Source</a>',
                           self.env.href.browser()))

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
                                                   rev=req.args.get('rev'),
                                                   format=req.args.get('format')))
            return True

    def process_request(self, req):
        path = req.args.get('path', '/')
        rev = req.args.get('rev')

        repos = self.env.get_repository(req.authname)
        node = get_existing_node(self.env, repos, path, rev)

        hidden_properties = [p.strip() for p
                             in self.config.get('browser', 'hide_properties',
                                                'svk:merge').split(',')]
        req.hdf['title'] = path
        req.hdf['browser'] = {
            'path': path,
            'revision': rev or repos.youngest_rev,
            'props': dict([(name, value)
                           for name, value in node.get_properties().items()
                           if not name in hidden_properties]),
            'href': self.env.href.browser(path, rev=rev or
                                          repos.youngest_rev),
            'log_href': self.env.href.log(path, rev=rev or None)
        }

        path_links = get_path_links(self.env.href, path, rev)
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

        order = req.args.get('order', 'name').lower()
        req.hdf['browser.order'] = order
        desc = req.args.has_key('desc')
        req.hdf['browser.desc'] = desc and 1 or 0

        info = []
        for entry in node.get_entries():
            info.append({
                'name': entry.name,
                'fullpath': entry.path,
                'is_dir': int(entry.isdir),
                'content_length': entry.content_length,
                'size': util.pretty_size(entry.content_length),
                'rev': entry.rev,
                'permission': 1, # FIXME
                'log_href': self.env.href.log(entry.path, rev=rev),
                'browser_href': self.env.href.browser(entry.path,
                                                      rev=rev)
            })
        changes = get_changes(self.env, repos, [i['rev'] for i in info])

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
                return neg * _natural_order(a['name'].lower(),
                                            b['name'].lower())
        info.sort(cmp_func)

        req.hdf['browser.items'] = info
        req.hdf['browser.changes'] = changes

    def _render_file(self, req, repos, node, rev=None):
        req.perm.assert_permission('FILE_VIEW')

        changeset = repos.get_changeset(node.rev)  
        req.hdf['file'] = {  
            'rev': node.rev,  
            'changeset_href': self.env.href.changeset(node.rev),
            'date': util.format_datetime(changeset.date),
            'age': util.pretty_timedelta(changeset.date),
            'author': changeset.author or 'anonymous',
            'message': wiki_to_html(changeset.message or '--', self.env, req,
                                    escape_newlines=True)
        }

        mimeview = Mimeview(self.env)
        
        def get_mime_type(content=None):
            mime_type = node.content_type
            if not mime_type or mime_type == 'application/octet-stream':
                mime_type = get_mimetype(node.name, content) or \
                            mime_type or 'text/plain'
            return mime_type

        format = req.args.get('format')
        if format in ['raw', 'txt']:
            content = node.get_content()
            chunk = content.read(CHUNK_SIZE)
            mime_type = get_mime_type(chunk)

            req.send_response(200)
            req.send_header('Content-Type',
                            format == 'txt' and 'text/plain' or mime_type)
            req.send_header('Content-Length', node.content_length)
            req.send_header('Last-Modified', util.http_date(node.last_modified))
            req.end_headers()

            while 1:
                if not chunk:
                    raise RequestDone
                req.write(chunk)
                chunk = content.read(CHUNK_SIZE)
        else:
            # Generate HTML preview
            content = node.get_content().read(mimeview.max_preview_size())
            mime_type = get_mime_type(content)
            use_rev = rev and node.rev
            
            if not is_binary(content):
                if mime_type != 'text/plain':
                    plain_href = self.env.href.browser(node.path, rev=use_rev,
                                                       format='txt')
                    add_link(req, 'alternate', plain_href, 'Plain Text',
                             'text/plain')
                    
            self.log.debug("Rendering preview of file %s with mime-type %s"
                           % (node.name, mime_type))

            req.hdf['file'] = mimeview.preview_to_hdf(req, content, mime_type,
                                                      node.name, node.rev,
                                                      annotations=['lineno'])

            raw_href = self.env.href.browser(node.path, rev=use_rev,
                                             format='raw')
            add_link(req, 'alternate', raw_href, 'Original Format', mime_type)
            req.hdf['file.raw_href'] = raw_href

            add_stylesheet(req, 'common/css/code.css')

    # IWikiSyntaxProvider methods
    
    def get_wiki_syntax(self):
        return []

    def get_link_resolvers(self):
        return [('repos', self._format_link),
                ('source', self._format_link),
                ('browser', self._format_link)]

    def _format_link(self, formatter, ns, path, label):
        match = IMG_RE.search(path)
        if formatter.flavor != 'oneliner' and match:
            return '<img src="%s" alt="%s" />' % \
                   (formatter.href.file(path, format='raw'), label)
        path, rev, line = get_path_rev_line(path)
        if line is not None:
            anchor = '#L%d' % line
        else:
            anchor = ''
        label = urllib.unquote(label)
        return '<a class="source" href="%s%s">%s</a>' \
               % (util.escape(formatter.href.browser(path, rev=rev)), anchor,
                  label)
