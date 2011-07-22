# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2009 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2004-2006 Christopher Lenz <cmlenz@gmx.de>
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
#         Christopher Lenz <cmlenz@gmx.de>
#         Christian Boos <cboos@neuf.fr>

from itertools import groupby
import os
import posixpath
import re
from StringIO import StringIO

from genshi.builder import tag

from trac.config import Option, BoolOption, IntOption
from trac.core import *
from trac.mimeview import Context, Mimeview
from trac.perm import IPermissionRequestor
from trac.resource import Resource, ResourceNotFound
from trac.search import ISearchSource, search_to_sql, shorten_result
from trac.timeline.api import ITimelineEventProvider
from trac.util import as_bool, content_disposition, embedded_numbers, pathjoin
from trac.util.compat import any
from trac.util.datefmt import from_utimestamp, pretty_timedelta
from trac.util.text import exception_to_unicode, to_unicode, \
                           unicode_urlencode, shorten_line, CRLF
from trac.util.translation import _, ngettext
from trac.versioncontrol.api import RepositoryManager, Changeset, Node, \
                                    NoSuchChangeset
from trac.versioncontrol.diff import get_diff_options, diff_blocks, \
                                     unified_diff
from trac.versioncontrol.web_ui.browser import BrowserModule
from trac.web import IRequestHandler, RequestDone
from trac.web.chrome import Chrome, INavigationContributor, \
                            add_ctxtnav, add_link, add_script, \
                            add_stylesheet, prevnext_nav
from trac.wiki import IWikiSyntaxProvider, WikiParser
from trac.wiki.formatter import format_to


class IPropertyDiffRenderer(Interface):
    """Render node properties in TracBrowser and TracChangeset views."""

    def match_property_diff(name):
        """Indicate whether this renderer can treat the given property diffs

        Returns a quality number, ranging from 0 (unsupported) to 9
        (''perfect'' match).
        """

    def render_property_diff(name, old_context, old_props,
                             new_context, new_props, options):
        """Render the given diff of property to HTML.

        `name` is the property name as given to `match_property_diff()`,
        `old_context` corresponds to the old node being render
        (useful when the rendering depends on the node kind)
        and `old_props` is the corresponding collection of all properties.
        Same for `new_node` and `new_props`.
        `options` are the current diffs options.

        The rendered result can be one of the following:
        - `None`: the property change will be shown the normal way
          (''changed from `old` to `new`'')
        - an `unicode` value: the change will be shown as textual content
        - `Markup` or other Genshi content: the change will shown as block
          markup
        """


class DefaultPropertyDiffRenderer(Component):
    """Default version control property difference renderer."""

    implements(IPropertyDiffRenderer)

    def match_property_diff(self, name):
        return 1

    def render_property_diff(self, name, old_context, old_props,
                             new_context, new_props, options):
        old, new = old_props[name], new_props[name]
        # Render as diff only if multiline (see #3002)
        if '\n' not in old and '\n' not in new:
            return None
        unidiff = '--- \n+++ \n' + \
                  '\n'.join(unified_diff(old.splitlines(), new.splitlines(),
                                         options.get('contextlines', 3)))
        return tag.li('Property ', tag.strong(name),
                      Mimeview(self.env).render(old_context, 'text/x-diff',
                                                unidiff))


class ChangesetModule(Component):
    """Renderer providing flexible functionality for showing sets of
    differences.

    If the differences shown are coming from a specific changeset,
    then that changeset information can be shown too.

    In addition, it is possible to show only a subset of the changeset:
    Only the changes affecting a given path will be shown. This is called
    the ''restricted'' changeset.

    But the differences can also be computed in a more general way,
    between two arbitrary paths and/or between two arbitrary revisions.
    In that case, there's no changeset information displayed.
    """

    implements(INavigationContributor, IPermissionRequestor, IRequestHandler,
               ITimelineEventProvider, IWikiSyntaxProvider, ISearchSource)

    property_diff_renderers = ExtensionPoint(IPropertyDiffRenderer)
    
    timeline_show_files = Option('timeline', 'changeset_show_files', '0',
        """Number of files to show (`-1` for unlimited, `0` to disable).

        This can also be `location`, for showing the common prefix for the
        changed files. (since 0.11).
        """)

    timeline_long_messages = BoolOption('timeline', 'changeset_long_messages',
                                        'false',
        """Whether wiki-formatted changeset messages should be multiline or
        not.

        If this option is not specified or is false and `wiki_format_messages`
        is set to true, changeset messages will be single line only, losing
        some formatting (bullet points, etc).""")

    timeline_collapse = BoolOption('timeline', 'changeset_collapse_events',
                                   'false',
        """Whether consecutive changesets from the same author having 
        exactly the same message should be presented as one event.
        That event will link to the range of changesets in the log view.
        (''since 0.11'')""")

    max_diff_files = IntOption('changeset', 'max_diff_files', 0,
        """Maximum number of modified files for which the changeset view will
        attempt to show the diffs inlined (''since 0.10'').""")

    max_diff_bytes = IntOption('changeset', 'max_diff_bytes', 10000000,
        """Maximum total size in bytes of the modified files (their old size
        plus their new size) for which the changeset view will attempt to show
        the diffs inlined (''since 0.10'').""")

    wiki_format_messages = BoolOption('changeset', 'wiki_format_messages',
                                      'true',
        """Whether wiki formatting should be applied to changeset messages.
        
        If this option is disabled, changeset messages will be rendered as
        pre-formatted text.""")

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'browser'

    def get_navigation_items(self, req):
        return []

    # IPermissionRequestor methods

    def get_permission_actions(self):
        return ['CHANGESET_VIEW']

    # IRequestHandler methods

    _request_re = re.compile(r"/changeset(?:/([^/]+)(/.*)?)?$")

    def match_request(self, req):
        match = re.match(self._request_re, req.path_info)
        if match:
            new, new_path = match.groups()
            if new:
                req.args['new'] = new
            if new_path:
                req.args['new_path'] = new_path
            return True

    def process_request(self, req):
        """The appropriate mode of operation is inferred from the request
        parameters:

         * If `new_path` and `old_path` are equal (or `old_path` is omitted)
           and `new` and `old` are equal (or `old` is omitted),
           then we're about to view a revision Changeset: `chgset` is True.
           Furthermore, if the path is not the root, the changeset is
           ''restricted'' to that path (only the changes affecting that path,
           its children or its ancestor directories will be shown).
         * In any other case, the set of changes corresponds to arbitrary
           differences between path@rev pairs. If `new_path` and `old_path`
           are equal, the ''restricted'' flag will also be set, meaning in this
           case that the differences between two revisions are restricted to
           those occurring on that path.

        In any case, either path@rev pairs must exist.
        """
        req.perm.require('CHANGESET_VIEW')
        
        # -- retrieve arguments
        full_new_path = new_path = req.args.get('new_path')
        new = req.args.get('new')
        full_old_path = old_path = req.args.get('old_path')
        old = req.args.get('old')
        reponame = req.args.get('reponame')

        xhr = req.get_header('X-Requested-With') == 'XMLHttpRequest'

        # -- support for the revision log ''View changes'' form,
        #    where we need to give the path and revision at the same time
        if old and '@' in old:
            old, old_path = old.split('@', 1)
        if new and '@' in new:
            new, new_path = new.split('@', 1)

        rm = RepositoryManager(self.env)
        if reponame:
            repos = rm.get_repository(reponame)
        else:
            reponame, repos, new_path = rm.get_repository_by_path(new_path)

            if old_path:
                old_reponame, old_repos, old_path = \
                    rm.get_repository_by_path(old_path)
                if old_repos != repos:
                    raise TracError(_("Can't compare across different "
                                      "repositories: %(old)s vs. %(new)s",
                                      old=old_reponame, new=reponame))

        if not repos:
            if reponame or (new_path and new_path != '/'):
                raise TracError(_("Repository '%(repo)s' not found",
                                  repo=reponame or new_path.strip('/')))
            else:
                raise TracError(_("No repository specified and no default "
                                  "repository configured."))

        # -- normalize and check for special case
        try:
            new_path = repos.normalize_path(new_path)
            new = repos.normalize_rev(new)
            full_new_path = '/' + pathjoin(repos.reponame, new_path)
            old_path = repos.normalize_path(old_path or new_path)
            old = repos.normalize_rev(old or new)
            full_old_path = '/' + pathjoin(repos.reponame, old_path)
        except NoSuchChangeset, e:
            raise ResourceNotFound(e.message, _('Invalid Changeset Number'))

        if old_path == new_path and old == new: # revert to Changeset
            old_path = old = None

        style, options, diff_data = get_diff_options(req)
        diff_opts = diff_data['options']

        # -- setup the `chgset` and `restricted` flags, see docstring above.
        chgset = not old and not old_path
        if chgset:
            restricted = new_path not in ('', '/') # (subset or not)
        else:
            restricted = old_path == new_path # (same path or not)

        # -- redirect if changing the diff options or alias requested
        if 'update' in req.args or reponame != repos.reponame:
            contextall = diff_opts['contextall'] or None
            reponame = repos.reponame or None
            if chgset:
                if restricted:
                    req.redirect(req.href.changeset(new, reponame, new_path,
                                                    contextall=contextall))
                else:
                    req.redirect(req.href.changeset(new, reponame,
                                                    contextall=contextall))
            else:
                req.redirect(req.href.changeset(new, reponame,
                                                new_path, old=old,
                                                old_path=full_old_path,
                                                contextall=contextall))

        # -- preparing the data
        if chgset:
            prev = repos.get_node(new_path, new).get_previous()
            if prev:
                prev_path, prev_rev = prev[:2]
            else:
                prev_path, prev_rev = new_path, repos.previous_rev(new)
            data = {'old_path': prev_path, 'old_rev': prev_rev,
                    'new_path': new_path, 'new_rev': new}
        else:
            if not new:
                new = repos.youngest_rev
            elif not old:
                old = repos.youngest_rev
            if not old_path:
                old_path = new_path
            data = {'old_path': old_path, 'old_rev': old,
                    'new_path': new_path, 'new_rev': new}
        data.update({'repos': repos, 'reponame': repos.reponame or None,
                     'diff': diff_data,
                     'wiki_format_messages': self.wiki_format_messages})

        if chgset:
            chgset = repos.get_changeset(new)
            req.perm(chgset.resource).require('CHANGESET_VIEW')

            # TODO: find a cheaper way to reimplement r2636
            req.check_modified(chgset.date, [
                style, ''.join(options), repos.name,
                diff_opts['contextlines'], diff_opts['contextall'],
                repos.rev_older_than(new, repos.youngest_rev),
                chgset.message, xhr,
                pretty_timedelta(chgset.date, None, 3600)])

        format = req.args.get('format')

        if format in ['diff', 'zip']:
            # choosing an appropriate filename
            rpath = new_path.replace('/','_')
            if chgset:
                if restricted:
                    filename = 'changeset_%s_%s' % (rpath, new)
                else:
                    filename = 'changeset_%s' % new
            else:
                if restricted:
                    filename = 'diff-%s-from-%s-to-%s' \
                                  % (rpath, old, new)
                elif old_path == '/': # special case for download (#238)
                    filename = '%s-%s' % (rpath, old)
                else:
                    filename = 'diff-from-%s-%s-to-%s-%s' \
                               % (old_path.replace('/','_'), old, rpath, new)
            if format == 'diff':
                self._render_diff(req, filename, repos, data)
            elif format == 'zip':
                self._render_zip(req, filename, repos, data)

        # -- HTML format
        self._render_html(req, repos, chgset, restricted, xhr, data)
        
        if chgset:
            diff_params = 'new=%s' % new
        else:
            diff_params = unicode_urlencode({
                'new_path': full_new_path, 'new': new,
                'old_path': full_old_path, 'old': old})
        add_link(req, 'alternate', '?format=diff&' + diff_params,
                 _('Unified Diff'), 'text/plain', 'diff')
        add_link(req, 'alternate', '?format=zip&' + diff_params,
                 _('Zip Archive'), 'application/zip', 'zip')
        add_script(req, 'common/js/diff.js')
        add_stylesheet(req, 'common/css/changeset.css')
        add_stylesheet(req, 'common/css/diff.css')
        add_stylesheet(req, 'common/css/code.css')
        if chgset:
            if restricted:
                prevnext_nav(req, _('Previous Change'), _('Next Change'))
            else:
                prevnext_nav(req, _('Previous Changeset'), _('Next Changeset'))
        else:
            rev_href = req.href.changeset(old, full_old_path, 
                                          old=new, old_path=full_new_path)
            add_ctxtnav(req, _('Reverse Diff'), href=rev_href)
            
        return 'changeset.html', data, None

    # Internal methods

    def _render_html(self, req, repos, chgset, restricted, xhr, data):
        """HTML version"""
        data['restricted'] = restricted
        display_rev = repos.display_rev
        data['display_rev'] = display_rev
        browser = BrowserModule(self.env)
        reponame = repos.reponame or None

        if chgset: # Changeset Mode (possibly restricted on a path)
            path, rev = data['new_path'], data['new_rev']

            # -- getting the change summary from the Changeset.get_changes
            def get_changes():
                for npath, kind, change, opath, orev in chgset.get_changes():
                    old_node = new_node = None
                    if (restricted and
                        not (npath == path or                # same path
                             npath.startswith(path + '/') or # npath is below
                             path.startswith(npath + '/'))): # npath is above
                        continue
                    if change != Changeset.ADD:
                        old_node = repos.get_node(opath, orev)
                    if change != Changeset.DELETE:
                        new_node = repos.get_node(npath, rev)
                    else:
                        # support showing paths deleted below a copy target
                        old_node.path = npath
                    yield old_node, new_node, kind, change

            def _changeset_title(rev):
                rev = display_rev(rev)
                if restricted:
                    return _('Changeset %(id)s for %(path)s', id=rev,
                             path=path)
                else:
                    return _('Changeset %(id)s', id=rev)

            data['changeset'] = chgset
            title = _changeset_title(rev)

            # Support for revision properties (#2545)
            context = Context.from_request(req, 'changeset', chgset.rev,
                                           parent=repos.resource)
            data['context'] = context
            revprops = chgset.get_properties()
            data['properties'] = browser.render_properties('revprop', context,
                                                           revprops)
            oldest_rev = repos.oldest_rev
            if chgset.rev != oldest_rev:
                if restricted:
                    prev = repos.get_node(path, rev).get_previous()
                    if prev:
                        prev_path, prev_rev = prev[:2]
                        if prev_rev:
                            prev_href = req.href.changeset(prev_rev, reponame,
                                                           prev_path)
                    else:
                        prev_path = prev_rev = None
                else:
                    add_link(req, 'first', 
                             req.href.changeset(oldest_rev, reponame),
                             _('Changeset %(id)s', id=display_rev(oldest_rev)))
                    prev_path = data['old_path']
                    prev_rev = repos.previous_rev(chgset.rev)
                    if prev_rev:
                        prev_href = req.href.changeset(prev_rev, reponame)
                if prev_rev:
                    add_link(req, 'prev', prev_href,
                             _changeset_title(prev_rev))
            youngest_rev = repos.youngest_rev
            if str(chgset.rev) != str(youngest_rev):
                if restricted:
                    next_rev = repos.next_rev(chgset.rev, path)
                    if next_rev:
                        if repos.has_node(path, next_rev):
                            next_href = req.href.changeset(next_rev, reponame,
                                                           path)
                        else: # must be a 'D'elete or 'R'ename, show full cset
                            next_href = req.href.changeset(next_rev, reponame)
                else:
                    add_link(req, 'last', 
                             req.href.changeset(youngest_rev, reponame),
                             _('Changeset %(id)s',
                               id=display_rev(youngest_rev)))
                    next_rev = repos.next_rev(chgset.rev)
                    if next_rev:
                        next_href = req.href.changeset(next_rev, reponame)
                if next_rev:
                    add_link(req, 'next', next_href,
                             _changeset_title(next_rev))
        else: # Diff Mode
            # -- getting the change summary from the Repository.get_changes
            def get_changes():
                for d in repos.get_changes(
                    new_path=data['new_path'], new_rev=data['new_rev'],
                    old_path=data['old_path'], old_rev=data['old_rev']):
                    yield d
            title = self.title_for_diff(data)
            data['changeset'] = False

        data['title'] = title

        if 'BROWSER_VIEW' not in req.perm:
            return

        def node_info(node, annotated):
            href = req.href.browser(
                reponame, node.created_path, rev=node.created_rev,
                annotate=annotated and 'blame' or None)
            title = _('Show revision %(rev)s of this file in browser',
                      rev=display_rev(node.rev))
            return {'path': node.path, 'rev': node.rev,
                    'shortrev': repos.short_rev(node.rev),
                    'href': href, 'title': title}
        # Reminder: node.path may not exist at node.rev
        #           as long as node.rev==node.created_rev
        #           ... and data['old_rev'] may have nothing to do
        #           with _that_ node specific history...

        options = data['diff']['options']

        def _prop_changes(old_node, new_node):
            old_props = old_node.get_properties()
            new_props = new_node.get_properties()
            old_ctx = Context.from_request(req, old_node.resource)
            new_ctx = Context.from_request(req, new_node.resource)
            changed_properties = []
            if old_props != new_props:
                for k, v in sorted(old_props.items()):
                    new = old = diff = None
                    if not k in new_props:
                        old = v # won't be displayed, no need to render it
                    elif v != new_props[k]:
                        diff = self.render_property_diff(
                            k, old_ctx, old_props, new_ctx, new_props, options)
                        if not diff:
                            old = browser.render_property(k, 'changeset',
                                                          old_ctx, old_props)
                            new = browser.render_property(k, 'changeset',
                                                          new_ctx, new_props)
                    if new or old or diff:
                        changed_properties.append({'name': k, 'old': old,
                                                   'new': new, 'diff': diff})
                for k, v in sorted(new_props.items()):
                    if not k in old_props:
                        new = browser.render_property(k, 'changeset',
                                                      new_ctx, new_props)
                        if new is not None:
                            changed_properties.append({'name': k, 'new': new,
                                                       'old': None})
            return changed_properties

        def _estimate_changes(old_node, new_node):
            old_size = old_node.get_content_length()
            new_size = new_node.get_content_length()
            return old_size + new_size

        def _content_changes(old_node, new_node):
            """Returns the list of differences.

            The list is empty when no differences between comparable files
            are detected, but the return value is None for non-comparable
            files.
            """
            mview = Mimeview(self.env)
            if mview.is_binary(old_node.content_type, old_node.path):
                return None
            if mview.is_binary(new_node.content_type, new_node.path):
                return None
            old_content = old_node.get_content().read()
            if mview.is_binary(content=old_content):
                return None
            new_content = new_node.get_content().read()
            if mview.is_binary(content=new_content):
                return None

            old_content = mview.to_unicode(old_content, old_node.content_type)
            new_content = mview.to_unicode(new_content, new_node.content_type)

            if old_content != new_content:
                context = options.get('contextlines', 3)
                if context < 0 or options.get('contextall'):
                    context = None
                tabwidth = self.config['diff'].getint('tab_width') or \
                           self.config['mimeviewer'].getint('tab_width', 8)
                ignore_blank_lines = options.get('ignoreblanklines')
                ignore_case = options.get('ignorecase')
                ignore_space = options.get('ignorewhitespace')
                return diff_blocks(old_content.splitlines(),
                                   new_content.splitlines(),
                                   context, tabwidth,
                                   ignore_blank_lines=ignore_blank_lines,
                                   ignore_case=ignore_case,
                                   ignore_space_changes=ignore_space)
            else:
                return []

        diff_bytes = diff_files = 0
        if self.max_diff_bytes or self.max_diff_files:
            for old_node, new_node, kind, change in get_changes():
                if change in Changeset.DIFF_CHANGES and kind == Node.FILE \
                        and old_node.can_view(req.perm) \
                        and new_node.can_view(req.perm):
                    diff_files += 1
                    diff_bytes += _estimate_changes(old_node, new_node)
        show_diffs = (not self.max_diff_files or \
                      0 < diff_files <= self.max_diff_files) and \
                     (not self.max_diff_bytes or \
                      diff_bytes <= self.max_diff_bytes or \
                      diff_files == 1)

        # XHR is used for blame support: display the changeset view without
        # the navigation and with the changes concerning the annotated file
        annotated = False
        if xhr:
            show_diffs = False
            annotated = repos.normalize_path(req.args.get('annotate'))

        has_diffs = False
        filestats = self._prepare_filestats()
        changes = []
        files = []
        for old_node, new_node, kind, change in get_changes():
            props = []
            diffs = []
            show_old = old_node and old_node.can_view(req.perm)
            show_new = new_node and new_node.can_view(req.perm)
            show_entry = change != Changeset.EDIT
            show_diff = show_diffs or (new_node and new_node.path == annotated)

            if change in Changeset.DIFF_CHANGES and show_old and show_new:
                assert old_node and new_node
                props = _prop_changes(old_node, new_node)
                if props:
                    show_entry = True
                if kind == Node.FILE and show_diff:
                    diffs = _content_changes(old_node, new_node)
                    if diffs != []:
                        if diffs:
                            has_diffs = True
                        # elif None (means: manually compare to (previous))
                        show_entry = True
            if (show_old or show_new) and (show_entry or not show_diff):
                info = {'change': change,
                        'old': old_node and node_info(old_node, annotated),
                        'new': new_node and node_info(new_node, annotated),
                        'props': props,
                        'diffs': diffs}
                files.append(new_node and new_node.path or \
                             old_node and old_node.path or '')
                filestats[change] += 1
                if change in Changeset.DIFF_CHANGES:
                    if chgset:
                        href = req.href.changeset(new_node.rev, reponame,
                                                  new_node.path)
                        title = _('Show the changeset %(id)s restricted to '
                                  '%(path)s', id=display_rev(new_node.rev),
                                  path=new_node.path)
                    else:
                        href = req.href.changeset(
                            new_node.created_rev, reponame,
                            new_node.created_path,
                            old=old_node.created_rev,
                            old_path=pathjoin(repos.reponame, 
                                              old_node.created_path))
                        title = _('Show the %(range)s differences restricted '
                                  'to %(path)s', range='[%s:%s]' % (
                                      display_rev(old_node.rev),
                                      display_rev(new_node.rev)),
                                  path=new_node.path)
                    info['href'] = href
                    info['title'] = old_node and title
                if change in Changeset.DIFF_CHANGES and not show_diff:
                    info['hide_diff'] = True
            else:
                info = None
            changes.append(info) # the sequence should be immutable

        data.update({'has_diffs': has_diffs, 'changes': changes, 'xhr': xhr,
                     'filestats': filestats, 'annotated': annotated,
                     'files': files, 
                     'location': self._get_parent_location(files),
                     'longcol': 'Revision', 'shortcol': 'r'})

        if xhr: # render and return the content only
            stream = Chrome(self.env).render_template(req, 'changeset.html',
                                                      data, fragment=True)
            content = stream.select('//div[@id="content"]')
            str_content = content.render('xhtml', encoding='utf-8')
            req.send_header('Content-Length', len(str_content))
            req.end_headers()
            req.write(str_content)
            raise RequestDone

        return data

    def _render_diff(self, req, filename, repos, data):
        """Raw Unified Diff version"""
        req.send_response(200)
        req.send_header('Content-Type', 'text/x-patch;charset=utf-8')
        req.send_header('Content-Disposition',
                        content_disposition('inline', filename + '.diff'))
        buf = StringIO()
        mimeview = Mimeview(self.env)

        for old_node, new_node, kind, change in repos.get_changes(
                new_path=data['new_path'], new_rev=data['new_rev'],
                old_path=data['old_path'], old_rev=data['old_rev']):
            # TODO: Property changes

            # Content changes
            if kind == Node.DIRECTORY:
                continue

            new_content = old_content = ''
            new_node_info = old_node_info = ('','')

            if old_node:
                if not old_node.can_view(req.perm):
                    continue
                if mimeview.is_binary(old_node.content_type, old_node.path):
                    continue
                old_content = old_node.get_content().read()
                if mimeview.is_binary(content=old_content):
                    continue
                old_node_info = (old_node.path, old_node.rev)
                old_content = mimeview.to_unicode(old_content,
                                                  old_node.content_type)
            if new_node:
                if not new_node.can_view(req.perm):
                    continue
                if mimeview.is_binary(new_node.content_type, new_node.path):
                    continue
                new_content = new_node.get_content().read()
                if mimeview.is_binary(content=new_content):
                    continue
                new_node_info = (new_node.path, new_node.rev)
                new_path = new_node.path
                new_content = mimeview.to_unicode(new_content,
                                                  new_node.content_type)
            else:
                old_node_path = repos.normalize_path(old_node.path)
                diff_old_path = repos.normalize_path(data['old_path'])
                new_path = pathjoin(data['new_path'],
                                    old_node_path[len(diff_old_path) + 1:])

            if old_content != new_content:
                options = data['diff']['options']
                context = options.get('contextlines', 3)
                if context < 0 or options.get('contextall'):
                    context = 3 # FIXME: unified_diff bugs with context=None
                ignore_blank_lines = options.get('ignoreblanklines')
                ignore_case = options.get('ignorecase')
                ignore_space = options.get('ignorewhitespace')
                if not old_node_info[0]:
                    old_node_info = new_node_info # support for 'A'dd changes
                buf.write('Index: ' + new_path + CRLF)
                buf.write('=' * 67 + CRLF)
                buf.write('--- %s\t(revision %s)' % old_node_info + CRLF)
                buf.write('+++ %s\t(revision %s)' % new_node_info + CRLF)
                for line in unified_diff(old_content.splitlines(),
                                         new_content.splitlines(), context,
                                         ignore_blank_lines=ignore_blank_lines,
                                         ignore_case=ignore_case,
                                         ignore_space_changes=ignore_space):
                    buf.write(line + CRLF)
                    
        diff_str = buf.getvalue().encode('utf-8')
        req.send_header('Content-Length', len(diff_str))
        req.end_headers()
        req.write(diff_str)
        raise RequestDone

    def _render_zip(self, req, filename, repos, data):
        """ZIP archive containing all the added and/or modified files."""
        req.send_response(200)
        req.send_header('Content-Type', 'application/zip')
        req.send_header('Content-Disposition',
                        content_disposition('inline', filename + '.zip'))

        from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED as compression

        buf = StringIO()
        zipfile = ZipFile(buf, 'w', compression)
        for old_node, new_node, kind, change in repos.get_changes(
            new_path=data['new_path'], new_rev=data['new_rev'],
            old_path=data['old_path'], old_rev=data['old_rev']):
            if (kind == Node.FILE or kind == Node.DIRECTORY) and \
                    change != Changeset.DELETE and new_node.can_view(req.perm):
                zipinfo = ZipInfo()
                # Note: unicode filenames are not supported by zipfile.
                # UTF-8 is not supported by all Zip tools either,
                # but as some do, UTF-8 is the best option here.
                zipinfo.filename = new_node.path.strip('/').encode('utf-8')
                zipinfo.date_time = new_node.last_modified.utctimetuple()[:6]
                zipinfo.compress_type = compression
                # setting zipinfo.external_attr is needed since Python 2.5
                if new_node.isfile:
                    zipinfo.external_attr = 0644 << 16L
                    content = new_node.get_content().read()
                elif new_node.isdir:
                    zipinfo.filename += '/'
                    zipinfo.external_attr = 040755 << 16L
                    content = ''
                zipfile.writestr(zipinfo, content)
        zipfile.close()

        zip_str = buf.getvalue()
        req.send_header("Content-Length", len(zip_str))
        req.end_headers()
        req.write(zip_str)
        raise RequestDone

    def title_for_diff(self, data):
        # TRANSLATOR: 'latest' (revision)
        latest = _('latest')
        if data['new_path'] == data['old_path']:
            # ''diff between 2 revisions'' mode
            return _('Diff [%(old_rev)s:%(new_rev)s] for %(path)s',
                     old_rev=data['old_rev'] or latest,
                     new_rev=data['new_rev'] or latest,
                     path=data['new_path'] or '/')
        else:
            # ''generalized diff'' mode
            return _('Diff from %(old_path)s@%(old_rev)s to %(new_path)s@'
                     '%(new_rev)s',
                     old_path=data['old_path'] or '/',
                     old_rev=data['old_rev'] or latest,
                     new_path=data['new_path'] or '/',
                     new_rev=data['new_rev'] or latest)

    def render_property_diff(self, name, old_node, old_props,
                             new_node, new_props, options):
        """Renders diffs of a node property to HTML."""
        if name in BrowserModule(self.env).hidden_properties:
            return
        candidates = []
        for renderer in self.property_diff_renderers:
            quality = renderer.match_property_diff(name)
            if quality > 0:
                candidates.append((quality, renderer))
        candidates.sort(reverse=True)
        for (quality, renderer) in candidates:
            try:
                return renderer.render_property_diff(name, old_node, old_props,
                                                     new_node, new_props,
                                                     options)
            except Exception, e:
                self.log.warning('Diff rendering failed for property %s with '
                                 'renderer %s: %s', name,
                                 renderer.__class__.__name__,
                                 exception_to_unicode(e, traceback=True))

    def _get_location(self, files):
        """Return the deepest common path for the given files.
           If all the files are actually the same, return that location."""
        if len(files) == 1:
            return files[0]
        else:
            return '/'.join(os.path.commonprefix([f.split('/') 
                                                  for f in files]))
    def _get_parent_location(self, files):
        """Only get a location when there are different files,
           otherwise return the empty string."""
        if files: 
            files.sort()
            prev = files[0]
            for f in files[1:]:
                if f != prev:
                    return self._get_location(files)
        return ''

    def _prepare_filestats(self):
        filestats = {}
        for chg in Changeset.ALL_CHANGES:
            filestats[chg] = 0
        return filestats

    # ITimelineEventProvider methods

    def get_timeline_filters(self, req):
        if 'CHANGESET_VIEW' in req.perm:
            # Non-'hidden' repositories will be listed as additional
            # repository filters, unless there is only a single repository.
            filters = []
            rm = RepositoryManager(self.env)
            repositories = rm.get_real_repositories()
            if len(repositories) > 1:
                filters = [
                    ('repo-' + repos.reponame,
                     u"\xa0\xa0-\xa0" + (repos.reponame or _('(default)')))
                    for repos in repositories
                    if not as_bool(repos.params.get('hidden'))
                    and repos.can_view(req.perm)]
                filters.sort()
                add_script(req, 'common/js/timeline_multirepos.js')
                changeset_label = _('Changesets in all repositories')
            else:
                changeset_label = _('Repository changesets')
            filters.insert(0, ('changeset', changeset_label))
            return filters
        else:
            return []

    def get_timeline_events(self, req, start, stop, filters):
        all_repos = 'changeset' in filters
        repo_filters = set(f for f in filters if f.startswith('repo-'))
        if all_repos or repo_filters:
            show_files = self.timeline_show_files
            show_location = show_files == 'location'
            if show_files in ('-1', 'unlimited'):
                show_files = -1
            elif show_files.isdigit():
                show_files = int(show_files)
            else:
                show_files = 0 # disabled
            
            if self.timeline_collapse:
                collapse_changesets = lambda c: (c.author, c.message)
            else:
                collapse_changesets = lambda c: c.rev
                
            uids_seen = {}
            def generate_changesets(repos):
                for _, changesets in groupby(repos.get_changesets(start, stop),
                                             key=collapse_changesets):
                    viewable_changesets = []
                    for cset in changesets:
                        cset_resource = Resource('changeset', cset.rev,
                                                 parent=repos.resource)
                        if cset.can_view(req.perm):
                            repos_for_uid = [repos.reponame]
                            uid = repos.get_changeset_uid(cset.rev)
                            if uid:
                                # uid can be seen in multiple repositories
                                if uid in uids_seen:
                                    uids_seen[uid].append(repos.reponame)
                                    continue # already viewable, simply append
                                uids_seen[uid] = repos_for_uid
                            viewable_changesets.append((cset, cset_resource,
                                                        repos_for_uid))
                    if viewable_changesets:
                        cset = viewable_changesets[-1][0]
                        yield ('changeset', cset.date, cset.author,
                               (viewable_changesets, 
                                show_location, show_files))

            rm = RepositoryManager(self.env)
            for repos in sorted(rm.get_real_repositories(),
                                key=lambda repos: repos.reponame):
                if all_repos or ('repo-' + repos.reponame) in repo_filters:
                    try:
                        for event in generate_changesets(repos):
                            yield event
                    except TracError, e:
                        self.log.error("Timeline event provider for repository"
                                       " '%s' failed: %r", 
                                       repos.reponame, exception_to_unicode(e))

    def render_timeline_event(self, context, field, event):
        changesets, show_location, show_files = event[3]
        cset, cset_resource, repos_for_uid = changesets[0]
        older_cset = changesets[-1][0]
        message = cset.message or ''
        reponame = cset_resource.parent.id
        rev_b, rev_a = cset.rev, older_cset.rev

        if field == 'url':
            if rev_a == rev_b:
                return context.href.changeset(rev_a, reponame or None)
            else:
                return context.href.log(reponame or None, rev=rev_b,
                                        stop_rev=rev_a)
            
        elif field == 'description':
            branch_markup = []
            for name, head in cset.get_branches():
                class_ = 'branch'
                if head:
                    class_ += ' head'
                branch_markup.append(tag.span(name, class_=class_))
            if self.wiki_format_messages:
                markup = ''
                if self.timeline_long_messages: # override default flavor
                    context = context()
                    context.set_hints(wiki_flavor='html', 
                                      preserve_newlines=True)
            else:
                markup = message
                message = None
            if 'BROWSER_VIEW' in context.perm:
                files = []
                if show_location:
                    filestats = self._prepare_filestats()
                    for c, r, repos_for_c in changesets:
                        for chg in c.get_changes():
                            resource = c.resource.parent.child('source',
                                                        chg[0] or '/', r.id)
                            if not 'FILE_VIEW' in context.perm(resource):
                                continue
                            filestats[chg[2]] += 1
                            files.append(chg[0])
                    stats = [(tag.div(class_=kind),
                              tag.span(count, ' ',
                                       count > 1 and
                                       (kind == 'copy' and
                                        'copies' or kind + 's') or kind))
                             for kind in Changeset.ALL_CHANGES
                             for count in (filestats[kind],) if count]
                    markup = tag.ul(
                        tag.li(stats, ' in ',
                               tag.strong(self._get_location(files) or '/')),
                        markup, class_="changes")
                elif show_files:
                    for c, r, repos_for_c in changesets:
                        for chg in c.get_changes():
                            resource = c.resource.parent.child('source',
                                                        chg[0] or '/', r.id)
                            if not 'FILE_VIEW' in context.perm(resource):
                                continue
                            if show_files > 0 and len(files) > show_files:
                                break
                            files.append(tag.li(tag.div(class_=chg[2]),
                                                chg[0] or '/'))
                    if show_files > 0 and len(files) > show_files:
                        files = files[:show_files] + [tag.li(u'\u2026')]
                    markup = tag(tag.ul(files, class_="changes"), markup)
            if message:
                markup += format_to(self.env, None, context(cset_resource),
                                    message)
            return tag(branch_markup, markup)

        single = rev_a == rev_b
        if not repos_for_uid[0]:
            repos_for_uid[0] = _('(default)')
        if reponame or len(repos_for_uid) > 1:
            title = ngettext('Changeset in %(repo)s ',
                             'Changesets in %(repo)s ',
                             single and 1 or 2, repo=', '.join(repos_for_uid))
        else:
            title = ngettext('Changeset ', 'Changesets ', single and 1 or 2)
        drev_a = older_cset.repos.display_rev(rev_a)
        if single:
            title = tag(title, tag.em('[%s]' % drev_a))
        else:
            drev_b = cset.repos.display_rev(rev_b)
            title = tag(title, tag.em('[%s-%s]' % (drev_a, drev_b)))
        if field == 'title':
            return title
        elif field == 'summary':
            return _("%(title)s: %(message)s",
                     title=title, message=shorten_line(message))
        
    # IWikiSyntaxProvider methods

    CHANGESET_ID = r"(?:\d+|[a-fA-F\d]{8,})" # only "long enough" hexa ids

    def get_wiki_syntax(self):
        yield (
            # [...] form: start with optional intertrac: [T... or [trac ...
            r"!?\[(?P<it_changeset>%s\s*)" % WikiParser.INTERTRAC_SCHEME +
            # hex digits + optional /path for the restricted changeset
            # + optional query and fragment
            r"%s(?:/[^\]]*)?(?:\?[^\]]*)?(?:#[^\]]*)?\]|" % self.CHANGESET_ID +
            # r... form: allow r1 but not r1:2 (handled by the log syntax)
            r"(?:\b|!)r\d+\b(?!:\d)(?:/[a-zA-Z0-9_/+-]+)?",
            lambda x, y, z:
            self._format_changeset_link(x, 'changeset',
                                        y[0] == 'r' and y[1:] or y[1:-1],
                                        y, z))

    def get_link_resolvers(self):
        yield ('changeset', self._format_changeset_link)
        yield ('diff', self._format_diff_link)

    def _format_changeset_link(self, formatter, ns, chgset, label,
                               fullmatch=None):
        intertrac = formatter.shorthand_intertrac_helper(ns, chgset, label,
                                                         fullmatch)
        if intertrac:
            return intertrac

        # identifying repository
        rm = RepositoryManager(self.env)
        chgset, params, fragment = formatter.split_link(chgset)
        sep = chgset.find('/')
        if sep > 0:
            rev, path = chgset[:sep], chgset[sep:]
        else:
            rev, path = chgset, '/'
        try:
            reponame, repos, path = rm.get_repository_by_path(path)
            if not reponame:
                reponame = rm.get_default_repository(formatter.context)
                if reponame is not None:
                    repos = rm.get_repository(reponame)
            if path == '/':
                path = None

            # rendering changeset link
            if repos:
                changeset = repos.get_changeset(rev)
                if changeset.can_view(formatter.perm):
                    href = formatter.href.changeset(rev,
                                                    repos.reponame or None,
                                                    path)
                    return tag.a(label, class_="changeset",
                                 title=shorten_line(changeset.message),
                                 href=href + params + fragment)
                errmsg = _("No permission to view changeset %(rev)s "
                           "on %(repos)s", rev=rev,
                           repos=reponame or _('(default)'))
            elif reponame:
                errmsg = _("Repository '%(repo)s' not found", repo=reponame)
            else:
                errmsg = _("No default repository defined")
        except TracError, e:
            errmsg = to_unicode(e)
        return tag.a(label, class_="missing changeset", title=errmsg)

    def _format_diff_link(self, formatter, ns, target, label):
        params, query, fragment = formatter.split_link(target)
        def pathrev(path):
            if '@' in path:
                return path.split('@', 1)
            else:
                return (path, None)
        if '//' in params:
            p1, p2 = params.split('//', 1)
            old, new = pathrev(p1), pathrev(p2)
            data = {'old_path': old[0], 'old_rev': old[1],
                    'new_path': new[0], 'new_rev': new[1]}
        else:
            old_path, old_rev = pathrev(params)
            new_rev = None
            if old_rev and ':' in old_rev:
                old_rev, new_rev = old_rev.split(':', 1)
            data = {'old_path': old_path, 'old_rev': old_rev,
                    'new_path': old_path, 'new_rev': new_rev}
        title = self.title_for_diff(data)
        href = None
        if any(data.values()):
            if query:
                query = '&' + query[1:]
            href = formatter.href.changeset(new_path=data['new_path'] or None,
                                            new=data['new_rev'],
                                            old_path=data['old_path'] or None,
                                            old=data['old_rev']) + query
        return tag.a(label, class_="changeset", title=title, href=href)

    # ISearchSource methods 
    
    ### FIXME: move this specific implementation into cache.py

    def get_search_filters(self, req):
        if 'CHANGESET_VIEW' in req.perm:
            yield ('changeset', _('Changesets'))

    def get_search_results(self, req, terms, filters):
        if not 'changeset' in filters:
            return
        rm = RepositoryManager(self.env)
        repositories = dict((repos.params['id'], repos)
                            for repos in rm.get_real_repositories())
        db = self.env.get_db_cnx()
        sql, args = search_to_sql(db, ['rev', 'message', 'author'], terms)
        cursor = db.cursor()
        cursor.execute("SELECT repos,rev,time,author,message "
                       "FROM revision WHERE " + sql, args)
        for id, rev, ts, author, log in cursor:
            try:
                rev = int(rev)
            except ValueError:
                pass
            repos = repositories.get(id)
            if not repos:
                continue # revisions for a no longer active repository
            cset = repos.resource.child('changeset', rev)
            if 'CHANGESET_VIEW' in req.perm(cset):
                yield (req.href.changeset(rev, repos.reponame or None),
                       '[%s]: %s' % (rev, shorten_line(log)),
                       from_utimestamp(ts), author, shorten_result(log, terms))


class AnyDiffModule(Component):

    implements(IRequestHandler)

    # IRequestHandler methods

    def match_request(self, req):
        return req.path_info == '/diff'

    def process_request(self, req):
        rm = RepositoryManager(self.env)

        if req.get_header('X-Requested-With') == 'XMLHttpRequest':
            dirname, prefix = posixpath.split(req.args.get('q'))
            prefix = prefix.lower()
            reponame, repos, path = rm.get_repository_by_path(dirname)
            # an entry is a (isdir, name, path) tuple
            def kind_order(entry):
                return (not entry[0], embedded_numbers(entry[1]))

            entries = []
            if repos:
                entries.extend((e.isdir, e.name, 
                                '/' + pathjoin(repos.reponame, e.path))
                               for e in repos.get_node(path).get_entries()
                               if e.can_view(req.perm))
            if not reponame:
                entries.extend((True, repos.reponame, '/' + repos.reponame)
                               for repos in rm.get_real_repositories()
                               if repos.can_view(req.perm))

            elem = tag.ul(
                [tag.li(isdir and tag.b(path) or path)
                 for (isdir, name, path) in sorted(entries, key=kind_order)
                 if name.lower().startswith(prefix)])

            xhtml = elem.generate().render('xhtml', encoding='utf-8')
            req.send_header('Content-Length', len(xhtml))
            req.write(xhtml)
            return

        # -- retrieve arguments
        new_path = req.args.get('new_path')
        new_rev = req.args.get('new_rev')
        old_path = req.args.get('old_path')
        old_rev = req.args.get('old_rev')

        # -- normalize and prepare rendering
        new_reponame, new_repos, new_path = \
            rm.get_repository_by_path(new_path)
        old_reponame, old_repos, old_path = \
            rm.get_repository_by_path(old_path)
        
        data = {}
        if new_repos:
            data.update(new_path='/' + pathjoin(new_repos.reponame, new_path),
                        new_rev=new_repos.normalize_rev(new_rev))
        else:
            data.update(new_path=req.args.get('new_path'), new_rev=new_rev)
        if old_repos:
            data.update(old_path='/' + pathjoin(old_repos.reponame, old_path),
                        old_rev=old_repos.normalize_rev(old_rev))
        else:
            data.update(old_path=req.args.get('old_path'), old_rev=old_rev)

        add_script(req, 'common/js/suggest.js')
        return 'diff_form.html', data, None
