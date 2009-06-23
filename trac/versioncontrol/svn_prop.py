# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2009 Edgewall Software
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
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
# Author: Christopher Lenz <cmlenz@gmx.de>
#         Christian Boos <cboos@neuf.fr>

import posixpath

from genshi.builder import tag

from trac.core import *
from trac.versioncontrol import NoSuchNode
from trac.versioncontrol.web_ui.browser import IPropertyRenderer
from trac.versioncontrol.web_ui.changeset import IPropertyDiffRenderer
from trac.util import Ranges, to_ranges
from trac.util.compat import set
from trac.util.translation import _


class SubversionPropertyRenderer(Component):
    implements(IPropertyRenderer, IPropertyDiffRenderer)

    def __init__(self):
        self._externals_map = {}

    # IPropertyRenderer methods

    def match_property(self, name, mode):
        return name in ('svn:externals', 'svn:mergeinfo', 'svn:needs-lock',
                        'svnmerge-blocked', 'svnmerge-integrated') and 4 or 0
    
    def render_property(self, name, mode, context, props):
        if name == 'svn:externals':
            return self._render_externals(props[name])
        elif name == 'svn:mergeinfo' or name.startswith('svnmerge-'):
            return self._render_mergeinfo(name, mode, context, props)
        elif name == 'svn:needs-lock':
            return self._render_needslock(context)

    def _render_externals(self, prop):
        if not self._externals_map:
            for dummykey, value in self.config.options('svn:externals'):
                value = value.split()
                if len(value) != 2:
                    self.log.warn("svn:externals entry %s doesn't contain "
                            "a space-separated key value pair, skipping.", 
                            label)
                    continue
                key, value = value
                self._externals_map[key] = value.replace('%', '%%') \
                                           .replace('$path', '%(path)s') \
                                           .replace('$rev', '%(rev)s')
        externals = []
        for external in prop.splitlines():
            elements = external.split()
            if not elements:
                continue
            localpath, rev, url = elements[0], '', elements[-1]
            if localpath.startswith('#'):
                externals.append((external, None, None, None, None))
                continue
            if len(elements) == 3:
                rev = elements[1]
                rev = rev.replace('-r', '')
            # retrieve a matching entry in the externals map
            prefix = []
            base_url = url
            while base_url:
                if base_url in self._externals_map or base_url==u'/':
                    break
                base_url, pref = posixpath.split(base_url)
                prefix.append(pref)
            href = self._externals_map.get(base_url)
            revstr = rev and ' at revision '+rev or ''
            if not href and (url.startswith('http://') or 
                             url.startswith('https://')):
                href = url.replace('%', '%%')
            if href:
                remotepath = ''
                if prefix:
                    remotepath = posixpath.join(*reversed(prefix))
                externals.append((localpath, revstr, base_url, remotepath,
                                  href % {'path': remotepath, 'rev': rev}))
            else:
                externals.append((localpath, revstr, url, None, None))
        externals_data = []
        for localpath, rev, url, remotepath, href in externals:
            label = localpath
            if url is None:
                title = ''
            elif href:
                if url:
                    url = ' in ' + url
                label += rev + url
                title = ''.join((remotepath, rev, url))
            else:
                title = _('No svn:externals configured in trac.ini')
            externals_data.append((label, href, title))
        return tag.ul([tag.li(tag.a(label, href=href, title=title))
                       for label, href, title in externals_data])

    def _render_mergeinfo(self, name, mode, context, props):
        """Parse svn:mergeinfo and svnmerge-* properties, converting branch
        names to links and providing links to the revision log for merged
        and eligible revisions.
        """
        has_eligible = name in ('svnmerge-integrated', 'svn:mergeinfo')
        revs_label = (_('merged'), _('blocked'))[name.endswith('blocked')]
        revs_cols = has_eligible and 2 or None
        repos = self.env.get_repository()
        rows = []
        for line in props[name].splitlines():
            path, revs = line.split(':', 1)
            spath = path.strip('/')
            revs = revs.strip()
            deleted = False
            if 'LOG_VIEW' in context.perm('source', spath):
                try:
                    node = repos.get_node(spath, context.resource.version)
                    row = [self._get_source_link(path, context),
                           self._get_revs_link(revs_label, context,
                                               spath, revs)]
                    if has_eligible:
                        eligible = set(repos._get_node_revs(spath,
                                                    context.resource.version))
                        eligible -= set(Ranges(revs))
                        blocked = self._get_blocked_revs(props, name, spath)
                        eligible -= set(Ranges(blocked))
                        eligible = to_ranges(eligible)
                        row.append(self._get_revs_link(_('eligible'), context,
                                                       spath, eligible))
                    rows.append((False, spath, [tag.td(each) for each in row]))
                    continue
                except NoSuchNode:
                    deleted = True
            revs = revs.replace(',', u',\u200b')
            rows.append((deleted, spath,
                         [tag.td(path), tag.td(revs, colspan=revs_cols)]))
        rows.sort()
        has_deleted = rows and rows[-1][0] or None
        return tag(has_deleted and tag.a(_('(toggle deleted branches)'),
                                         class_='trac-toggledeleted',
                                         href='#'),
                   tag.table(tag.tbody(
                       [tag.tr(row, class_=deleted and 'trac-deleted' or None)
                        for deleted, p, row in rows]), class_='props'))

    def _get_blocked_revs(self, props, name, path):
        """Return the revisions blocked from merging for the given property
        name and path.
        """
        if name == 'svnmerge-integrated':
            prop = props.get('svnmerge-blocked', '')
        else:
            return ""
        for line in prop.splitlines():
            try:
                p, revs = line.split(':', 1)
                if p.strip('/') == path:
                    return revs
            except Exception:
                pass
        return ""

    def _get_source_link(self, path, context):
        """Return a link to a merge source."""
        return tag.a(path, title=_('View merge source'),
                     href=context.href.browser(path,
                                               rev=context.resource.version))

    def _get_revs_link(self, label, context, spath, revs):
        """Return a link to the revision log when more than one revision is
        given, to the revision itself for a single revision, or a `<span>`
        with "no revision" for none.
        """
        if not revs:
            return tag.span(label, title=_('No revisions'))
        elif ',' in revs or '-' in revs:
            revs_href = context.href.log(spath, revs=revs)
        else:
            revs_href = context.href.changeset(revs, spath)
        return tag.a(label, title=revs.replace(',', ', '), href=revs_href)

    def _render_needslock(self, context):
        return tag.img(src=context.href.chrome('common/lock-locked.png'),
                       alt="needs lock", title="needs lock")

    # IPropertyDiffRenderer methods

    def match_property_diff(self, name):
        return name in ('svn:mergeinfo', 'svnmerge-blocked',
                        'svnmerge-integrated') and 4 or 0

    def render_property_diff(self, name, old_context, old_props,
                             new_context, new_props, options):
        # Build 3 columns table showing modifications on merge sources
        # || source || added revs || removed revs ||
        # || source || removed                    ||
        def parse_sources(props):
            sources = {}
            for line in props[name].splitlines():
                path, revs = line.split(':', 1)
                spath = path.strip('/')
                sources[spath] = (path, set(Ranges(revs.strip())))
            return sources
        old_sources = parse_sources(old_props)
        new_sources = parse_sources(new_props)
        # Go through new sources, detect modified ones or added ones
        blocked = name.endswith('blocked')
        added_label = [_('merged: '), _('blocked: ')][blocked]
        removed_label = [_('reverse-merged: '), _('un-blocked: ')][blocked]
        def revs_link(revs, context):
            if revs:
                revs = to_ranges(revs)
                return self._get_revs_link(revs.replace(',', u',\u200b'),
                                           context, spath, revs)
        repos = self.env.get_repository()
        modified_sources = []
        for spath, (path, new_revs) in new_sources.iteritems():
            if spath in old_sources:
                old_revs, status = old_sources.pop(spath)[1], None
            else:
                old_revs, status = set(), _(' (added)')
            added = new_revs - old_revs
            removed = old_revs - new_revs
            try:
                all_revs = set(repos._get_node_revs(spath))
                added &= all_revs
                removed &= all_revs
            except NoSuchNode:
                pass
            if added or removed:
                modified_sources.append((
                    path, [self._get_source_link(path, new_context), status],
                    added and tag(added_label, revs_link(added, new_context)),
                    removed and tag(removed_label,
                                    revs_link(removed, old_context))))
        # Go through remaining old sources, those were deleted
        removed_sources = []
        for spath, (path, old_revs) in old_sources.iteritems():
            removed_sources.append((path,
                                    self._get_source_link(path, old_context)))
        if modified_sources or removed_sources:
            modified_sources.sort()
            removed_sources.sort()
            changes = tag.table(tag.tbody(
                [tag.tr(tag.td(src), tag.td(added), tag.td(removed))
                 for p, src, added, removed in modified_sources],
                [tag.tr(tag.td(src), tag.td(_('removed'), colspan=2))
                 for p, src in removed_sources]), class_='props')
        else:
            changes = tag.em(_(' (with no actual effect on merging)'))
        return tag.li(tag('Property ', tag.strong(name), ' changed'),
                      changes)
