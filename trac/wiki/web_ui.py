# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2006 Edgewall Software
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

from datetime import datetime
import os
import pkg_resources
import re
import StringIO

from genshi.builder import tag

from trac.attachment import AttachmentModule
from trac.context import Context, ResourceSystem, ResourceNotFound
from trac.core import *
from trac.mimeview.api import Mimeview, IContentConverter
from trac.perm import IPermissionRequestor
from trac.search import ISearchSource, search_to_sql, shorten_result
from trac.timeline.api import ITimelineEventProvider, TimelineEvent
from trac.util import get_reporter_id
from trac.util.datefmt import to_timestamp, utc
from trac.util.text import shorten_line
from trac.versioncontrol.diff import get_diff_options, diff_blocks
from trac.web.chrome import add_link, add_script, add_stylesheet, \
                            INavigationContributor, ITemplateProvider
from trac.web import IRequestHandler
from trac.wiki.api import IWikiPageManipulator, WikiSystem
from trac.wiki.model import WikiPage


class InvalidWikiPage(TracError):
    """Exception raised when a Wiki page fails validation."""


class WikiModule(Component):

    implements(IContentConverter, INavigationContributor, IPermissionRequestor,
               IRequestHandler, ITimelineEventProvider, ISearchSource,
               ITemplateProvider)

    page_manipulators = ExtensionPoint(IWikiPageManipulator)

    PAGE_TEMPLATES_PREFIX = 'PageTemplates/'
    DEFAULT_PAGE_TEMPLATE = 'DefaultPage'

    # IContentConverter methods
    def get_supported_conversions(self):
        yield ('txt', 'Plain Text', 'txt', 'text/x-trac-wiki', 'text/plain', 9)

    def convert_content(self, req, mimetype, content, key):
        # Tell the browser that the content should be downloaded and
        # not rendered. The x=y part is needed to keep Safari from being 
        # confused by the multiple content-disposition headers.
        req.send_header('Content-Disposition', 'attachment; x=y')

        return (content, 'text/plain;charset=utf-8')

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'wiki'

    def get_navigation_items(self, req):
        if 'WIKI_VIEW' in req.perm('wiki'):
            yield ('mainnav', 'wiki',
                   tag.a('Wiki', href=req.href.wiki(), accesskey=1))
            yield ('metanav', 'help',
                   tag.a('Help/Guide', href=req.href.wiki('TracGuide'),
                         accesskey=6))

    # IPermissionRequestor methods

    def get_permission_actions(self):
        actions = ['WIKI_CREATE', 'WIKI_DELETE', 'WIKI_MODIFY', 'WIKI_VIEW']
        return actions + [('WIKI_ADMIN', actions)]

    # IRequestHandler methods

    def match_request(self, req):
        match = re.match(r'^/wiki(?:/(.*)|$)', req.path_info)
        if 'WIKI_VIEW' in req.perm('wiki') and match:
            if match.group(1):
                req.args['page'] = match.group(1)
            return 1

    def process_request(self, req):
        action = req.args.get('action', 'view')
        pagename = req.args.get('page', 'WikiStart')
        version = req.args.get('version')

        if pagename.endswith('/'):
            req.redirect(req.href.wiki(pagename.strip('/')))

        db = self.env.get_db_cnx()
        page = WikiPage(self.env, pagename, version, db)
        latest_page = WikiPage(self.env, pagename, None, db)

        if version and page.version == 0 and latest_page.version != 0:
            raise TracError('No version "%s" for Wiki page "%s"' %
                            (version, pagename))

        context = Context(self.env, req)('wiki', pagename, version=version,
                                         resource=page)

        add_stylesheet(req, 'common/css/wiki.css')

        if req.method == 'POST':
            if action == 'edit':
                if 'cancel' in req.args:
                    req.redirect(req.href.wiki(page.name))
                elif int(version) != latest_page.version:
                    return self._render_editor(context, 'collision')
                elif 'preview' in req.args:
                    return self._render_editor(context, 'preview')
                elif 'diff' in req.args:
                    return self._render_editor(context, 'diff')
                else:
                    self._do_save(context)
            elif action == 'delete':
                self._do_delete(context)
            elif action == 'diff':
                get_diff_options(req)
                req.redirect(req.href.wiki(
                    page.name, version=page.version,
                    old_version=req.args.get('old_version'), action='diff'))
        elif action == 'delete':
            return self._render_confirm(context)
        elif action == 'edit':
            return self._render_editor(context)
        elif action == 'diff':
            return self._render_diff(context)
        elif action == 'history':
            return self._render_history(context)
        else:
            req.perm.require('WIKI_VIEW', context)
            format = req.args.get('format')
            if format:
                Mimeview(self.env).send_converted(req, 'text/x-trac-wiki',
                                                  page.text, format, page.name)
            return self._render_view(context)

    # ITemplateProvider methods

    def get_htdocs_dirs(self):
        return []

    def get_templates_dirs(self):
        return [pkg_resources.resource_filename('trac.wiki', 'templates')]

    # Internal methods

    def _page_data(self, context, action=''):
        page_name = context.name()
        title = context.summary()
        if action:
            title += ' (%s)' % action
        return {'page': context.resource,
                'context': context,
                'action': action,
                'page_name': page_name,
                'title': title}

    def _prepare_diff(self, context, old_text, new_text,
                      old_version, new_version):
        req, page = context.req, context.resource
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
        def version_info(v):
            return {'path': context.name(), 'rev': v, 'shortrev': v,
                    'href': v and context.resource_href(version=v) or None}
        changes = [{'diffs': diffs, 'props': [],
                    'new': version_info(new_version),
                    'old': version_info(old_version)}]

        add_stylesheet(req, 'common/css/diff.css')
        add_script(req, 'common/js/diff.js')
        return diff_data, changes

    def _do_delete(self, context):
        page = context.resource
        req = context.req
        db = context.db

        if page.readonly:
            req.perm.require('WIKI_ADMIN', context)
        else:
            req.perm.require('WIKI_DELETE', context)

        if 'cancel' in req.args:
            req.redirect(req.href.wiki(page.name))

        version = int(req.args.get('version', 0)) or None
        old_version = int(req.args.get('old_version', 0)) or version

        if version and old_version and version > old_version:
            # delete from `old_version` exclusive to `version` inclusive:
            for v in range(old_version, version):
                page.delete(v + 1, db)
        else:
            # only delete that `version`, or the whole page if `None`
            page.delete(version, db)
        db.commit()

        if not page.exists:
            req.redirect(req.href.wiki())
        else:
            req.redirect(req.href.wiki(page.name))

    def _do_save(self, context):
        page = context.resource
        req = context.req
        db = context.db
        context_perm = req.perm(context)

        if page.readonly:
            context_perm.require('WIKI_ADMIN')
        elif not page.exists:
            context_perm.require('WIKI_CREATE')
        else:
            context_perm.require('WIKI_MODIFY')

        page.text = req.args.get('text')
        if 'WIKI_ADMIN' in context_perm:
            # Modify the read-only flag if it has been changed and the user is
            # WIKI_ADMIN
            page.readonly = int('readonly' in req.args)

        # Give the manipulators a pass at post-processing the page
        for manipulator in self.page_manipulators:
            for field, message in manipulator.validate_wiki_page(req, page):
                if field:
                    raise InvalidWikiPage("The Wiki page field %s is invalid: %s"
                                          % (field, message))
                else:
                    raise InvalidWikiPage("Invalid Wiki page: %s" % message)

        try:
            page.save(get_reporter_id(req, 'author'), req.args.get('comment'),
                      req.remote_addr)
            not_modified = False
        except TracError:
            not_modified = True
        req.redirect(context.resource_href(version=not_modified and \
                                           page.version or None))

    def _render_confirm(self, context):
        page = context.resource
        req = context.req
        db = context.db

        if page.readonly:
            req.perm.require('WIKI_ADMIN', context)
        else:
            req.perm.require('WIKI_DELETE', context)

        version = None
        if 'delete_version' in req.args:
            version = int(req.args.get('version', 0))
        old_version = int(req.args.get('old_version') or 0) or version

        data = self._page_data(context, 'delete')
        data.update({'new_version': None, 'old_version': None,
                     'num_versions': 0})
        if version is not None:
            num_versions = 0
            for v,t,author,comment,ipnr in page.get_history():
                num_versions += 1;
                if num_versions > 1:
                    break
            data.update({'new_version': version, 'old_version': old_version,
                         'num_versions': num_versions})
        return 'wiki_delete.html', data, None

    def _render_diff(self, context):
        page = context.resource
        req = context.req
        db = context.db

        req.perm.require('WIKI_VIEW', context)

        data = self._page_data(context, 'diff')

        if not page.exists:
            raise TracError("Version %s of page %s does not exist" %
                            (req.args.get('version'), page.name))

        old_version = req.args.get('old_version')
        if old_version:
            old_version = int(old_version)
            if old_version == page.version:
                old_version = None
            elif old_version > page.version: # FIXME: what about reverse diffs?
                req.perm.require('WIKI_VIEW', context(version=old_version))
                old_version, page = page.version, \
                                    WikiPage(self.env, page.name, old_version)
        latest_page = WikiPage(self.env, page.name)
        new_version = int(page.version)

        date = author = comment = ipnr = None
        num_changes = 0
        old_page = None
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
                    if (old_version and version == old_version) or \
                            not old_version:
                        old_version = version
                        req.perm.require('WIKI_VIEW', context(version=old_version))
                        old_page = WikiPage(self.env, page.name, old_version)
                        break
                else:
                    next_version = version
        if not old_version:
            old_version = 0

        # -- text diffs
        old_text = old_page and old_page.text.splitlines() or []
        new_text = page.text.splitlines()
        diff_data, changes = self._prepare_diff(context, old_text, new_text,
                                                old_version, new_version)

        # -- prev/up/next links
        if prev_version:
            add_link(req, 'prev', req.href.wiki(page.name, action='diff',
                                                version=prev_version),
                     'Version %d' % prev_version)
        add_link(req, 'up', req.href.wiki(page.name, action='history'),
                 'Page history')
        if next_version:
            add_link(req, 'next', req.href.wiki(page.name, action='diff',
                                                version=next_version),
                     'Version %d' % next_version)

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
        return 'wiki_diff.html', data, None

    def _render_editor(self, context, action='edit'):
        page, req = context.resource, context.req
        context.version = None # use implicit ''latest'' in links

        if page.readonly:
            req.perm.require('WIKI_ADMIN', context)
        else:
            req.perm.require('WIKI_MODIFY', context)
        original_text = page.text
        if 'text' in req.args:
            page.text = req.args.get('text')
        elif 'template' in req.args:
            template = self.PAGE_TEMPLATES_PREFIX + req.args.get('template')
            if 'WIKI_VIEW' in req.perm(context(id=template)):
                template_page = WikiPage(self.env, template)
                if template_page.exists:
                    page.text = template_page.text
        if action == 'preview':
            page.readonly = 'readonly' in req.args

        author = get_reporter_id(req, 'author')
        comment = req.args.get('comment', '')
        editrows = req.args.get('editrows')
        
        if editrows:
            pref = req.session.get('wiki_editrows', '20')
            if editrows != pref:
                req.session['wiki_editrows'] = editrows
        else:
            editrows = req.session.get('wiki_editrows', '20')

        data = self._page_data(context, action)
        data.update({
            'author': author,
            'comment': comment,
            'edit_rows': editrows,
            'scroll_bar_pos': req.args.get('scroll_bar_pos', ''),
            'diff': None,
        })
        if action == 'diff':
            old_text = original_text and original_text.splitlines() or []
            new_text = page.text and page.text.splitlines() or []
            diff_data, changes = self._prepare_diff(
                context, old_text, new_text, page.version, '')
            data.update({'diff': diff_data, 'changes': changes,
                         'action': 'preview',
                         'longcol': 'Version', 'shortcol': 'v'})

        return 'wiki_edit.html', data, None

    def _render_history(self, context):
        """Extract the complete history for a given page.

        This information is used to present a changelog/history for a given
        page.
        """
        page = context.resource
        req = context.req
        db = context.db

        req.perm.require('WIKI_VIEW', context)

        if not page.exists:
            raise TracError, "Page %s does not exist" % page.name

        data = self._page_data(context, 'history')

        history = []
        for version, date, author, comment, ipnr in page.get_history():
            history.append({
                'version': version,
                'date': date,
                'author': author,
                'comment': comment,
                'ipnr': ipnr
            })
        data['history'] = history
        return 'history_view.html', data, None

    def _render_view(self, context):
        page = context.resource
        req = context.req

        version = req.args.get('version')

        # Add registered converters
        for conversion in Mimeview(self.env).get_supported_conversions(
                                             'text/x-trac-wiki'):
            conversion_href = req.href.wiki(page.name, version=version,
                                            format=conversion[0])
            add_link(req, 'alternate', conversion_href, conversion[1],
                     conversion[3])

        data = self._page_data(context)
        if page.name == 'WikiStart':
            data['title'] = ''

        if not page.exists:
            if 'WIKI_CREATE' not in req.perm(context):
                raise ResourceNotFound('Page %s not found' % page.name)

        latest_page = WikiPage(self.env, page.name)

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
        templates = [t[len(prefix):] for t in
                     WikiSystem(self.env).get_pages(prefix) if 'WIKI_VIEW'
                     in req.perm(context(id=t))]

        # -- prev/up/next links
        if prev_version:
            add_link(req, 'prev', req.href.wiki(page.name,
                                                version=prev_version),
                     'Version %d' % prev_version)
        add_link(req, 'up', req.href.wiki(page.name),
                 'View Latest Version')
        if next_version:
            add_link(req, 'next', req.href.wiki(page.name,
                                                version=next_version),
                     'Version %d' % next_version)

        data.update({
            'latest_version': latest_page.version,
            'attachments': AttachmentModule(self.env).attachment_list(context),
            'default_template': self.DEFAULT_PAGE_TEMPLATE,
            'templates': templates,
            'version': version
        })
        return 'wiki_view.html', data, None

    # ITimelineEventProvider methods

    def get_timeline_filters(self, req):
        if 'WIKI_VIEW' in req.perm:
            yield ('wiki', 'Wiki changes')

    def get_timeline_events(self, req, start, stop, filters):
        if 'wiki' in filters:
            start, stop = to_timestamp(start), to_timestamp(stop)
            context = Context(self.env, req)
            cursor = context.db.cursor()
            cursor.execute("SELECT time,name,comment,author,ipnr,version "
                           "FROM wiki WHERE time>=%s AND time<=%s",
                           (start, stop))
            for ts,name,comment,author,ipnr,version in cursor:
                if 'WIKI_VIEW' not in req.perm('wiki', name):
                    continue
                ctx = context('wiki', name, version=version)
                title = tag(tag.em(ctx.name()),
                            version > 1 and ' edited' or ' created')
                markup = None
                if version > 1:
                    markup = tag.a('(diff)',
                                   href=ctx.resource_href(action='diff'))
                t = datetime.fromtimestamp(ts, utc)
                event = TimelineEvent(self, 'wiki')
                event.set_changeinfo(t, author, ipnr=ipnr)
                event.add_markup(title=title, markup=markup)
                event.add_wiki(ctx, body=comment)
                yield event

            # Attachments
            for event in AttachmentModule(self.env) \
                    .get_timeline_events(context('wiki'), start, stop):
                yield event

    def event_formatter(self, event, key):
        return None

    # ISearchSource methods

    def get_search_filters(self, req):
        if 'WIKI_VIEW' in req.perm:
            yield ('wiki', 'Wiki')

    def get_search_results(self, req, terms, filters):
        if not 'wiki' in filters:
            return
        db = self.env.get_db_cnx()
        sql_query, args = search_to_sql(db, ['w1.name', 'w1.author', 'w1.text'],
                                        terms)
        cursor = db.cursor()
        cursor.execute("SELECT w1.name,w1.time,w1.author,w1.text "
                       "FROM wiki w1,"
                       "(SELECT name,max(version) AS ver "
                       "FROM wiki GROUP BY name) w2 "
                       "WHERE w1.version = w2.ver AND w1.name = w2.name "
                       "AND " + sql_query, args)

        for name, ts, author, text in cursor:
            if 'WIKI_VIEW' in req.perm('wiki', name):
                yield (req.href.wiki(name), '%s: %s' % (name, shorten_line(text)),
                       datetime.fromtimestamp(ts, utc), author,
                       shorten_result(text, terms))
