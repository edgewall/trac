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
import pkg_resources
import re
from StringIO import StringIO

from genshi.core import Markup
from genshi.builder import tag

from trac.attachment import AttachmentModule
from trac.config import BoolOption, Option, IntOption
from trac.core import *
from trac.mimeview.api import Mimeview, IContentConverter, Context
from trac.resource import Resource, ResourceNotFound, get_resource_url, \
                         render_resource_link, get_resource_shortname
from trac.search import ISearchSource, search_to_sql, shorten_result
from trac.ticket.api import TicketSystem, ITicketManipulator
from trac.ticket.model import Milestone, Ticket, group_milestones
from trac.ticket.notification import TicketNotifyEmail
from trac.timeline.api import ITimelineEventProvider
from trac.util import as_bool, get_reporter_id
from trac.util.compat import any
from trac.util.datefmt import format_datetime, from_utimestamp, \
                              to_utimestamp, utc
from trac.util.text import exception_to_unicode, obfuscate_email_address, \
                           shorten_line, to_unicode
from trac.util.presentation import separated
from trac.util.translation import _, tag_, tagn_, N_, gettext, ngettext
from trac.versioncontrol.diff import get_diff_options, diff_blocks
from trac.web import arg_list_to_args, parse_arg_list, IRequestHandler
from trac.web.chrome import add_link, add_notice, add_script, add_stylesheet, \
                            add_warning, add_ctxtnav, prevnext_nav, Chrome, \
                            INavigationContributor, ITemplateProvider
from trac.wiki.formatter import format_to, format_to_html, format_to_oneliner


class InvalidTicket(TracError):
    """Exception raised when a ticket fails validation."""
    title = N_("Invalid Ticket")


class TicketModule(Component):

    implements(IContentConverter, INavigationContributor, IRequestHandler,
               ISearchSource, ITemplateProvider, ITimelineEventProvider)

    ticket_manipulators = ExtensionPoint(ITicketManipulator)

    timeline_details = BoolOption('timeline', 'ticket_show_details', 'false',
        """Enable the display of all ticket changes in the timeline, not only
        open / close operations (''since 0.9'').""")

    max_description_size = IntOption('ticket', 'max_description_size', 262144,
        """Don't accept tickets with a too big description.
        (''since 0.11'').""")

    max_comment_size = IntOption('ticket', 'max_comment_size', 262144,
        """Don't accept tickets with a too big comment.
        (''since 0.11.2'')""")

    timeline_newticket_formatter = Option('timeline', 'newticket_formatter',
                                          'oneliner',
        """Which formatter flavor (e.g. 'html' or 'oneliner') should be
        used when presenting the description for new tickets.
        If 'oneliner', the [timeline] abbreviated_messages option applies.
        (''since 0.11'').""")

    preserve_newlines = Option('ticket', 'preserve_newlines', 'default',
        """Whether Wiki formatter should respect the new lines present
        in the Wiki text.
        If set to 'default', this is equivalent to 'yes' for new environments
        but keeps the old behavior for upgraded environments (i.e. 'no').
        (''since 0.11'').""")

    ticketlink_query = Option('query', 'ticketlink_query',
        default='?status=!closed', 
        doc="""The base query to be used when linkifying values of ticket
            fields. The query is a URL query
            string starting with `?` as used in `query:`
            [TracQuery#UsingTracLinks Trac links].
            (''since 0.12'')""")

    def __init__(self):
        self._warn_for_default_attr = set()

    def __getattr__(self, name):
        """Delegate access to ticket default Options which were move to
        TicketSystem.

        .. todo:: remove in 0.13
        """
        if name.startswith('default_'):
            if name not in self._warn_for_default_attr:
                self.log.warning("%s option should be accessed via "
                                 "TicketSystem component", name)
                self._warn_for_default_attr.add(name)
            return getattr(TicketSystem(self.env), name)
        raise AttributeError("TicketModule has no attribute '%s'" % name)

    @property
    def must_preserve_newlines(self):
        preserve_newlines = self.preserve_newlines
        if preserve_newlines == 'default':
            preserve_newlines = self.env.get_version(initial=True) >= 21 # 0.11
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
            return self.export_rss(req, ticket)

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        if re.match(r'/newticket/?', req.path_info):
            return 'newticket'
        return 'tickets'

    def get_navigation_items(self, req):
        if 'TICKET_CREATE' in req.perm:
            yield ('mainnav', 'newticket', 
                   tag.a(_("New Ticket"), href=req.href.newticket(),
                         accesskey=7))

    # IRequestHandler methods

    def match_request(self, req):
        if req.path_info == "/newticket":
            return True
        match = re.match(r'/ticket/([0-9]+)$', req.path_info)
        if match:
            req.args['id'] = match.group(1)
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
        if not 'ticket' in filters:
            return
        ticket_realm = Resource('ticket')
        db = self.env.get_db_cnx()
        sql, args = search_to_sql(db, ['summary', 'keywords', 'description',
                                         'reporter', 'cc', 
                                         db.cast('id', 'text')], terms)
        sql2, args2 = search_to_sql(db, ['newvalue'], terms)
        sql3, args3 = search_to_sql(db, ['value'], terms)
        cursor = db.cursor()
        cursor.execute("""
            SELECT summary,description,reporter,type,id,time,status,resolution 
            FROM ticket
            WHERE id IN (
                SELECT id FROM ticket WHERE %s
              UNION
                SELECT ticket FROM ticket_change
                WHERE field='comment' AND %s
              UNION
                SELECT ticket FROM ticket_custom WHERE %s
            )
            """ % (sql, sql2, sql3), args + args2 + args3)
        ticketsystem = TicketSystem(self.env)
        for summary, desc, author, type, tid, ts, status, resolution in cursor:
            t = ticket_realm(id=tid)
            if 'TICKET_VIEW' in req.perm(t):
                yield (req.href.ticket(tid),
                       tag_("%(title)s: %(message)s",
                            title=tag.span(get_resource_shortname(self.env, t),
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
                yield ('ticket_details', _("Ticket updates"), False)

    def get_timeline_events(self, req, start, stop, filters):
        ts_start = to_utimestamp(start)
        ts_stop = to_utimestamp(stop)

        status_map = {'new': ('newticket', N_("created")),
                      'reopened': ('reopenedticket', N_("reopened")),
                      'closed': ('closedticket', N_("closed")),
                      'edit': ('editedticket', N_("updated"))}

        ticket_realm = Resource('ticket')

        field_labels = TicketSystem(self.env).get_ticket_field_labels()

        def produce_event((id, ts, author, type, summary, description),
                          status, fields, comment, cid):
            ticket = ticket_realm(id=id)
            if 'TICKET_VIEW' not in req.perm(ticket):
                return None
            resolution = fields.get('resolution')
            info = ''
            if status == 'edit':
                if 'ticket_details' in filters:
                    if len(fields) > 0:
                        labels = [tag.i(field_labels.get(k, k.capitalize()))
                                  for k in fields.keys()]
                        info = tagn_("%(labels)s changed",
                                     "%(labels)s changed", len(labels),
                                     labels=separated(labels, ', ')) + tag.br()
                else:
                    return None
            elif 'ticket' in filters:
                if status == 'closed' and resolution:
                    if resolution and comment:
                        info = _("%(title)s: %(message)s", title=resolution,
                                 message='') # typographical translation (fr)
                    else:
                        info = resolution
            else:
                return None
            kind, verb = status_map[status]
            return (kind, from_utimestamp(ts), author,
                    (ticket, verb, info, summary, status, resolution, type,
                     description, comment, cid))

        # Ticket changes
        db = self.env.get_db_cnx()
        if 'ticket' in filters or 'ticket_details' in filters:
            cursor = db.cursor()

            cursor.execute("""
                SELECT t.id,tc.time,tc.author,t.type,t.summary, 
                       tc.field,tc.oldvalue,tc.newvalue 
                FROM ticket_change tc 
                    INNER JOIN ticket t ON t.id = tc.ticket 
                        AND tc.time>=%s AND tc.time<=%s 
                ORDER BY tc.time
                """ % (ts_start, ts_stop))
            data = None
            for id,t,author,type,summary,field,oldvalue,newvalue in cursor:
                if not (oldvalue or newvalue):
                    # ignore empty change from custom field created or deleted
                    continue 
                if not data or (id, t) != data[:2]:
                    if data:
                        ev = produce_event(data, status, fields, comment, cid)
                        if ev:
                            yield ev
                    status, fields, comment, cid = 'edit', {}, '', None
                    data = (id, t, author, type, summary, None)
                if field == 'comment':
                    comment = newvalue
                    cid = oldvalue and oldvalue.split('.')[-1]
                    # Always use the author from the comment field
                    data = data[:2] + (author,) + data[3:]
                elif field == 'status' and newvalue in ('reopened', 'closed'):
                    status = newvalue
                elif field[0] != '_': # properties like _comment{n} are hidden
                    fields[field] = newvalue
            if data:
                ev = produce_event(data, status, fields, comment, cid)
                if ev:
                    yield ev

            # New tickets
            if 'ticket' in filters:
                cursor.execute("""
                    SELECT id,time,reporter,type,summary,description
                    FROM ticket WHERE time>=%s AND time<=%s
                    """, (ts_start, ts_stop))
                for row in cursor:
                    ev = produce_event(row, 'new', {}, None, None)
                    if ev:
                        yield ev

            # Attachments
            if 'ticket_details' in filters:
                for event in AttachmentModule(self.env).get_timeline_events(
                    req, ticket_realm, start, stop):
                    yield event

    def render_timeline_event(self, context, field, event):
        ticket, verb, info, summary, status, resolution, type, \
                description, comment, cid = event[3]
        if field == 'url':
            href = context.href.ticket(ticket.id)
            if cid:
                href += '#comment:' + cid
            return href
        elif field == 'title':
            title = TicketSystem(self.env).format_summary(summary, status,
                                                          resolution, type)
            return tag_("Ticket %(ticketref)s (%(summary)s) %(verb)s",
                        ticketref=tag.em('#', ticket.id, title=title),
                        summary=shorten_line(summary), verb=gettext(verb))
        elif field == 'description':
            descr = message = ''
            if status == 'new':
                message = description
            else:
                descr = info
                message = comment
            t_context = context(resource=ticket)
            t_context.set_hints(preserve_newlines=self.must_preserve_newlines)
            if status == 'new' and \
                    context.get_hint('wiki_flavor') == 'oneliner': 
                flavor = self.timeline_newticket_formatter
                t_context.set_hints(wiki_flavor=flavor,
                                    shorten_lines=flavor == 'oneliner')
            return descr + format_to(self.env, None, t_context, message)

    # Internal methods

    def _get_action_controllers(self, req, ticket, action):
        """Generator yielding the controllers handling the given `action`"""
        for controller in TicketSystem(self.env).action_controllers:
            actions = [a for w, a in
                       controller.get_ticket_actions(req, ticket) or []]
            if action in actions:
                yield controller

    def _process_newticket_request(self, req):
        req.perm.require('TICKET_CREATE')
        ticket = Ticket(self.env)

        plain_fields = True # support for /newticket?version=0.11 GETs
        field_reporter = 'reporter'

        if req.method == 'POST':
            plain_fields = False
            field_reporter = 'field_reporter'
            if 'field_owner' in req.args and 'TICKET_MODIFY' not in req.perm:
                del req.args['field_owner']

        self._populate(req, ticket, plain_fields)
        ticket.values['status'] = 'new'     # Force initial status
        reporter_id = req.args.get(field_reporter) or \
                      get_reporter_id(req, 'author')
        ticket.values['reporter'] = reporter_id

        valid = None
        if req.method == 'POST' and not 'preview' in req.args:
            valid = self._validate_ticket(req, ticket)
            if valid:
                self._do_create(req, ticket) # (redirected if successful)
            # else fall through in a preview
            req.args['preview'] = True

        # don't validate for new tickets and don't validate twice
        if valid is None and 'preview' in req.args:
            valid = self._validate_ticket(req, ticket)
            
        # Preview a new ticket
        data = self._prepare_data(req, ticket)        
        data.update({
            'author_id': reporter_id,
            'actions': [],
            'version': None,
            'description_change': None,
            'valid': valid
        })

        fields = self._prepare_fields(req, ticket)

        # setup default values for the new ticket
        
        for field in fields:
            ticket.values.setdefault(field['name'], field.get('value'))

        # position 'owner' immediately before 'cc',
        # if not already positioned after (?)

        field_names = [field['name'] for field in ticket.fields
                       if not field.get('custom')]
        if 'owner' in field_names:
            curr_idx = field_names.index('owner')
            if 'cc' in field_names:
                insert_idx = field_names.index('cc')
            else:
                insert_idx = len(field_names)
            if curr_idx < insert_idx:
                ticket.fields.insert(insert_idx, ticket.fields[curr_idx])
                del ticket.fields[curr_idx]

        data['fields'] = fields

        add_stylesheet(req, 'common/css/ticket.css')
        add_script(req, 'common/js/folding.js')
        Chrome(self.env).add_wiki_toolbars(req)
        return 'ticket.html', data, None

    def _process_ticket_request(self, req):
        id = int(req.args.get('id'))
        version = req.args.get('version', None)
        if version is not None:
            try:
                version = int(version)
            except ValueError:
                version = None

        req.perm('ticket', id, version).require('TICKET_VIEW')
        ticket = Ticket(self.env, id, version=version)
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
            cnum = int(req.args['cnum'])
            return self._render_comment_history(req, ticket, data, cnum)
        elif action == 'comment-diff':
            cnum = int(req.args['cnum'])
            return self._render_comment_diff(req, ticket, data, cnum)
        elif 'preview_comment' in req.args:
            field_changes = {}
            data.update({'action': None,
                         'reassign_owner': req.authname,
                         'resolve_resolution': None,
                         'timestamp': str(ticket['changetime'])})
        elif req.method == 'POST': # 'Preview' or 'Submit'
            if 'cancel_comment' in req.args:
                req.redirect(req.href.ticket(ticket.id))
            elif 'edit_comment' in req.args:
                comment = req.args.get('edited_comment', '')
                cnum = int(req.args['cnum_edit'])
                change = ticket.get_change(cnum)
                if not (req.authname and req.authname != 'anonymous'
                        and change and change['author'] == req.authname):
                    req.perm(ticket.resource).require('TICKET_EDIT_COMMENT')
                ticket.modify_comment(change['date'], req.authname, comment)
                req.redirect(req.href.ticket(ticket.id) + '#comment:%d' % cnum)

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
                                 tracini=tag.tt('trac.ini')))

            # Apply changes made by the workflow
            self._apply_ticket_changes(ticket, field_changes)
            # Unconditionally run the validation so that the user gets
            # information any and all problems.  But it's only valid if it
            # validates and there were no problems with the workflow side of
            # things.
            valid = self._validate_ticket(req, ticket, not valid) and valid
            if 'preview' not in req.args:
                if valid:
                    # redirected if successful
                    self._do_save(req, ticket, action)
                # else fall through in a preview
                req.args['preview'] = True

            # Preview an existing ticket (after a Preview or a failed Save)
            data.update({
                'action': action,
                'timestamp': req.args.get('ts'),
                'reassign_owner': (req.args.get('reassign_choice') 
                                   or req.authname),
                'resolve_resolution': req.args.get('resolve_choice'),
                'valid': valid
                })
        else: # simply 'View'ing the ticket
            field_changes = {}
            data.update({'action': None,
                         'reassign_owner': req.authname,
                         'resolve_resolution': None,
                         # Store a timestamp for detecting "mid air collisions"
                         'timestamp': str(ticket['changetime'])})

        data.update({'comment': req.args.get('comment'),
                     'cnum_edit': req.args.get('cnum_edit'),
                     'edited_comment': req.args.get('edited_comment'),
                     'cnum_hist': req.args.get('cnum_hist'),
                     'cversion': req.args.get('cversion')})

        self._insert_ticket_data(req, ticket, data,
                                 get_reporter_id(req, 'author'), field_changes)

        mime = Mimeview(self.env)
        format = req.args.get('format')
        if format:
            # FIXME: mime.send_converted(context, ticket, 'ticket_x') (#3332)
            filename = ('t%d' % ticket.id, None)[format == 'rss']
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
            db = self.env.get_db_cnx()
            cursor = db.cursor()
            cursor.execute("SELECT min(id), max(id) FROM ticket")
            for (min_id, max_id) in cursor:
                min_id = int(min_id)
                max_id = int(max_id)
                if min_id < ticket.id:
                    add_ticket_link('first', min_id)
                    cursor.execute("SELECT max(id) FROM ticket WHERE id < %s",
                                   (ticket.id,))
                    for (prev_id,) in cursor:
                        add_ticket_link('prev', int(prev_id))
                if ticket.id < max_id:
                    add_ticket_link('last', max_id)
                    cursor.execute("SELECT min(id) FROM ticket WHERE %s < id",
                                   (ticket.id,))
                    for (next_id,) in cursor:
                        add_ticket_link('next', int(next_id))
                break

        add_stylesheet(req, 'common/css/ticket.css')
        add_script(req, 'common/js/folding.js')
        Chrome(self.env).add_wiki_toolbars(req)
        Chrome(self.env).add_auto_preview(req)

        # Add registered converters
        for conversion in mime.get_supported_conversions('trac.ticket.Ticket'):
            format = conversion[0]
            conversion_href = get_resource_url(self.env, ticket.resource,
                                               req.href, format=format)
            add_link(req, 'alternate', conversion_href, conversion[1],
                     conversion[4], format)
                     
        prevnext_nav(req, _("Previous Ticket"), _("Next Ticket"), 
                     _("Back to Query"))

        return 'ticket.html', data, None

    def _prepare_data(self, req, ticket, absurls=False):
        return {'ticket': ticket,
                'context': Context.from_request(req, ticket.resource,
                                                absurls=absurls),
                'preserve_newlines': self.must_preserve_newlines}

    def _toggle_cc(self, req, cc):
        """Return an (action, recipient) tuple corresponding to a change
        of CC status for this user relative to the current `cc_list`."""
        entries = []
        email = req.session.get('email', '').strip()
        if email:
            entries.append(email)
        if req.authname != 'anonymous':
            entries.append(req.authname)
        else:
            author = get_reporter_id(req, 'author').strip()
            if author and author != 'anonymous':
                email = author.split()[-1]
                if (email[0], email[-1]) == ('<', '>'):
                    email = email[1:-1]
                entries.append(email)
        add = []
        remove = []
        cc_list = Chrome(self.env).cc_list(cc)
        for entry in entries:
            if entry in cc_list:
                remove.append(entry)
            else:
                add.append(entry)
        action = entry = ''
        if remove:
            action, entry = ('remove', remove[0])
        elif add:
            action, entry = ('add', add[0])
        return (action, entry, cc_list)
        
    def _populate(self, req, ticket, plain_fields=False):
        if not plain_fields:
            fields = dict([(k[6:], v) for k, v in req.args.iteritems()
                           if k.startswith('field_')])
        else:
            fields = req.args.copy()
        # Prevent direct changes to protected fields (status and resolution are
        # set in the workflow, in get_ticket_changes())
        for each in Ticket.protected_fields:
            fields.pop(each, None)
            fields.pop('checkbox_' + each, None)    # See Ticket.populate()
        ticket.populate(fields)
        # special case for updating the Cc: field
        if 'cc_update' in req.args:
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
        history = [c for c in history if any([f in text_fields
                                              for f in c['fields']])]
        history.append({'version': 0, 'comment': "''Initial version''",
                        'date': ticket['time'],
                        'author': ticket['reporter'] # not 100% accurate...
                        })
        data.update({'title': _("Ticket History"),
                     'resource': ticket.resource,
                     'history': history})

        add_ctxtnav(req, _("Back to Ticket #%(num)s", num=ticket.id),
                           req.href.ticket(ticket.id))
        return 'history_view.html', data, None

    def _render_diff(self, req, ticket, data, text_fields):
        """Show differences between two versions of a ticket description.

        `text_fields` is optionally a list of fields of interest, that are
        considered for jumping to the next change.
        """
        new_version = int(req.args.get('version', 1))
        old_version = int(req.args.get('old_version', new_version))
        if old_version > new_version:
            old_version, new_version = new_version, old_version

        # get the list of versions having a description change
        history = self._get_history(req, ticket)
        changes = {}
        descriptions = []
        old_idx = new_idx = -1 # indexes in descriptions
        for change in history:
            version = change['version']
            changes[version] = change
            if any([f in text_fields for f in change['fields']]):
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
            for version in range(from_version, to_version+1):
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
                    prop = {'name': label, 'field': k,
                            'old': {'name': label, 'value': old},
                            'new': {'name': label, 'value': new}}
                    rendered = self._render_property_diff(req, ticket, k,
                                                          old, new, tnew)
                    if rendered:
                        prop['diff'] = tag.li(
                            tag_("Property %(label)s %(rendered)s",
                                 label=tag.strong(label), rendered=rendered))
                    props.append(prop)
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
            old_text = old_text and old_text.splitlines() or []
            new_text = new_ticket.get(field)
            new_text = new_text and new_text.splitlines() or []
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

        return 'diff_view.html', data, None

    def _make_comment_url(self, req, ticket, cnum, version=None):
        return req.href.ticket(ticket.id,
                               cnum_hist=version is not None and cnum or None,
                               cversion=version) + '#comment:%d' % cnum

    def _get_comment_history(self, req, ticket, cnum):
        history = []
        for version, date, author, comment in ticket.get_comment_history(cnum):
            history.append({
                'version': version, 'date': date, 'author': author,
                'comment': version == 0 and _("''Initial version''") or '',
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
        return 'history_view.html', data, None

    def _render_comment_diff(self, req, ticket, data, cnum):
        """Show differences between two versions of a ticket comment."""
        req.perm(ticket.resource).require('TICKET_VIEW')
        new_version = int(req.args.get('version', 1))
        old_version = int(req.args.get('old_version', new_version))
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
                return text and text.splitlines() or []
            except KeyError:
                raise ResourceNotFound(_("No version %(version)d for comment "
                                         "%(cnum)d on ticket #%(ticket)s",
                                         version=version, cnum=cnum,
                                         ticket=ticket.id))
        
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

        return 'diff_view.html', data, None

    def export_csv(self, req, ticket, sep=',', mimetype='text/plain'):
        # FIXME: consider dumping history of changes here as well
        #        as one row of output doesn't seem to be terribly useful...
        fields = [f for f in ticket.fields 
                  if f['name'] not in ('time', 'changetime')]
        content = StringIO()
        writer = csv.writer(content, delimiter=sep, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(['id'] + [unicode(f['name']) for f in fields])

        context = Context.from_request(req, ticket.resource)
        cols = [unicode(ticket.id)]
        for f in fields:
            name = f['name']
            value = ticket.values.get(name, '')
            if name in ('cc', 'reporter'):
                value = Chrome(self.env).format_emails(context, value, ' ')
            elif name in ticket.time_fields:
                value = format_datetime(value, tzinfo=req.tz)
            cols.append(value.encode('utf-8'))
        writer.writerow(cols)
        return (content.getvalue(), '%s;charset=utf-8' % mimetype)

    def export_rss(self, req, ticket):
        changes = []
        change_summary = {}

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
                                                  'application/rss+xml')
        return output, 'application/rss+xml'

    # Ticket validation and changes
    
    def _validate_ticket(self, req, ticket, force_collision_check=False):
        valid = True
        resource = ticket.resource

        # If the ticket has been changed, check the proper permissions
        if ticket.exists and ticket._old:
            # Status and resolution can be modified by the workflow even
            # without having TICKET_CHGPROP
            changed = set(ticket._old) - set(['status', 'resolution'])
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
                ticket.values.update(ticket._old)

        comment = req.args.get('comment')
        if comment:
            if not ('TICKET_CHGPROP' in req.perm(resource) or \
                    'TICKET_APPEND' in req.perm(resource)):
                add_warning(req, _("No permissions to add a comment."))
                valid = False

        # Mid air collision?
        if ticket.exists and (ticket._old or comment or force_collision_check):
            if req.args.get('ts') != str(ticket['changetime']):
                add_warning(req, _("Sorry, can not save your changes. "
                              "This ticket has been modified by someone else "
                              "since you started"))
                valid = False

        # Always require a summary
        if not ticket['summary']:
            add_warning(req, _("Tickets must contain a summary."))
            valid = False
            
        # Always validate for known values
        for field in ticket.fields:
            if 'options' not in field:
                continue
            if field['name'] == 'status':
                continue
            name = field['name']
            if name in ticket.values and name in ticket._old:
                value = ticket[name]
                if value:
                    if value not in field['options']:
                        add_warning(req, '"%s" is not a valid value for '
                                    'the %s field.' % (value, name))
                        valid = False
                elif not field.get('optional', False):
                    add_warning(req, _("field %(name)s must be set",
                                       name=name))
                    valid = False

        # Validate description length
        if len(ticket['description'] or '') > self.max_description_size:
            add_warning(req, _("Ticket description is too long (must be less "
                               "than %(num)s characters)",
                               num=self.max_description_size))
            valid = False

        # Validate comment length
        if len(comment or '') > self.max_comment_size:
            add_warning(req, _("Ticket comment is too long (must be less "
                               "than %(num)s characters)",
                               num=self.max_comment_size))
            valid = False

        # Validate comment numbering
        try:
            # comment index must be a number
            int(req.args.get('cnum') or 0)
            # replyto must be 'description' or a number
            replyto = req.args.get('replyto')
            if replyto != 'description':
                int(replyto or 0)
        except ValueError:
            # Shouldn't happen in "normal" circumstances, hence not a warning
            raise InvalidTicket(_("Invalid comment threading identifier"))

        # Custom validation rules
        for manipulator in self.ticket_manipulators:
            for field, message in manipulator.validate_ticket(req, ticket):
                valid = False
                if field:
                    add_warning(req, _("The ticket field '%(field)s' is "
                                       "invalid: %(message)s",
                                       field=field, message=message))
                else:
                    add_warning(req, message)
        return valid

    def _do_create(self, req, ticket):
        ticket.insert()

        # Notify
        try:
            tn = TicketNotifyEmail(self.env)
            tn.notify(ticket, newticket=True)
        except Exception, e:
            self.log.error("Failure sending notification on creation of "
                    "ticket #%s: %s", ticket.id, exception_to_unicode(e))
            add_warning(req, _("The ticket has been created, but an error "
                               "occurred while sending notifications: "
                               "%(message)s", message=to_unicode(e)))

        # Redirect the user to the newly created ticket or add attachment
        ticketref=tag.a('#', ticket.id, href=req.href.ticket(ticket.id))
        if 'attachment' in req.args:
            add_notice(req, tag_("The ticket %(ticketref)s has been created. "
                                 "You can now attach the desired files.",
                                 ticketref=ticketref))
            req.redirect(req.href.attachment('ticket', ticket.id,
                                             action='new'))
        if 'TICKET_VIEW' not in req.perm('ticket', ticket.id):
            add_notice(req, tag_("The ticket %(ticketref)s has been created, "
                                 "but you don't have permission to view it.",
                                 ticketref=ticketref))
            req.redirect(req.href.newticket())
        req.redirect(req.href.ticket(ticket.id))

    def _do_save(self, req, ticket, action):
        cnum = req.args.get('cnum')
        replyto = req.args.get('replyto')
        internal_cnum = cnum
        if cnum and replyto: # record parent.child relationship
            internal_cnum = '%s.%s' % (replyto, cnum)

        # Save the action controllers we need to call side-effects for before
        # we save the changes to the ticket.
        controllers = list(self._get_action_controllers(req, ticket, action))

        # -- Save changes

        fragment = ''
        now = datetime.now(utc)
        if ticket.save_changes(get_reporter_id(req, 'author'),
                                     req.args.get('comment'), when=now,
                                     cnum=internal_cnum):
            fragment = cnum and '#comment:' + cnum or ''
            try:
                tn = TicketNotifyEmail(self.env)
                tn.notify(ticket, newticket=False, modtime=now)
            except Exception, e:
                self.log.error("Failure sending notification on change to "
                        "ticket #%s: %s", ticket.id, exception_to_unicode(e))
                # TRANSLATOR: The 'change' has been saved... (link)
                change = _('change')
                if fragment:
                    change = tag.a(change, href=fragment)
                add_warning(req, tag_("The %(change)s has been saved, but an "
                                      "error occurred while sending "
                                      "notifications: %(message)s",
                                      change=change, message=to_unicode(e)))
                fragment = ''

        # After saving the changes, apply the side-effects.
        for controller in controllers:
            self.env.log.debug("Side effect for %s" %
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
            for key in action_changes.keys():
                old = ticket[key]
                new = action_changes[key]
                # Check for conflicting changes between controllers
                if key in field_changes:
                    last_new = field_changes[key]['new']
                    last_by = field_changes[key]['by'] 
                    if last_new != new and last_by:
                        problems.append('%s changed "%s" to "%s", '
                                        'but %s changed it to "%s".' %
                                        (cname, key, new, last_by, last_new))
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

    def _query_link(self, req, name, value, text=None):
        """Return a link to /query with the appropriate name and value"""
        default_query = self.ticketlink_query.startswith('?') and \
                        self.ticketlink_query[1:] or self.ticketlink_query
        args = arg_list_to_args(parse_arg_list(default_query))
        args[name] = value
        return tag.a(text or value, href=req.href.query(args))

    def _query_link_words(self, context, name, value):
        """Splits a list of words and makes a query link to each separately"""
        if not isinstance(value, basestring): # None or other non-splitable
            return value
        default_query = self.ticketlink_query.startswith('?') and \
                        self.ticketlink_query[1:] or self.ticketlink_query
        args = arg_list_to_args(parse_arg_list(default_query))
        items = []
        for i, word in enumerate(re.split(r'([;,\s]+)', value)):
            if i % 2:
                items.append(word)
            elif word:
                rendered = name != 'cc' and word \
                           or Chrome(self.env).format_emails(context, word)
                if rendered == word:
                    word_args = args.copy()
                    word_args[name] = '~' + word
                    items.append(tag.a(word,
                                       href=context.href.query(word_args)))
                else:
                    items.append(rendered)
        return tag(items)

    def _prepare_fields(self, req, ticket):
        context = Context.from_request(req, ticket.resource)
        fields = []
        owner_field = None
        for field in ticket.fields:
            name = field['name']
            type_ = field['type']
 
            # enable a link to custom query for all choice fields
            if type_ not in ['text', 'textarea']:
                field['rendered'] = self._query_link(req, name, ticket[name])

            # per field settings
            if name in ('summary', 'reporter', 'description', 'status',
                        'resolution', 'time', 'changetime'):
                field['skip'] = True
            elif name == 'owner':
                TicketSystem(self.env).eventually_restrict_owner(field, ticket)
                type_ = field['type']
                field['skip'] = True
                if not ticket.exists:
                    field['label'] = _("Owner")
                    if 'TICKET_MODIFY' in req.perm(ticket.resource):
                        field['skip'] = False
                        owner_field = field
            elif name == 'milestone':
                milestones = [Milestone(self.env, opt)
                              for opt in field['options']]
                milestones = [m for m in milestones
                              if 'MILESTONE_VIEW' in req.perm(m.resource)]
                groups = group_milestones(milestones, ticket.exists 
                    and 'TICKET_ADMIN' in req.perm(ticket.resource))
                field['options'] = []
                field['optgroups'] = [
                    {'label': label, 'options': [m.name for m in milestones]}
                    for (label, milestones) in groups]
                milestone = Resource('milestone', ticket[name])
                field['rendered'] = render_resource_link(self.env, context,
                                                         milestone, 'compact')
            elif name == 'keywords':
                field['rendered'] = self._query_link_words(context, name,
                                                           ticket[name])
            elif name == 'cc':
                field['rendered'] = self._query_link_words(context, name,
                                                           ticket[name])
                if ticket.exists and \
                        'TICKET_EDIT_CC' not in req.perm(ticket.resource):
                    cc = ticket._old.get('cc', ticket['cc'])
                    cc_action, cc_entry, cc_list = self._toggle_cc(req, cc)
                    field['edit_label'] = {
                            'add': _("Add to Cc"),
                            'remove': _("Remove from Cc"),
                            '': _("Add/Remove from Cc")}[cc_action]
                    field['cc_entry'] = cc_entry or _("<Author field>")
                    field['cc_update'] = 'cc_update' in req.args or None

            # per type settings
            if type_ in ('radio', 'select'):
                if ticket.exists:
                    value = ticket.values.get(name)
                    options = field['options']
                    optgroups = []
                    for x in field.get('optgroups', []):
                        optgroups.extend(x['options'])
                    if value and \
                        (not value in options and \
                         not value in optgroups):
                        # Current ticket value must be visible,
                        # even if it's not among the possible values
                        options.append(value)
            elif type_ == 'checkbox':
                value = ticket.values.get(name)
                if value in ('1', '0'):
                    field['rendered'] = self._query_link(req, name, value,
                                value == '1' and _("yes") or _("no"))
            elif type_ == 'text':
                if field.get('format') == 'wiki':
                    field['rendered'] = format_to_oneliner(self.env, context,
                                                           ticket[name])
            elif type_ == 'textarea':
                if field.get('format') == 'wiki':
                    field['rendered'] = \
                        format_to_html(self.env, context, ticket[name],
                                escape_newlines=self.must_preserve_newlines)
            
            # ensure sane defaults
            field.setdefault('optional', False)
            field.setdefault('options', [])
            field.setdefault('skip', False)
            fields.append(field)
        
        # Move owner field to end when shown
        if owner_field is not None:
            fields.remove(owner_field)
            fields.append(owner_field)
        return fields
        
    def _insert_ticket_data(self, req, ticket, data, author_id, field_changes):
        """Insert ticket data into the template `data`"""
        replyto = req.args.get('replyto')
        data['replyto'] = replyto
        data['version'] = ticket.resource.version
        data['description_change'] = None

        data['author_id'] = author_id

        # -- Ticket fields

        fields = self._prepare_fields(req, ticket)

        # -- Ticket Change History

        def quote_original(author, original, link):
            if 'comment' not in req.args: # i.e. the comment was not yet edited
                data['comment'] = '\n'.join(
                    ["Replying to [%s %s]:" % (link,
                                        obfuscate_email_address(author))] +
                    ["> %s" % line for line in original.splitlines()] + [''])

        if replyto == 'description':
            quote_original(ticket['reporter'], ticket['description'],
                           'ticket:%d' % ticket.id)
        values = {}
        replies = {}
        changes = []
        cnum = 0
        skip = False
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
            if not skip:
                changes.append(change)

        if ticket.resource.version is not None:
            ticket.values.update(values)

        # -- Workflow support
        
        selected_action = req.args.get('action')
        
        # action_controls is an ordered list of "renders" tuples, where
        # renders is a list of (action_key, label, widgets, hints) representing
        # the user interface for each action
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
        if not selected_action:
            if action_controls:
                selected_action = action_controls[0][0]

        # Insert change preview
        change_preview = {
            'date': datetime.now(utc),
            'author': author_id,
            'fields': field_changes,
            'preview': True,
            'comment': req.args.get('comment', data.get('comment')),
        }
        replyto = req.args.get('replyto')
        if replyto:
            change_preview['replyto'] = replyto
        if req.method == 'POST':
            self._apply_ticket_changes(ticket, field_changes)
            self._render_property_changes(req, ticket, field_changes)

        if ticket.resource.version is not None: ### FIXME
            ticket.values.update(values)

        context = Context.from_request(req, ticket.resource)

        # Display the owner and reporter links when not obfuscated
        chrome = Chrome(self.env)
        for user in 'reporter', 'owner':
            if chrome.format_author(req, ticket[user]) == ticket[user]:
                data['%s_link' % user] = self._query_link(req, user,
                                                            ticket[user])
        data.update({
            'context': context,
            'fields': fields, 'changes': changes,
            'replies': replies, 'cnum': cnum + 1,
            'attachments': AttachmentModule(self.env).attachment_data(context),
            'action_controls': action_controls,
            'action': selected_action,
            'change_preview': change_preview,
        })

    def rendered_changelog_entries(self, req, ticket, when=None):
        """Iterate on changelog entries, consolidating related changes
        in a `dict` object.
        """
        attachment_realm = ticket.resource.child('attachment')
        for group in self.grouped_changelog_entries(ticket, None, when):
            t = ticket.resource(version=group.get('cnum', None))
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
            rendered = self._render_property_diff(req, ticket, field, old, new,
                                                  resource_new)
            if rendered:
                changes['rendered'] = rendered

    def _render_property_diff(self, req, ticket, field, old, new, 
                              resource_new=None):
        rendered = None
        # per type special rendering of diffs
        type_ = None
        for f in ticket.fields:
            if f['name'] == field:
                type_ = f['type']
                break
        if type_ == 'checkbox':
            rendered = new == '1' and _("set") or _("unset")
        elif type_ == 'textarea':
            if not resource_new:
                rendered = _("modified")
            else:
                href = get_resource_url(self.env, resource_new, req.href,
                                        action='diff')
                # TRANSLATOR: modified ('diff') (link)
                diff = tag.a(_("diff"), href=href)
                rendered = tag_("modified (%(diff)s)", diff=diff)

        # per name special rendering of diffs
        old_list, new_list = None, None
        render_elt = lambda x: x
        sep = ', '
        if field == 'cc':
            chrome = Chrome(self.env)
            old_list, new_list = chrome.cc_list(old), chrome.cc_list(new)
            if not (Chrome(self.env).show_email_addresses or 
                    'EMAIL_VIEW' in req.perm(resource_new or ticket.resource)):
                render_elt = obfuscate_email_address
        elif field == 'keywords':
            old_list, new_list = old.split(), new.split()
            sep = ' '
        if (old_list, new_list) != (None, None):
            added = [tag.em(render_elt(x)) for x in new_list 
                     if x not in old_list]
            remvd = [tag.em(render_elt(x)) for x in old_list
                     if x not in new_list]
            added = added and tagn_("%(items)s added", "%(items)s added",
                                    len(added), items=separated(added, sep))
            remvd = remvd and tagn_("%(items)s removed", "%(items)s removed",
                                    len(remvd), items=separated(remvd, sep))
            if added or remvd:
                rendered = tag(added, added and remvd and _("; "), remvd)
        if field in ('reporter', 'owner'):
            if not (Chrome(self.env).show_email_addresses or 
                    'EMAIL_VIEW' in req.perm(resource_new or ticket.resource)):
                old = obfuscate_email_address(old)
                new = obfuscate_email_address(new)
            if old and not new:
                rendered = tag_("%(value)s deleted", value=tag.em(old))
            elif new and not old:
                rendered = tag_("set to %(value)s", value=tag.em(new))
            elif old and new:
                rendered = tag_("changed from %(old)s to %(new)s",
                                old=tag.em(old), new=tag.em(new))
        return rendered

    def grouped_changelog_entries(self, ticket, db, when=None):
        """Iterate on changelog entries, consolidating related changes
        in a `dict` object.
        """
        field_labels = TicketSystem(self.env).get_ticket_field_labels()
        changelog = ticket.get_changelog(when=when, db=db)
        autonum = 0 # used for "root" numbers
        last_uid = current = None
        for date, author, field, old, new, permanent in changelog:
            uid = permanent and (date,) or (date, author)
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
                        {'author': author, 'date': from_utimestamp(long(new))})
            elif (old or new) and old != new:
                current['fields'][field] = {
                    'old': old, 'new': new,
                    'label': field_labels.get(field, field)}
        if current:
            last_comment = comment_history[max(comment_history)]
            last_comment['comment'] = current['comment']
            yield current
