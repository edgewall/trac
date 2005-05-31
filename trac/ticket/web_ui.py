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
from trac.Notify import TicketNotifyEmail
from trac.ticket import Ticket, TicketSystem
from trac.Timeline import ITimelineEventProvider
from trac.web.chrome import add_link, add_stylesheet, INavigationContributor
from trac.web.main import IRequestHandler
from trac.wiki import wiki_to_html, wiki_to_oneliner

def insert_custom_fields(env, hdf, vals={}):
    for idx, field in util.enum(TicketSystem(env).get_custom_fields()):
        name = field['name']
        value = vals.get('custom_' + name, field['value'])
        prefix = 'ticket.custom.%d' % idx
        hdf[prefix] = {
            'name': field['name'],
            'type': field['type'],
            'label': field['label'] or field['name'],
            'value': value
        }
        if field['type'] == 'select' or field['type'] == 'radio':
            for optidx, option in util.enum(field['options']):
                hdf['%s.option.%d' % (prefix, optidx)] = option
                if value and (option == value or str(optidx) == value):
                    hdf['%s.option.%d.selected' % (prefix, optidx)] = True
        elif field['type'] == 'checkbox':
            if value in util.TRUE:
                hdf['%s.selected' % prefix] = True
        elif field['type'] == 'textarea':
            hdf['%s.width' % prefix] = field['width']
            hdf['%s.height' % prefix] = field['height']


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

        ticket = Ticket()
        ticket.populate(req.args)
        for field in Ticket.std_fields:
            default = self.config.get('ticket', 'default_' + field)
            if default:
                ticket.setdefault(field, default)
        ticket.setdefault('reporter', util.get_reporter_id(req))

        if ticket.has_key('description'):
            req.hdf['newticket.description_preview'] = wiki_to_html(ticket['description'],
                                                                    self.env,
                                                                    req, db)

        req.hdf['title'] = 'New Ticket'
        req.hdf['newticket'] = dict(zip(ticket.keys(), [util.escape(v) for v
                                                        in ticket.values()]))

        util.sql_to_hdf(db, "SELECT name FROM component ORDER BY name",
                        req.hdf, 'newticket.components')
        util.sql_to_hdf(db, "SELECT name FROM milestone WHERE "
                            "COALESCE(completed,0)=0 ORDER BY name",
                        req.hdf, 'newticket.milestones')
        util.sql_to_hdf(db, "SELECT name FROM version ORDER BY name",
                        req.hdf, 'newticket.versions')
        util.sql_to_hdf(db, "SELECT name FROM enum WHERE type='ticket_type' "
                            "ORDER BY value",
                        req.hdf, 'enums.ticket_type')
        util.sql_to_hdf(db, "SELECT name FROM enum WHERE type='priority' "
                            "ORDER BY value",
                        req.hdf, 'enums.priority')
        util.sql_to_hdf(db, "SELECT name FROM enum WHERE type='severity' "
                            "ORDER BY value",
                        req.hdf, 'enums.severity')

        restrict_owner = self.config.get('ticket', 'restrict_owner')
        if restrict_owner.lower() in util.TRUE:
            users = []
            for username, name, email in self.env.get_known_users(db):
                label = username
                if name:
                    label = '%s (%s)' % (util.escape(username),
                                         util.escape(name))
                users.append({'name': username, 'label': label})
            req.hdf['newticket.users'] = users

        insert_custom_fields(self.env, req.hdf, ticket)

        add_stylesheet(req, 'ticket.css')
        return 'newticket.cs', None

    # Internal methods

    def _do_create(self, req, db):
        if not req.args.get('summary'):
            raise TracError('Tickets must contain a summary.')

        ticket = Ticket()
        ticket.populate(req.args)
        ticket.setdefault('reporter', req.authname)

        # The owner field defaults to the component owner
        cursor = db.cursor()
        if ticket.get('component') and ticket.get('owner', '') == '':
            cursor.execute('SELECT owner FROM component '
                           'WHERE name=%s', ticket['component'])
            owner = cursor.fetchone()[0]
            ticket['owner'] = owner

        tktid = ticket.insert(db)

        # Notify
        try:
            tn = TicketNotifyEmail(self.env)
            tn.notify(ticket, newticket=1)
        except Exception, e:
            self.log.exception("Failure sending notification on creation of "
                               "ticket #%d: %s" % (tktid, e))

        # Redirect the user to the newly created ticket
        req.redirect(self.env.href.ticket(tktid))


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

        ticket = Ticket(db, id)
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

        self._insert_ticket_data(req, db, ticket['id'], ticket, reporter_id)

        # If the ticket is being shown in the context of a query, add
        # links to help navigate in the query result set
        if 'query_tickets' in req.session:
            tickets = req.session['query_tickets'].split()
            if str(id) in tickets:
                idx = tickets.index(str(ticket['id']))
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
            absurls = req.args.get('format') == 'rss' # Kludge
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
                if absurls:
                    href = self.env.abs_href.ticket(id)
                else:
                    href = self.env.href.ticket(id)
                title = 'Ticket <em title="%s">#%s</em> (%s) %s by %s' % (
                        util.escape(summary), id, type, verbs[state],
                        util.escape(author))
                message = wiki_to_oneliner(util.shorten_line(message), self.env,
                                           db, absurls=absurls)
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
        ticket.save_changes(db, req.args.get('author', req.authname),
                            req.args.get('comment'), when=now)

        try:
            tn = TicketNotifyEmail(self.env)
            tn.notify(ticket, newticket=0, modtime=now)
        except Exception, e:
            self.log.exception("Failure sending notification on change to "
                               "ticket #%d: %s" % (ticket['id'], e))

        req.redirect(self.env.href.ticket(ticket['id']))

    def _insert_ticket_data(self, req, db, id, ticket, reporter_id):
        """Insert ticket data into the hdf"""
        req.hdf['ticket'] = dict(zip(ticket.keys(),
                                 map(lambda x: util.escape(x), ticket.values())))
        req.hdf['ticket.href'] = self.env.href.ticket(id)

        util.sql_to_hdf(db, "SELECT name FROM component ORDER BY name",
                        req.hdf, 'ticket.components')
        util.sql_to_hdf(db, "SELECT name FROM milestone ORDER BY name",
                        req.hdf, 'ticket.milestones')
        util.sql_to_hdf(db, "SELECT name FROM version ORDER BY name",
                        req.hdf, 'ticket.versions')
        util.sql_to_hdf(db, "SELECT name FROM enum WHERE type='ticket_type'"
                                 " ORDER BY value",
                        req.hdf, 'enums.ticket_type')
        util.sql_to_hdf(db, "SELECT name FROM enum WHERE type='priority'"
                                 " ORDER BY value",
                        req.hdf, 'enums.priority')
        util.sql_to_hdf(db, "SELECT name FROM enum WHERE type='severity'"
                                 " ORDER BY value",
                        req.hdf, 'enums.severity')
        util.sql_to_hdf(db, "SELECT name FROM enum WHERE type='resolution'"
                                 " ORDER BY value",
                        req.hdf, 'enums.resolution')
        util.hdf_add_if_missing(req.hdf, 'ticket.components', ticket['component'])
        util.hdf_add_if_missing(req.hdf, 'ticket.milestones', ticket['milestone'])
        util.hdf_add_if_missing(req.hdf, 'ticket.versions', ticket['version'])
        util.hdf_add_if_missing(req.hdf, 'enums.ticket_type', ticket['type'])
        util.hdf_add_if_missing(req.hdf, 'enums.priority', ticket['priority'])
        util.hdf_add_if_missing(req.hdf, 'enums.severity', ticket['severity'])
        util.hdf_add_if_missing(req.hdf, 'enums.resolution', 'fixed')

        req.hdf['ticket.reporter_id'] = util.escape(reporter_id)
        req.hdf['title'] = '#%d (%s)' % (id, util.escape(ticket['summary']))
        req.hdf['ticket.description.formatted'] = wiki_to_html(ticket['description'],
                                                                 self.env, req,
                                                               db)

        opened = int(ticket['time'])
        req.hdf['ticket.opened'] = time.strftime('%c', time.localtime(opened))
        req.hdf['ticket.opened_delta'] = util.pretty_timedelta(opened)
        lastmod = int(ticket['changetime'])
        if lastmod != opened:
            req.hdf['ticket.lastmod'] = time.strftime('%c', time.localtime(lastmod))
            req.hdf['ticket.lastmod_delta'] = util.pretty_timedelta(lastmod)

        restrict_owner = self.config.get('ticket', 'restrict_owner')
        if restrict_owner.lower() in util.TRUE:
            users = []
            for username, name, email in self.env.get_known_users(db):
                label = username
                if name:
                    label = '%s (%s)' % (util.escape(username),
                                         util.escape(name))
                users.append({'name': username, 'label': label})
            req.hdf['ticket.users'] = users

        changelog = ticket.get_changelog(db)
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

        insert_custom_fields(self.env, req.hdf, ticket)

        # List attached files
        for idx, attachment in util.enum(Attachment.select(self.env, 'ticket',
                                                           id)):
            hdf = attachment_to_hdf(self.env, db, req, attachment)
            req.hdf['ticket.attachments.%s' % idx] = hdf
        if req.perm.has_permission(perm.TICKET_APPEND):
            req.hdf['ticket.attach_href'] = self.env.href.attachment('ticket',
                                                                     id)

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
