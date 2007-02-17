# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2006 Edgewall Software
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

from datetime import datetime
import os
import re
from StringIO import StringIO
import time

from genshi.core import Markup
from genshi.builder import tag

from trac.attachment import Attachment, AttachmentModule
from trac.config import BoolOption, Option
from trac.context import Context
from trac.core import *
from trac.mimeview.api import Mimeview, IContentConverter
from trac.search import ISearchSource, search_to_sql, shorten_result
from trac.ticket import Milestone, Ticket, TicketSystem, ITicketManipulator
from trac.ticket.notification import TicketNotifyEmail
from trac.timeline.api import ITimelineEventProvider, TimelineEvent
from trac.util import get_reporter_id
from trac.util.compat import any
from trac.util.datefmt import to_timestamp, utc
from trac.util.text import CRLF, shorten_line
from trac.versioncontrol.diff import get_diff_options, diff_blocks
from trac.web import IRequestHandler
from trac.web.chrome import add_link, add_script, add_stylesheet, \
                            INavigationContributor, Chrome

class InvalidTicket(TracError):
    """Exception raised when a ticket fails validation."""


class TicketModule(Component):

    implements(IContentConverter, INavigationContributor, IRequestHandler,
               ISearchSource, ITimelineEventProvider)

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
        """Default component for newly created tickets""")

    timeline_details = BoolOption('timeline', 'ticket_show_details', 'false',
        """Enable the display of all ticket changes in the timeline
        (''since 0.9'').""")

    # IContentConverter methods

    def get_supported_conversions(self):
        yield ('csv', 'Comma-delimited Text', 'csv',
               'trac.ticket.Ticket', 'text/csv', 8)
        yield ('tab', 'Tab-delimited Text', 'tsv',
               'trac.ticket.Ticket', 'text/tab-separated-values', 8)
        yield ('rss', 'RSS Feed', 'xml',
               'trac.ticket.Ticket', 'application/rss+xml', 8)

    def convert_content(self, req, mimetype, ticket, key):
        if key == 'csv':
            return self.export_csv(ticket, mimetype='text/csv')
        elif key == 'tab':
            return self.export_csv(ticket, sep='\t',
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
                   tag.a('New Ticket', href=req.href.newticket(), accesskey=7))

    # IRequestHandler methods

    def match_request(self, req):
        if re.match(r'/newticket/?$', req.path_info) is not None:
            return True
        match = re.match(r'/ticket/([0-9]+)$', req.path_info)
        if match:
            req.args['id'] = match.group(1)
            return True

    def process_request(self, req):
        if 'id' in req.args:
            return self.process_ticket_request(req)
        return self.process_newticket_request(req)

    def process_newticket_request(self, req):
        context = Context(self.env, req)('ticket')
        req.perm.require('TICKET_CREATE')

        if req.method == 'POST' and 'field_owner' in req.args and \
               'TICKET_MODIFY' not in req.perm:
            del req.args['field_owner']

        if req.method == 'POST' and 'preview' not in req.args:
            self._do_create(context) # ...redirected

        # Preview a new ticket
        ticket = Ticket(self.env, db=context.db)
        context = context('ticket', ticket.id, resource=ticket)
        
        self._populate(req, ticket)
        ticket.values['reporter'] = get_reporter_id(req, 'reporter')

        data = {}
        data['ticket'] = ticket
        data['context'] = context

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

        data['fields'] = []
        for field in ticket.fields:
            name = field['name']
            if name in ('summary', 'reporter', 'description', 'status',
                        'resolution'):
                field['skip'] = True
            elif name == 'owner':
                field['label'] = 'Assign to'
                if 'TICKET_MODIFY' not in req.perm:
                    field['skip'] = True
            elif name == 'milestone':
                # Don't make completed milestones available for selection
                options = [opt for opt in field['options'] if not
                           Milestone(self.env, opt, db=context.db).is_completed]
                # TODO:    context('milestone', opt).resource.is_completed
                field['options'] = options
            data['fields'].append(field)

        if 'TICKET_APPEND' in req.perm:
            data['can_attach'] = True
            data['attachment'] = req.args.get('attachment')

        add_stylesheet(req, 'common/css/ticket.css')
        return 'ticket_new.html', data, None

    def process_ticket_request(self, req):
        req.perm.require('TICKET_VIEW')
        action = req.args.get('action', ('history' in req.args and 'history' or
                                         'view'))
        id = int(req.args.get('id'))
        
        context = Context(self.env, req)('ticket', id)
        
        ticket = context.resource
        
        data = {}
        data['ticket'] = ticket
        data['context'] = context
        
        if action in ('history', 'diff'):
            field = req.args.get('field')
            if field:
                text_fields = [field]
            else:
                text_fields = [field['name'] for field in 
                               TicketSystem(self.env).get_ticket_fields() if
                               field['type'] == 'textarea']
            if action == 'history':
                return self._render_history(context, data, text_fields)
            elif action == 'diff':
                return self._render_diff(context, data, text_fields)
        elif req.method == 'POST':
            if 'preview' not in req.args:
                self._do_save(context)
            else:
                # Use user supplied values
                self._populate(req, ticket)
                self._validate_ticket(req, ticket)

                data['action'] = action
                data['timestamp'] = req.args.get('ts')
                data['reassign_owner'] = req.args.get('reassign_choice') \
                                         or req.authname
                data['resolve_resolution'] = req.args.get('resolve_choice')
                comment = req.args.get('comment')
                if comment:
                    data['comment'] = comment
        else:
            data['reassign_owner'] = req.authname
            # Store a timestamp in order to detect "mid air collisions"
            data['timestamp'] = str(ticket.time_changed)

        self._insert_ticket_data(context, data, get_reporter_id(req, 'author'))

        mime = Mimeview(self.env)
        format = req.args.get('format')
        if format:
            mime.send_converted(req, 'trac.ticket.Ticket', ticket, format,
                                'ticket_%d' % ticket.id)

        def add_ticket_link(css_class, id):
            ctx = context('ticket', id)
            add_link(req, css_class, ctx.resource_href(), ctx.name())

        global_sequence = True
        # If the ticket is being shown in the context of a query, add
        # links to help navigate in the query result set
        if 'query_tickets' in req.session:
            tickets = req.session['query_tickets'].split()
            if str(id) in tickets:
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
            cursor.execute("SELECT max(id) FROM ticket")
            for max_id, in cursor:
                max_id = int(max_id)
                if ticket.id > 1:
                    add_ticket_link('first', 1)
                    add_ticket_link('prev', ticket.id - 1)
                if ticket.id < max_id:
                    add_ticket_link('next', ticket.id + 1)
                    add_ticket_link('last', max_id)

        add_stylesheet(req, 'common/css/ticket.css')

        # Add registered converters
        for conversion in mime.get_supported_conversions('trac.ticket.Ticket'):
            conversion_href = req.href.ticket(ticket.id, format=conversion[0])
            add_link(req, 'alternate', conversion_href, conversion[1],
                     conversion[3])

        return 'ticket_view.html', data, None

    def _populate(self, req, ticket):
        ticket.populate(dict([(k[6:],v) for k,v in req.args.iteritems()
                              if k.startswith('field_')]))

    def _get_history(self, context):
        ticket = context.resource
        history = []
        for change in self.grouped_changelog_entries(ticket, context.db):
            if change['permanent']:
                change['version'] = change['cnum']
                history.append(change)
        return history
        
    def _render_history(self, context, data, text_fields):
        """Extract the history for a ticket description."""
        
        req = context.req
        ticket = context.resource
        req.perm.require('TICKET_VIEW')

        history = self._get_history(context)
        history.reverse()
        history = [c for c in history if any([f in text_fields
                                              for f in c['fields']])]
        history.append({'version': 0, 'comment': "''Initial version''",
                        'date': ticket.time_created,
                        'author': ticket['reporter'] # not 100% accurate...
                        })
        data.update({'title': 'Ticket History', 'history': history})

        return 'history_view.html', data, None

    def _render_diff(self, context, data, text_fields):
        """Show differences between two versions of a ticket description.

        `text_fields` is optionally a list of fields of interest, that are
        considered for jumping to the next change.
        """
        req = context.req
        ticket = context.resource
        req.perm.require('TICKET_VIEW')

        new_version = int(req.args.get('version', 1))
        old_version = int(req.args.get('old_version', new_version))
        if old_version > new_version:
            old_version, new_version = new_version, old_version

        # get the list of versions having a description change
        history = self._get_history(context)
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
            raise TracError('No differences to show')

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

        def version_info(v, field=None):
            path = context.name()
            # TODO: field info should probably be part of the Context as well
            if field:
                path = tag(path, Markup(' &ndash; '), field)
            if v:
                rev, shortrev = 'Version %d' % v, 'v%d' % v
            else:
                rev, shortrev = 'Initial Version', 'initial'
            return {'path':  path, 'rev': rev, 'shortrev': shortrev,
                    'href': context.resource_href(version=v)}

        # -- prop changes
        props = []
        for k, v in new_ticket.iteritems():
            if k not in text_fields:
                old, new = old_ticket[k], new_ticket[k]
                if old != new:
                    props.append({'name': k, 'old': old, 'new': new})
        changes.append({'props': props,
                        'new': version_info(new_version),
                        'old': version_info(old_version)})


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

            changes.append({'diffs': diffs,
                            'new': version_info(new_version, field),
                            'old': version_info(old_version, field)})

        # -- prev/up/next links
        if prev_version:
            add_link(req, 'prev', req.href.ticket(ticket.id, action='diff',
                                                  version=prev_version),
                     'Version %d' % prev_version)
        add_link(req, 'up', req.href.ticket(ticket.id, action='history'),
                 'Ticket History')
        if next_version:
            add_link(req, 'next', req.href.ticket(ticket.id, action='diff',
                                                  version=next_version),
                     'Version %d' % next_version)

        add_stylesheet(req, 'common/css/diff.css')
        add_script(req, 'common/js/diff.js')
        
        data.update({
            'title': 'Ticket Diff',
            'old_version': old_version, 'new_version': new_version,
            'changes': changes, 'diff': diff_data,
            'num_changes': num_changes, 'change': new_change,
            'old_ticket': old_ticket, 'new_ticket': new_ticket
            })
        
        return 'diff_view.html', data, None

    # ISearchSource methods

    def get_search_filters(self, req):
        if 'TICKET_VIEW' in req.perm:
            yield ('ticket', 'Tickets')

    def get_search_results(self, req, terms, filters):
        if not 'ticket' in filters:
            return
        context = Context(self.env, req)
        db = context.db
        sql, args = search_to_sql(db, ['b.newvalue'], terms)
        sql2, args2 = search_to_sql(db, ['summary', 'keywords', 'description',
                                         'reporter', 'cc', 'id'], terms)
        cursor = db.cursor()
        cursor.execute("SELECT DISTINCT a.summary,a.description,a.reporter, "
                       "a.type,a.id,a.time,a.status,a.resolution "
                       "FROM ticket a "
                       "LEFT JOIN ticket_change b ON a.id = b.ticket "
                       "WHERE (b.field='comment' AND %s ) OR %s" % (sql, sql2),
                       args + args2)
        for summary, desc, author, type, tid, ts, status, resolution in cursor:
            ctx = context('ticket', tid)
            yield (ctx.resource_href(),
                   tag(tag.span(ctx.shortname(), class_=status), ': ',
                       ctx.format_summary(summary, status, resolution, type)),
                   datetime.fromtimestamp(ts, utc), author,
                   shorten_result(desc, terms))

    # ITimelineEventProvider methods

    def get_timeline_filters(self, req):
        if 'TICKET_VIEW' in req.perm:
            yield ('ticket', 'Ticket changes')
            if self.timeline_details:
                yield ('ticket_details', 'Ticket details', False)

    def get_timeline_events(self, req, start, stop, filters):
        start = to_timestamp(start)
        stop = to_timestamp(stop)

        status_map = {'new': ('newticket', 'created'),
                      'reopened': ('newticket', 'reopened'),
                      'closed': ('closedticket', 'closed'),
                      'edit': ('editedticket', 'updated')}
        context = Context(self.env, req)

        def produce((id, ts, author, type, summary), status, fields,
                    comment, cid):
            ctx = context('ticket', id)
            info = ''
            resolution = fields.get('resolution')
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
            title = ctx.format_summary(summary, status, resolution, type)
            title = tag('Ticket ', tag.em(ctx.shortname(), title=title),
                        ' (', shorten_line(summary), ') ', verb)
            ticket_href = ctx.resource_href()
            if cid:
                ticket_href += '#comment:' + cid
            markup = message = None
            if status == 'new':
                markup = summary
            else:
                markup = info
                message = comment
            t = datetime.fromtimestamp(ts, utc)
            event = TimelineEvent(kind, title, ticket_href, markup)
            event.set_changeinfo(t, author)
            event.set_context(ctx, message)
            return event

        # Ticket changes
        if 'ticket' in filters or 'ticket_details' in filters:
            cursor = context.db.cursor()

            cursor.execute("SELECT t.id,tc.time,tc.author,t.type,t.summary, "
                           "       tc.field,tc.oldvalue,tc.newvalue "
                           "  FROM ticket_change tc "
                           "    INNER JOIN ticket t ON t.id = tc.ticket "
                           "      AND tc.time>=%s AND tc.time<=%s "
                           "ORDER BY tc.time"
                           % (start, stop))
            previous_update = None
            for id,t,author,type,summary,field,oldvalue,newvalue in cursor:
                if not previous_update or (id,t,author) != previous_update[:3]:
                    if previous_update:
                        ev = produce(previous_update, status, fields,
                                     comment, cid)
                        if ev:
                            yield ev
                    status, fields, comment, cid = 'edit', {}, '', None
                    previous_update = (id, t, author, type, summary)
                if field == 'comment':
                    comment = newvalue
                    cid = oldvalue and oldvalue.split('.')[-1]
                elif field == 'status' and newvalue in ('reopened', 'closed'):
                    status = newvalue
                else:
                    fields[field] = newvalue
            if previous_update:
                ev = produce(previous_update, status, fields, comment, cid)
                if ev:
                    yield ev

            # New tickets
            if 'ticket' in filters:
                cursor.execute("SELECT id,time,reporter,type,summary"
                               "  FROM ticket WHERE time>=%s AND time<=%s",
                               (start, stop))
                for row in cursor:
                    yield produce(row, 'new', {}, None, None)

            # Attachments
            if 'ticket_details' in filters:
                for event in AttachmentModule(self.env) \
                        .get_timeline_events(context('ticket'), start, stop):
                    yield event

    # Internal methods

    def export_csv(self, ticket, sep=',', mimetype='text/plain'):
        content = StringIO()
        content.write(sep.join(['id'] + [f['name'] for f in ticket.fields])
                      + CRLF)
        content.write(sep.join([unicode(ticket.id)] +
                                [ticket.values.get(f['name'], '')
                                 .replace(sep, '_').replace('\\', '\\\\')
                                 .replace('\n', '\\n').replace('\r', '\\r')
                                 for f in ticket.fields]) + CRLF)
        return (content.getvalue(), '%s;charset=utf-8' % mimetype)

    def export_rss(self, req, ticket):
        db = self.env.get_db_cnx()
        changes = []
        change_summary = {}

        for change in self.grouped_changelog_entries(ticket, db):
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

        data = {
            'ticket': ticket,
            'context': Context(self.env, req, 'ticket', ticket.id, db=db),
            'changes': changes,
        }

        output = Chrome(self.env).render_template(req, 'ticket.rss', data,
                                                  'application/rss+xml')
        return output, 'application/rss+xml'

    def _validate_ticket(self, req, ticket):
        # Always validate for known values
        for field in ticket.fields:
            if 'options' not in field:
                continue
            name = field['name']
            if name in ticket.values and name in ticket._old:
                value = ticket[name]
                if value:
                    if value not in field['options']:
                        raise InvalidTicket('"%s" is not a valid value for '
                                            'the %s field.' % (value, name))
                elif not field.get('optional', False):
                    raise InvalidTicket('field %s must be set' % name)

        # Custom validation rules
        for manipulator in self.ticket_manipulators:
            for field, message in manipulator.validate_ticket(req, ticket):
                if field:
                    raise InvalidTicket("The ticket %s field is invalid: %s" %
                                        (field, message))
                else:
                    raise InvalidTicket("Invalid ticket: %s" % message)

    def _do_create(self, context):
        req = context.req
        ticket = context.resource

        if 'field_summary' not in req.args:
            raise TracError('Tickets must contain a summary.')

        self._populate(req, ticket)
        ticket.values['reporter'] = get_reporter_id(req, 'reporter')
        self._validate_ticket(req, ticket)

        ticket.insert(db=context.db)
        context.db.commit()
        context.id = ticket.id

        # Notify
        try:
            tn = TicketNotifyEmail(self.env)
            tn.notify(ticket, newticket=True)
        except Exception, e:
            self.log.exception("Failure sending notification on creation of "
                               "ticket #%s: %s" % (ticket.id, e))

        # Redirect the user to the newly created ticket or add attachment
        if 'attachment' in req.args:
            req.redirect(req.href.attachment('ticket', ticket.id, action='new'))

        req.redirect(req.href.ticket(ticket.id))

    def _do_save(self, context):
        req = context.req
        ticket = context.resource
        
        if 'TICKET_CHGPROP' in req.perm:
            # TICKET_CHGPROP gives permission to edit the ticket
            if not req.args.get('field_summary'):
                raise TracError('Tickets must contain summary.')

            if 'field_description' in req.args or 'field_reporter' in req.args:
                req.perm.require('TICKET_ADMIN')

            self._populate(req, ticket)
        else:
            req.perm.require('TICKET_APPEND')

        # Mid air collision?
        if req.args.get('ts') != str(ticket.time_changed):
            raise TracError("Sorry, can not save your changes. "
                            "This ticket has been modified by someone else "
                            "since you started", 'Mid Air Collision')

        # Do any action on the ticket?
        action = req.args.get('action')
        actions = TicketSystem(self.env).get_available_actions(ticket, req.perm)
        if action not in actions:
            raise TracError('Invalid action "%s"' % action)

        # TODO: this should not be hard-coded like this
        if action == 'accept':
            ticket['status'] =  'assigned'
            ticket['owner'] = req.authname
        if action == 'resolve':
            ticket['status'] = 'closed'
            ticket['resolution'] = req.args.get('resolve_choice')
        elif action == 'reassign':
            ticket['owner'] = req.args.get('reassign_choice')
            ticket['status'] = 'new'
        elif action == 'reopen':
            ticket['status'] = 'reopened'
            ticket['resolution'] = ''

        now = datetime.now(utc)
        self._validate_ticket(req, ticket)

        cnum = req.args.get('cnum')        
        replyto = req.args.get('replyto')
        internal_cnum = cnum
        if cnum and replyto: # record parent.child relationship
            internal_cnum = '%s.%s' % (replyto, cnum)
        if ticket.save_changes(get_reporter_id(req, 'author'),
                               req.args.get('comment'), when=now,
                               db=context.db, cnum=internal_cnum):
            context.db.commit()

            try:
                tn = TicketNotifyEmail(self.env)
                tn.notify(ticket, newticket=False, modtime=now)
            except Exception, e:
                self.log.exception("Failure sending notification on change to "
                                   "ticket #%s: %s" % (ticket.id, e))

        fragment = cnum and '#comment:'+cnum or ''
        req.redirect(req.href.ticket(ticket.id) + fragment)

    def _insert_ticket_data(self, context, data, reporter_id):
        """Insert ticket data into the hdf"""
        req = context.req
        ticket = context.resource

        replyto = req.args.get('replyto')
        version = req.args.get('version', None)
        
        data['replyto'] = replyto
        if version:
            try:
                version = int(version)
                data['version'] = version
            except ValueError:
                version = None

        # -- Ticket fields
        types = {}
        fields = []
        for field in TicketSystem(self.env).get_ticket_fields():
            name = field['name']
            type_ = field['type']
            types[name] = type_
            if type_ in ('radio', 'select'):
                value = ticket.values.get(field['name'])
                options = field['options']
                if name == 'milestone' and 'TICKET_ADMIN' not in req.perm:
                    options = [opt for opt in options if not
                               Milestone(self.env, opt,
                                         db=context.db).is_completed]
                    # FIXME: ... un air de "deja vu" ;)
                if value and not value in options:
                    # Current ticket value must be visible even if its not in the
                    # possible values
                    options.append(value)
                field['options'] = options
            if name in ('summary', 'reporter', 'description', 'status',
                        'resolution', 'owner'):
                field['skip'] = True
            fields.append(field)

        data['reporter_id'] = reporter_id

        # FIXME: get rid of this once datetime branch is merged
        data['opened'] = ticket.time_created
        if ticket.time_changed != ticket.time_created:
            data['lastmod'] = ticket.time_changed

        # -- Ticket Change History

        def quote_original(author, original, link):
            if 'comment' not in req.args: # i.e. the comment was not yet edited
                data['comment'] = '\n'.join(
                    ['Replying to [%s %s]:' % (link, author)] +
                    ['> %s' % line for line in original.splitlines()] + [''])

        if replyto == 'description':
            quote_original(ticket['reporter'], ticket['description'],
                           'ticket:%d' % ticket.id)
        values = {}
        replies = {}
        changes = []
        cnum = 0
        skip = False
        for change in self.grouped_changelog_entries(ticket, context.db):
            if change['permanent']:
                cnum = change['cnum']
                if version is not None and cnum > version:
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
                    comment = ''
                    if replyto == str(cnum):
                        quote_original(change['author'], comment,
                                       'comment:%s' % replyto)
                    if version:
                        # Override ticket value by current changes
                        for k, v in change['fields'].iteritems():
                            values[k] = v['new']
                    if 'description' in change['fields']:
                        data['description_change'] = change
            if not skip:
                changes.append(change)

        if version is not None:
            ticket.values.update(values)
            
        data.update({
            'fields': fields, 'changes': changes, 'field_types': types,
            'replies': replies, 'cnum': cnum + 1,
            'attachments': list(Attachment.select(self.env, 'ticket',
                                                  ticket.id)),
            'attach_href': ('TICKET_APPEND' in req.perm and \
                            req.href.attachment('ticket', ticket.id)),
            'actions': TicketSystem(self.env).get_available_actions(ticket,
                                                                    req.perm)
            })

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
                           'permanent': permanent}
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
            else:
                current['fields'][field] = {'old': old, 'new': new}
        if current:
            yield current
