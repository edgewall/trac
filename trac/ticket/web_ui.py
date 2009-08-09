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
import os
import pkg_resources
import re
from StringIO import StringIO
import time

from genshi.core import Markup
from genshi.builder import tag

from trac.attachment import AttachmentModule
from trac.config import BoolOption, Option, IntOption, _TRUE_VALUES
from trac.core import *
from trac.mimeview.api import Mimeview, IContentConverter, Context
from trac.resource import Resource, get_resource_url, \
                         render_resource_link, get_resource_shortname
from trac.search import ISearchSource, search_to_sql, shorten_result
from trac.ticket.api import TicketSystem, ITicketManipulator, \
                            ITicketActionController
from trac.ticket.model import Milestone, Ticket, group_milestones
from trac.ticket.notification import TicketNotifyEmail
from trac.timeline.api import ITimelineEventProvider
from trac.util import get_reporter_id
from trac.util.compat import any
from trac.util.datefmt import to_timestamp, utc
from trac.util.text import CRLF, shorten_line, obfuscate_email_address, \
                           exception_to_unicode
from trac.util.presentation import separated
from trac.util.translation import _
from trac.versioncontrol.diff import get_diff_options, diff_blocks
from trac.web import IRequestHandler
from trac.web.chrome import add_link, add_script, add_stylesheet, \
                            add_warning, add_ctxtnav, prevnext_nav, Chrome, \
                            INavigationContributor, ITemplateProvider
from trac.wiki.formatter import format_to, format_to_html, format_to_oneliner

class InvalidTicket(TracError):
    """Exception raised when a ticket fails validation."""
    title = "Invalid Ticket"


class TicketModule(Component):

    implements(IContentConverter, INavigationContributor, IRequestHandler,
               ISearchSource, ITemplateProvider, ITimelineEventProvider)

    ticket_manipulators = ExtensionPoint(ITicketManipulator)

    default_version = Option('ticket', 'default_version', '',
        """Default version for newly created tickets.""")

    default_type = Option('ticket', 'default_type', 'defect',
        """Default type for newly created tickets (''since 0.9'').""")

    default_priority = Option('ticket', 'default_priority', 'major',
        """Default priority for newly created tickets.""")

    default_milestone = Option('ticket', 'default_milestone', '',
        """Default milestone for newly created tickets.""")

    default_component = Option('ticket', 'default_component', '',
        """Default component for newly created tickets.""")

    default_severity = Option('ticket', 'default_severity', '',
        """Default severity for newly created tickets.""")

    default_summary = Option('ticket', 'default_summary', '',
        """Default summary (title) for newly created tickets.""")

    default_description = Option('ticket', 'default_description', '',
        """Default description for newly created tickets.""")

    default_keywords = Option('ticket', 'default_keywords', '',
        """Default keywords for newly created tickets.""")

    default_owner = Option('ticket', 'default_owner', '',
        """Default owner for newly created tickets.""")

    default_cc = Option('ticket', 'default_cc', '',
        """Default cc: list for newly created tickets.""")

    default_resolution = Option('ticket', 'default_resolution', 'fixed',
        """Default resolution for resolving (closing) tickets
        (''since 0.11'').""")

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

    def _must_preserve_newlines(self):
        preserve_newlines = self.preserve_newlines
        if preserve_newlines == 'default':
            preserve_newlines = self.env.get_version(initial=True) >= 21 # 0.11
        return preserve_newlines in _TRUE_VALUES
    must_preserve_newlines = property(_must_preserve_newlines)

    # IContentConverter methods

    def get_supported_conversions(self):
        yield ('csv', _('Comma-delimited Text'), 'csv',
               'trac.ticket.Ticket', 'text/csv', 8)
        yield ('tab', _('Tab-delimited Text'), 'tsv',
               'trac.ticket.Ticket', 'text/tab-separated-values', 8)
        yield ('rss', _('RSS Feed'), 'xml',
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
                   tag.a(_('New Ticket'), href=req.href.newticket(),
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
            yield ('ticket', 'Tickets')

    def get_search_results(self, req, terms, filters):
        if not 'ticket' in filters:
            return
        ticket_realm = Resource('ticket')
        db = self.env.get_db_cnx()
        sql, args = search_to_sql(db, ['b.newvalue'], terms)
        sql2, args2 = search_to_sql(db, ['summary', 'keywords', 'description',
                                         'reporter', 'cc', 
                                         db.cast('id', 'text')], terms)
        sql3, args3 = search_to_sql(db, ['c.value'], terms)
        cursor = db.cursor()
        cursor.execute("SELECT DISTINCT a.summary,a.description,a.reporter, "
                       "a.type,a.id,a.time,a.status,a.resolution "
                       "FROM ticket a "
                       "LEFT JOIN ticket_change b ON a.id = b.ticket "
                       "LEFT OUTER JOIN ticket_custom c ON (a.id = c.ticket) "
                       "WHERE (b.field='comment' AND %s) OR %s OR %s" % 
                       (sql, sql2, sql3), args + args2 + args3)
        ticketsystem = TicketSystem(self.env)
        for summary, desc, author, type, tid, ts, status, resolution in cursor:
            t = ticket_realm(id=tid)
            if 'TICKET_VIEW' in req.perm(t):
                yield (req.href.ticket(tid),
                       tag(tag.span(get_resource_shortname(self.env, t),
                                    class_=status),
                           ': ',
                           ticketsystem.format_summary(summary, status,
                                                       resolution, type)),
                       datetime.fromtimestamp(ts, utc), author,
                       shorten_result(desc, terms))
        
        # Attachments
        for result in AttachmentModule(self.env).get_search_results(
            req, ticket_realm, terms):
            yield result        

    # ITimelineEventProvider methods

    def get_timeline_filters(self, req):
        if 'TICKET_VIEW' in req.perm:
            yield ('ticket', _('Opened and closed tickets'))
            if self.timeline_details:
                yield ('ticket_details', _('Ticket updates'), False)

    def get_timeline_events(self, req, start, stop, filters):
        ts_start = to_timestamp(start)
        ts_stop = to_timestamp(stop)

        status_map = {'new': ('newticket', 'created'),
                      'reopened': ('reopenedticket', 'reopened'),
                      'closed': ('closedticket', 'closed'),
                      'edit': ('editedticket', 'updated')}

        ticket_realm = Resource('ticket')

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
                        keys = fields.keys()
                        info = tag([[tag.i(f), ', '] for f in keys[:-1]],
                                   tag.i(keys[-1]), ' changed', tag.br())
                else:
                    return None
            elif 'ticket' in filters:
                if status == 'closed' and resolution:
                    info = resolution
                    if info and comment:
                        info += ': '
            else:
                return None
            kind, verb = status_map[status]
            return (kind, datetime.fromtimestamp(ts, utc), author,
                    (ticket, verb, info, summary, status, resolution, type,
                     description, comment, cid))

        # Ticket changes
        db = self.env.get_db_cnx()
        if 'ticket' in filters or 'ticket_details' in filters:
            cursor = db.cursor()

            cursor.execute("SELECT t.id,tc.time,tc.author,t.type,t.summary, "
                           "       tc.field,tc.oldvalue,tc.newvalue "
                           "  FROM ticket_change tc "
                           "    INNER JOIN ticket t ON t.id = tc.ticket "
                           "      AND tc.time>=%s AND tc.time<=%s "
                           "ORDER BY tc.time"
                           % (ts_start, ts_stop))
            previous_update = None
            for id,t,author,type,summary,field,oldvalue,newvalue in cursor:
                if not previous_update or (id,t,author) != previous_update[:3]:
                    if previous_update:
                        ev = produce_event(previous_update, status, fields,
                                           comment, cid)
                        if ev:
                            yield ev
                    status, fields, comment, cid = 'edit', {}, '', None
                    previous_update = (id, t, author, type, summary, None)
                if field == 'comment':
                    comment = newvalue
                    cid = oldvalue and oldvalue.split('.')[-1]
                elif field == 'status' and newvalue in ('reopened', 'closed'):
                    status = newvalue
                else:
                    fields[field] = newvalue
            if previous_update:
                ev = produce_event(previous_update, status, fields,
                                   comment, cid)
                if ev:
                    yield ev

            # New tickets
            if 'ticket' in filters:
                cursor.execute("SELECT id,time,reporter,type,summary,"
                               "description"
                               "  FROM ticket WHERE time>=%s AND time<=%s",
                               (ts_start, ts_stop))
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
            return tag('Ticket ', tag.em('#', ticket.id, title=title),
                       ' (', shorten_line(summary), ') ', verb)
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
            actions = [a for w,a in
                       controller.get_ticket_actions(req, ticket)]
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
        data['comment'] = None
        

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
        elif req.method == 'POST': # 'Preview' or 'Submit'
            # Do any action on the ticket?
            actions = TicketSystem(self.env).get_available_actions(
                req, ticket)
            if action not in actions:
                raise TracError(_('Invalid action "%(name)s"', name=action))
                # (this should never happen in normal situations)

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
                for problem in problems:
                    add_warning(req, problem)
                    add_warning(req,
                                tag(tag.p('Please review your configuration, '
                                          'probably starting with'),
                                    tag.pre('[trac]\nworkflow = ...\n'),
                                    tag.p('in your ', tag.tt('trac.ini'), '.'))
                                )

            self._apply_ticket_changes(ticket, field_changes) # Apply changes made by the workflow
            # Unconditionally run the validation so that the user gets
            # information any and all problems.  But it's only valid if it
            # validates and there were no problems with the workflow side of
            # things.
            valid = self._validate_ticket(req, ticket) and not problems
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
                'comment': req.args.get('comment'),
                'valid': valid
                })
        else: # simply 'View'ing the ticket
            field_changes = None
            data.update({'action': None,
                         'reassign_owner': req.authname,
                         'resolve_resolution': None,
                         # Store a timestamp for detecting "mid air collisions"
                         'timestamp': str(ticket.time_changed)})

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
                         'Ticket #%s' % id)

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

        # Add registered converters
        for conversion in mime.get_supported_conversions('trac.ticket.Ticket'):
            format = conversion[0]
            conversion_href = get_resource_url(self.env, ticket.resource,
                                               req.href, format=format)
            add_link(req, 'alternate', conversion_href, conversion[1],
                     conversion[4], format)
                     
        prevnext_nav(req, _('Ticket'), _('Back to Query'))

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
        fields = req.args
        if not plain_fields:
            fields = dict([(k[6:],v) for k,v in fields.items()
                           if k.startswith('field_')])
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
                        'date': ticket.time_created,
                        'author': ticket['reporter'] # not 100% accurate...
                        })
        data.update({'title': _('Ticket History'),
                     'resource': ticket.resource,
                     'history': history})

        add_ctxtnav(req, 'Back to Ticket #%s'%ticket.id, req.href.ticket(ticket.id))
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
            raise TracError(_('No differences to show'))

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

        changes = []

        def version_info(t, field=None):
            path = 'Ticket #%s' % ticket.id
            # TODO: field info should probably be part of the Resource as well
            if field:
                path = tag(path, Markup(' &ndash; '), field)
            if t.version:
                rev = _('Version %(num)s', num=t.version)
                shortrev = 'v%d' % t.version
            else:
                rev, shortrev = _('Initial Version'), _('initial')
            return {'path':  path, 'rev': rev, 'shortrev': shortrev,
                    'href': get_resource_url(self.env, t, req.href)}

        # -- prop changes
        props = []
        for k, v in new_ticket.iteritems():
            if k not in text_fields:
                old, new = old_ticket[k], new_ticket[k]
                if old != new:
                    prop = {'name': k,
                            'old': {'name': k, 'value': old},
                            'new': {'name': k, 'value': new}}
                    rendered = self._render_property_diff(req, ticket, k,
                                                          old, new, tnew)
                    if rendered:
                        prop['diff'] = tag.li('Property ', tag.strong(k),
                                                   ' ', rendered)
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

            changes.append({'diffs': diffs, 'props': [],
                            'new': version_info(tnew, field),
                            'old': version_info(told, field)})

        # -- prev/up/next links
        if prev_version:
            add_link(req, 'prev', get_resource_url(self.env, ticket.resource,
                                                   req.href, action='diff',
                                                   version=prev_version),
                     _('Version %(num)s', num=prev_version))
        add_link(req, 'up', get_resource_url(self.env, ticket.resource,
                                             req.href, action='history'),
                 'Ticket History')
        if next_version:
            add_link(req, 'next', get_resource_url(self.env, ticket.resource,
                                                   req.href, action='diff',
                                                   version=next_version),
                     _('Version %(num)s', num=next_version))

        prevnext_nav(req, _('Change'), _('Ticket History'))
        add_stylesheet(req, 'common/css/diff.css')
        add_script(req, 'common/js/diff.js')

        data.update({
            'title': _('Ticket Diff'),
            'resource': ticket.resource,
            'old_version': old_version, 'new_version': new_version,
            'changes': changes, 'diff': diff_data,
            'num_changes': num_changes, 'change': new_change,
            'old_ticket': old_ticket, 'new_ticket': new_ticket,
            'longcol': '', 'shortcol': ''
        })

        return 'diff_view.html', data, None

    def export_csv(self, req, ticket, sep=',', mimetype='text/plain'):
        # FIXME: consider dumping history of changes here as well
        #        as one row of output doesn't seem to be terribly useful...
        content = StringIO()
        writer = csv.writer(content, delimiter=sep, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(['id'] + [unicode(f['name']) for f in ticket.fields])

        context = Context.from_request(req, ticket.resource)
        cols = [unicode(ticket.id)]
        for f in ticket.fields:
            name = f['name']
            value = ticket.values.get(name, '')
            if name in ('cc', 'reporter'):
                value = Chrome(self.env).format_emails(context, value, ' ')
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
            change['title'] = '; '.join(['%s %s' % (', '.join(v), k) for k, v \
                                         in change_summary.iteritems()])

        data = self._prepare_data(req, ticket, absurls=True)
        data['changes'] = changes
        output = Chrome(self.env).render_template(req, 'ticket.rss', data,
                                                  'application/rss+xml')
        return output, 'application/rss+xml'

    # Ticket validation and changes
    
    def _validate_ticket(self, req, ticket):
        valid = True
        resource = ticket.resource

        # If the ticket has been changed, check the proper permissions
        if ticket.exists and ticket._old:
            cnt = 0
            # EDIT_DESCRIPTION and CHGPROP are independent permissions
            if 'description' in ticket._old:
                cnt = 1
                if 'TICKET_EDIT_DESCRIPTION' not in req.perm(resource):
                    add_warning(req, _("No permission to edit description."))
                    valid = False
            if len(ticket._old) > cnt:
                errmsg = _("No permission to change ticket fields.")
                if 'TICKET_CHGPROP' not in req.perm(resource):
                    add_warning(req, errmsg)
                    valid = False
                else: # per-field additional checks
                   if 'reporter' in ticket._old and \
                       'TICKET_ADMIN' not in req.perm(resource):
                    add_warning(req, errmsg)
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
        if ticket.exists and (ticket._old or comment):
            if req.args.get('ts') != str(ticket.time_changed):
                add_warning(req, _("Sorry, can not save your changes. "
                              "This ticket has been modified by someone else "
                              "since you started"))
                valid = False

        # Always require a summary
        if not ticket['summary']:
            add_warning(req, _('Tickets must contain a summary.'))
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
                    add_warning(req, 'field %s must be set' % name)
                    valid = False

        # Validate description length
        if len(ticket['description'] or '') > self.max_description_size:
            add_warning(req, _('Ticket description is too long (must be less '
                          'than %(num)s characters)',
                          num=self.max_description_size))
            valid = False

        # Validate comment length
        if len(comment or '') > self.max_comment_size:
            add_warning(req, _('Ticket comment is too long (must be less '
                               'than %(num)s characters)',
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
            raise InvalidTicket(_('Invalid comment threading identifier'))

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
        req.perm(ticket.resource).require('TICKET_VIEW')

        # Notify
        try:
            tn = TicketNotifyEmail(self.env)
            tn.notify(ticket, newticket=True)
        except Exception, e:
            self.log.error("Failure sending notification on creation of "
                    "ticket #%s: %s", ticket.id, exception_to_unicode(e))

        # Redirect the user to the newly created ticket or add attachment
        if 'attachment' in req.args:
            req.redirect(req.href.attachment('ticket', ticket.id,
                                             action='new'))
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

        now = datetime.now(utc)
        if ticket.save_changes(get_reporter_id(req, 'author'),
                                     req.args.get('comment'), when=now,
                                     cnum=internal_cnum):
            try:
                tn = TicketNotifyEmail(self.env)
                tn.notify(ticket, newticket=False, modtime=now)
            except Exception, e:
                self.log.error("Failure sending notification on change to "
                        "ticket #%s: %s", ticket.id, exception_to_unicode(e))

        # After saving the changes, apply the side-effects.
        for controller in controllers:
            self.env.log.debug('Side effect for %s' %
                               controller.__class__.__name__)
            controller.apply_action_side_effects(req, ticket, action)

        fragment = cnum and '#comment:'+cnum or ''
        req.redirect(req.href.ticket(ticket.id) + fragment)

    def get_ticket_changes(self, req, ticket, selected_action):
        """Returns a dictionary of field changes.
        
        The field changes are represented as:
        `{field: {'old': oldvalue, 'new': newvalue, 'by': what}, ...}`
        """
        # Start with user changes
        field_changes = {}
        for field, value in ticket._old.iteritems():
            field_changes[field] = {'old': value,
                                    'new': ticket[field],
                                    'by':'user'}

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
                field_changes[key] = {'old': old, 'new': new, 'by': cname}

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

    def _prepare_fields(self, req, ticket):
        context = Context.from_request(req, ticket.resource)
        fields = []
        owner_field = None
        for field in ticket.fields:
            name = field['name']
            type_ = field['type']
 
            # per field settings
            if name in ('summary', 'reporter', 'description', 'status',
                        'resolution'):
                field['skip'] = True
            elif name == 'owner':
                TicketSystem(self.env).eventually_restrict_owner(field, ticket)
                type_ = field['type']
                field['skip'] = True
                if not ticket.exists:
                    field['label'] = 'Assign to'
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
            elif name == 'cc':
                emails = Chrome(self.env).format_emails(context, ticket[name])
                field['rendered'] = emails
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
                    field['rendered'] = value == '1' and _('yes') or _('no')
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
                    ['Replying to [%s %s]:' % (link,
                                        obfuscate_email_address(author))] +
                    ['> %s' % line for line in original.splitlines()] + [''])

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
        change_preview = None
        if req.method == 'POST':
            self._apply_ticket_changes(ticket, field_changes)
            self._render_property_changes(req, ticket, field_changes)
            change_preview = {
                'date': datetime.now(utc),
                'author': author_id,
                'fields': field_changes,
                'preview': True,
            }
            comment = req.args.get('comment')
            if comment:
                change_preview['comment'] = comment
            replyto = req.args.get('replyto')
            if replyto:
                change_preview['replyto'] = replyto

        if ticket.resource.version is not None: ### FIXME
            ticket.values.update(values)

        context = Context.from_request(req, ticket.resource)
        data.update({
            'context': context,
            'fields': fields, 'changes': changes,
            'replies': replies, 'cnum': cnum + 1,
            'attachments': AttachmentModule(self.env).attachment_data(context),
            'action_controls': action_controls,
            'action': selected_action,
            'change_preview': change_preview
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
            rendered = new == '1' and "set" or "unset"
        elif type_ == 'textarea':
            if not resource_new:
                rendered = _('modified')
            else:
                href = get_resource_url(self.env, resource_new, req.href,
                                        action='diff')
                rendered = tag('modified (', tag.a('diff', href=href), ')')

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
            old_list, new_list = (old or '').split(), new.split()
            sep = ' '
        if (old_list, new_list) != (None, None):
            added = [tag.em(render_elt(x)) for x in new_list 
                     if x not in old_list]
            remvd = [tag.em(render_elt(x)) for x in old_list
                     if x not in new_list]
            added = added and tag(separated(added, sep), " added")
            remvd = remvd and tag(separated(remvd, sep), " removed")
            if added or remvd:
                rendered = tag(added, added and remvd and '; ', remvd)
        if field in ('reporter', 'owner'):
            if not (Chrome(self.env).show_email_addresses or 
                    'EMAIL_VIEW' in req.perm(resource_new or ticket.resource)):
                old = obfuscate_email_address(old)
                new = obfuscate_email_address(new)
            if old and not new:
                rendered = tag(tag.em(old), " deleted")
            elif new and not old:
                rendered = tag("set to ", tag.em(new))
            elif old and new:
                rendered = tag("changed from ", tag.em(old),
                               " to ", tag.em(new))
        return rendered

    def grouped_changelog_entries(self, ticket, db, when=None):
        """Iterate on changelog entries, consolidating related changes
        in a `dict` object.
        """
        changelog = ticket.get_changelog(when=when, db=db)
        autonum = 0 # used for "root" numbers
        last_uid = current = None
        for date, author, field, old, new, permanent in changelog:
            uid = date, author, permanent
            if uid != last_uid:
                if current:
                    yield current
                last_uid = uid
                current = {'date': date, 'author': author, 'fields': {},
                           'permanent': permanent, 'comment': ''}
                if permanent and not when:
                    autonum += 1
                    current['cnum'] = autonum
            # some common processing for fields
            if field == 'comment':
                current['comment'] = new
                if old:
                    if '.' in old: # retrieve parent.child relationship
                        parent_num, this_num = old.split('.', 1)
                        current['replyto'] = parent_num
                    else:
                        this_num = old
                    current['cnum'] = int(this_num)
            elif old or new:
                current['fields'][field] = {'old': old, 'new': new}
        if current:
            yield current
