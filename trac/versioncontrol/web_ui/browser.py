# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2009 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2005-2007 Christian Boos <cboos@neuf.fr>
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

from datetime import datetime, timedelta
from fnmatch import fnmatchcase
import re

from genshi.builder import tag

from trac.config import ListOption, BoolOption, Option
from trac.core import *
from trac.mimeview.api import Mimeview, is_binary, \
                              IHTMLPreviewAnnotator, Context
from trac.perm import IPermissionRequestor
from trac.resource import Resource, ResourceNotFound
from trac.util import as_bool, embedded_numbers
from trac.util.compat import any, cleandoc
from trac.util.datefmt import http_date, to_datetime, utc
from trac.util.html import escape, Markup
from trac.util.text import exception_to_unicode, shorten_line
from trac.util.translation import _
from trac.web import IRequestHandler, RequestDone
from trac.web.chrome import add_ctxtnav, add_link, add_script, add_stylesheet, \
                            prevnext_nav, INavigationContributor
from trac.wiki.api import IWikiSyntaxProvider, IWikiMacroProvider, parse_args
from trac.wiki.formatter import format_to_html, format_to_oneliner
from trac.versioncontrol.api import NoSuchChangeset, RepositoryManager
from trac.versioncontrol.web_ui.util import *


CHUNK_SIZE = 4096


class IPropertyRenderer(Interface):
    """Render node properties in TracBrowser and TracChangeset views."""

    def match_property(name, mode):
        """Indicate whether this renderer can treat the given property

        `mode` is the current rendering context, which can be:
         - 'browser' rendered in the browser view
         - 'changeset' rendered in the changeset view as a node property
         - 'revprop' rendered in the changeset view as a revision property
        Other identifiers might be used by plugins, so it's advised to simply
        ignore unknown modes.

        Returns a quality number, ranging from 0 (unsupported) to 9
        (''perfect'' match).
        """

    def render_property(name, mode, context, props):
        """Render the given property.

        `name` is the property name as given to `match()`,
        `mode` is the same as for `match_property`,
        `context` is the context for the node being render
        (useful when the rendering depends on the node kind) and
        `props` is the collection of the corresponding properties
        (i.e. the `node.get_properties()`).

        The rendered result can be one of the following:
        - `None`: the property will be skipped
        - an `unicode` value: the property will be displayed as text
        - a `RenderedProperty` instance: the property will only be displayed
          using the instance's `content` attribute, and the other attributes
          will also be used in some display contexts (like `revprop`)
        - `Markup` or other Genshi content: the property will be displayed
          normally, using that content as a block-level markup
        """


class RenderedProperty(object):
    def __init__(self, name=None, name_attributes=None,
                 content=None, content_attributes=None):
        self.name = name
        self.name_attributes = name_attributes
        self.content = content
        self.content_attributes = content_attributes


class DefaultPropertyRenderer(Component):
    """Default version control property renderer."""

    implements(IPropertyRenderer)

    def match_property(self, name, mode):
        return 1

    def render_property(self, name, mode, context, props):
        # No special treatment besides respecting newlines in values.
        value = props[name]
        if value and '\n' in value:
            value = Markup(''.join(['<br />%s' % escape(v)
                                    for v in value.split('\n')]))
        return value


class WikiPropertyRenderer(Component):
    """Wiki text property renderer."""

    implements(IPropertyRenderer)

    wiki_properties = ListOption('browser', 'wiki_properties',
                                 'trac:description',
        doc="""Comma-separated list of version control properties to render
        as wiki content in the repository browser.

        (''since 0.11'')""")

    oneliner_properties = ListOption('browser', 'oneliner_properties',
                                 'trac:summary',
        doc="""Comma-separated list of version control properties to render
        as oneliner wiki content in the repository browser.

        (''since 0.11'')""")

    def match_property(self, name, mode):
        return (name in self.wiki_properties or \
                name in self.oneliner_properties) and 4 or 0

    def render_property(self, name, mode, context, props):
        if name in self.wiki_properties:
            return format_to_html(self.env, context, props[name])
        else:
            return format_to_oneliner(self.env, context, props[name])


class TimeRange(object):

    min = datetime(1, 1, 1, 0, 0, 0, 0, utc) # tz aware version of datetime.min
    
    def __init__(self, base):
        self.oldest = self.newest = base
        self._total = None

    def seconds_between(self, dt1, dt2):
        delta = dt1 - dt2
        return delta.days * 24 * 3600 + delta.seconds
    
    def to_seconds(self, dt):
        return self.seconds_between(dt, TimeRange.min)

    def from_seconds(self, secs):
        return TimeRange.min + timedelta(*divmod(secs, 24* 3600))

    def relative(self, datetime):
        if self._total is None:
            self._total = float(self.seconds_between(self.newest, self.oldest))
        age = 1.0
        if self._total:
            age = self.seconds_between(datetime, self.oldest) / self._total
        return age

    def insert(self, datetime):
        self._total = None
        self.oldest = min(self.oldest, datetime)
        self.newest = max(self.newest, datetime)



class BrowserModule(Component):

    implements(INavigationContributor, IPermissionRequestor, IRequestHandler,
               IWikiSyntaxProvider, IHTMLPreviewAnnotator, 
               IWikiMacroProvider)

    property_renderers = ExtensionPoint(IPropertyRenderer)

    downloadable_paths = ListOption('browser', 'downloadable_paths',
                                    '/trunk, /branches/*, /tags/*',
        doc="""List of repository paths that can be downloaded.
        
        Leave the option empty if you want to disable all downloads, otherwise
        set it to a comma-separated list of authorized paths (those paths are
        glob patterns, i.e. "*" can be used as a wild card)
        (''since 0.10'')""")

    color_scale = BoolOption('browser', 'color_scale', True,
        doc="""Enable colorization of the ''age'' column.
        
        This uses the same color scale as the source code annotation:
        blue is older, red is newer.
        (''since 0.11'')""")

    NEWEST_COLOR = (255, 136, 136)

    newest_color = Option('browser', 'newest_color', repr(NEWEST_COLOR),
        doc="""(r,g,b) color triple to use for the color corresponding
        to the newest color, for the color scale used in ''blame'' or
        the browser ''age'' column if `color_scale` is enabled.
        (''since 0.11'')""")

    OLDEST_COLOR = (136, 136, 255)

    oldest_color = Option('browser', 'oldest_color', repr(OLDEST_COLOR),
        doc="""(r,g,b) color triple to use for the color corresponding
        to the oldest color, for the color scale used in ''blame'' or
        the browser ''age'' column if `color_scale` is enabled.
        (''since 0.11'')""")

    intermediate_point = Option('browser', 'intermediate_point', '',
        doc="""If set to a value between 0 and 1 (exclusive), this will be the
        point chosen to set the `intermediate_color` for interpolating
        the color value.
        (''since 0.11'')""")

    intermediate_color = Option('browser', 'intermediate_color', '',
        doc="""(r,g,b) color triple to use for the color corresponding
        to the intermediate color, if two linear interpolations are used
        for the color scale (see `intermediate_point`).
        If not set, the intermediate color between `oldest_color` and
        `newest_color` will be used.
        (''since 0.11'')""")

    render_unsafe_content = BoolOption('browser', 'render_unsafe_content',
                                        'false',
        """Whether raw files should be rendered in the browser, or only made 
        downloadable.
 
        Pretty much any file may be interpreted as HTML by the browser,
        which allows a malicious user to create a file containing cross-site
        scripting attacks.
        
        For open repositories where anyone can check-in a file, it is
        recommended to leave this option disabled (which is the default).""")

    hidden_properties = ListOption('browser', 'hide_properties', 'svk:merge',
        doc="""Comma-separated list of version control properties to hide from
        the repository browser.
        (''since 0.9'')""")

    # public methods

    def get_custom_colorizer(self):
        """Returns a converter for values from [0.0, 1.0] to a RGB triple."""
        
        def interpolate(old, new, value):
            # Provides a linearly interpolated color triple for `value`
            # which must be a floating point value between 0.0 and 1.0
            return tuple([int(b + (a - b) * value) for a, b in zip(new, old)])

        def parse_color(rgb, default):
            # Get three ints out of a `rgb` string or return `default`
            try:
                t = tuple([int(v) for v in re.split(r'(\d+)', rgb)[1::2]])
                return len(t) == 3 and t or default
            except ValueError:
                return default
        
        newest_color = parse_color(self.newest_color, self.NEWEST_COLOR)
        oldest_color = parse_color(self.oldest_color, self.OLDEST_COLOR)
        try:
            intermediate = float(self.intermediate_point)
        except ValueError:
            intermediate = None
        if intermediate:
            intermediate_color = parse_color(self.intermediate_color, None)
            if not intermediate_color:
                intermediate_color = tuple([(a + b) / 2 for a, b in
                                            zip(newest_color, oldest_color)])
            def colorizer(value):
                if value <= intermediate:
                    value = value / intermediate
                    return interpolate(oldest_color, intermediate_color, value)
                else:
                    value = (value - intermediate) / (1.0 - intermediate)
                    return interpolate(intermediate_color, newest_color, value)
        else:
            def colorizer(value):
                return interpolate(oldest_color, newest_color, value)
        return colorizer
        
    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'browser'

    def get_navigation_items(self, req):
        rm = RepositoryManager(self.env)
        if 'BROWSER_VIEW' in req.perm and rm.get_real_repositories():
            yield ('mainnav', 'browser',
                   tag.a(_('Browse Source'), href=req.href.browser()))

    # IPermissionRequestor methods

    def get_permission_actions(self):
        return ['BROWSER_VIEW', 'FILE_VIEW']

    # IRequestHandler methods

    def match_request(self, req):
        match = re.match(r'/(export|browser|file)(/.*)?$', req.path_info)
        if match:
            mode, path = match.groups()
            if mode == 'export':
                if path and '/' in path:
                    path_elts = path.split('/', 2)
                    if len(path_elts) != 3:
                        return False
                    path = path_elts[2]
                    req.args['rev'] = path_elts[1]
                    req.args['format'] = 'raw'
            elif mode == 'file':
                req.redirect(req.href.browser(path, rev=req.args.get('rev'),
                                              format=req.args.get('format')),
                             permanent=True)
            req.args['path'] = path or '/'
            return True

    def process_request(self, req):
        req.perm.require('BROWSER_VIEW')

        presel = req.args.get('preselected')
        if presel and (presel + '/').startswith(req.href.browser() + '/'):
            req.redirect(presel)

        path = req.args.get('path', '/')
        rev = req.args.get('rev', '')
        if rev in ('', 'HEAD'):
            rev = None
        order = req.args.get('order', 'name').lower()
        desc = req.args.has_key('desc')
        xhr = req.get_header('X-Requested-With') == 'XMLHttpRequest'
        
        rm = RepositoryManager(self.env)
        all_repositories = rm.get_all_repositories()
        reponame, repos, path = rm.get_repository_by_path(path)

        # Repository index
        show_index = not reponame and path == '/'
        if show_index:
            if repos and (as_bool(all_repositories[''].get('hidden'))
                          or not repos.can_view(req.perm)):
                repos = None

        if not repos and reponame:
            raise ResourceNotFound(_("Repository '%(repo)s' not found",
                                     repo=reponame))

        if reponame and reponame != repos.reponame: # Redirect alias
            qs = req.query_string
            req.redirect(req.href.browser(repos.reponame or None, path)
                         + (qs and '?' + qs or ''))
        reponame = repos and repos.reponame or None
        
        # Find node for the requested path/rev
        context = Context.from_request(req)
        node = None
        display_rev = lambda rev: rev
        if repos:
            try:
                if rev:
                    rev = repos.normalize_rev(rev)
                # If `rev` is `None`, we'll try to reuse `None` consistently,
                # as a special shortcut to the latest revision.
                rev_or_latest = rev or repos.youngest_rev
                node = get_existing_node(req, repos, path, rev_or_latest)
            except NoSuchChangeset, e:
                raise ResourceNotFound(e.message,
                                       _('Invalid changeset number'))

            context = context(repos.resource.child('source', path,
                                                   version=rev_or_latest))
            display_rev = repos.display_rev

        # Prepare template data
        path_links = get_path_links(req.href, reponame, path, rev,
                                    order, desc)

        repo_data = dir_data = file_data = None
        if show_index:
            repo_data = self._render_repository_index(
                                        context, all_repositories, order, desc)
        if node:
            if node.isdir:
                dir_data = self._render_dir(req, repos, node, rev, order, desc)
            elif node.isfile:
                file_data = self._render_file(req, context, repos, node, rev)

        if not repos and not (repo_data and repo_data['repositories']):
            raise ResourceNotFound(_("No node %(path)s", path=path))

        quickjump_data = properties_data = None
        if node and not xhr:
            properties_data = self.render_properties(
                    'browser', context, node.get_properties())
            quickjump_data = list(repos.get_quickjump_entries(rev))

        data = {
            'context': context, 'reponame': reponame, 'repos': repos,
            'repoinfo': all_repositories.get(reponame or ''),
            'path': path, 'rev': node and node.rev, 'stickyrev': rev,
            'display_rev': display_rev,
            'created_path': node and node.created_path,
            'created_rev': node and node.created_rev,
            'properties': properties_data,
            'path_links': path_links,
            'order': order, 'desc': desc and 1 or None,
            'repo': repo_data, 'dir': dir_data, 'file': file_data,
            'quickjump_entries': quickjump_data,
            'wiki_format_messages': \
                self.config['changeset'].getbool('wiki_format_messages'),
            'xhr': xhr,
        }                   
        if xhr: # render and return the content only
            return 'dir_entries.html', data, None

        if dir_data or repo_data:
            add_script(req, 'common/js/expand_dir.js')
            add_script(req, 'common/js/keyboard_nav.js')

        # Links for contextual navigation
        if node:
            if node.isfile:
                prev_rev = repos.previous_rev(rev=node.created_rev,
                                              path=node.created_path)
                if prev_rev:
                    href = req.href.browser(reponame,
                                            node.created_path, rev=prev_rev)
                    add_link(req, 'prev', href,
                             _('Revision %(num)s', num=display_rev(prev_rev)))
                if rev is not None:
                    add_link(req, 'up', req.href.browser(reponame,
                                                         node.created_path))
                next_rev = repos.next_rev(rev=node.created_rev,
                                          path=node.created_path)
                if next_rev:
                    href = req.href.browser(reponame, node.created_path,
                                            rev=next_rev)
                    add_link(req, 'next', href,
                             _('Revision %(num)s', num=display_rev(next_rev)))
                prevnext_nav(req, _('Previous Revision'), _('Next Revision'),
                             _('Latest Revision'))
            else:
                if path != '/':
                    add_link(req, 'up', path_links[-2]['href'],
                             _('Parent directory'))
                add_ctxtnav(req, tag.a(_('Last Change'), 
                            href=req.href.changeset(node.created_rev, reponame,
                                                    node.created_path)))
            if node.isfile:
                annotate = data['file']['annotate']
                if annotate:
                    add_ctxtnav(req, _('Normal'), 
                                title=_('View file without annotations'), 
                                href=req.href.browser(reponame,
                                                      node.created_path, 
                                                      rev=rev))
                if annotate != 'blame':
                    add_ctxtnav(req, _('Blame'), 
                                title=_('Annotate each line with the last '
                                        'changed revision '
                                        '(this can be time consuming...)'), 
                                href=req.href.browser(reponame,
                                                      node.created_path, 
                                                      rev=rev,
                                                      annotate='blame'))
            add_ctxtnav(req, _('Revision Log'), 
                        href=req.href.log(reponame, path, rev=rev))
            path_url = repos.get_path_url(path, rev)
            if path_url:
                if path_url.startswith('//'):
                    path_url = req.scheme + ':' + path_url
                add_ctxtnav(req, _('Repository URL'), href=path_url)

        add_stylesheet(req, 'common/css/browser.css')
        return 'browser.html', data, None

    # Internal methods

    def _render_repository_index(self, context, all_repositories, order, desc):
        # Color scale for the age column
        timerange = custom_colorizer = None
        if self.color_scale:
            custom_colorizer = self.get_custom_colorizer()

        rm = RepositoryManager(self.env)
        repositories = []
        for reponame, repoinfo in all_repositories.iteritems():
            if not reponame or as_bool(repoinfo.get('hidden')):
                continue
            try:
                repos = rm.get_repository(reponame)
                if repos:
                    if not repos.can_view(context.perm):
                        continue
                    try:
                        youngest = repos.get_changeset(repos.youngest_rev)
                    except NoSuchChangeset:
                        youngest = None
                    if self.color_scale and youngest:
                        if not timerange:
                            timerange = TimeRange(youngest.date)
                        else:
                            timerange.insert(youngest.date)
                    entry = (reponame, repoinfo, repos, youngest, None)
                else:
                    entry = (reponame, repoinfo, None, None, u"\u2013")
            except TracError, err:
                entry = (reponame, repoinfo, None, None,
                         exception_to_unicode(err))
            if entry[-1] is not None:   # Check permission in case of error
                root = Resource('repository', reponame).child('source', '/')
                if 'BROWSER_VIEW' not in context.perm(root):
                    continue
            repositories.append(entry)

        # Ordering of repositories
        if order == 'date':
            def repo_order((reponame, repoinfo, repos, youngest, err)):
                return (youngest and youngest.date or to_datetime(0),
                        embedded_numbers(reponame.lower()))
        elif order == 'author':
            def repo_order((reponame, repoinfo, repos, youngest, err)):
                return (youngest and youngest.author.lower() or '',
                        embedded_numbers(reponame.lower()))
        else:
            def repo_order((reponame, repoinfo, repos, youngest, err)):
                return embedded_numbers(reponame.lower())

        repositories = sorted(repositories, key=repo_order, reverse=desc)

        return {'repositories' : repositories,
                'timerange': timerange, 'colorize_age': custom_colorizer}

    def _render_dir(self, req, repos, node, rev, order, desc):
        req.perm(node.resource).require('BROWSER_VIEW')

        # Entries metadata
        class entry(object):
            __slots__ = ('name', 'rev', 'created_rev', 'kind', 'isdir', 'path',
                         'content_length')

            def __init__(self, node):
                for f in entry.__slots__:
                    setattr(self, f, getattr(node, f))
                
        entries = [entry(n) for n in node.get_entries()
                   if n.can_view(req.perm)]
        changes = get_changes(repos, [i.created_rev for i in entries],
                              self.log)

        if rev:
            newest = repos.get_changeset(rev).date
        else:
            newest = datetime.now(req.tz)

        # Color scale for the age column
        timerange = custom_colorizer = None
        if self.color_scale:
            timerange = TimeRange(newest)
            max_s = req.args.get('range_max_secs')
            min_s = req.args.get('range_min_secs')
            parent_range = [timerange.from_seconds(long(s))
                            for s in [max_s, min_s] if s]
            this_range = [c.date for c in changes.values() if c]
            for dt in this_range + parent_range:
                timerange.insert(dt)
            custom_colorizer = self.get_custom_colorizer()

        # Ordering of entries
        if order == 'date':
            def file_order(a):
                return (changes[a.created_rev].date,
                        embedded_numbers(a.name.lower()))
        elif order == 'size':
            def file_order(a):
                return (a.content_length,
                        embedded_numbers(a.name.lower()))
        elif order == 'author':
            def file_order(a):
                return (changes[a.created_rev].author.lower(),
                        embedded_numbers(a.name.lower()))
        else:
            def file_order(a):
                return embedded_numbers(a.name.lower())

        dir_order = desc and 1 or -1

        def browse_order(a):
            return a.isdir and dir_order or 0, file_order(a)
        entries = sorted(entries, key=browse_order, reverse=desc)

        # ''Zip Archive'' alternate link
        path = node.path.strip('/')
        if repos.reponame:
            path = repos.reponame + '/' + path
        if any(fnmatchcase(path, p.strip('/'))
               for p in self.downloadable_paths):
            zip_href = req.href.changeset(rev or repos.youngest_rev, 
                                          repos.reponame or None, node.path,
                                          old=rev,
                                          old_path=repos.reponame or '/',
                                          format='zip')
            add_link(req, 'alternate', zip_href, _('Zip Archive'),
                     'application/zip', 'zip')

        return {'entries': entries, 'changes': changes,
                'timerange': timerange, 'colorize_age': custom_colorizer,
                'range_max_secs': (timerange and
                                   timerange.to_seconds(timerange.newest)),
                'range_min_secs': (timerange and
                                   timerange.to_seconds(timerange.oldest)),
                }

    def _render_file(self, req, context, repos, node, rev=None):
        req.perm(node.resource).require('FILE_VIEW')

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
        if format in ('raw', 'txt'):
            req.send_response(200)
            req.send_header('Content-Type',
                            format == 'txt' and 'text/plain' or mime_type)
            req.send_header('Content-Length', node.content_length)
            req.send_header('Last-Modified', http_date(node.last_modified))
            if rev is None:
                req.send_header('Pragma', 'no-cache')
                req.send_header('Cache-Control', 'no-cache')
                req.send_header('Expires', 'Fri, 01 Jan 1999 00:00:00 GMT')
            if not self.render_unsafe_content:
                # Force browser to download files instead of rendering
                # them, since they might contain malicious code enabling 
                # XSS attacks
                req.send_header('Content-Disposition', 'attachment')
            req.end_headers()

            while 1:
                if not chunk:
                    raise RequestDone
                req.write(chunk)
                chunk = content.read(CHUNK_SIZE)
        else:
            # The changeset corresponding to the last change on `node` 
            # is more interesting than the `rev` changeset.
            changeset = repos.get_changeset(node.created_rev)

            # add ''Plain Text'' alternate link if needed
            if not is_binary(chunk) and mime_type != 'text/plain':
                plain_href = req.href.browser(repos.reponame or None,
                                              node.path, rev=rev, format='txt')
                add_link(req, 'alternate', plain_href, _('Plain Text'),
                         'text/plain')

            # add ''Original Format'' alternate link (always)
            raw_href = req.href.export(rev or repos.youngest_rev, 
                                       repos.reponame or None, node.path)
            add_link(req, 'alternate', raw_href, _('Original Format'),
                     mime_type)

            self.log.debug("Rendering preview of node %s@%s with mime-type %s"
                           % (node.name, str(rev), mime_type))

            del content # the remainder of that content is not needed

            add_stylesheet(req, 'common/css/code.css')

            annotations = ['lineno']
            annotate = req.args.get('annotate')
            if annotate:
                annotations.insert(0, annotate)
            preview_data = mimeview.preview_data(context, node.get_content(),
                                                 node.get_content_length(),
                                                 mime_type, node.created_path,
                                                 raw_href,
                                                 annotations=annotations,
                                                 force_source=bool(annotate))
            return {
                'changeset': changeset,
                'size': node.content_length,
                'preview': preview_data,
                'annotate': annotate,
                }

    # public methods
    
    def render_properties(self, mode, context, props):
        """Prepare rendering of a collection of properties."""
        return filter(None, [self.render_property(name, mode, context, props)
                             for name in sorted(props)])

    def render_property(self, name, mode, context, props):
        """Renders a node property to HTML."""
        if name in self.hidden_properties:
            return
        candidates = []
        for renderer in self.property_renderers:
            quality = renderer.match_property(name, mode)
            if quality > 0:
                candidates.append((quality, renderer))
        candidates.sort(reverse=True)
        for (quality, renderer) in candidates:
            try:
                rendered = renderer.render_property(name, mode, context, props)
                if not rendered:
                    return rendered
                if isinstance(rendered, RenderedProperty):
                    value = rendered.content
                else:
                    value = rendered
                    rendered = None
                prop = {'name': name, 'value': value, 'rendered': rendered}
                return prop
            except Exception, e:
                self.log.warning('Rendering failed for property %s with '
                                 'renderer %s: %s', name,
                                 renderer.__class__.__name__,
                                 exception_to_unicode(e, traceback=True))

    # IWikiSyntaxProvider methods

    def get_wiki_syntax(self):
        return []

    def get_link_resolvers(self):
        """TracBrowser link resolvers.
         - `source:` and `browser:`
             * simple paths (/dir/file)
             * paths at a given revision (/dir/file@234)
             * paths with line number marks (/dir/file@234:10,20-30)
             * paths with line number anchor (/dir/file@234#L100)
            Marks and anchor can be combined.
            The revision must be present when specifying line numbers.
            In the few cases where it would be redundant (e.g. for tags), the
            revision number itself can be omitted: /tags/v10/file@100-110#L99
        """
        return [('repos', self._format_browser_link),
                ('export', self._format_export_link),
                ('source', self._format_browser_link),
                ('browser', self._format_browser_link)]

    def _format_export_link(self, formatter, ns, export, label):
        export, query, fragment = formatter.split_link(export)
        if ':' in export:
            rev, path = export.split(':', 1)
        elif '@' in export:
            path, rev = export.split('@', 1)
        else:
            rev, path = 'HEAD', export
        return tag.a(label, class_='export',
                     href=formatter.href.export(rev, path) + fragment)

    def _format_browser_link(self, formatter, ns, path, label):
        path, query, fragment = formatter.split_link(path)
        rev = marks = None
        match = self.PATH_LINK_RE.match(path)
        if match:
            path, rev, marks = match.groups()
        return tag.a(label, class_='source',
                     href=(formatter.href.browser(path, rev=rev, marks=marks) +
                           query + fragment))

    PATH_LINK_RE = re.compile(r"([^@#:]*)"     # path
                              r"[@:]([^#:]+)?" # rev
                              r"(?::(\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*))?" # marks
                              )

    # IHTMLPreviewAnnotator methods

    def get_annotation_type(self):
        return 'blame', _('Rev'), _('Revision in which the line changed')

    def get_annotation_data(self, context):
        """Cache the annotation data corresponding to each revision."""
        return BlameAnnotator(self.env, context)

    def annotate_row(self, context, row, lineno, line, blame_annotator):
        blame_annotator.annotate(row, lineno)

    # IWikiMacroProvider methods

    def get_macros(self):
        yield "RepositoryIndex"

    def get_macro_description(self, name):
        return cleandoc("""
        Display the list of available repositories.

        Can be given the following named arguments:
        
          ''format''::
            Select the rendering format:
            - ''compact'' produces a comma-separated list of repository prefix
              names (default)
            - ''list'' produces a description list of repository prefix names 
            - ''table'' produces a table view, similar to the one visible in
              the ''Browse View'' page
          ''glob''::
            Do a glob-style filtering on the repository names (defaults to '*')
          ''order''::
            Order repositories by the given column (one of "name", "date" or
            "author")
          ''desc''::
            When set to 1, order by descending order

        (''since 0.12'')
        """)

    def expand_macro(self, formatter, name, content):
        args, kwargs = parse_args(content)
        format = kwargs.get('format', 'compact')
        glob = kwargs.get('glob', '*')
        order = kwargs.get('order')
        desc = as_bool(kwargs.get('desc', 0))

        rm = RepositoryManager(self.env)
        all_repos = dict(rdata for rdata in rm.get_all_repositories().items()
                         if fnmatchcase(rdata[0], glob))

        if format == 'table':
            repo = self._render_repository_index(formatter.context, all_repos,
                                                 order, desc)

            add_stylesheet(formatter.req, 'common/css/browser.css')
            wiki_format_messages = self.config['changeset'] \
                                       .getbool('wiki_format_messages')
            data = {'repo': repo, 'order': order, 'desc': desc and 1 or None,
                    'reponame': None, 'path': '/', 'stickyrev': None,
                    'wiki_format_messages': wiki_format_messages}
            from trac.web.chrome import Chrome
            return Chrome(self.env).render_template(
                    formatter.req, 'repository_index.html', data, None,
                    fragment=True)

        def get_repository(reponame):
            try:
                return rm.get_repository(reponame)
            except TracError:
                return

        all_repos = [(reponame, get_repository(reponame))
                     for reponame in all_repos]
        all_repos = sorted(((reponame, repos) for reponame, repos in all_repos
                            if repos
                            and not as_bool(repos.params.get('hidden'))
                            and repos.can_view(formatter.perm)),
                           reverse=desc)

        def repolink(reponame, repos):
            label = reponame or _('(default)')
            return Markup(tag.a(label, 
                          title=_('View repository %(repo)s', repo=label),
                          href=formatter.href.browser(repos.reponame or None)))

        if format == 'list':
            return tag.dl([
                tag(tag.dt(repolink(reponame, repos)),
                    tag.dd(repos.params.get('description')))
                for reponame, repos in all_repos])
        else: # compact
            return Markup(', ').join([repolink(reponame, repos)
                                      for reponame, repos in all_repos])

        

class BlameAnnotator(object):

    def __init__(self, env, context):
        self.env = env
        self.context = context
        rm = RepositoryManager(self.env)
        self.repos = rm.get_repository(context.resource.parent.id)
        self.path = context.resource.id
        self.rev = context.resource.version
        # maintain state
        self.prev_chgset = None
        self.chgset_data = {}
        add_script(context.req, 'common/js/blame.js')
        add_stylesheet(context.req, 'common/css/changeset.css')
        add_stylesheet(context.req, 'common/css/diff.css')
        self.reset()

    def reset(self):
        rev = self.rev
        node = self.repos.get_node(self.path, rev)
        # FIXME: get_annotations() should be in the Resource API
        # -- get revision numbers for each line
        self.annotations = node.get_annotations()
        # -- from the annotations, retrieve changesets and
        # determine the span of dates covered, for the color code.
        # Note: changesets[i].rev can differ from annotations[i]
        # (long form vs. compact, short rev form for the latter).
        self.changesets = []
        chgset = self.repos.get_changeset(rev)
        chgsets = {rev: chgset}
        self.timerange = TimeRange(chgset.date)
        for idx in range(len(self.annotations)):
            rev = self.annotations[idx]
            chgset = chgsets.get(rev)
            if not chgset:
                chgset = self.repos.get_changeset(rev)
                chgsets[rev] = chgset
                self.timerange.insert(chgset.date)
            # get list of changeset parallel to annotations
            self.changesets.append(chgset)
        # -- retrieve the original path of the source, for each rev
        # (support for copy/renames)
        self.paths = {}
        for path, rev, chg in node.get_history():
            self.paths[rev] = path
        # -- get custom colorize function
        browser = BrowserModule(self.env)
        self.colorize_age = browser.get_custom_colorizer()

    def annotate(self, row, lineno):
        if lineno > len(self.annotations):
            row.append(tag.th())
            return
        rev = self.annotations[lineno-1]
        chgset = self.changesets[lineno-1]
        path = self.paths.get(rev, None)
        # Note: path will be None if copy/rename is not supported
        # by get_history
        
        # -- compute anchor and style once per revision
        if rev not in self.chgset_data:
            chgset_href = \
                self.context.href.changeset(rev, self.repos.reponame or None,
                                            path)
            short_author = chgset.author.split(' ', 1)[0]
            title = shorten_line('%s: %s' % (short_author, chgset.message))
            anchor = tag.a('[%s]' % self.repos.short_rev(rev), # shortname
                           title=title, href=chgset_href)
            color = self.colorize_age(self.timerange.relative(chgset.date))
            style = 'background-color: rgb(%d, %d, %d);' % color
            self.chgset_data[rev] = (anchor, style)
        else:
            anchor, style = self.chgset_data[rev]

        if self.prev_chgset != chgset:
            self.prev_style = style
        # optimize away the path if there's no copy/rename info
        if not path or path == self.path:
            path = ''
        # -- produce blame column, eventually with an anchor
        style = self.prev_style
        if lineno < len(self.changesets) and self.changesets[lineno] == chgset:
            style += ' border-bottom: none;'
        blame_col = tag.th(style=style, class_='blame r%s' % rev)
        if self.prev_chgset != chgset:
            blame_col.append(anchor)
            self.prev_chgset = chgset
        row.append(blame_col)
