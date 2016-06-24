# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2009 Edgewall Software
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
# Copyright (C) 2005-2007 Christian Boos <cboos@edgewall.org>
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
#         Christian Boos <cboos@edgewall.org>

import posixpath

from genshi.builder import tag

from trac.config import ConfigSection
from trac.core import *
from trac.versioncontrol.api import NoSuchNode, RepositoryManager
from trac.versioncontrol.web_ui.browser import IPropertyRenderer
from trac.versioncontrol.web_ui.changeset import IPropertyDiffRenderer
from trac.util import Ranges, to_ranges
from trac.util.translation import _, tag_
from trac.web.chrome import chrome_resource_path
from tracopt.versioncontrol.svn.svn_fs import _path_within_scope


class SubversionPropertyRenderer(Component):

    implements(IPropertyRenderer)

    svn_externals_section = ConfigSection('svn:externals',
        """The TracBrowser for Subversion can interpret the `svn:externals`
        property of folders. By default, it only turns the URLs into links as
        Trac can't browse remote repositories.

        However, if you have another Trac instance (or an other repository
        browser like [http://www.viewvc.org/ ViewVC]) configured to browse the
        target repository, then you can instruct Trac which other repository
        browser to use for which external URL. This mapping is done in the
        `[svn:externals]` section of the TracIni.

        Example:
        {{{
        [svn:externals]
        1 = svn://server/repos1                       http://trac/proj1/browser/$path?rev=$rev
        2 = svn://server/repos2                       http://trac/proj2/browser/$path?rev=$rev
        3 = http://theirserver.org/svn/eng-soft       http://ourserver/viewvc/svn/$path/?pathrev=25914
        4 = svn://anotherserver.com/tools_repository  http://ourserver/tracs/tools/browser/$path?rev=$rev
        }}}
        With the above, the
        `svn://anotherserver.com/tools_repository/tags/1.1/tools` external will
        be mapped to `http://ourserver/tracs/tools/browser/tags/1.1/tools?rev=`
        (and `rev` will be set to the appropriate revision number if the
        external additionally specifies a revision, see the
        [%(svnbook)s SVN Book on externals] for more details).

        Note that the number used as a key in the above section is purely used
        as a place holder, as the URLs themselves can't be used as a key due to
        various limitations in the configuration file parser.

        Finally, the relative URLs introduced in
        [http://subversion.apache.org/docs/release-notes/1.5.html#externals Subversion 1.5]
        are not yet supported.
        """,
        doc_args={'svnbook': 'http://svnbook.red-bean.com/en/1.7/svn.advanced.externals.html'})

    def __init__(self):
        self._externals_map = {}

    # IPropertyRenderer methods

    def match_property(self, name, mode):
        if name in ('svn:externals', 'svn:needs-lock'):
            return 4
        return 2 if name in ('svn:mergeinfo', 'svnmerge-blocked',
                             'svnmerge-integrated') else 0

    def render_property(self, name, mode, context, props):
        if name == 'svn:externals':
            return self._render_externals(props[name])
        elif name == 'svn:needs-lock':
            return self._render_needslock(context)
        elif name == 'svn:mergeinfo' or name.startswith('svnmerge-'):
            return self._render_mergeinfo(name, mode, context, props)

    def _is_abs_url(self, url):
        return url and '://' in url

    def _render_externals(self, prop):
        if not self._externals_map:
            for dummykey, value in self.svn_externals_section.options():
                value = value.split()
                if len(value) != 2:
                    self.log.warn("svn:externals entry %s doesn't contain "
                                  "a space-separated key value pair, "
                                  "skipping.", dummykey)
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
            if not self._is_abs_url(url):
                externals.append((external, None, None, None, None))
                continue
            prefix = []
            base_url = url
            while base_url:
                if base_url in self._externals_map or base_url == u'/':
                    break
                base_url, pref = posixpath.split(base_url)
                prefix.append(pref)
            href = self._externals_map.get(base_url)
            revstr = ' at revision ' + rev if rev else ''
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

    def _render_needslock(self, context):
        url = chrome_resource_path(context.req, 'common/lock-locked.png')
        return tag.img(src=url, alt=_("needs lock"), title=_("needs lock"))

    def _render_mergeinfo(self, name, mode, context, props):
        rows = []
        for row in props[name].splitlines():
            try:
                (path, revs) = row.rsplit(':', 1)
                rows.append([tag.td(path),
                             tag.td(revs.replace(',', u',\u200b'))])
            except ValueError:
                rows.append(tag.td(row, colspan=2))
        return tag.table(tag.tbody([tag.tr(row) for row in rows]),
                         class_='props')


class SubversionMergePropertyRenderer(Component):
    implements(IPropertyRenderer)

    # IPropertyRenderer methods

    def match_property(self, name, mode):
        return 4 if name in ('svn:mergeinfo', 'svnmerge-blocked',
                             'svnmerge-integrated') else 0

    def render_property(self, name, mode, context, props):
        """Parse svn:mergeinfo and svnmerge-* properties, converting branch
        names to links and providing links to the revision log for merged
        and eligible revisions.
        """
        has_eligible = name in ('svnmerge-integrated', 'svn:mergeinfo')
        revs_label = _('blocked') if name.endswith('blocked') else _('merged')
        revs_cols = 2 if has_eligible else None
        reponame = context.resource.parent.id
        target_path = context.resource.id
        repos = RepositoryManager(self.env).get_repository(reponame)
        target_rev = context.resource.version
        if has_eligible:
            node = repos.get_node(target_path, target_rev)
            branch_starts = {}
            for path, rev in node.get_copy_ancestry():
                if path not in branch_starts:
                    branch_starts[path] = rev + 1
        rows = []
        eligible_infos = []
        if name.startswith('svnmerge-'):
            sources = props[name].split()
        else:
            sources = props[name].splitlines()
        for line in sources:
            path, revs = line.split(':', 1)
            spath = _path_within_scope(repos.scope, path)
            if spath is None:
                continue
            revs = revs.strip()
            inheritable, non_inheritable = _partition_inheritable(revs)
            revs = ','.join(inheritable)
            deleted = False
            try:
                node = repos.get_node(spath, target_rev)
                resource = context.resource.parent.child('source', spath)
                if 'LOG_VIEW' in context.perm(resource):
                    row = [_get_source_link(spath, context),
                           _get_revs_link(revs_label, context, spath, revs)]
                    if non_inheritable:
                        non_inheritable = ','.join(non_inheritable)
                        row.append(_get_revs_link(_('non-inheritable'), context,
                                                  spath, non_inheritable,
                                                  _('merged on the directory '
                                                    'itself but not below')))
                    if has_eligible:
                        first_rev = branch_starts.get(spath)
                        if not first_rev:
                            first_rev = node.get_branch_origin()
                        eligible = set(xrange(first_rev or 1, target_rev + 1))
                        eligible -= set(Ranges(revs))
                        blocked = _get_blocked_revs(props, name, spath)
                        if blocked:
                            eligible -= set(Ranges(blocked))
                        if eligible:
                            node = repos.get_node(spath, max(eligible))
                            eligible_infos.append((spath, node, eligible, row))
                            continue
                        eligible = to_ranges(eligible)
                        row.append(_get_revs_link(_('eligible'), context,
                                                  spath, eligible))
                    rows.append((False, spath, [tag.td(each) for each in row]))
                    continue
            except NoSuchNode:
                deleted = True
            revs = revs.replace(',', u',\u200b')
            rows.append((deleted, spath,
                         [tag.td('/' + spath),
                          tag.td(revs, colspan=revs_cols)]))

        # fetch eligible revisions for each path at a time
        changed_revs = {}
        changed_nodes = [(node, min(eligible))
                         for spath, node, eligible, row in eligible_infos]
        if changed_nodes:
            changed_revs = repos._get_changed_revs(changed_nodes)
        for spath, node, eligible, row in eligible_infos:
            if spath in changed_revs:
                eligible &= set(changed_revs[spath])
            else:
                eligible.clear()
            row.append(_get_revs_link(_("eligible"), context, spath,
                                      to_ranges(eligible)))
            rows.append((False, spath, [tag.td(each) for each in row]))

        if not rows:
            return None
        rows.sort()
        if rows and rows[-1][0]:
            toggledeleted = tag.a(_("(toggle deleted branches)"),
                                  class_='trac-toggledeleted', href='#')
        else:
            toggledeleted = None
        return tag(toggledeleted,
                   tag.table(tag.tbody(
                       [tag.tr(row, class_='trac-deleted' if deleted else None)
                        for deleted, spath, row in rows]), class_='props'))


def _partition_inheritable(revs):
    """Non-inheritable revision ranges are marked with a trailing '*'."""
    inheritable, non_inheritable = [], []
    for r in revs.split(','):
        if r and r[-1] == '*':
            non_inheritable.append(r[:-1])
        else:
            inheritable.append(r)
    return inheritable, non_inheritable

def _get_blocked_revs(props, name, path):
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

def _get_source_link(spath, context):
    """Return a link to a merge source."""
    reponame = context.resource.parent.id
    return tag.a('/' + spath, title=_('View merge source'),
                 href=context.href.browser(reponame or None, spath,
                                           rev=context.resource.version))

def _get_revs_link(label, context, spath, revs, title=None):
    """Return a link to the revision log when more than one revision is
    given, to the revision itself for a single revision, or a `<span>`
    with "no revision" for none.
    """
    reponame = context.resource.parent.id
    if not revs:
        return tag.span(label, title=_('No revisions'))
    elif ',' in revs or '-' in revs:
        revs_href = context.href.log(reponame or None, spath, revs=revs)
    else:
        revs_href = context.href.changeset(revs, reponame or None, spath)
    revs = revs.replace(',', ', ')
    if title:
        title = _("%(title)s: %(revs)s", title=title, revs=revs)
    else:
        title = revs
    return tag.a(label, title=title, href=revs_href)


class SubversionMergePropertyDiffRenderer(Component):
    implements(IPropertyDiffRenderer)

    # IPropertyDiffRenderer methods

    def match_property_diff(self, name):
        return 4 if name in ('svn:mergeinfo', 'svnmerge-blocked',
                             'svnmerge-integrated') else 0

    def render_property_diff(self, name, old_context, old_props,
                             new_context, new_props, options):
        # Build 5 columns table showing modifications on merge sources
        # || source || added || removed || added (ni) || removed (ni) ||
        # || source || removed                                        ||
        rm = RepositoryManager(self.env)
        repos = rm.get_repository(old_context.resource.parent.id)
        def parse_sources(props):
            sources = {}
            value = props[name]
            lines = value.splitlines() if name == 'svn:mergeinfo' \
                                       else value.split()
            for line in lines:
                path, revs = line.split(':', 1)
                spath = _path_within_scope(repos.scope, path)
                if spath is not None:
                    inheritable, non_inheritable = _partition_inheritable(revs)
                    sources[spath] = (set(Ranges(inheritable)),
                                      set(Ranges(non_inheritable)))
            return sources
        old_sources = parse_sources(old_props)
        new_sources = parse_sources(new_props)
        # Go through new sources, detect modified ones or added ones
        blocked = name.endswith('blocked')
        added_label = [_("merged: "), _("blocked: ")][blocked]
        removed_label = [_("reverse-merged: "), _("un-blocked: ")][blocked]
        added_ni_label = _("marked as non-inheritable: ")
        removed_ni_label = _("unmarked as non-inheritable: ")

        sources = []
        changed_revs = {}
        changed_nodes = []
        for spath, (new_revs, new_revs_ni) in new_sources.iteritems():
            new_spath = spath not in old_sources
            if new_spath:
                old_revs = old_revs_ni = set()
            else:
                old_revs, old_revs_ni = old_sources.pop(spath)
            added = new_revs - old_revs
            removed = old_revs - new_revs
            # unless new revisions differ from old revisions
            if not added and not removed:
                continue
            added_ni = new_revs_ni - old_revs_ni
            removed_ni = old_revs_ni - new_revs_ni
            revs = sorted(added | removed | added_ni | removed_ni)
            try:
                node = repos.get_node(spath, revs[-1])
                changed_nodes.append((node, revs[0]))
            except NoSuchNode:
                pass
            sources.append((spath, new_spath, added, removed, added_ni,
                            removed_ni))
        if changed_nodes:
            changed_revs = repos._get_changed_revs(changed_nodes)

        def revs_link(revs, context):
            if revs:
                revs = to_ranges(revs)
                return _get_revs_link(revs.replace(',', u',\u200b'),
                                      context, spath, revs)
        modified_sources = []
        for spath, new_spath, added, removed, added_ni, removed_ni in sources:
            if spath in changed_revs:
                revs = set(changed_revs[spath])
                added &= revs
                removed &= revs
                added_ni &= revs
                removed_ni &= revs
            if added or removed:
                if new_spath:
                    status = _(" (added)")
                else:
                    status = None
                modified_sources.append((
                    spath, [_get_source_link(spath, new_context), status],
                    added and tag(added_label, revs_link(added, new_context)),
                    removed and tag(removed_label,
                                    revs_link(removed, old_context)),
                    added_ni and tag(added_ni_label,
                                     revs_link(added_ni, new_context)),
                    removed_ni and tag(removed_ni_label,
                                       revs_link(removed_ni, old_context))
                    ))
        # Go through remaining old sources, those were deleted
        removed_sources = []
        for spath, old_revs in old_sources.iteritems():
            removed_sources.append((spath,
                                    _get_source_link(spath, old_context)))
        if modified_sources or removed_sources:
            modified_sources.sort()
            removed_sources.sort()
            changes = tag.table(tag.tbody(
                [tag.tr(tag.td(c) for c in cols[1:])
                 for cols in modified_sources],
                [tag.tr(tag.td(src), tag.td(_('removed'), colspan=4))
                 for spath, src in removed_sources]), class_='props')
        else:
            changes = tag.em(_(' (with no actual effect on merging)'))
        return tag.li(tag_('Property %(prop)s changed', prop=tag.strong(name)),
                      changes)
