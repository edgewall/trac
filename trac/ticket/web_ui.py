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

from trac.attachment import Attachment, AttachmentModule
from trac.config import BoolOption, Option
from trac.core import *
from trac.mimeview.api import Mimeview, IContentConverter
from trac.search import ISearchSource, search_to_sql, shorten_result
from trac.ticket import Milestone, Ticket, TicketSystem, ITicketManipulator
from trac.ticket.notification import TicketNotifyEmail
from trac.timeline.api import ITimelineEventProvider, TimelineEvent
from trac.util import get_reporter_id
from trac.util.datefmt import to_timestamp, utc
from trac.util.html import html, Markup
from trac.util.text import CRLF, shorten_line
from trac.web import IRequestHandler
from trac.web.chrome import add_link, add_stylesheet, INavigationContributor, \
                            Chrome


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
                   html.A('New Ticket', href=req.href.newticket(), accesskey=7))

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
        req.perm.require('TICKET_CREATE')
        data = {}
        db = self.env.get_db_cnx()

        if req.method == 'POST' and 'owner' in req.args and \
               'TICKET_MODIFY' not in req.perm:
            del req.args['owner']

        if req.method == 'POST' and 'preview' not in req.args:
            self._do_create(req, db)

        ticket = Ticket(self.env, db=db)
        ticket.populate(req.args)
        ticket.values['reporter'] = get_reporter_id(req, 'reporter')
        data['ticket'] = ticket

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
                           Milestone(self.env, opt, db=db).is_completed]
                field['options'] = options
            data['fields'].append(field)

        if 'TICKET_APPEND' in req.perm:
            data['can_attach'] = True
            data['attachment'] = req.args.get('attachment')

        add_stylesheet(req, 'common/css/ticket.css')
        return 'ticket_new.html', data, None

    def process_ticket_request(self, req):
        req.perm.require('TICKET_VIEW')
        data = {}

        action = req.args.get('action', 'view')

        db = self.env.get_db_cnx()
        id = int(req.args.get('id'))

        ticket = Ticket(self.env, id, db=db)
        data['ticket'] = ticket

        if req.method == 'POST':
            if 'preview' not in req.args:
                self._do_save(req, db, ticket)
            else:
                # Use user supplied values
                ticket.populate(req.args)
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

        self._insert_ticket_data(req, db, ticket, data,
                                 get_reporter_id(req, 'author'))

        mime = Mimeview(self.env)
        format = req.args.get('format')
        if format:
            mime.send_converted(req, 'trac.ticket.Ticket', ticket, format,
                                'ticket_%d' % ticket.id)

        # If the ticket is being shown in the context of a query, add
        # links to help navigate in the query result set
        if 'query_tickets' in req.session:
            tickets = req.session['query_tickets'].split()
            if str(id) in tickets:
                idx = tickets.index(str(ticket.id))
                if idx > 0:
                    add_link(req, 'first', req.href.ticket(tickets[0]),
                             'Ticket #%s' % tickets[0])
                    add_link(req, 'prev', req.href.ticket(tickets[idx - 1]),
                             'Ticket #%s' % tickets[idx - 1])
                if idx < len(tickets) - 1:
                    add_link(req, 'next', req.href.ticket(tickets[idx + 1]),
                             'Ticket #%s' % tickets[idx + 1])
                    add_link(req, 'last', req.href.ticket(tickets[-1]),
                             'Ticket #%s' % tickets[-1])
                add_link(req, 'up', req.session['query_href'])

        add_stylesheet(req, 'common/css/ticket.css')

        # Add registered converters
        for conversion in mime.get_supported_conversions('trac.ticket.Ticket'):
            conversion_href = req.href.ticket(ticket.id, format=conversion[0])
            add_link(req, 'alternate', conversion_href, conversion[1],
                     conversion[3])

        return 'ticket_view.html', data, None

    # ISearchSource methods

    def get_search_filters(self, req):
        if 'TICKET_VIEW' in req.perm:
            yield ('ticket', 'Tickets')

    def get_search_results(self, req, terms, filters):
        if not 'ticket' in filters:
            return
        db = self.env.get_db_cnx()
        sql, args = search_to_sql(db, ['b.newvalue'], terms)
        sql2, args2 = search_to_sql(db, ['summary', 'keywords', 'description',
                                         'reporter', 'cc', 'id'], terms)
        cursor = db.cursor()
        cursor.execute("SELECT DISTINCT a.summary,a.description,a.reporter, "
                       "a.keywords,a.id,a.time,a.status FROM ticket a "
                       "LEFT JOIN ticket_change b ON a.id = b.ticket "
                       "WHERE (b.field='comment' AND %s ) OR %s" % (sql, sql2),
                       args + args2)
        for summary, desc, author, keywords, tid, ts, status in cursor:
            ticket = '#%d: ' % tid
            if status == 'closed':
                ticket = Markup('<span style="text-decoration: line-through">'
                                '#%s</span>: ', tid)
            yield (req.href.ticket(tid),
                   ticket + shorten_line(summary),
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

        def produce((id, ts, author, type, summary), status, fields,
                    comment, cid):
            info = ''
            if status == 'edit':
                if 'ticket_details' in filters:
                    if len(fields) > 0:
                        keys = fields.keys()
                        info = html([[html.i(f), ', '] for f in keys[:-1]],
                                    html.i(keys[-1]), ' changed', html.br())
                else:
                    return None
            elif 'ticket' in filters:
                if status == 'closed' and fields.has_key('resolution'):
                    info = fields['resolution']
                    if info and comment:
                        info += ': '
            else:
                return None
            kind, verb = status_map[status]
            title = html('Ticket ', html.em('#', id, title=summary),
                         ' (%s) ' % (type or 'Ticket'), verb)
            ticket_href = req.href.ticket(id)
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
            event.set_context('ticket', id, message)
            return event

        # Ticket changes
        if 'ticket' in filters or 'ticket_details' in filters:
            db = self.env.get_db_cnx()
            cursor = db.cursor()

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
                def display(id):
                    return html('ticket ', html.em('#', id))
                att = AttachmentModule(self.env)
                for event in att.get_timeline_events(req, db, 'ticket',
                                                     start, stop, display):
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

    def _do_create(self, req, db):
        if 'summary' not in req.args:
            raise TracError('Tickets must contain a summary.')

        ticket = Ticket(self.env, db=db)
        ticket.populate(req.args)
        ticket.values['reporter'] = get_reporter_id(req, 'reporter')
        self._validate_ticket(req, ticket)

        ticket.insert(db=db)
        db.commit()

        # Notify
        try:
            tn = TicketNotifyEmail(self.env)
            tn.notify(ticket, newticket=True)
        except Exception, e:
            self.log.exception("Failure sending notification on creation of "
                               "ticket #%s: %s" % (ticket.id, e))

        # Redirect the user to the newly created ticket
        if 'attachment' in req.args:
            req.redirect(req.href.attachment('ticket', ticket.id, action='new'))

        req.redirect(req.href.ticket(ticket.id))

    def _do_save(self, req, db, ticket):
        if 'TICKET_CHGPROP' in req.perm:
            # TICKET_CHGPROP gives permission to edit the ticket
            if not req.args.get('summary'):
                raise TracError('Tickets must contain summary.')

            if req.args.has_key('description') or req.args.has_key('reporter'):
                req.perm.require('TICKET_ADMIN')

            ticket.populate(req.args)
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
                               req.args.get('comment'), when=now, db=db,
                               cnum=internal_cnum):
            db.commit()

            try:
                tn = TicketNotifyEmail(self.env)
                tn.notify(ticket, newticket=False, modtime=now)
            except Exception, e:
                self.log.exception("Failure sending notification on change to "
                                   "ticket #%s: %s" % (ticket.id, e))

        fragment = cnum and '#comment:'+cnum or ''
        req.redirect(req.href.ticket(ticket.id) + fragment)

    def _insert_ticket_data(self, req, db, ticket, data, reporter_id):
        """Insert ticket data into the hdf"""
        replyto = req.args.get('replyto')
        data['replyto'] = replyto

        # -- Ticket fields

        data['fields'] = []
        for field in TicketSystem(self.env).get_ticket_fields():
            name = field['name']
            if field['type'] in ('radio', 'select'):
                value = ticket.values.get(field['name'])
                options = field['options']
                if name == 'milestone' and 'TICKET_ADMIN' not in req.perm:
                    options = [opt for opt in options if not
                               Milestone(self.env, opt, db=db).is_completed]
                if value and not value in options:
                    # Current ticket value must be visible even if its not in the
                    # possible values
                    options.append(value)
                field['options'] = options
            if name in ('summary', 'reporter', 'description', 'status',
                        'resolution', 'owner'):
                field['skip'] = True
            data['fields'].append(field)

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
        replies = {}
        changes = []
        cnum = 0
        description_lastmod = description_author = None
        for change in self.grouped_changelog_entries(ticket, db):
            changes.append(change)
            # wikify comment
            comment = ''
            if change['permanent']:
                cnum = change['cnum']
                # keep track of replies threading
                if 'replyto' in change:
                    replies.setdefault(change['replyto'], []).append(cnum)
                # eventually cite the replied to comment
                if replyto == str(cnum):
                    quote_original(change['author'], comment,
                                   'comment:%s' % replyto)
            if 'description' in change['fields']:
                change['fields']['description'] = ''
                description_lastmod = change['date']
                description_author = change['author']

        data['changes'] = changes
        data['replies'] = replies
        data['cnum'] = cnum + 1
        if description_lastmod:
            data['description_author'] = description_author
            data['description_lastmod'] = description_lastmod

        # -- Ticket Attachments

        data['attachments'] = list(Attachment.select(self.env, 'ticket',
                                                     ticket.id))
        if 'TICKET_APPEND' in req.perm:
            data['attach_href'] = req.href.attachment('ticket', ticket.id)

        # Add the possible actions to hdf
        actions = TicketSystem(self.env).get_available_actions(ticket, req.perm)
        data['actions'] = actions

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
