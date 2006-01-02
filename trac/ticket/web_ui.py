# -*- coding: iso-8859-1 -*-
#
# Copyright (C) 2003-2006 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgström <jonas@edgewall.com>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://projects.edgewall.com/trac/.
#
# Author: Jonas Borgström <jonas@edgewall.com>

import os
import re
import time

from trac import util
from trac.attachment import attachment_to_hdf, Attachment
from trac.core import *
from trac.env import IEnvironmentSetupParticipant
from trac.Notify import TicketNotifyEmail
from trac.ticket import Milestone, Ticket, TicketSystem
from trac.Timeline import ITimelineEventProvider
from trac.web import IRequestHandler
from trac.web.chrome import add_link, add_stylesheet, INavigationContributor
from trac.wiki import wiki_to_html, wiki_to_oneliner


class NewticketModule(Component):

    implements(IEnvironmentSetupParticipant, INavigationContributor,
               IRequestHandler)

    # IEnvironmentSetupParticipant methods

    def environment_created(self):
        """Create the `site_newticket.cs` template file in the environment."""
        if self.env.path:
            templates_dir = os.path.join(self.env.path, 'templates')
            if not os.path.exists(templates_dir):
                os.mkdir(templates_dir)
            template_name = os.path.join(templates_dir, 'site_newticket.cs')
            template_file = file(template_name, 'w')
            template_file.write("""<?cs
####################################################################
# New ticket prelude - Included directly above the new ticket form
?>
""")

    def environment_needs_upgrade(self, db):
        return False

    def upgrade_environment(self, db):
        pass

    # INavigationContributor methods

    def get_active_navigation_item(self, req):
        return 'newticket'

    def get_navigation_items(self, req):
        if not req.perm.has_permission('TICKET_CREATE'):
            return
        yield ('mainnav', 'newticket', 
               util.Markup('<a href="%s" accesskey="7">New Ticket</a>',
                           self.env.href.newticket()))

    # IRequestHandler methods

    def match_request(self, req):
        return re.match(r'/newticket/?', req.path_info) is not None

    def process_request(self, req):
        req.perm.assert_permission('TICKET_CREATE')

        db = self.env.get_db_cnx()

        if req.method == 'POST' and not req.args.has_key('preview'):
            self._do_create(req, db)

        ticket = Ticket(self.env, db=db)
        ticket.populate(req.args)
        ticket.values.setdefault('reporter', util.get_reporter_id(req))

        if ticket.values.has_key('description'):
            description = wiki_to_html(ticket['description'], self.env, req, db)
            req.hdf['newticket.description_preview'] = description

        req.hdf['title'] = 'New Ticket'
        req.hdf['newticket'] = ticket.values

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

        for field in ticket.fields:
            name = field['name']
            del field['name']
            if name in ('summary', 'reporter', 'description', 'type', 'status',
                        'resolution'):
                field['skip'] = True
            elif name == 'owner':
                field['label'] = 'Assign to'
            elif name == 'milestone':
                # Don't make completed milestones available for selection
                options = field['options'][:]
                for option in field['options']:
                    milestone = Milestone(self.env, option, db=db)
                    if milestone.is_completed:
                        options.remove(option)
                field['options'] = options
            req.hdf['newticket.fields.' + name] = field

        add_stylesheet(req, 'common/css/ticket.css')
        return 'newticket.cs', None

    # Internal methods

    def _do_create(self, req, db):
        if not req.args.get('summary'):
            raise TracError('Tickets must contain a summary.')

        ticket = Ticket(self.env, db=db)
        ticket.values.setdefault('reporter', util.get_reporter_id(req))
        ticket.populate(req.args)
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
        match = re.match(r'/ticket/([0-9]+)', req.path_info)
        if match:
            req.args['id'] = match.group(1)
            return True

    def process_request(self, req):
        req.perm.assert_permission('TICKET_VIEW')

        action = req.args.get('action', 'view')

        if not req.args.has_key('id'):
            req.redirect(self.env.href.wiki())

        db = self.env.get_db_cnx()
        id = int(req.args.get('id'))

        ticket = Ticket(self.env, id, db=db)
        reporter_id = util.get_reporter_id(req)

        if req.method == 'POST':
            if not req.args.has_key('preview'):
                self._do_save(req, db, ticket)
            else:
                # Use user supplied values
                ticket.populate(req.args)
                req.hdf['ticket.action'] = action
                req.hdf['ticket.ts'] = req.args.get('ts')
                req.hdf['ticket.reassign_owner'] = req.args.get('reassign_owner') \
                                                   or req.authname
                req.hdf['ticket.resolve_resolution'] = req.args.get('resolve_resolution')
                reporter_id = req.args.get('author')
                comment = req.args.get('comment')
                if comment:
                    req.hdf['ticket.comment'] = comment
                    # Wiki format a preview of comment
                    req.hdf['ticket.comment_preview'] = wiki_to_html(comment,
                                                                     self.env,
                                                                     req, db)
        else:
            req.hdf['ticket.reassign_owner'] = req.authname
            # Store a timestamp in order to detect "mid air collisions"
            req.hdf['ticket.ts'] = ticket.time_changed

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

        add_stylesheet(req, 'common/css/ticket.css')
        return 'ticket.cs', None

    # ITimelineEventProvider methods

    def get_timeline_filters(self, req):
        if req.perm.has_permission('TICKET_VIEW'):
            yield ('ticket', 'Ticket changes')
            if self.config.getbool('timeline', 'ticket_show_details'):
                yield ('ticket_details', 'Ticket details', False)

    def get_timeline_events(self, req, start, stop, filters):
        rss = req.args.get('format') == 'rss' # Kludge

        status_map = {'new': ('newticket', 'created'),
                      'reopened': ('newticket', 'reopened'),
                      'closed': ('closedticket', 'closed'),
                      'edit': ('editedticket', 'updated')}

        def produce((id, t, author, type, summary), status, fields, comment):
            if status == 'edit':
                if 'ticket_details' in filters:
                    info = ''
                    if len(fields) > 0:
                        info = ', '.join(['<i>%s</i>' % f for f in \
                                          fields.keys()]) + ' changed<br />'
                else:
                    return None
            elif 'ticket' in filters:
                if status == 'closed' and fields.has_key('resolution'):
                    info = fields['resolution']
                    if info and comment:
                        info = '%s: ' % info
                else:
                    info = ''
            else:
                return None
            kind, verb = status_map[status]
            title = util.Markup('Ticket <em title="%s">#%s</em> (%s) %s by %s',
                                summary, id, type, verb, author)
            href = rss and self.env.abs_href.ticket(id) \
                   or self.env.href.ticket(id)

            if status == 'new':
                message = util.escape(summary)
            else:
                message = util.Markup(info)
                if comment:
                    if rss:
                        message += wiki_to_html(comment, self.env, req, db,
                                                absurls=True)
                    else:
                        message += wiki_to_oneliner(comment, self.env, db,
                                                    shorten=True)
            return kind, href, title, t, author, message

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
                        ev = produce(previous_update, status, fields, comment)
                        if ev:
                            yield ev
                    status, fields, comment = 'edit', {}, ''
                    previous_update = (id,t,author, type, summary)
                if field == 'comment':
                    comment = newvalue
                elif field == 'status' and newvalue in ('reopened', 'closed'):
                    status = newvalue
                else:
                    fields[field] = newvalue
            if previous_update:
                ev = produce(previous_update, status, fields, comment)
                if ev:
                    yield ev
            
            # New tickets
            if 'ticket' in filters:
                cursor.execute("SELECT id,time,reporter,type,summary"
                               "  FROM ticket WHERE time>=%s AND time<=%s",
                               (start, stop))
                for row in cursor:
                    yield produce(row, 'new', {}, None)
 

    # Internal methods

    def _do_save(self, req, db, ticket):
        if req.perm.has_permission('TICKET_CHGPROP'):
            # TICKET_CHGPROP gives permission to edit the ticket
            if not req.args.get('summary'):
                raise TracError('Tickets must contain summary.')

            if req.args.has_key('description') or req.args.has_key('reporter'):
                req.perm.assert_permission('TICKET_ADMIN')

            ticket.populate(req.args)
        else:
            req.perm.assert_permission('TICKET_APPEND')

        # Mid air collision?
        if int(req.args.get('ts')) != ticket.time_changed:
            raise TracError("Sorry, can not save your changes. "
                            "This ticket has been modified by someone else "
                            "since you started", 'Mid Air Collision')

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
        req.hdf['ticket'] = ticket.values
        req.hdf['ticket.id'] = ticket.id
        req.hdf['ticket.href'] = self.env.href.ticket(ticket.id)

        for field in TicketSystem(self.env).get_ticket_fields():
            if field['type'] in ('radio', 'select'):
                value = ticket.values.get(field['name'])
                options = field['options']
                if value and not value in options:
                    # Current ticket value must be visible even if its not in the
                    # possible values
                    options.append(value)
                field['options'] = options
            name = field['name']
            del field['name']
            if name in ('summary', 'reporter', 'description', 'type', 'status',
                        'resolution', 'owner'):
                field['skip'] = True
            req.hdf['ticket.fields.' + name] = field

        req.hdf['ticket.reporter_id'] = reporter_id
        req.hdf['title'] = '#%d (%s)' % (ticket.id, ticket['summary'])
        req.hdf['ticket.description.formatted'] = wiki_to_html(ticket['description'],
                                                               self.env, req, db)

        req.hdf['ticket.opened'] = util.format_datetime(ticket.time_created)
        req.hdf['ticket.opened_delta'] = util.pretty_timedelta(ticket.time_created)
        if ticket.time_changed != ticket.time_created:
            req.hdf['ticket.lastmod'] = util.format_datetime(ticket.time_changed)
            req.hdf['ticket.lastmod_delta'] = util.pretty_timedelta(ticket.time_changed)

        changelog = ticket.get_changelog(db=db)
        curr_author = None
        curr_date   = 0
        changes = []
        for date, author, field, old, new in changelog:
            if date != curr_date or author != curr_author:
                changes.append({
                    'date': util.format_datetime(date),
                    'author': author,
                    'fields': {}
                })
                curr_date = date
                curr_author = author
            if field == 'comment':
                changes[-1]['comment'] = wiki_to_html(new, self.env, req, db)
            elif field == 'description':
                changes[-1]['fields'][field] = ''
            else:
                changes[-1]['fields'][field] = {'old': old,
                                                'new': new}
        req.hdf['ticket.changes'] = changes

        # List attached files
        for idx, attachment in enumerate(Attachment.select(self.env, 'ticket',
                                                           ticket.id)):
            hdf = attachment_to_hdf(self.env, db, req, attachment)
            req.hdf['ticket.attachments.%s' % idx] = hdf
        if req.perm.has_permission('TICKET_APPEND'):
            req.hdf['ticket.attach_href'] = self.env.href.attachment('ticket',
                                                                     ticket.id)

        # Add the possible actions to hdf
        actions = TicketSystem(self.env).get_available_actions(ticket, req.perm)
        for action in actions:
            req.hdf['ticket.actions.' + action] = '1'
