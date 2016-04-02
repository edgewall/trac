# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2009 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2004-2005 Christopher Lenz <cmlenz@gmx.de>
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

from __future__ import with_statement

import pkg_resources
import re

from genshi.builder import tag

from trac.attachment import AttachmentModule
from trac.config import IntOption
from trac.core import *
from trac.mimeview.api import IContentConverter, Mimeview
from trac.perm import IPermissionRequestor
from trac.resource import *
from trac.search import ISearchSource, search_to_sql, shorten_result
from trac.timeline.api import ITimelineEventProvider
from trac.util import as_int, get_reporter_id
from trac.util.datefmt import from_utimestamp, to_utimestamp
from trac.util.text import shorten_line
from trac.util.translation import _, tag_
from trac.versioncontrol.diff import get_diff_options, diff_blocks
from trac.web.api import HTTPBadRequest, IRequestHandler
from trac.web.chrome import (Chrome, INavigationContributor,
                             ITemplateProvider, add_ctxtnav, add_link,
                             add_notice, add_script, add_stylesheet,
                             add_warning, prevnext_nav, web_context)
from trac.wiki.api import IWikiPageManipulator, WikiSystem, validate_page_name
from trac.wiki.formatter import format_to, OneLinerFormatter
from trac.wiki.model import WikiPage


class InvalidWikiPage(TracError):
    """Exception raised when a Wiki page fails validation.

    :deprecated: Not used anymore since 0.11
    """


class WikiModule(Component):

    implements(IContentConverter, INavigationContributor,
               IPermissionRequestor, IRequestHandler, ITimelineEventProvider,
               ISearchSource, ITemplateProvider)

    page_manipulators = ExtensionPoint(IWikiPageManipulator)

    max_size = IntOption('wiki', 'max_size', 262144,
        """Maximum allowed wiki page size in characters. (''since 0.11.2'')""")

    PAGE_TEMPLATES_PREFIX = 'PageTemplates/'
    DEFAULT_PAGE_TEMPLATE = 'DefaultPage'

    # IContentConverter methods

    def get_supported_conversions(self):
        yield ('txt', _("Plain Text"), 'txt', 'text/x-trac-wiki',
               'text/plain', 9)

    def convert_content(self, req, mimetype, content, key):
        return content, 'text/plain;charset=utf-8'

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'wiki'

    def get_navigation_items(self, req):
        if 'WIKI_VIEW' in req.perm('wiki', 'WikiStart'):
            yield ('mainnav', 'wiki',
                   tag.a(_("Wiki"), href=req.href.wiki(), accesskey=1))
        if 'WIKI_VIEW' in req.perm('wiki', 'TracGuide'):
            yield ('metanav', 'help',
                   tag.a(_("Help/Guide"), href=req.href.wiki('TracGuide'),
                         accesskey=6))

    # IPermissionRequestor methods

    def get_permission_actions(self):
        actions = ['WIKI_CREATE', 'WIKI_DELETE', 'WIKI_MODIFY', 'WIKI_RENAME',
                   'WIKI_VIEW']
        return actions + [('WIKI_ADMIN', actions)]

    # IRequestHandler methods

    def match_request(self, req):
        match = re.match(r'/wiki(?:/(.+))?$', req.path_info)
        if match:
            if match.group(1):
                req.args['page'] = match.group(1)
            return 1

    def process_request(self, req):
        action = req.args.get('action', 'view')
        pagename = req.args.get('page', 'WikiStart')
        version = req.args.get('version')
        old_version = req.args.get('old_version')

        if pagename.startswith('/') or pagename.endswith('/') or \
                '//' in pagename:
            pagename = re.sub(r'/{2,}', '/', pagename.strip('/'))
            req.redirect(req.href.wiki(pagename))
        if not validate_page_name(pagename):
            raise TracError(_("Invalid Wiki page name '%(name)s'",
                              name=pagename))

        if version is not None:
            version_as_int = as_int(version, None)
            if version_as_int is None:
                raise ResourceNotFound(
                    _('No version "%(num)s" for Wiki page "%(name)s"',
                      num=version, name=pagename))
            version = version_as_int

        page = WikiPage(self.env, pagename)
        versioned_page = WikiPage(self.env, pagename, version=version)

        req.perm(versioned_page.resource).require('WIKI_VIEW')

        if version and versioned_page.version != int(version):
            raise ResourceNotFound(
                _('No version "%(num)s" for Wiki page "%(name)s"',
                  num=version, name=page.name))

        add_stylesheet(req, 'common/css/wiki.css')

        if req.method == 'POST':
            if action == 'edit':
                if 'cancel' in req.args:
                    req.redirect(req.href.wiki(page.name))

                has_collision = int(version) != page.version
                for a in ('preview', 'diff', 'merge'):
                    if a in req.args:
                        action = a
                        break
                versioned_page.text = req.args.get('text')
                valid = self._validate(req, versioned_page)
                if action == 'edit' and not has_collision and valid:
                    return self._do_save(req, versioned_page)
                else:
                    return self._render_editor(req, page, action,
                                               has_collision)
            elif action == 'delete':
                self._do_delete(req, versioned_page)
            elif action == 'rename':
                return self._do_rename(req, page)
            elif action == 'diff':
                style, options, diff_data = get_diff_options(req)
                contextall = diff_data['options']['contextall']
                req.redirect(req.href.wiki(versioned_page.name, action='diff',
                                           old_version=old_version,
                                           version=version,
                                           contextall=contextall or None))
            else:
                raise HTTPBadRequest(_("Invalid request arguments."))
        elif action == 'delete':
            return self._render_confirm_delete(req, page)
        elif action == 'rename':
            return self._render_confirm_rename(req, page)
        elif action == 'edit':
            return self._render_editor(req, page)
        elif action == 'diff':
            return self._render_diff(req, versioned_page)
        elif action == 'history':
            return self._render_history(req, versioned_page)
        else:
            format = req.args.get('format')
            if format:
                Mimeview(self.env).send_converted(req, 'text/x-trac-wiki',
                                                  versioned_page.text,
                                                  format, versioned_page.name)
            return self._render_view(req, versioned_page)

    # ITemplateProvider methods

    def get_htdocs_dirs(self):
        return []

    def get_templates_dirs(self):
        return [pkg_resources.resource_filename('trac.wiki', 'templates')]

    # Internal methods

    def _validate(self, req, page):
        valid = True

        # Validate page size
        if len(req.args.get('text', '')) > self.max_size:
            add_warning(req, _("The wiki page is too long (must be less "
                               "than %(num)s characters)",
                               num=self.max_size))
            valid = False

        # Give the manipulators a pass at post-processing the page
        for manipulator in self.page_manipulators:
            for field, message in manipulator.validate_wiki_page(req, page):
                valid = False
                if field:
                    add_warning(req, tag_("The Wiki page field '%(field)s'"
                                          " is invalid: %(message)s",
                                          field=field, message=message))
                else:
                    add_warning(req, tag_("Invalid Wiki page: %(message)s",
                                          message=message))
        return valid

    def _page_data(self, req, page, action=''):
        title = get_resource_summary(self.env, page.resource)
        if action:
            title += ' (%s)' % action
        return {'page': page, 'action': action, 'title': title}

    def _prepare_diff(self, req, page, old_text, new_text,
                      old_version, new_version):
        diff_style, diff_options, diff_data = get_diff_options(req)
        diff_context = 3
        for option in diff_options:
            if option.startswith('-U'):
                diff_context = int(option[2:])
                break
        if diff_context < 0:
            diff_context = None
        diffs = diff_blocks(old_text, new_text, context=diff_context,
                            ignore_blank_lines='-B' in diff_options,
                            ignore_case='-i' in diff_options,
                            ignore_space_changes='-b' in diff_options)
        def version_info(v, last=0):
            return {'path': get_resource_name(self.env, page.resource),
                    # TRANSLATOR: wiki page
                    'rev': v or _("currently edited"),
                    'shortrev': v or last + 1,
                    'href': req.href.wiki(page.name, version=v)
                            if v else None}
        changes = [{'diffs': diffs, 'props': [],
                    'new': version_info(new_version, old_version),
                    'old': version_info(old_version)}]

        add_stylesheet(req, 'common/css/diff.css')
        add_script(req, 'common/js/diff.js')
        return diff_data, changes

    def _do_delete(self, req, page):
        if page.readonly:
            req.perm(page.resource).require('WIKI_ADMIN')
        else:
            req.perm(page.resource).require('WIKI_DELETE')

        if 'cancel' in req.args:
            req.redirect(get_resource_url(self.env, page.resource, req.href))

        version = int(req.args.get('version', 0)) or None
        old_version = int(req.args.get('old_version', 0)) or version

        with self.env.db_transaction as db:
            if version and old_version and version > old_version:
                # delete from `old_version` exclusive to `version` inclusive:
                for v in range(old_version, version):
                    page.delete(v + 1, db)
            else:
                # only delete that `version`, or the whole page if `None`
                page.delete(version, db)

        if not page.exists:
            add_notice(req, _("The page %(name)s has been deleted.",
                              name=page.name))
            req.redirect(req.href.wiki())
        else:
            if version and old_version and version > old_version + 1:
                add_notice(req, _("The versions %(from_)d to %(to)d of the "
                                  "page %(name)s have been deleted.",
                           from_=old_version + 1, to=version, name=page.name))
            else:
                add_notice(req, _("The version %(version)d of the page "
                                  "%(name)s has been deleted.",
                                  version=version, name=page.name))
            req.redirect(req.href.wiki(page.name))

    def _do_rename(self, req, page):
        if page.readonly:
            req.perm(page.resource).require('WIKI_ADMIN')
        else:
            req.perm(page.resource).require('WIKI_RENAME')

        if 'cancel' in req.args:
            req.redirect(get_resource_url(self.env, page.resource, req.href))

        old_name, old_version = page.name, page.version
        new_name = req.args.get('new_name', '')
        new_name = re.sub(r'/{2,}', '/', new_name.strip('/'))
        redirect = req.args.get('redirect')

        # verify input parameters
        warn = None
        if not new_name:
            warn = _("A new name is mandatory for a rename.")
        elif not validate_page_name(new_name):
            warn = _("The new name is invalid (a name which is separated "
                     "with slashes cannot be '.' or '..').")
        elif new_name == old_name:
            warn = _("The new name must be different from the old name.")
        elif WikiPage(self.env, new_name).exists:
            warn = _("The page %(name)s already exists.", name=new_name)
        if warn:
            add_warning(req, warn)
            return self._render_confirm_rename(req, page, new_name)

        with self.env.db_transaction as db:
            page.rename(new_name)
            if redirect:
                redirection = WikiPage(self.env, old_name, db=db)
                redirection.text = _('See [wiki:"%(name)s"].', name=new_name)
                author = get_reporter_id(req)
                comment = u'[wiki:"%s@%d" %s] \u2192 [wiki:"%s"].' % (
                          new_name, old_version, old_name, new_name)
                redirection.save(author, comment, req.remote_addr)

        add_notice(req, _("The page %(old_name)s has been renamed to "
                          "%(new_name)s.", old_name=old_name,
                          new_name=new_name))
        if redirect:
            add_notice(req, _("The page %(old_name)s has been recreated "
                              "with a redirect to %(new_name)s.",
                              old_name=old_name, new_name=new_name))

        req.redirect(req.href.wiki(old_name if redirect else new_name))

    def _do_save(self, req, page):
        if page.readonly:
            req.perm(page.resource).require('WIKI_ADMIN')
        elif not page.exists:
            req.perm(page.resource).require('WIKI_CREATE')
        else:
            req.perm(page.resource).require('WIKI_MODIFY')

        if 'WIKI_ADMIN' in req.perm(page.resource):
            # Modify the read-only flag if it has been changed and the user is
            # WIKI_ADMIN
            page.readonly = int('readonly' in req.args)

        try:
            page.save(get_reporter_id(req, 'author'), req.args.get('comment'),
                      req.remote_addr)
            add_notice(req, _("Your changes have been saved in version "
                              "%(version)s.", version=page.version))
            req.redirect(get_resource_url(self.env, page.resource, req.href,
                                          version=None))
        except TracError:
            add_warning(req, _("Page not modified, showing latest version."))
            return self._render_view(req, page)

    def _render_confirm_delete(self, req, page):
        if page.readonly:
            req.perm(page.resource).require('WIKI_ADMIN')
        else:
            req.perm(page.resource).require('WIKI_DELETE')

        version = None
        if 'delete_version' in req.args:
            version = int(req.args.get('version', 0))
        old_version = as_int(req.args.get('old_version'), version)

        what = 'multiple' if version and old_version \
                             and version - old_version > 1 \
               else 'single' if version else 'page'

        num_versions = 0
        new_date = None
        old_date = None
        for v, t, author, comment, ipnr in page.get_history():
            if (v <= version or what == 'page') and new_date is None:
                new_date = t
            if (v <= old_version and what == 'multiple' or
                num_versions > 1 and what == 'single'):
                break
            num_versions += 1
            old_date = t

        data = self._page_data(req, page, 'delete')
        data.update({'what': what, 'new_version': None, 'old_version': None,
                     'num_versions': num_versions, 'new_date': new_date,
                     'old_date': old_date})
        if version is not None:
            data.update({'new_version': version, 'old_version': old_version})
        self._wiki_ctxtnav(req, page)
        return 'wiki_delete.html', data, None

    def _render_confirm_rename(self, req, page, new_name=None):
        if page.readonly:
            req.perm(page.resource).require('WIKI_ADMIN')
        else:
            req.perm(page.resource).require('WIKI_RENAME')

        data = self._page_data(req, page, 'rename')
        data['new_name'] = new_name if new_name is not None else page.name
        self._wiki_ctxtnav(req, page)
        return 'wiki_rename.html', data, None

    def _render_diff(self, req, page):
        if not page.exists:
            raise TracError(_("Version %(num)s of page \"%(name)s\" does not "
                              "exist",
                              num=req.args.get('version'), name=page.name))

        old_version = req.args.get('old_version')
        if old_version:
            old_version = int(old_version)
            if old_version == page.version:
                old_version = None
            elif old_version > page.version:
                # FIXME: what about reverse diffs?
                old_version = page.resource.version
                page = WikiPage(self.env, page.name, version=old_version)
                req.perm(page.resource).require('WIKI_VIEW')
        latest_page = WikiPage(self.env, page.name, version=None)
        req.perm(latest_page.resource).require('WIKI_VIEW')
        new_version = int(page.version)

        date = author = comment = ipnr = None
        num_changes = 0
        prev_version = next_version = None
        for version, t, a, c, i in latest_page.get_history():
            if version == new_version:
                date = t
                author = a or 'anonymous'
                comment = c or '--'
                ipnr = i or ''
            else:
                if version < new_version:
                    num_changes += 1
                    if not prev_version:
                        prev_version = version
                    if old_version is None or version == old_version:
                        old_version = version
                        break
                else:
                    next_version = version
        if not old_version:
            old_version = 0
        old_page = WikiPage(self.env, page.name, old_version)
        req.perm(old_page.resource).require('WIKI_VIEW')

        # -- text diffs
        old_text = old_page.text.splitlines()
        new_text = page.text.splitlines()
        diff_data, changes = self._prepare_diff(req, page, old_text, new_text,
                                                old_version, new_version)

        # -- prev/up/next links
        if prev_version:
            add_link(req, 'prev', req.href.wiki(page.name, action='diff',
                                                version=prev_version),
                     _("Version %(num)s", num=prev_version))
        add_link(req, 'up', req.href.wiki(page.name, action='history'),
                 _('Page history'))
        if next_version:
            add_link(req, 'next', req.href.wiki(page.name, action='diff',
                                                version=next_version),
                     _("Version %(num)s", num=next_version))

        data = self._page_data(req, page, 'diff')
        data.update({
            'change': {'date': date, 'author': author, 'ipnr': ipnr,
                       'comment': comment},
            'new_version': new_version, 'old_version': old_version,
            'latest_version': latest_page.version,
            'num_changes': num_changes,
            'longcol': 'Version', 'shortcol': 'v',
            'changes': changes,
            'diff': diff_data,
        })
        prevnext_nav(req, _("Previous Change"), _("Next Change"),
                     _("Wiki History"))
        return 'wiki_diff.html', data, None

    def _render_editor(self, req, page, action='edit', has_collision=False):
        if has_collision:
            if action == 'merge':
                page = WikiPage(self.env, page.name, version=None)
                req.perm(page.resource).require('WIKI_VIEW')
            else:
                action = 'collision'

        if page.readonly:
            req.perm(page.resource).require('WIKI_ADMIN')
        elif not page.exists:
            req.perm(page.resource).require('WIKI_CREATE')
        else:
            req.perm(page.resource).require('WIKI_MODIFY')
        original_text = page.text
        comment = req.args.get('comment', '')
        if 'text' in req.args:
            page.text = req.args.get('text')
        elif 'template' in req.args:
            template = self.PAGE_TEMPLATES_PREFIX + req.args.get('template')
            template_page = WikiPage(self.env, template)
            if template_page and template_page.exists and \
                    'WIKI_VIEW' in req.perm(template_page.resource):
                page.text = template_page.text
        elif 'version' in req.args:
            old_page = WikiPage(self.env, page.name,
                                version=int(req.args['version']))
            req.perm(page.resource).require('WIKI_VIEW')
            page.text = old_page.text
            comment = _("Reverted to version %(version)s.",
                        version=req.args['version'])
        if action in ('preview', 'diff'):
            page.readonly = 'readonly' in req.args

        author = get_reporter_id(req, 'author')
        defaults = {'editrows': '20'}
        prefs = dict((key, req.session.get('wiki_%s' % key, defaults.get(key)))
                     for key in ('editrows', 'sidebyside'))

        if 'from_editor' in req.args:
            sidebyside = req.args.get('sidebyside') or None
            if sidebyside != prefs['sidebyside']:
                req.session.set('wiki_sidebyside', int(bool(sidebyside)), 0)
        else:
            sidebyside = prefs['sidebyside']

        if sidebyside:
            editrows = max(int(prefs['editrows']),
                           len(page.text.splitlines()) + 1)
        else:
            editrows = req.args.get('editrows')
            if editrows:
                if editrows != prefs['editrows']:
                    req.session.set('wiki_editrows', editrows,
                                    defaults['editrows'])
            else:
                editrows = prefs['editrows']

        data = self._page_data(req, page, action)
        context = web_context(req, page.resource)
        data.update({
            'context': context,
            'author': author,
            'comment': comment,
            'edit_rows': editrows,
            'sidebyside': sidebyside,
            'scroll_bar_pos': req.args.get('scroll_bar_pos', ''),
            'diff': None,
            'attachments': AttachmentModule(self.env).attachment_data(context),
        })
        if action in ('diff', 'merge'):
            old_text = original_text.splitlines() if original_text else []
            new_text = page.text.splitlines() if page.text else []
            diff_data, changes = self._prepare_diff(
                req, page, old_text, new_text, page.version, '')
            data.update({'diff': diff_data, 'changes': changes,
                         'action': 'preview', 'merge': action == 'merge',
                         'longcol': 'Version', 'shortcol': 'v'})
        elif sidebyside and action != 'collision':
            data['action'] = 'preview'

        self._wiki_ctxtnav(req, page)
        Chrome(self.env).add_wiki_toolbars(req)
        Chrome(self.env).add_auto_preview(req)
        add_script(req, 'common/js/folding.js')
        return 'wiki_edit.html', data, None

    def _render_history(self, req, page):
        """Extract the complete history for a given page.

        This information is used to present a changelog/history for a given
        page.
        """
        if not page.exists:
            raise TracError(_("Page %(name)s does not exist", name=page.name))

        data = self._page_data(req, page, 'history')

        history = []
        for version, date, author, comment, ipnr in page.get_history():
            history.append({
                'version': version,
                'date': date,
                'author': author,
                'comment': comment,
                'ipnr': ipnr
            })
        data.update({'history': history, 'resource': page.resource})
        add_ctxtnav(req, _("Back to %(wikipage)s", wikipage=page.name),
                    req.href.wiki(page.name))
        return 'history_view.html', data, None

    def _render_view(self, req, page):
        version = page.resource.version

        # Add registered converters
        if page.exists:
            for conversion in Mimeview(self.env) \
                              .get_supported_conversions('text/x-trac-wiki'):
                conversion_href = req.href.wiki(page.name, version=version,
                                                format=conversion[0])
                add_link(req, 'alternate', conversion_href, conversion[1],
                         conversion[3])

        data = self._page_data(req, page)
        if page.name == 'WikiStart':
            data['title'] = ''

        ws = WikiSystem(self.env)
        context = web_context(req, page.resource)
        higher, related = [], []
        if not page.exists:
            if 'WIKI_CREATE' not in req.perm(page.resource):
                raise ResourceNotFound(_("Page %(name)s not found",
                                         name=page.name))
            formatter = OneLinerFormatter(self.env, context)
            if '/' in page.name:
                parts = page.name.split('/')
                for i in range(len(parts) - 2, -1, -1):
                    name = '/'.join(parts[:i] + [parts[-1]])
                    if not ws.has_page(name):
                        higher.append(ws._format_link(formatter, 'wiki',
                                                      '/' + name, name, False))
            else:
                name = page.name
            name = name.lower()
            related = [each for each in ws.pages
                       if name in each.lower()
                          and 'WIKI_VIEW' in req.perm('wiki', each)]
            related.sort()
            related = [ws._format_link(formatter, 'wiki', '/' + each, each,
                                       False)
                       for each in related]

        latest_page = WikiPage(self.env, page.name, version=None)

        prev_version = next_version = None
        if version:
            try:
                version = int(version)
                for hist in latest_page.get_history():
                    v = hist[0]
                    if v != version:
                        if v < version:
                            if not prev_version:
                                prev_version = v
                                break
                        else:
                            next_version = v
            except ValueError:
                version = None

        prefix = self.PAGE_TEMPLATES_PREFIX
        templates = [template[len(prefix):]
                     for template in ws.get_pages(prefix)
                     if 'WIKI_VIEW' in req.perm('wiki', template)]

        # -- prev/up/next links
        if prev_version:
            add_link(req, 'prev',
                     req.href.wiki(page.name, version=prev_version),
                     _("Version %(num)s", num=prev_version))

        parent = None
        if version:
            add_link(req, 'up', req.href.wiki(page.name, version=None),
                     _("View latest version"))
        elif '/' in page.name:
            parent = page.name[:page.name.rindex('/')]
            add_link(req, 'up', req.href.wiki(parent, version=None),
                     _("View parent page"))

        if next_version:
            add_link(req, 'next',
                     req.href.wiki(page.name, version=next_version),
                     _('Version %(num)s', num=next_version))

        # Add ctxtnav entries
        if version:
            prevnext_nav(req, _("Previous Version"), _("Next Version"),
                         _("View Latest Version"))
        else:
            if parent:
                add_ctxtnav(req, _('Up'), req.href.wiki(parent))
            self._wiki_ctxtnav(req, page)

        # Plugin content validation
        fields = {'text': page.text}
        for manipulator in self.page_manipulators:
            manipulator.prepare_wiki_page(req, page, fields)
        text = fields.get('text', '')

        data.update({
            'context': context,
            'text': text,
            'latest_version': latest_page.version,
            'attachments': AttachmentModule(self.env).attachment_data(context),
            'default_template': self.DEFAULT_PAGE_TEMPLATE,
            'templates': templates,
            'version': version,
            'higher': higher, 'related': related,
            'resourcepath_template': 'wiki_page_path.html',
        })
        add_script(req, 'common/js/folding.js')
        return 'wiki_view.html', data, None

    def _wiki_ctxtnav(self, req, page):
        """Add the normal wiki ctxtnav entries."""
        add_ctxtnav(req, _("Start Page"), req.href.wiki('WikiStart'))
        add_ctxtnav(req, _("Index"), req.href.wiki('TitleIndex'))
        if page.exists:
            add_ctxtnav(req, _("History"), req.href.wiki(page.name,
                                                         action='history'))

    # ITimelineEventProvider methods

    def get_timeline_filters(self, req):
        if 'WIKI_VIEW' in req.perm:
            yield ('wiki', _('Wiki changes'))

    def get_timeline_events(self, req, start, stop, filters):
        if 'wiki' in filters:
            wiki_realm = Resource('wiki')
            for ts, name, comment, author, version in self.env.db_query("""
                    SELECT time, name, comment, author, version FROM wiki
                    WHERE time>=%s AND time<=%s
                    """, (to_utimestamp(start), to_utimestamp(stop))):
                wiki_page = wiki_realm(id=name, version=version)
                if 'WIKI_VIEW' not in req.perm(wiki_page):
                    continue
                yield ('wiki', from_utimestamp(ts), author,
                       (wiki_page, comment))

            # Attachments
            for event in AttachmentModule(self.env).get_timeline_events(
                    req, wiki_realm, start, stop):
                yield event

    def render_timeline_event(self, context, field, event):
        wiki_page, comment = event[3]
        if field == 'url':
            return context.href.wiki(wiki_page.id, version=wiki_page.version)
        elif field == 'title':
            name = tag.em(get_resource_name(self.env, wiki_page))
            if wiki_page.version > 1:
                return tag_("%(page)s edited", page=name)
            else:
                return tag_("%(page)s created", page=name)
        elif field == 'description':
            markup = format_to(self.env, None,
                               context.child(resource=wiki_page), comment)
            if wiki_page.version > 1:
                diff_href = context.href.wiki(
                    wiki_page.id, version=wiki_page.version, action='diff')
                markup = tag(markup,
                             " (", tag.a(_("diff"), href=diff_href), ")")
            return markup

    # ISearchSource methods

    def get_search_filters(self, req):
        if 'WIKI_VIEW' in req.perm:
            yield ('wiki', _('Wiki'))

    def get_search_results(self, req, terms, filters):
        if not 'wiki' in filters:
            return
        with self.env.db_query as db:
            sql_query, args = search_to_sql(db, ['w1.name', 'w1.author',
                                                 'w1.text'], terms)
            wiki_realm = Resource('wiki')
            for name, ts, author, text in db("""
                    SELECT w1.name, w1.time, w1.author, w1.text
                    FROM wiki w1,(SELECT name, max(version) AS ver
                                  FROM wiki GROUP BY name) w2
                    WHERE w1.version = w2.ver AND w1.name = w2.name
                    AND """ + sql_query, args):
                page = wiki_realm(id=name)
                if 'WIKI_VIEW' in req.perm(page):
                    yield (get_resource_url(self.env, page, req.href),
                           '%s: %s' % (name, shorten_line(text)),
                           from_utimestamp(ts), author,
                           shorten_result(text, terms))

        # Attachments
        for result in AttachmentModule(self.env).get_search_results(
                req, wiki_realm, terms):
            yield result
