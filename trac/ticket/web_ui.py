# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2003, 2004, 2005 Edgewall Software
# Copyright (C) 2003, 2004, 2005 Jonas Borgström <jonas@edgewall.com>
#
# Trac is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version.
#
# Trac is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#
# Author: Jonas Borgström <jonas@edgewall.com>

from __future__ import generators
import re
import time

from trac import perm, util
from trac.attachment import attachment_to_hdf, Attachment
from trac.core import *
from trac.Milestone import Milestone
from trac.Notify import TicketNotifyEmail
from trac.ticket import Ticket, TicketSystem
from trac.Timeline import ITimelineEventProvider
from trac.web.chrome import add_link, add_stylesheet, INavigationContributor
from trac.web.main import IRequestHandler
from trac.wiki import wiki_to_html, wiki_to_oneliner


class NewticketModule(Component):

    implements(INavigationContributor, IRequestHandler)

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'newticket'

    def get_navigation_items(self, req):
        if not req.perm.has_permission(perm.TICKET_CREATE):
            return
        yield 'mainnav', 'newticket', '<a href="%s">New Ticket</a>' \
              % (self.env.href.newticket())

    # IRequestHandler methods

    def match_request(self, req):
        return req.path_info == '/newticket'

    def process_request(self, req):
        req.perm.assert_permission(perm.TICKET_CREATE)

        db = self.env.get_db_cnx()

        if req.method == 'POST' and 'preview' not in req.args.keys():
            self._do_create(req, db)

        ticket = Ticket(self.env, db=db)
        ticket.populate(req.args)
        ticket.values.setdefault('reporter', util.get_reporter_id(req))

        if 'description' in ticket.values.keys():
            description = wiki_to_html(ticket['description'], self.env, req, db)
            req.hdf['newticket.description_preview'] = description

        req.hdf['title'] = 'New Ticket'
        req.hdf['newticket'] = dict(zip(ticket.values.keys(),
                                        [util.escape(value) for value
                                         in ticket.values.values()]))

        for field in ticket.fields:
            name = field['name']
            del field['name']
            if name in ('summary', 'reporter', 'owner', 'description', 'type',
                        'status', 'resolution'):
                field['skip'] = True
            if name == 'milestone':
                # Don't make completed milestones available for selection
                options = field['options']
                for option in field['options']:
                    milestone = Milestone(self.env, option, db=db)
                    if milestone.is_completed:
                        options.remove(option)
                field['options'] = options
            req.hdf['newticket.fields.' + name] = field

        add_stylesheet(req, 'ticket.css')
        return 'newticket.cs', None

    # Internal methods

    def _do_create(self, req, db):
        if not req.args.get('summary'):
            raise TracError('Tickets must contain a summary.')

        ticket = Ticket(self.env, db=db)
        ticket.values.setdefault('reporter', util.get_reporter_id(req))
        ticket.populate(req.args)
        ticket.insert(db)
        db.commit()

        # Notify
        try:
            tn = TicketNotifyEmail(self.env)
            tn.notify(ticket, newticket=True)
        except Exception, e:
            self.log.exception("Failure sending notification on creation of "
                               "ticket #%s: %s" % (ticket.id, e))

        # Redirect the user to the newly created ticket
        req.redirect(self.env.href.ticket(ticket.id))


class TicketModule(Component):

    implements(INavigationContributor, IRequestHandler, ITimelineEventProvider)

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'tickets'

    def get_navigation_items(self, req):
        return []

    # IRequestHandler methods

    def match_request(self, req):
        match = re.match(r'/ticket/([0-9]+)?', req.path_info)
        if match:
            req.args['id'] = match.group(1)
            return 1

    def process_request(self, req):
        req.perm.assert_permission(perm.TICKET_VIEW)

        action = req.args.get('action', 'view')

        if not req.args.has_key('id'):
            req.redirect(self.env.href.wiki())

        db = self.env.get_db_cnx()
        id = int(req.args.get('id'))

        ticket = Ticket(self.env, id, db=db)
        reporter_id = util.get_reporter_id(req)

        if req.method == 'POST':
            if 'preview' not in req.args.keys():
                self._do_save(req, db, ticket)
            else:
                # Use user supplied values
                ticket.populate(req.args)
                req.hdf['ticket.action'] = action
                req.hdf['ticket.reassign_owner'] = req.args.get('reassign_owner') \
                                                   or req.authname
                req.hdf['ticket.resolve_resolution'] = req.args.get('resolve_resolution')
                reporter_id = req.args.get('author')
                comment = req.args.get('comment')
                if comment:
                    req.hdf['ticket.comment'] = util.escape(comment)
                    # Wiki format a preview of comment
                    req.hdf['ticket.comment_preview'] = wiki_to_html(comment,
                                                                     self.env,
                                                                     req, db)
        else:
            req.hdf['ticket.reassign_owner'] = req.authname

        self._insert_ticket_data(req, db, ticket, reporter_id)

        # If the ticket is being shown in the context of a query, add
        # links to help navigate in the query result set
        if 'query_tickets' in req.session:
            tickets = req.session['query_tickets'].split()
            if str(id) in tickets:
                idx = tickets.index(str(ticket.id))
                if idx > 0:
                    add_link(req, 'first', self.env.href.ticket(tickets[0]),
                             'Ticket #%s' % tickets[0])
                    add_link(req, 'prev', self.env.href.ticket(tickets[idx - 1]),
                             'Ticket #%s' % tickets[idx - 1])
                if idx < len(tickets) - 1:
                    add_link(req, 'next', self.env.href.ticket(tickets[idx + 1]),
                             'Ticket #%s' % tickets[idx + 1])
                    add_link(req, 'last', self.env.href.ticket(tickets[-1]),
                             'Ticket #%s' % tickets[-1])
                add_link(req, 'up', req.session['query_href'])

        add_stylesheet(req, 'ticket.css')
        return 'ticket.cs', None

    # ITimelineEventProvider methods

    def get_timeline_filters(self, req):
        if req.perm.has_permission(perm.TICKET_VIEW):
            yield ('ticket', 'Ticket changes')

    def get_timeline_events(self, req, start, stop, filters):
        if 'ticket' in filters:
            format = req.args.get('format')
            sql = []

            # New tickets
            sql.append("SELECT time,id,'','new',type,summary,reporter,summary"
                       " FROM ticket WHERE time>=%s AND time<=%s")

            # Reopened tickets
            sql.append("SELECT t1.time,t1.ticket,'','reopened',t.type,"
                       "       t2.newvalue,t1.author,t.summary "
                       " FROM ticket_change t1"
                       "   LEFT OUTER JOIN ticket_change t2 ON (t1.time=t2.time"
                       "     AND t1.ticket=t2.ticket AND t2.field='comment')"
                       "   LEFT JOIN ticket t on t.id = t1.ticket "
                       " WHERE t1.field='status' AND t1.newvalue='reopened'"
                       "   AND t1.time>=%s AND t1.time<=%s")

            # Closed tickets
            sql.append("SELECT t1.time,t1.ticket,t2.newvalue,'closed',t.type,"
                       "       t3.newvalue,t1.author,t.summary"
                       " FROM ticket_change t1"
                       "   INNER JOIN ticket_change t2 ON t1.ticket=t2.ticket"
                       "     AND t1.time=t2.time"
                       "   LEFT OUTER JOIN ticket_change t3 ON t1.time=t3.time"
                       "     AND t1.ticket=t3.ticket AND t3.field='comment'"
                       "   LEFT JOIN ticket t on t.id = t1.ticket "
                       " WHERE t1.field='status' AND t1.newvalue='closed'"
                       "   AND t2.field='resolution'"
                       "   AND t1.time>=%s AND t1.time<=%s")

            db = self.env.get_db_cnx()
            cursor = db.cursor()
            cursor.execute(" UNION ALL ".join(sql), start, stop, start, stop,
                           start, stop)
            kinds = {'new': 'newticket', 'reopened': 'newticket',
                     'closed': 'closedticket'}
            verbs = {'new': 'created', 'reopened': 'reopened',
                     'closed': 'closed'}
            for t,id,resolution,state,type,message,author,summary in cursor:
                title = 'Ticket <em title="%s">#%s</em> (%s) %s by %s' % (
                        util.escape(summary), id, type, verbs[state],
                        util.escape(author))
                if format == 'rss':
                    href = self.env.abs_href.ticket(id)
                    message = wiki_to_html(message or '--', self.env, db)
                else:
                    href = self.env.href.ticket(id)
                    message = wiki_to_oneliner(util.shorten_line(message),
                                               self.env, db)
                yield kinds[state], href, title, t, author, message

    # Internal methods

    def _do_save(self, req, db, ticket):
        if req.perm.has_permission(perm.TICKET_CHGPROP):
            # TICKET_CHGPROP gives permission to edit the ticket
            if not req.args.get('summary'):
                raise TracError('Tickets must contain summary.')

            if 'description' in req.args.keys() or 'reporter' in req.args.keys():
                req.perm.assert_permission(perm.TICKET_ADMIN)

            ticket.populate(req.args)
        else:
            req.perm.assert_permission(perm.TICKET_APPEND)

        # Do any action on the ticket?
        action = req.args.get('action')
        actions = TicketSystem(self.env).get_available_actions(ticket, req.perm)
        if action not in actions:
            raise TracError('Invalid action')

        # TODO: this should not be hard-coded like this
        if action == 'accept':
            ticket['status'] =  'assigned'
            ticket['owner'] = req.authname
        if action == 'resolve':
            ticket['status'] = 'closed'
            ticket['resolution'] = req.args.get('resolve_resolution')
        elif action == 'reassign':
            ticket['owner'] = req.args.get('reassign_owner')
            ticket['status'] = 'new'
        elif action == 'reopen':
            ticket['status'] = 'reopened'
            ticket['resolution'] = ''

        now = int(time.time())
        ticket.save_changes(req.args.get('author', req.authname),
                            req.args.get('comment'), when=now, db=db)
        db.commit()

        try:
            tn = TicketNotifyEmail(self.env)
            tn.notify(ticket, newticket=False, modtime=now)
        except Exception, e:
            self.log.exception("Failure sending notification on change to "
                               "ticket #%s: %s" % (ticket.id, e))

        req.redirect(self.env.href.ticket(ticket.id))

    def _insert_ticket_data(self, req, db, ticket, reporter_id):
        """Insert ticket data into the hdf"""
        req.hdf['ticket'] = dict(zip(ticket.values.keys(),
                                 map(lambda x: util.escape(x),
                                     ticket.values.values())))
        req.hdf['ticket.id'] = ticket.id
        req.hdf['ticket.href'] = self.env.href.ticket(ticket.id)

        for field in TicketSystem(self.env).get_ticket_fields():
            if field['type'] in ('radio', 'select'):
                value = ticket[field['name']]
                if value and not value in field['options']:
                    # Current ticket value must be visible even if its not in the
                    # possible values
                    field['options'].append(value)
            name = field['name']
            del field['name']
            if name in ('summary', 'reporter', 'description', 'type', 'status',
                        'resolution', 'owner'):
                field['skip'] = True
            req.hdf['ticket.fields.' + name] = field

        req.hdf['ticket.reporter_id'] = util.escape(reporter_id)
        req.hdf['title'] = '#%d (%s)' % (ticket.id,
                                         util.escape(ticket['summary']))
        req.hdf['ticket.description.formatted'] = wiki_to_html(ticket['description'],
                                                               self.env, req, db)

        req.hdf['ticket.opened'] = time.strftime('%c', time.localtime(ticket.time_created))
        req.hdf['ticket.opened_delta'] = util.pretty_timedelta(ticket.time_created)
        if ticket.time_changed != ticket.time_created:
            req.hdf['ticket.lastmod'] = time.strftime('%c', time.localtime(ticket.time_changed))
            req.hdf['ticket.lastmod_delta'] = util.pretty_timedelta(ticket.time_changed)

        changelog = ticket.get_changelog(db=db)
        curr_author = None
        curr_date   = 0
        changes = []
        for date, author, field, old, new in changelog:
            if date != curr_date or author != curr_author:
                changes.append({
                    'date': time.strftime('%c', time.localtime(date)),
                    'author': util.escape(author),
                    'fields': {}
                })
                curr_date = date
                curr_author = author
            if field == 'comment':
                changes[-1]['comment'] = wiki_to_html(new, self.env, req, db)
            elif field == 'description':
                changes[-1]['fields'][field] = ''
            else:
                changes[-1]['fields'][field] = {'old': old, 'new': new}
        req.hdf['ticket.changes'] = changes

        # List attached files
        for idx, attachment in util.enum(Attachment.select(self.env, 'ticket',
                                                           ticket.id)):
            hdf = attachment_to_hdf(self.env, db, req, attachment)
            req.hdf['ticket.attachments.%s' % idx] = hdf
        if req.perm.has_permission(perm.TICKET_APPEND):
            req.hdf['ticket.attach_href'] = self.env.href.attachment('ticket',
                                                                     ticket.id)

        # Add the possible actions to hdf
        actions = TicketSystem(self.env).get_available_actions(ticket, req.perm)
        for action in actions:
            req.hdf['ticket.actions.' + action] = '1'


class UpdateDetailsForTimeline(Component):
    """Provide all details about ticket changes in the Timeline"""

    implements(ITimelineEventProvider)

    # ITimelineEventProvider methods

    def get_timeline_filters(self, req):
        if req.perm.has_permission(perm.TICKET_VIEW):
            yield ('ticket_details', 'Ticket details')

    def get_timeline_events(self, req, start, stop, filters):
        if 'ticket_details' in filters:
            db = self.env.get_db_cnx()
            cursor = db.cursor()
            cursor.execute("SELECT tc.time,tc.ticket,t.type,tc.field, "
                           "       tc.oldvalue,tc.newvalue,tc.author,t.summary "
                           "FROM ticket_change tc"
                           "   INNER JOIN ticket t ON t.id = tc.ticket "
                           "AND tc.time>=%s AND tc.time<=%s ORDER BY tc.time"
                           % (start, stop))
            previous_update = None
            updates = []
            ticket_change = False
            for time,id,type,field,oldvalue,newvalue,author,summary in cursor:
                if not previous_update or (time,id,author) != previous_update[:3]:
                    if previous_update and not ticket_change:
                        updates.append((previous_update,field_changes,comment))
                    ticket_change = False
                    field_changes = []
                    comment = ''
                    previous_update = (time,id,author,type,summary)
                if field == 'comment':
                    comment = newvalue
                elif field == 'status' and newvalue in ['reopened', 'closed']:
                    ticket_change = True
                else:
                    field_changes.append(field)
            if previous_update and not ticket_change:
                updates.append((previous_update,field_changes,comment))

            absurls = req.args.get('format') == 'rss' # Kludge
            for (t,id,author,type,summary),field_changes,comment in updates:
                if absurls:
                    href = self.env.abs_href.ticket(id)
                else:
                    href = self.env.href.ticket(id) 
                title = 'Ticket <em title="%s">#%s</em> (%s) updated by %s' \
                        % (util.escape(summary), id, type, util.escape(author))
                message = ''
                if len(field_changes) > 0:
                    message = ', '.join(field_changes) + ' changed.<br />'
                message += wiki_to_oneliner(util.shorten_line(comment),
                                            self.env, db, absurls=absurls)
                yield 'editedticket', href, title, t, author, message
