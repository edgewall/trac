# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2009 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgström <jonas@edgewall.com>
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

import csv
from datetime import datetime
import io
import pkg_resources
import re

from trac.attachment import AttachmentModule
from trac.config import BoolOption, Option
from trac.core import *
from trac.mimeview.api import Mimeview, IContentConverter
from trac.notification.api import NotificationSystem
from trac.perm import IPermissionPolicy
from trac.resource import (
    Resource, ResourceNotFound, get_resource_url, render_resource_link,
    get_resource_shortname
)
from trac.search import ISearchSource, search_to_sql, shorten_result
from trac.ticket import model
from trac.ticket.api import TicketSystem, ITicketManipulator
from trac.ticket.notification import TicketChangeEvent
from trac.ticket.roadmap import group_milestones
from trac.timeline.api import ITimelineEventProvider
from trac.util import as_bool, as_int, get_reporter_id, lazy
from trac.util.datefmt import (
    datetime_now, format_datetime, format_date_or_datetime, from_utimestamp,
    get_date_format_hint, get_datetime_format_hint, parse_date, to_utimestamp,
    user_time, utc
)
from trac.util.html import Markup, tag, to_fragment
from trac.util.text import (
    exception_to_unicode, empty, is_obfuscated, shorten_line
)
from trac.util.presentation import separated
from trac.util.translation import _, tag_, tagn_, N_, ngettext
from trac.versioncontrol.diff import get_diff_options, diff_blocks
from trac.web.api import IRequestHandler, arg_list_to_args, parse_arg_list
from trac.web.chrome import (
    Chrome, INavigationContributor, ITemplateProvider, accesskey,
    add_ctxtnav, add_link, add_notice, add_script, add_script_data,
    add_stylesheet, add_warning, auth_link, chrome_info_script, prevnext_nav,
    web_context
)
from trac.wiki.formatter import format_to, format_to_html


class InvalidTicket(TracError):
    """Exception raised when a ticket fails validation.

    :since 1.3.2: deprecated and will be removed in 1.5.1
    """
    title = N_("Invalid Ticket")


class TicketModule(Component):

    implements(IContentConverter, INavigationContributor, IRequestHandler,
               ISearchSource, ITemplateProvider, ITimelineEventProvider)

    ticket_manipulators = ExtensionPoint(ITicketManipulator)

    realm = TicketSystem.realm

    timeline_details = BoolOption('timeline', 'ticket_show_details', 'true',
        """Enable the display of all ticket changes in the timeline, not only
        open / close operations.""")

    timeline_component = BoolOption('timeline', 'ticket_show_component',
                                    'false',
        """Enable the display of component of tickets in the timeline.
        (''since 1.1.1'')""")

    timeline_newticket_formatter = Option('timeline', 'newticket_formatter',
                                          'oneliner',
        """Which formatter flavor (e.g. 'html' or 'oneliner') should be
        used when presenting the description for new tickets.
        If 'oneliner', the [timeline] abbreviated_messages option applies.
        """)

    preserve_newlines = Option('ticket', 'preserve_newlines', 'default',
        """Whether Wiki formatter should respect the new lines present
        in the Wiki text.
        If set to 'default', this is equivalent to 'yes' for new environments
        but keeps the old behavior for upgraded environments (i.e. 'no').
        """)

    ticketlink_query = Option('query', 'ticketlink_query',
        default='?status=!closed',
        doc="""The base query to be used when linkifying values of ticket
            fields. The query is a URL query
            string starting with `?` as used in `query:`
            [TracQuery#UsingTracLinks Trac links].
            """)

    ticket_path_re = re.compile(r'/ticket/([0-9]+)$')

    def __init__(self):
        self._warn_for_moved_attr = set()

    def __getattr__(self, name):
        """Delegate access to Options which were moved to TicketSystem.

        .. todo:: remove in 1.5.1
        """
        if name in ('max_comment_size', 'max_description_size',
                    'max_summary_size'):
            if name not in self._warn_for_moved_attr:
                self.log.warning("%s option should be accessed via "
                                 "TicketSystem component", name)
                self._warn_for_moved_attr.add(name)
            return getattr(TicketSystem(self.env), name)
        raise AttributeError("TicketModule has no attribute '%s'" % name)

    @lazy
    def must_preserve_newlines(self):
        preserve_newlines = self.preserve_newlines
        if preserve_newlines == 'default':
            preserve_newlines = self.env.database_initial_version >= 21 # 0.11
        return as_bool(preserve_newlines)

    # IContentConverter methods

    def get_supported_conversions(self):
        yield ('csv', _("Comma-delimited Text"), 'csv',
               'trac.ticket.Ticket', 'text/csv', 8)
        yield ('tab', _("Tab-delimited Text"), 'tsv',
               'trac.ticket.Ticket', 'text/tab-separated-values', 8)
        yield ('rss', _("RSS Feed"), 'xml',
               'trac.ticket.Ticket', 'application/rss+xml', 8)

    def convert_content(self, req, mimetype, ticket, key):
        if key == 'csv':
            return self.export_csv(req, ticket, mimetype='text/csv')
        elif key == 'tab':
            return self.export_csv(req, ticket, sep='\t',
                                   mimetype='text/tab-separated-values')
        elif key == 'rss':
            return self._export_rss(req, ticket)

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        if self.ticket_path_re.match(req.path_info):
            return 'tickets'
        return 'newticket'

    def get_navigation_items(self, req):
        if 'TICKET_CREATE' in req.perm:
            yield ('mainnav', 'newticket',
                   tag.a(_("New Ticket"), href=req.href.newticket(),
                         accesskey=accesskey(req, 7)))

    # IRequestHandler methods

    def match_request(self, req):
        match = self.ticket_path_re.match(req.path_info)
        if match:
            req.args['id'] = match.group(1)
            return True
        if req.path_info == '/newticket':
            return True

    def process_request(self, req):
        if 'id' in req.args:
            if req.path_info == '/newticket':
                raise TracError(_("id can't be set for a new ticket request."))
            return self._process_ticket_request(req)
        return self._process_newticket_request(req)

    # ITemplateProvider methods

    def get_htdocs_dirs(self):
        return []

    def get_templates_dirs(self):
        return [pkg_resources.resource_filename('trac.ticket', 'templates')]

    # ISearchSource methods

    def get_search_filters(self, req):
        if 'TICKET_VIEW' in req.perm:
            yield ('ticket', _("Tickets"))

    def get_search_results(self, req, terms, filters):
        if 'ticket' not in filters:
            return
        ticket_realm = Resource(self.realm)
        with self.env.db_query as db:
            sql, args = search_to_sql(db, ['summary', 'keywords',
                                           'description', 'reporter', 'cc',
                                           db.cast('id', 'text')], terms)
            sql2, args2 = search_to_sql(db, ['newvalue'], terms)
            sql3, args3 = search_to_sql(db, ['value'], terms)
            ticketsystem = TicketSystem(self.env)
            for summary, desc, author, type, tid, ts, status, resolution in \
                    db("""SELECT summary, description, reporter, type, id,
                                 time, status, resolution
                          FROM ticket
                          WHERE id IN (
                              SELECT id FROM ticket WHERE %s
                            UNION
                              SELECT ticket FROM ticket_change
                              WHERE field='comment' AND %s
                            UNION
                              SELECT ticket FROM ticket_custom WHERE %s
                          )
                          """ % (sql, sql2, sql3),
                          args + args2 + args3):
                t = ticket_realm(id=tid)
                if 'TICKET_VIEW' in req.perm(t):
                    yield (req.href.ticket(tid),
                           tag_("%(title)s: %(message)s",
                                title=tag.span(
                                    get_resource_shortname(self.env, t),
                                    class_=status),
                                message=ticketsystem.format_summary(
                                    summary, status, resolution, type)),
                           from_utimestamp(ts), author,
                           shorten_result(desc, terms))

        # Attachments
        for result in AttachmentModule(self.env).get_search_results(
            req, ticket_realm, terms):
            yield result

    # ITimelineEventProvider methods

    def get_timeline_filters(self, req):
        if 'TICKET_VIEW' in req.perm:
            yield ('ticket', _("Tickets opened and closed"))
            if self.timeline_details:
                yield ('ticket_details', _("Ticket updates"), True)

    def get_timeline_events(self, req, start, stop, filters):
        ts_start = to_utimestamp(start)
        ts_stop = to_utimestamp(stop)

        status_map = {'new': ('newticket', 'created'),
                      'reopened': ('reopenedticket', 'reopened'),
                      'closed': ('closedticket', 'closed'),
                      'edit': ('editedticket', 'updated')}

        ticket_realm = Resource(self.realm)

        field_labels = TicketSystem(self.env).get_ticket_field_labels()

        def produce_event(values, status, fields, comment, cid):
            id, ts, author, type, summary, description, component = values
            ticket = ticket_realm(id=id)
            if 'TICKET_VIEW' not in req.perm(ticket):
                return None
            resolution = fields.get('resolution')
            info = ''
            if status == 'edit':
                if 'ticket_details' in filters:
                    if fields:
                        labels = [tag.i(field_labels.get(k, k.capitalize()))
                                  for k in fields]
                        info = tagn_("%(labels)s changed",
                                     "%(labels)s changed", len(labels),
                                     labels=separated(labels, ', ')) + tag.br()
                else:
                    return None
            elif 'ticket' in filters:
                if status == 'closed' and resolution:
                    if resolution and comment:
                        info = _("%(title)s: %(message)s", title=resolution,
                                 message='')  # typographical translation (fr)
                    else:
                        info = resolution
            else:
                return None
            kind, verb = status_map[status]
            return (kind, from_utimestamp(ts), author,
                    (ticket, verb, info, summary, status, resolution, type,
                     description, component, comment, cid))

        def produce_ticket_change_events(db):
            data = None
            for (id, t, author, type, summary,
                 component, field, oldvalue, newvalue) in db("""
                    SELECT t.id, tc.time, tc.author, t.type, t.summary,
                           t.component, tc.field, tc.oldvalue, tc.newvalue
                    FROM ticket_change tc
                    INNER JOIN ticket t ON
                        t.id = tc.ticket AND tc.time>=%%s AND tc.time<=%%s
                    LEFT OUTER JOIN enum p ON
                        p.type='priority' AND p.name=t.priority
                    ORDER BY tc.time, COALESCE(p.value,'')='', %s, tc.ticket
                    """ % db.cast('p.value', 'int'), (ts_start, ts_stop)):
                if not (oldvalue or newvalue):
                    # ignore empty change corresponding to custom field
                    # created (None -> '') or deleted ('' -> None)
                    continue
                if not data or (id, t) != data[:2]:
                    if data:
                        ev = produce_event(data, status, fields, comment,
                                           cid)
                        if ev:
                            yield (ev, data[1])
                    status, fields, comment, cid = 'edit', {}, '', None
                    data = (id, t, author, type, summary, None, component)
                if field == 'comment':
                    comment = newvalue
                    cid = oldvalue and oldvalue.split('.')[-1]
                    # Always use the author from the comment field
                    data = data[:2] + (author,) + data[3:]
                elif field == 'status' and \
                        newvalue in ('reopened', 'closed'):
                    status = newvalue
                elif field[0] != '_':
                    # properties like _comment{n} are hidden
                    fields[field] = newvalue
            if data:
                ev = produce_event(data, status, fields, comment, cid)
                if ev:
                    yield (ev, data[1])

        # Ticket changes
        with self.env.db_query as db:
            if 'ticket' in filters or 'ticket_details' in filters:
                prev_t = None
                prev_ev = None
                batch_ev = None
                for ev, t in produce_ticket_change_events(db):
                    if batch_ev:
                        if prev_t == t:
                            ticket = ev[3][0]
                            batch_ev[3][0].append(ticket.id)
                        else:
                            yield batch_ev
                            prev_ev = ev
                            prev_t = t
                            batch_ev = None
                    elif prev_t and prev_t == t:
                        prev_ticket = prev_ev[3][0]
                        ticket = ev[3][0]
                        tickets = [prev_ticket.id, ticket.id]
                        batch_data = (tickets,) + ev[3][1:]
                        batch_ev = ('batchmodify', ev[1], ev[2], batch_data)
                    else:
                        if prev_ev:
                            yield prev_ev
                        prev_ev = ev
                        prev_t = t
                if batch_ev:
                    yield batch_ev
                elif prev_ev:
                    yield prev_ev

                # New tickets
                if 'ticket' in filters:
                    for row in db("""SELECT id, time, reporter, type, summary,
                                            description, component
                                     FROM ticket WHERE time>=%s AND time<=%s
                                     """, (ts_start, ts_stop)):
                        ev = produce_event(row, 'new', {}, None, None)
                        if ev:
                            yield ev

            # Attachments
            if 'ticket_details' in filters:
                for event in AttachmentModule(self.env).get_timeline_events(
                    req, ticket_realm, start, stop):
                    yield event

    def render_timeline_event(self, context, field, event):
        kind = event[0]
        if kind == 'batchmodify':
            return self._render_batched_timeline_event(context, field, event)
        ticket, verb, info, summary, status, resolution, type, \
                description, component, comment, cid = event[3]
        if field == 'url':
            href = context.href.ticket(ticket.id)
            if cid:
                href += '#comment:' + cid
            return href
        elif field == 'title':
            title = TicketSystem(self.env).format_summary(summary, status,
                                                          resolution, type)
            message = {
                'created': N_("Ticket %(ticketref)s (%(summary)s) created"),
                'reopened': N_("Ticket %(ticketref)s (%(summary)s) reopened"),
                'closed': N_("Ticket %(ticketref)s (%(summary)s) closed"),
                'updated': N_("Ticket %(ticketref)s (%(summary)s) updated"),
            }[verb]
            # Add component as prefix to summary if enabled and available
            component_prefix = ''
            if self.timeline_component and component:
                component_prefix = component + ' - '
            summary_complete = component_prefix + shorten_line(summary)
            return tag_(message,
                        ticketref=tag.em('#', ticket.id, title=title),
                        summary=summary_complete)
        elif field == 'description':
            descr = message = ''
            if status == 'new':
                message = description
            else:
                descr = info
                message = comment
            t_context = context.child(resource=ticket)
            t_context.set_hints(preserve_newlines=self.must_preserve_newlines)
            if status == 'new' and \
                    context.get_hint('wiki_flavor') == 'oneliner':
                flavor = self.timeline_newticket_formatter
                t_context.set_hints(wiki_flavor=flavor,
                                    shorten_lines=flavor == 'oneliner')
            return descr + format_to(self.env, None, t_context, message)

    def _render_batched_timeline_event(self, context, field, event):
        tickets, verb, info, summary, status, resolution, type, \
                description, component, comment, cid = event[3]
        if field == 'url':
            return context.href.query(id=','.join(str(t) for t in tickets))
        elif field == 'title':
            ticketids = u',\u200b'.join(str(t) for t in tickets)
            title = _("Tickets %(ticketids)s", ticketids=ticketids)
            return tag_("Tickets %(ticketlist)s batch updated",
                        ticketlist=tag.em('#', ticketids, title=title))
        elif field == 'description':
            t_context = context()
            t_context.set_hints(preserve_newlines=self.must_preserve_newlines)
            return info + format_to(self.env, None, t_context, comment)

    # Internal methods

    def _get_action_controls(self, req, ticket):
        # action_controls is an ordered list of "renders" tuples, where
        # renders is a list of (action_key, label, widgets, hints)
        # representing the user interface for each action
        action_controls = []
        sorted_actions = TicketSystem(self.env).get_available_actions(req,
                                                                      ticket)
        for action in sorted_actions:
            first_label = None
            hints = []
            widgets = []
            for controller in self._get_action_controllers(req, ticket,
                                                           action):
                label, widget, hint = controller.render_ticket_action_control(
                    req, ticket, action)
                if not first_label:
                    first_label = label
                widgets.append(widget)
                hints.append(hint)
            action_controls.append((action, first_label, tag(widgets), hints))

        # The default action is the first in the action_controls list.
        selected_action = req.args.get('action')
        if not selected_action and action_controls:
            selected_action = action_controls[0][0]

        if not action_controls:
            add_warning(req, tag_("There are no workflow actions defined for "
                                  "this ticket's status."))

        return action_controls, selected_action

    def _get_action_controllers(self, req, ticket, action):
        """Generator yielding the controllers handling the given `action`"""
        for controller in TicketSystem(self.env).action_controllers:
            actions = [a for w, a in
                       controller.get_ticket_actions(req, ticket) or []]
            if action in actions:
                yield controller

    def _process_newticket_request(self, req):
        req.perm(self.realm).require('TICKET_CREATE')
        ticket = model.Ticket(self.env)

        plain_fields = True  # support for /newticket?version=0.11 GETs
        field_reporter = 'reporter'

        if req.method == 'POST':
            plain_fields = False
            field_reporter = 'field_reporter'

        self._populate(req, ticket, plain_fields)

        reporter_id = req.args.get(field_reporter) or \
                      get_reporter_id(req, 'author')
        ticket['reporter'] = reporter_id

        preview = 'preview' in req.args
        if preview or req.method == 'POST':
            actions = TicketSystem(self.env) \
                      .get_available_actions(req, ticket)
            default_action = actions[0] if len(actions) > 0 else None
            action = req.args.get('action', default_action)
            valid = True
            # Do any action on the ticket?
            if action and action not in actions:
                valid = False
                add_warning(req, _('The action "%(name)s" is not available.',
                                   name=action))

            field_changes, problems = self.get_ticket_changes(req, ticket,
                                                              action)
            if problems:
                valid = False
                for problem in problems:
                    add_warning(req, problem)
                add_warning(req,
                            tag_("Please review your configuration, "
                                 "probably starting with %(section)s "
                                 "in your %(tracini)s.",
                                 section=tag.pre('[ticket]', tag.br(),
                                                 'workflow = ...'),
                                 tracini=tag.code('trac.ini')))

            # Apply changes made by the workflow
            self._apply_ticket_changes(ticket, field_changes)

            valid &= self._validate_ticket(req, ticket)
            if not preview and req.method == 'POST':
                if valid:
                    # redirects on success
                    self._do_create(req, ticket, action)
                # else fall through in a preview
                req.args['preview'] = True

        action_controls, selected_action = \
            self._get_action_controls(req, ticket)
        disable_submit = not action_controls

        # Preview a new ticket
        data = self._prepare_data(req, ticket)
        data.update({
            'author_id': reporter_id,
            'actions': [],
            'version': None,
            'description_change': None,
            'action_controls': action_controls,
            'action': selected_action,
            'disable_submit': disable_submit,
        })

        fields = self._prepare_fields(req, ticket)

        data['fields'] = fields
        data['fields_map'] = {field['name']: i
                              for i, field in enumerate(fields)}

        if req.is_xhr:
            data['preview_mode'] = True
            data['chrome_info_script'] = chrome_info_script
            return 'ticket_box.html', data

        add_stylesheet(req, 'common/css/ticket.css')
        chrome = Chrome(self.env)
        chrome.add_wiki_toolbars(req)
        if not disable_submit:
            chrome.add_auto_preview(req)
        chrome.add_jquery_ui(req)
        return 'ticket.html', data

    def _process_ticket_request(self, req):
        id = req.args.getint('id')
        version = req.args.getint('version', None)

        if req.is_xhr and 'preview_comment' in req.args:
            context = web_context(req, self.realm, id, version)
            escape_newlines = self.must_preserve_newlines
            rendered = format_to_html(self.env, context,
                                      req.args.get('edited_comment', ''),
                                      escape_newlines=escape_newlines) + \
                       chrome_info_script(req)
            req.send(rendered.encode('utf-8'))

        req.perm(self.realm, id, version).require('TICKET_VIEW')
        ticket = model.Ticket(self.env, id, version=version)
        action = req.args.get('action', ('history' in req.args and 'history' or
                                         'view'))

        data = self._prepare_data(req, ticket)

        if action in ('history', 'diff'):
            field = req.args.get('field')
            if field:
                text_fields = [field]
            else:
                text_fields = [field['name'] for field in ticket.fields if
                               field['type'] == 'textarea']
            if action == 'history':
                return self._render_history(req, ticket, data, text_fields)
            elif action == 'diff':
                return self._render_diff(req, ticket, data, text_fields)
        elif action == 'comment-history':
            req.args.require('cnum')
            cnum = req.args.getint('cnum')
            return self._render_comment_history(req, ticket, data, cnum)
        elif action == 'comment-diff':
            req.args.require('cnum')
            cnum = req.args.getint('cnum')
            return self._render_comment_diff(req, ticket, data, cnum)
        elif 'preview_comment' in req.args:
            field_changes = {}
            data.update({'action': None,
                         'reassign_owner': req.authname,
                         'resolve_resolution': None,
                         'start_time': ticket['changetime']})
            self._validate_ticket(req, ticket)
        elif 'cancel_comment' in req.args:
            req.redirect(req.href.ticket(ticket.id))
        elif 'edit_comment' in req.args:
            comment = req.args.get('edited_comment', '')
            cnum = req.args.getint('cnum_edit')
            change = ticket.get_change(cnum)
            if not change:
                raise TracError(_("Comment %(num)s not found", num=cnum))
            comment_resource = \
                Resource('comment', cnum, parent=ticket.resource)
            req.perm(comment_resource).require('TICKET_EDIT_COMMENT')
            if self._validate_ticket(req, ticket):
                ticket.modify_comment(change['date'], req.authname, comment)
                req.redirect(req.href.ticket(ticket.id) +
                             '#comment:%d' % cnum)
            else:
                field_changes = {}
                data.update({'action': None,
                             'reassign_owner': req.authname,
                             'resolve_resolution': None,
                             'start_time': ticket['changetime']})
        elif req.method == 'POST':

            valid = True

            # Do any action on the ticket?
            actions = TicketSystem(self.env).get_available_actions(req, ticket)
            if action not in actions:
                valid = False
                add_warning(req, _('The action "%(name)s" is not available.',
                                   name=action))

            # We have a bit of a problem.  There are two sources of changes to
            # the ticket: the user, and the workflow.  We need to show all the
            # changes that are proposed, but we need to be able to drop the
            # workflow changes if the user changes the action they want to do
            # from one preview to the next.
            #
            # the _populate() call pulls all the changes from the webpage; but
            # the webpage includes both changes by the user and changes by the
            # workflow... so we aren't able to differentiate them clearly.

            self._populate(req, ticket) # Apply changes made by the user
            field_changes, problems = self.get_ticket_changes(req, ticket,
                                                              action)
            if problems:
                valid = False
                for problem in problems:
                    add_warning(req, problem)
                add_warning(req,
                            tag_("Please review your configuration, "
                                 "probably starting with %(section)s "
                                 "in your %(tracini)s.",
                                 section=tag.pre('[ticket]', tag.br(),
                                                 'workflow = ...'),
                                 tracini=tag.code('trac.ini')))

            # Apply changes made by the workflow
            self._apply_ticket_changes(ticket, field_changes)
            # Unconditionally run the validation so that the user gets
            # information any and all problems.  But it's only valid if it
            # validates and there were no problems with the workflow side of
            # things.
            valid &= self._validate_ticket(req, ticket, not valid)
            if 'submit' in req.args:
                if valid:
                    # redirected if successful
                    self._do_save(req, ticket, action)
                # else fall through in a preview
                req.args['preview'] = True

            # Preview an existing ticket (after a Preview or a failed Save)
            start_time = from_utimestamp(int(req.args.get('start_time', 0)))
            data.update({
                'action': action, 'start_time': start_time,
                'reassign_owner': (req.args.get('reassign_choice')
                                   or req.authname),
                'resolve_resolution': req.args.get('resolve_choice'),
            })
        else: # simply 'View'ing the ticket
            field_changes = {}
            data.update({'action': None,
                         'reassign_owner': req.authname,
                         'resolve_resolution': None,
                         # Store a timestamp for detecting "mid air collisions"
                         'start_time': ticket['changetime']})

        data.update({'comment': req.args.get('comment'),
                     'cnum_edit': req.args.get('cnum_edit'),
                     'edited_comment': req.args.get('edited_comment'),
                     'cnum_hist': req.args.get('cnum_hist'),
                     'cversion': req.args.get('cversion')})

        self._insert_ticket_data(req, ticket, data,
                                 get_reporter_id(req, 'author'), field_changes)

        if req.is_xhr:
            data['preview_mode'] = bool(data['change_preview']['fields'])
            data['chrome_info_script'] = chrome_info_script
            return 'ticket_preview.html', data

        mime = Mimeview(self.env)
        format = req.args.get('format')
        if format:
            # FIXME: mime.send_converted(context, ticket, 'ticket_x') (#3332)
            filename = 't%d' % ticket.id if format != 'rss' else None
            mime.send_converted(req, 'trac.ticket.Ticket', ticket,
                                format, filename=filename)

        def add_ticket_link(css_class, id):
            t = ticket.resource(id=id, version=None)
            if t:
                add_link(req, css_class, req.href.ticket(id),
                         _("Ticket #%(id)s", id=id))

        global_sequence = True
        # If the ticket is being shown in the context of a query, add
        # links to help navigate in the query result set
        if 'query_tickets' in req.session:
            tickets = req.session['query_tickets'].split()
            if str(ticket.id) in tickets:
                idx = tickets.index(str(ticket.id))
                if idx > 0:
                    add_ticket_link('first', tickets[0])
                    add_ticket_link('prev', tickets[idx - 1])
                if idx < len(tickets) - 1:
                    add_ticket_link('next', tickets[idx + 1])
                    add_ticket_link('last', tickets[-1])
                add_link(req, 'up', req.session['query_href'])
                global_sequence = False
        if global_sequence:
            with self.env.db_query as db:
                for min_id, max_id in db(
                        "SELECT min(id), max(id) FROM ticket"):
                    min_id = int(min_id)
                    max_id = int(max_id)
                    if min_id < ticket.id:
                        add_ticket_link('first', min_id)
                        for prev_id, in db(
                                "SELECT max(id) FROM ticket WHERE id < %s",
                                (ticket.id,)):
                            add_ticket_link('prev', int(prev_id))
                    if ticket.id < max_id:
                        add_ticket_link('last', max_id)
                        for next_id, in db(
                                "SELECT min(id) FROM ticket WHERE %s < id",
                                (ticket.id,)):
                            add_ticket_link('next', int(next_id))
                    break

        # Data need for Javascript-specific logic
        old_values = {name: ticket[name]
                      for name in [field['name'] for field in ticket.fields]}
        old_values['id'] = ticket.id
        add_script_data(req, {'comments_prefs': self._get_prefs(req),
                              'old_values': old_values,
                              'changes': data['changes'],
                              })
        add_stylesheet(req, 'common/css/ticket.css')
        chrome = Chrome(self.env)
        chrome.add_wiki_toolbars(req)
        if not data['disable_submit']:
            chrome.add_auto_preview(req)
        chrome.add_jquery_ui(req)

        # Add registered converters
        for conversion in mime.get_supported_conversions('trac.ticket.Ticket'):
            format = conversion.key
            conversion_href = get_resource_url(self.env, ticket.resource,
                                               req.href, format=format)
            if format == 'rss':
                conversion_href = auth_link(req, conversion_href)
            add_link(req, 'alternate', conversion_href, conversion.name,
                     conversion.out_mimetype, format)

        prevnext_nav(req, _("Previous Ticket"), _("Next Ticket"),
                     _("Back to Query"))

        return 'ticket.html', data

    def _get_prefs(self, req):
        return {'comments_order': req.session.get('ticket_comments_order',
                                                  'oldest'),
                'show_prop_changes': req.session.get('ticket_show_prop_changes',
                                                     'true'),
                'show_comments': req.session.get('ticket_show_comments',
                                                 'true')}

    def _prepare_data(self, req, ticket, absurls=False):
        return {'ticket': ticket, 'to_utimestamp': to_utimestamp,
                'context': web_context(req, ticket.resource, absurls=absurls),
                'preserve_newlines': self.must_preserve_newlines,
                'emtpy': empty}

    def _cc_list(self, cc):
        return Chrome(self.env).cc_list(cc)

    def _toggle_cc(self, req, cc):
        """Return an (action, recipient) tuple corresponding to a change
        of CC status for this user relative to the current `cc_list`."""
        entry = None
        if req.is_authenticated:
            entry = req.authname
        else:
            email = req.session.get('email', '').strip()
            if email:
                entry = email
            else:
                author = get_reporter_id(req, 'author').strip()
                if author and author != 'anonymous':
                    email = author.split()[-1]
                    if email.startswith('<') and email.endswith('>'):
                        entry = email.strip('<>')
        action = None
        cc_list = self._cc_list(cc)
        if entry:
            action = 'remove' if entry in cc_list else 'add'
        return action, entry, cc_list

    def _populate(self, req, ticket, plain_fields=False):
        if not plain_fields:
            fields = {k[6:]: req.args.get(k) for k in req.args
                      if k.startswith('field_') and
                         'revert_' + k[6:] not in req.args}
            # Handle revert of checkboxes (in particular, revert to 1)
            for k in list(fields):
                if k.startswith('checkbox_'):
                    k = k[9:]
                    if 'revert_' + k in req.args:
                        fields[k] = ticket[k]
        else:
            fields = {k: req.args.get(k) for k in req.args}
        # Prevent direct changes to protected fields (status and resolution are
        # set in the workflow, in get_ticket_changes())
        for each in model.Ticket.protected_fields:
            fields.pop(each, None)
            fields.pop('checkbox_' + each, None)    # See Ticket.populate()
        for field, value in fields.iteritems():
            if field in ticket.time_fields:
                try:
                    fields[field] = user_time(req, parse_date, value) \
                                    if value else None
                except TracError as e:
                    # Handle bad user input for custom time fields gracefully.
                    if field in ticket.custom_fields:
                        # Leave it to _validate_ticket() to complain.
                        fields[field] = value
                    else:
                        raise TracError(e)
        ticket.populate(fields)
        # special case for updating the Cc: field
        if 'cc_update' in req.args and 'revert_cc' not in req.args:
            cc_action, cc_entry, cc_list = self._toggle_cc(req, ticket['cc'])
            if cc_action == 'remove':
                cc_list.remove(cc_entry)
            elif cc_action == 'add':
                cc_list.append(cc_entry)
            ticket['cc'] = ', '.join(cc_list)

    def _get_history(self, req, ticket):
        history = []
        for change in self.rendered_changelog_entries(req, ticket):
            if change['permanent']:
                change['version'] = change['cnum']
                history.append(change)
        return history

    def _render_history(self, req, ticket, data, text_fields):
        """Extract the history for a ticket description."""
        req.perm(ticket.resource).require('TICKET_VIEW')

        history = self._get_history(req, ticket)
        history.reverse()
        history = [c for c in history if any(f in text_fields
                                             for f in c['fields'])]
        history.append({'version': 0, 'comment': "''Initial version''",
                        'date': ticket['time'],
                        'author': ticket['reporter']  # not 100% accurate...
                        })
        data.update({'title': _("Ticket History"),
                     'resource': ticket.resource,
                     'history': history})

        add_ctxtnav(req, _("Back to Ticket #%(num)s", num=ticket.id),
                    req.href.ticket(ticket.id))
        return 'history_view.html', data

    def _render_diff(self, req, ticket, data, text_fields):
        """Show differences between two versions of a ticket description.

        `text_fields` is optionally a list of fields of interest, that are
        considered for jumping to the next change.
        """
        new_version = req.args.getint('version', 1)
        old_version = req.args.getint('old_version', new_version)
        if old_version > new_version:
            old_version, new_version = new_version, old_version

        # get the list of versions having a description change
        history = self._get_history(req, ticket)
        changes = {}
        descriptions = []
        old_idx = new_idx = -1  # indexes in descriptions
        for change in history:
            version = change['version']
            changes[version] = change
            if any(f in text_fields for f in change['fields']):
                if old_version and version <= old_version:
                    old_idx = len(descriptions)
                if new_idx == -1 and new_version and version >= new_version:
                    new_idx = len(descriptions)
                descriptions.append((version, change))

        # determine precisely old and new versions
        if old_version == new_version:
            if new_idx >= 0:
                old_idx = new_idx - 1
        if old_idx >= 0:
            old_version, old_change = descriptions[old_idx]
        else:
            old_version, old_change = 0, None
        num_changes = new_idx - old_idx
        if new_idx >= 0:
            new_version, new_change = descriptions[new_idx]
        else:
            raise TracError(_("No differences to show"))

        tnew = ticket.resource(version=new_version)
        told = ticket.resource(version=old_version)

        req.perm(tnew).require('TICKET_VIEW')
        req.perm(told).require('TICKET_VIEW')

        # determine prev and next versions
        prev_version = old_version
        next_version = None
        if new_idx < len(descriptions) - 1:
            next_version = descriptions[new_idx+1][0]

        # -- old properties (old_ticket) and new properties (new_ticket)

        # assume a linear sequence of change numbers, starting at 1, with gaps
        def replay_changes(values, old_values, from_version, to_version):
            for version in xrange(from_version, to_version+1):
                if version in changes:
                    for k, v in changes[version]['fields'].iteritems():
                        values[k] = v['new']
                        if old_values is not None and k not in old_values:
                            old_values[k] = v['old']

        old_ticket = {}
        if old_version:
            replay_changes(old_ticket, None, 1, old_version)

        new_ticket = dict(old_ticket)
        replay_changes(new_ticket, old_ticket, old_version+1, new_version)

        field_labels = TicketSystem(self.env).get_ticket_field_labels()

        changes = []

        def version_info(t, field=None):
            path = _("Ticket #%(id)s", id=ticket.id)
            # TODO: field info should probably be part of the Resource as well
            if field:
                path = tag(path, Markup(' &ndash; '),
                           field_labels.get(field, field.capitalize()))
            if t.version:
                rev = _("Version %(num)s", num=t.version)
                shortrev = 'v%d' % t.version
            else:
                rev, shortrev = _("Initial Version"), _("initial")
            return {'path':  path, 'rev': rev, 'shortrev': shortrev,
                    'href': get_resource_url(self.env, t, req.href)}

        # -- prop changes
        props = []
        for k, v in new_ticket.iteritems():
            if k not in text_fields:
                old, new = old_ticket[k], new_ticket[k]
                if old != new:
                    label = field_labels.get(k, k.capitalize())
                    rendered = self._render_property_diff(req, ticket, k,
                                                          old, new, tnew)
                    diff = tag.li(
                        tag_("Property %(label)s %(rendered)s",
                             label=tag.strong(label), rendered=rendered))
                    props.append({'name': label, 'field': k, 'diff': diff})
        changes.append({'props': props, 'diffs': [],
                        'new': version_info(tnew),
                        'old': version_info(told)})

        # -- text diffs
        diff_style, diff_options, diff_data = get_diff_options(req)
        diff_context = 3
        for option in diff_options:
            if option.startswith('-U'):
                diff_context = int(option[2:])
                break
        if diff_context < 0:
            diff_context = None

        for field in text_fields:
            old_text = old_ticket.get(field)
            old_text = old_text.splitlines() if old_text else []
            new_text = new_ticket.get(field)
            new_text = new_text.splitlines() if new_text else []
            diffs = diff_blocks(old_text, new_text, context=diff_context,
                                ignore_blank_lines='-B' in diff_options,
                                ignore_case='-i' in diff_options,
                                ignore_space_changes='-b' in diff_options)

            changes.append({'diffs': diffs, 'props': [], 'field': field,
                            'new': version_info(tnew, field),
                            'old': version_info(told, field)})

        # -- prev/up/next links
        if prev_version:
            add_link(req, 'prev', get_resource_url(self.env, ticket.resource,
                                                   req.href, action='diff',
                                                   version=prev_version),
                     _("Version %(num)s", num=prev_version))
        add_link(req, 'up', get_resource_url(self.env, ticket.resource,
                                             req.href, action='history'),
                 _("Ticket History"))
        if next_version:
            add_link(req, 'next', get_resource_url(self.env, ticket.resource,
                                                   req.href, action='diff',
                                                   version=next_version),
                     _("Version %(num)s", num=next_version))

        prevnext_nav(req, _("Previous Change"), _("Next Change"),
                     _("Ticket History"))
        add_stylesheet(req, 'common/css/diff.css')
        add_script(req, 'common/js/diff.js')

        data.update({
            'title': _("Ticket Diff"),
            'resource': ticket.resource,
            'old_version': old_version, 'new_version': new_version,
            'changes': changes, 'diff': diff_data,
            'num_changes': num_changes, 'change': new_change,
            'old_ticket': old_ticket, 'new_ticket': new_ticket,
            'longcol': '', 'shortcol': ''
        })

        return 'diff_view.html', data

    def _make_comment_url(self, req, ticket, cnum, version=None):
        return req.href.ticket(ticket.id,
                               cnum_hist=cnum if version is not None else None,
                               cversion=version) + '#comment:%d' % cnum

    def _get_comment_history(self, req, ticket, cnum):
        history = []
        for version, date, author, comment in \
                ticket.get_comment_history(cnum) or []:
            history.append({
                'version': version, 'date': date, 'author': author,
                'comment': None,
                'value': comment,
                'url': self._make_comment_url(req, ticket, cnum, version)
            })
        return history

    def _render_comment_history(self, req, ticket, data, cnum):
        """Extract the history for a ticket comment."""
        req.perm(ticket.resource).require('TICKET_VIEW')
        history = self._get_comment_history(req, ticket, cnum)
        history.reverse()
        url = self._make_comment_url(req, ticket, cnum)
        data.update({
            'title': _("Ticket Comment History"),
            'resource': ticket.resource,
            'name': _("Ticket #%(num)s, comment %(cnum)d",
                      num=ticket.id, cnum=cnum),
            'url': url,
            'diff_action': 'comment-diff', 'diff_args': [('cnum', cnum)],
            'history': history,
        })
        add_ctxtnav(req, _("Back to Ticket #%(num)s", num=ticket.id), url)
        return 'history_view.html', data

    def _render_comment_diff(self, req, ticket, data, cnum):
        """Show differences between two versions of a ticket comment."""
        req.perm(ticket.resource).require('TICKET_VIEW')
        new_version = req.args.getint('version', 1)
        old_version = req.args.getint('old_version', new_version)
        if old_version > new_version:
            old_version, new_version = new_version, old_version
        elif old_version == new_version:
            old_version = new_version - 1

        history = {}
        for change in self._get_comment_history(req, ticket, cnum):
            history[change['version']] = change

        def version_info(version):
            path = _("Ticket #%(num)s, comment %(cnum)d",
                     num=ticket.id, cnum=cnum)
            if version:
                rev = _("Version %(num)s", num=version)
                shortrev = 'v%d' % version
            else:
                rev, shortrev = _("Initial Version"), _("initial")
            return {'path':  path, 'rev': rev, 'shortrev': shortrev}

        diff_style, diff_options, diff_data = get_diff_options(req)
        diff_context = 3
        for option in diff_options:
            if option.startswith('-U'):
                diff_context = int(option[2:])
                break
        if diff_context < 0:
            diff_context = None

        def get_text(version):
            try:
                text = history[version]['value']
            except KeyError:
                raise ResourceNotFound(_("No version %(version)d for comment "
                                         "%(cnum)d on ticket #%(ticket)s",
                                         version=version, cnum=cnum,
                                         ticket=ticket.id))
            return text.splitlines() if text else []

        old_text = get_text(old_version)
        new_text = get_text(new_version)
        diffs = diff_blocks(old_text, new_text, context=diff_context,
                            ignore_blank_lines='-B' in diff_options,
                            ignore_case='-i' in diff_options,
                            ignore_space_changes='-b' in diff_options)

        changes = [{'diffs': diffs, 'props': [],
                    'new': version_info(new_version),
                    'old': version_info(old_version)}]

        # -- prev/up/next links
        prev_version = old_version
        next_version = None
        if new_version < len(history) - 1:
            next_version = new_version + 1

        if prev_version:
            url = req.href.ticket(ticket.id, cnum=cnum, action='comment-diff',
                                  version=prev_version)
            add_link(req, 'prev', url, _("Version %(num)s", num=prev_version))
        add_link(req, 'up', req.href.ticket(ticket.id, cnum=cnum,
                                            action='comment-history'),
                 _("Ticket Comment History"))
        if next_version:
            url = req.href.ticket(ticket.id, cnum=cnum, action='comment-diff',
                                  version=next_version)
            add_link(req, 'next', url, _("Version %(num)s", num=next_version))

        prevnext_nav(req, _("Previous Change"), _("Next Change"),
                     _("Ticket Comment History"))
        add_stylesheet(req, 'common/css/diff.css')
        add_script(req, 'common/js/diff.js')

        data.update({
            'title': _("Ticket Comment Diff"),
            'resource': ticket.resource,
            'name': _("Ticket #%(num)s, comment %(cnum)d",
                      num=ticket.id, cnum=cnum),
            'url': self._make_comment_url(req, ticket, cnum),
            'old_url': self._make_comment_url(req, ticket, cnum, old_version),
            'new_url': self._make_comment_url(req, ticket, cnum, new_version),
            'diff_url': req.href.ticket(ticket.id, cnum=cnum,
                                        action='comment-diff',
                                        version=new_version),
            'diff_action': 'comment-diff', 'diff_args': [('cnum', cnum)],
            'old_version': old_version, 'new_version': new_version,
            'changes': changes, 'diff': diff_data,
            'num_changes': new_version - old_version,
            'change': history[new_version],
            'ticket': ticket, 'cnum': cnum,
            'longcol': '', 'shortcol': ''
        })

        return 'diff_view.html', data

    def export_csv(self, req, ticket, sep=',', mimetype='text/plain'):
        # FIXME: consider dumping history of changes here as well
        #        as one row of output doesn't seem to be terribly useful...
        fields = [f for f in ticket.fields
                  if f['name'] not in ('time', 'changetime')]
        content = io.BytesIO()
        content.write(b'\xef\xbb\xbf')   # BOM
        writer = csv.writer(content, delimiter=sep, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(['id'] + [unicode(f['name']) for f in fields])

        context = web_context(req, ticket.resource)
        cols = [unicode(ticket.id)]
        for f in fields:
            name = f['name']
            value = ticket[name] or ''
            if name in ('cc', 'owner', 'reporter'):
                value = Chrome(self.env).format_emails(context, value, ' ')
            elif name in ticket.time_fields:
                format = ticket.fields.by_name(name).get('format')
                value = user_time(req, format_date_or_datetime, format,
                                  value) if value else ''
            cols.append(value.encode('utf-8'))
        writer.writerow(cols)
        return content.getvalue(), '%s;charset=utf-8' % mimetype

    def _export_rss(self, req, ticket):
        changes = []

        for change in self.rendered_changelog_entries(req, ticket):
            changes.append(change)
            # compute a change summary
            change_summary = {}
            # wikify comment
            if 'comment' in change:
                change_summary['added'] = ['comment']
            for field, values in change['fields'].iteritems():
                if field == 'description':
                    change_summary.setdefault('changed', []).append(field)
                else:
                    chg = 'changed'
                    if not values['old']:
                        chg = 'set'
                    elif not values['new']:
                        chg = 'deleted'
                    change_summary.setdefault(chg, []).append(field)
            c = change_summary.get('changed')
            if c:
                c = ngettext("%(labels)s changed", "%(labels)s changed",
                             len(c), labels=', '.join(c))
            s = change_summary.get('set')
            if s:
                s = ngettext("%(labels)s set", "%(labels)s set",
                             len(s), labels=', '.join(s))
            d = change_summary.get('deleted')
            if d:
                d = ngettext("%(labels)s deleted", "%(labels)s deleted",
                             len(d), labels=', '.join(d))
            change['title'] = _("; ").join(g for g in [c, s, d] if g)

        data = self._prepare_data(req, ticket, absurls=True)
        data['changes'] = changes
        output = Chrome(self.env).render_template(req, 'ticket.rss', data,
                                                  {'content_type':
                                                   'application/rss+xml',
                                                   'iterable': True})

        return output, 'application/rss+xml'

    # Ticket validation and changes

    def _validate_ticket(self, req, ticket, force_collision_check=False):
        valid = True
        resource = ticket.resource

        # If the ticket has been changed, check the proper permissions
        if ticket.exists and ticket._old:
            # Status and resolution can be modified by the workflow even
            # without having TICKET_CHGPROP
            changed = set(ticket._old) - {'status', 'resolution'}
            if 'description' in changed \
                    and 'TICKET_EDIT_DESCRIPTION' not in req.perm(resource):
                add_warning(req, _("No permission to edit the ticket "
                                   "description."))
                valid = False
            changed.discard('description')
            if 'reporter' in changed \
                    and 'TICKET_ADMIN' not in req.perm(resource):
                add_warning(req, _("No permission to change the ticket "
                                   "reporter."))
                valid = False
            changed.discard('reporter')
            if changed and 'TICKET_CHGPROP' not in req.perm(resource):
                add_warning(req, _("No permission to change ticket fields."))
                valid = False
            if not valid:
                ticket.populate(ticket._old)

        comment = req.args.get('comment')
        if comment and 'TICKET_APPEND' not in req.perm(resource):
            add_warning(req, _("No permissions to add a comment."))
            valid = False

        # Mid air collision?
        if ticket.exists and (ticket._old or comment or force_collision_check):
            changetime = str(to_utimestamp(ticket['changetime']))
            if 'preview' in req.args and \
                    req.args.get('start_time') != changetime:
                add_warning(req, _("This ticket has been modified since you "
                                   "started editing."))
            elif req.args.get('view_time') != changetime:
                add_warning(req, _("Your changes have not been saved because "
                                   "this ticket has been modified since you "
                                   "started editing."))
                valid = False

        # Validate comment id: replyto must be 'description' or a number
        replyto = req.args.get('replyto') or 0
        if replyto != 'description' and as_int(replyto, None) is None:
            # Shouldn't happen in "normal" circumstances, hence not a warning
            raise TracValueError(_("Invalid comment threading identifier"))

        # Validate custom rules.
        comment = comment or req.args.get('edited_comment')
        for manipulator in self.ticket_manipulators:
            if hasattr(manipulator, 'validate_comment'):
                for message in manipulator.validate_comment(req, comment):
                    valid = False
                    add_warning(req, tag_("The ticket comment is invalid: "
                                          "%(message)s",
                                          message=message))

            for field, message in manipulator.validate_ticket(req, ticket):
                valid = False
                if field:
                    add_warning(req, tag_("The ticket field %(field)s is "
                                          "invalid: %(message)s",
                                          field=tag.strong(field),
                                          message=message))
                else:
                    add_warning(req, message)

        return valid

    def _do_create(self, req, ticket, action):
        # Save the action controllers we need to call side-effects for before
        # we save the changes to the ticket.
        controllers = list(self._get_action_controllers(req, ticket, action))

        ticket.insert()

        # After saving the changes, apply the side-effects.
        for controller in controllers:
            self.log.debug("Side effect for %s",
                           controller.__class__.__name__)
            controller.apply_action_side_effects(req, ticket, action)

        # Notify. Use author=req.authname rather than ticket['reporter']
        # because ticket may be created on behalf of another user (#11949).
        event = TicketChangeEvent('created', ticket, ticket['time'],
                                  req.authname)
        try:
            NotificationSystem(self.env).notify(event)
        except Exception as e:
            self.log.error("Failure sending notification on creation of "
                           "ticket #%s: %s",
                           ticket.id, exception_to_unicode(e))
            add_warning(req, tag_("The ticket has been created, but an error "
                                  "occurred while sending notifications: "
                                  "%(message)s", message=to_fragment(e)))

        # Redirect the user to the newly created ticket or add attachment
        ticketref = tag.a('#', ticket.id, href=req.href.ticket(ticket.id))
        if 'attachment' in req.args:
            add_notice(req, tag_("The ticket %(ticketref)s has been created. "
                                 "You can now attach the desired files.",
                                 ticketref=ticketref))
            req.redirect(req.href.attachment(ticket.realm, ticket.id,
                                             action='new'))
        if 'TICKET_VIEW' not in req.perm(ticket.resource):
            add_notice(req, tag_("The ticket %(ticketref)s has been created, "
                                 "but you don't have permission to view it.",
                                 ticketref=ticketref))
            req.redirect(req.href.newticket())
        req.redirect(req.href.ticket(ticket.id))

    def _do_save(self, req, ticket, action):
        # Save the action controllers we need to call side-effects for before
        # we save the changes to the ticket.
        controllers = list(self._get_action_controllers(req, ticket, action))

        # -- Save changes

        fragment = ''
        now = datetime_now(utc)
        author = get_reporter_id(req, 'author')
        comment = req.args.get('comment')
        cnum = ticket.save_changes(author, comment, when=now,
                                   replyto=req.args.get('replyto'))
        if cnum:
            fragment = '#comment:%d' % cnum
            event = TicketChangeEvent('changed', ticket, now, author, comment)
            try:
                NotificationSystem(self.env).notify(event)
            except Exception as e:
                self.log.error("Failure sending notification on change to "
                               "ticket #%s: %s",
                               ticket.id, exception_to_unicode(e))
                # TRANSLATOR: The 'change' has been saved... (link)
                change = _('change')
                if fragment:
                    change = tag.a(change, href=fragment)
                add_warning(req, tag_("The %(change)s has been saved, but an "
                                      "error occurred while sending "
                                      "notifications: %(message)s",
                                      change=change, message=to_fragment(e)))
                fragment = ''

        # After saving the changes, apply the side-effects.
        for controller in controllers:
            self.log.debug("Side effect for %s",
                           controller.__class__.__name__)
            controller.apply_action_side_effects(req, ticket, action)

        req.redirect(req.href.ticket(ticket.id) + fragment)

    def get_ticket_changes(self, req, ticket, selected_action):
        """Returns a dictionary of field changes.

        The field changes are represented as:
        `{field: {'old': oldvalue, 'new': newvalue, 'by': what}, ...}`
        """
        field_labels = TicketSystem(self.env).get_ticket_field_labels()
        field_changes = {}
        def store_change(field, old, new, author):
            field_changes[field] = {'old': old, 'new': new, 'by': author,
                                    'label': field_labels.get(field, field)}
        # Start with user changes
        for field, value in ticket._old.iteritems():
            store_change(field, value or '', ticket[field], 'user')

        # Apply controller changes corresponding to the selected action
        problems = []
        for controller in self._get_action_controllers(req, ticket,
                                                       selected_action):
            cname = controller.__class__.__name__
            action_changes = controller.get_ticket_changes(req, ticket,
                                                           selected_action)
            for key in action_changes:
                old = ticket[key]
                new = action_changes[key]
                # Check for conflicting changes between controllers
                if key in field_changes:
                    last_new = field_changes[key]['new']
                    last_by = field_changes[key]['by']
                    if last_new != new and last_by:
                        problems.append(
                            _('%(controller1)s changed "%(key)s" to '
                              '"%(val1)s", but %(controller2)s changed '
                              'it to "%(val2)s".', controller1=cname, key=key,
                              val1=new, controller2=last_by, val2=last_new))
                store_change(key, old, new, cname)

        # Detect non-changes
        for key, item in field_changes.items():
            if item['old'] == item['new']:
                del field_changes[key]
        return field_changes, problems

    def _apply_ticket_changes(self, ticket, field_changes):
        """Apply the changes obtained from `get_ticket_changes` to the ticket
        """
        for key in field_changes:
            ticket[key] = field_changes[key]['new']

    def _query_link(self, req, name, value, text=None, class_=None):
        """Return a link to /query with the appropriate name and value"""
        from trac.ticket.query import QueryModule
        if not self.env.is_component_enabled(QueryModule):
            return text or value
        args = arg_list_to_args(parse_arg_list(self.ticketlink_query))
        args[name] = value
        if name == 'resolution':
            args['status'] = 'closed'
        if text or value:
            return tag.a(text or value, href=req.href.query(args),
                         class_=class_)

    def _query_link_words(self, context, name, value):
        """Splits a list of words and makes a query link to each separately"""
        from trac.ticket.query import QueryModule
        if not (isinstance(value, basestring) and  # None or other non-splitable
                self.env.is_component_enabled(QueryModule)):
            return value
        args = arg_list_to_args(parse_arg_list(self.ticketlink_query))
        items = []
        for i, word in enumerate(re.split(r'([;,\s]+)', value)):
            if i % 2:
                items.append(word.strip() + ' ')
            elif word:
                rendered = Chrome(self.env).format_author(context, word) \
                           if name == 'cc' else word
                if not is_obfuscated(rendered):
                    word_args = args.copy()
                    word_args[name] = '~' + word
                    items.append(tag.a(rendered,
                                       href=context.href.query(word_args)))
                else:
                    items.append(rendered)
        return tag(items)

    def _prepare_fields(self, req, ticket, field_changes=None):
        context = web_context(req, ticket.resource)
        fields = []
        for field in ticket.fields:
            name = field['name']
            type_ = field['type']

            # ensure sane defaults
            field.setdefault('optional', False)
            field.setdefault('options', [])
            field.setdefault('skip', False)
            field.setdefault('editable', True)

            # enable a link to custom query for all choice fields
            if type_ not in ['text', 'textarea', 'time']:
                field['rendered'] = self._query_link(req, name, ticket[name])

            # per field settings
            if name in ('summary', 'reporter', 'description', 'owner',
                        'status', 'resolution', 'time', 'changetime'):
                field['skip'] = True
            elif name == 'milestone' and not field.get('custom'):
                milestones = [m for m in (model.Milestone(self.env, opt)
                                          for opt in field['options'])
                                if 'TICKET_CHG_MILESTONE'
                                in req.perm(m.resource)]
                field['editable'] = milestones != []
                groups = group_milestones(milestones, ticket.exists
                    and 'TICKET_ADMIN' in req.perm(ticket.resource))
                field['options'] = []
                field['optgroups'] = [
                    {'label': label, 'options': [m.name for m in milestones]}
                    for (label, milestones) in groups]
                milestone = Resource('milestone', ticket[name])
                field['rendered'] = render_resource_link(self.env, context,
                                                         milestone, 'compact')
            elif name == 'version' and not field.get('custom'):
                try:
                    version = model.Version(self.env, ticket[name])
                except ResourceNotFound:
                    pass
                else:
                    if version.time:
                        dt = user_time(req, format_datetime, version.time)
                        title = _("Released %(datetime)s", datetime=dt)
                        field['rendered'](title=title)
            elif name == 'cc':
                cc_changed = field_changes is not None and 'cc' in field_changes
                if 'TICKET_EDIT_CC' not in req.perm(ticket.resource):
                    cc = ticket._old.get('cc', ticket['cc'])
                    cc_action, cc_entry, cc_list = self._toggle_cc(req, cc)
                    cc_update = 'cc_update' in req.args \
                                and 'revert_cc' not in req.args
                    field['edit_label'] = {
                            'add': _("Add Cc"),
                            'remove': _("Remove Cc"),
                            None: _("Cc")}[cc_action]
                    field['cc_action'] = cc_action
                    field['cc_entry'] = cc_entry
                    field['cc_update'] = cc_update
                    if cc_changed:
                        field_changes['cc']['cc_update'] = cc_update
                if cc_changed:
                    # normalize the new CC: list; also remove the
                    # change altogether if there's no real change
                    old_cc_list = self._cc_list(field_changes['cc']['old'])
                    new_cc_list = self._cc_list(field_changes['cc']['new']
                                                .replace(' ', ','))
                    if new_cc_list == old_cc_list:
                        del field_changes['cc']
                    else:
                        field_changes['cc']['new'] = ','.join(new_cc_list)

            # per type settings
            if type_ in ('radio', 'select'):
                if ticket.exists and field['editable']:
                    value = ticket[name]
                    options = field['options']
                    optgroups = []
                    for x in field.get('optgroups', []):
                        optgroups.extend(x['options'])
                    if value and \
                            (value not in options and
                             value not in optgroups):
                        # Current ticket value must be visible,
                        # even if it's not among the possible values
                        options.append(value)
            elif type_ == 'checkbox':
                value = ticket[name]
                if value in ('1', '0'):
                    field['rendered'] = self._query_link(req, name, value,
                                _("yes") if value == '1' else _("no"))
            elif type_ == 'text':
                if field.get('format') == 'reference':
                    field['rendered'] = self._query_link(req, name,
                                                         ticket[name])
                elif field.get('format') == 'list':
                    field['rendered'] = self._query_link_words(context, name,
                                                               ticket[name])
            elif type_ == 'time':
                value = ticket[name]
                field['timevalue'] = value
                format = field.get('format', 'datetime')
                if isinstance(value, datetime):
                    field['edit'] = user_time(req, format_date_or_datetime,
                                              format, value)
                else:
                    field['edit'] = value or ''
                locale = getattr(req, 'lc_time', None)
                if format == 'date':
                    field['format_hint'] = get_date_format_hint(locale)
                else:
                    field['format_hint'] = get_datetime_format_hint(locale)

            fields.append(field)

        return fields

    def _insert_ticket_data(self, req, ticket, data, author_id, field_changes):
        """Insert ticket data into the template `data`"""
        replyto = req.args.get('replyto')
        data['replyto'] = replyto
        data['version'] = ticket.resource.version
        data['description_change'] = None
        data['author_id'] = author_id
        chrome = Chrome(self.env)

        # -- Ticket fields

        fields = self._prepare_fields(req, ticket, field_changes)
        fields_map = {field['name']: i for i, field in enumerate(fields)}

        # -- Ticket Change History

        def quote_original(author, original, link):
            if 'comment' not in req.args:  # i.e. comment was not yet edited
                formatted_author = \
                    chrome.format_author(req, author, show_email=False)
                data['comment'] = '\n'.join(
                    ["Replying to [%s %s]:" % (link, formatted_author)] +
                    ["> %s" % line for line in original.splitlines()] + [''])

        if replyto == 'description':
            quote_original(ticket['reporter'], ticket['description'],
                           'ticket:%d' % ticket.id)
        values = {}
        replies = {}
        changes = []
        cnum = 0
        skip = False
        start_time = data.get('start_time', ticket['changetime'])
        conflicts = set()
        for change in self.rendered_changelog_entries(req, ticket):
            # change['permanent'] is false for attachment changes; true for
            # other changes.
            if change['permanent']:
                cnum = change['cnum']
                if ticket.resource.version is not None and \
                        cnum > ticket.resource.version:
                    # Retrieve initial ticket values from later changes
                    for k, v in change['fields'].iteritems():
                        if k not in values:
                            values[k] = v['old']
                    skip = True
                else:
                    # keep track of replies threading
                    if 'replyto' in change:
                        replies.setdefault(change['replyto'], []).append(cnum)
                    # eventually cite the replied to comment
                    if replyto == str(cnum):
                        quote_original(change['author'], change['comment'],
                                       'comment:%s' % replyto)
                    if ticket.resource.version:
                        # Override ticket value by current changes
                        for k, v in change['fields'].iteritems():
                            values[k] = v['new']
                    if 'description' in change['fields']:
                        data['description_change'] = change
                if change['date'] > start_time:
                    conflicts.update(change['fields'])
            if not skip:
                changes.append(change)

        if ticket.resource.version is not None:
            ticket.populate(values)

        # retrieve close time from changes
        closetime = None
        for c in changes:
            s = c['fields'].get('status')
            if s:
                closetime = c['date'] if s['new'] == 'closed' else None

        # Workflow support
        action_controls, selected_action = \
            self._get_action_controls(req, ticket)

        # Insert change preview
        change_preview = {
            'author': author_id, 'fields': field_changes, 'preview': True,
            'comment': req.args.get('comment', data.get('comment')),
            'comment_history': {},
        }
        replyto = req.args.get('replyto')
        if replyto:
            change_preview['replyto'] = replyto
        if req.method == 'POST':
            self._apply_ticket_changes(ticket, field_changes)
            self._render_property_changes(req, ticket, field_changes)

        if ticket.resource.version is not None: ### FIXME
            ticket.populate(values)

        context = web_context(req, ticket.resource)

        # Display the owner and reporter links when not obfuscated
        for role in 'reporter', 'owner':
            user = ticket[role]
            formatted_user = chrome.format_author(req, user)
            if not is_obfuscated(formatted_user):
                data['%s_link' % role] = self._query_link(
                    req, role, user, formatted_user,
                    class_=chrome.author_class(req, user))
        data.update({
            'context': context, 'conflicts': conflicts,
            'fields': fields, 'fields_map': fields_map,
            'changes': changes, 'replies': replies,
            'attachments': AttachmentModule(self.env).attachment_data(context),
            'action_controls': action_controls, 'action': selected_action,
            'change_preview': change_preview, 'closetime': closetime,
            'disable_submit': len(action_controls) == 0,
        })

    def rendered_changelog_entries(self, req, ticket, when=None):
        """Iterate on changelog entries, consolidating related changes
        in a `dict` object.
        """
        attachment_realm = ticket.resource.child('attachment')
        for group in self.grouped_changelog_entries(ticket, when=when):
            t = ticket.resource(version=group.get('cnum'))
            if 'TICKET_VIEW' in req.perm(t):
                self._render_property_changes(req, ticket, group['fields'], t)
                if 'attachment' in group['fields']:
                    filename = group['fields']['attachment']['new']
                    attachment = attachment_realm(id=filename)
                    if 'ATTACHMENT_VIEW' not in req.perm(attachment):
                        del group['fields']['attachment']
                        if not group['fields']:
                            continue
                yield group

    def _render_property_changes(self, req, ticket, fields, resource_new=None):
        for field, changes in fields.iteritems():
            new, old = changes['new'], changes['old']
            changes['rendered'] = \
                self._render_property_diff(req, ticket, field, old, new,
                                           resource_new)

    def _render_property_diff(self, req, ticket, field, old, new,
                              resource_new=None):

        def render_list(elt_renderer, separator, old_list, new_list):
            if not elt_renderer:
                elt_renderer = lambda e: e
            added = [elt_renderer(x) for x in new_list if x not in old_list]
            remvd = [elt_renderer(x) for x in old_list if x not in new_list]
            added = added and tagn_("%(items)s added", "%(items)s added",
                                    len(added),
                                    items=separated(added, separator))
            remvd = remvd and tagn_("%(items)s removed", "%(items)s removed",
                                    len(remvd),
                                    items=separated(remvd, separator))
            if added or remvd:
                return tag(added, added and remvd and _("; "), remvd)

        def render_default(old, new):
            if old and new:
                rendered = tag(tag.span(old, class_='trac-field-old'), u' → ',
                               tag.span(new, class_='trac-field-new'))
            elif not old and new:
                rendered = tag(u'→ ', tag.span(new, class_='trac-field-new'))
            else:  # old and not new
                rendered = tag.span(old, class_='trac-field-deleted')
            return rendered

        chrome = Chrome(self.env)
        def authorinfo(author):
            resource = resource_new or ticket.resource
            return chrome.authorinfo(req, author, resource=resource)

        field_info = ticket.fields.by_name(field, {})
        type_ = field_info.get('type')
        # per name special rendering of diffs
        if field == 'cc':
            old_list, new_list = self._cc_list(old), self._cc_list(new)
            rendered = render_list(authorinfo, ' ', old_list, new_list)
        elif field in ('reporter', 'owner'):
            old_author = authorinfo(old)
            new_author = authorinfo(new)
            if old and not new:
                rendered = tag_("%(value)s deleted", value=old_author)
            elif new and not old:
                rendered = tag_("set to %(value)s", value=new_author)
            else:  # old and new:
                rendered = tag_("changed from %(old)s to %(new)s",
                                old=old_author, new=new_author)
        # per type special rendering of diffs
        elif type_ == 'checkbox':
            rendered = _("set") if new == '1' else _("unset")
        elif type_ == 'textarea':
            if not resource_new:
                rendered = _("modified")
            else:
                href = get_resource_url(self.env, resource_new, req.href,
                                        action='diff')
                # TRANSLATOR: modified ('diff') (link)
                diff = tag.a(_("diff"), href=href)
                rendered = tag_("modified (%(diff)s)", diff=diff)
        elif type_ == 'text' and field_info.get('format') == 'list':
            old_list = re.split(r'[;,\s]+', old) if old else []
            new_list = re.split(r'[;,\s]+', new) if new else []
            rendered = render_list(None, ' ', old_list, new_list)
        elif type_ == 'time':
            format_ = field_info.get('format')
            old = user_time(req, format_date_or_datetime, format_, old) \
                  if isinstance(old, datetime) else old or ''
            new = user_time(req, format_date_or_datetime, format_, new) \
                  if isinstance(new, datetime) else new or ''
            rendered = render_default(old, new)
        # default rendering
        else:
            rendered = render_default(old, new)

        return rendered

    def grouped_changelog_entries(self, ticket, when=None):
        """Iterate on changelog entries, consolidating related changes
        in a `dict` object.
        """
        field_labels = TicketSystem(self.env).get_ticket_field_labels()
        changelog = ticket.get_changelog(when=when)
        autonum = 0  # used for "root" numbers
        last_uid = current = None
        for date, author, field, old, new, permanent in changelog:
            uid = (date,) if permanent else (date, author)
            if uid != last_uid:
                if current:
                    last_comment = comment_history[max(comment_history)]
                    last_comment['comment'] = current['comment']
                    yield current
                last_uid = uid
                comment_history = {0: {'date': date}}
                current = {'date': date, 'fields': {},
                           'permanent': permanent, 'comment': '',
                           'comment_history': comment_history}
                if permanent and not when:
                    autonum += 1
                    current['cnum'] = autonum
            # some common processing for fields
            if not field.startswith('_'):
                current.setdefault('author', author)
                comment_history[0].setdefault('author', author)
            if field == 'comment':
                current['comment'] = new
                # Always take the author from the comment field if available
                current['author'] = comment_history[0]['author'] = author
                if old:
                    if '.' in old: # retrieve parent.child relationship
                        parent_num, this_num = old.split('.', 1)
                        current['replyto'] = parent_num
                    else:
                        this_num = old
                    current['cnum'] = autonum = int(this_num)
            elif field.startswith('_comment'):      # Comment edits
                rev = int(field[8:])
                comment_history.setdefault(rev, {}).update({'comment': old})
                comment_history.setdefault(rev + 1, {}).update(
                        {'author': author, 'date': from_utimestamp(int(new))})
            elif (old or new) and old != new:
                current['fields'][field] = {
                    'old': old, 'new': new,
                    'label': field_labels.get(field, field)}
        if current:
            last_comment = comment_history[max(comment_history)]
            last_comment['comment'] = current['comment']
            yield current


class DefaultTicketPolicy(Component):
    """Default permission policy for the ticket system.

    * Users with `MILESTONE_VIEW` can edit the ticket milestone field.
    * Authenticated users with `TICKET_APPEND` or `TICKET_CHGPROP` can
      edit the description of a ticket they reported.
    * Authenticated users with `TICKET_APPEND` can edit their own ticket
      comments.
    * The CC field can be edited when creating a ticket even if the
      user doesn't have `TICKET_EDIT_CC`.
    """

    implements(IPermissionPolicy)

    realm = TicketSystem.realm

    def check_permission(self, action, username, resource, perm):

        if action == 'TICKET_CHG_MILESTONE' and \
                self._is_valid_resource(resource, 'milestone') and \
                'MILESTONE_VIEW' in perm:
            return True

        if action == 'TICKET_EDIT_DESCRIPTION' and \
                username != 'anonymous' and \
                self._is_valid_resource(resource, self.realm) and \
                ('TICKET_CHGPROP' in perm or 'TICKET_APPEND' in perm):
            ticket = model.Ticket(self.env, resource.id)
            if username == ticket['reporter']:
                return True

        if action == 'TICKET_EDIT_COMMENT' and \
                username != 'anonymous' and \
                self._is_valid_resource(resource, 'comment') and \
                self._is_valid_resource(resource.parent, self.realm) and \
                'TICKET_APPEND' in perm(resource.parent):
            ticket = model.Ticket(self.env, resource.parent.id)
            change = ticket.get_change(resource.id)
            if change and username == change['author']:
                return True

        if action == 'TICKET_EDIT_CC' and \
                self._is_valid_resource(resource, self.realm, exists=False):
            ticket = model.Ticket(self.env, resource.id)
            if not ticket.exists:
                return True

    def _is_valid_resource(self, resource, expected_realm, exists=True):
        return resource and resource.realm == expected_realm and \
               (resource.id is not None if exists else resource.id is None)
