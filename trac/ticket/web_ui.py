# -*- coding: utf-8 -*-
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
from StringIO import StringIO

from trac.attachment import attachments_to_hdf, Attachment, AttachmentModule
from trac.config import BoolOption, Option
from trac.core import *
from trac.env import IEnvironmentSetupParticipant
from trac.ticket import Milestone, Ticket, TicketSystem, ITicketManipulator
from trac.ticket.notification import TicketNotifyEmail
from trac.Timeline import ITimelineEventProvider
from trac.util import get_reporter_id
from trac.util.datefmt import format_datetime, pretty_timedelta, http_date
from trac.util.text import CRLF
from trac.util.markup import html, Markup
from trac.web import IRequestHandler
from trac.web.chrome import add_link, add_stylesheet, INavigationContributor
from trac.wiki import wiki_to_html, wiki_to_oneliner
from trac.mimeview.api import Mimeview, IContentConverter


class InvalidTicket(TracError):
    """Exception raised when a ticket fails validation."""


class TicketModuleBase(Component):
    # FIXME: temporary place-holder for unified ticket validation until
    #        ticket controller unification is merged
    abstract = True

    ticket_manipulators = ExtensionPoint(ITicketManipulator)

    def _validate_ticket(self, req, ticket):
        for manipulator in self.ticket_manipulators:
            for field, message in manipulator.validate_ticket(req, ticket):
                if field:
                    raise InvalidTicket("The ticket %s field is invalid: %s" %
                                        (field, message))
                else:
                    raise InvalidTicket("Invalid ticket: %s" % message)


class NewticketModule(TicketModuleBase):

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
               html.A('New Ticket', href=req.href.newticket(), accesskey=7))

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
        ticket.values['reporter'] = get_reporter_id(req, 'reporter')

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

        if req.perm.has_permission('TICKET_APPEND'):
            req.hdf['newticket.can_attach'] = True
            req.hdf['newticket.attachment'] = req.args.get('attachment')

        add_stylesheet(req, 'common/css/ticket.css')
        return 'newticket.cs', None

    # Internal methods

    def _do_create(self, req, db):
        if not req.args.get('summary'):
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
            tn.notify(ticket, req, newticket=True)
        except Exception, e:
            self.log.exception("Failure sending notification on creation of "
                               "ticket #%s: %s" % (ticket.id, e))

        # Redirect the user to the newly created ticket
        if req.args.get('attachment'):
            req.redirect(req.href.attachment('ticket', ticket.id, action='new'))
        else:
            req.redirect(req.href.ticket(ticket.id))


class TicketModule(TicketModuleBase):

    implements(INavigationContributor, IRequestHandler, ITimelineEventProvider,
               IContentConverter)

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

        db = self.env.get_db_cnx()
        id = int(req.args.get('id'))

        ticket = Ticket(self.env, id, db=db)

        if req.method == 'POST':
            if not req.args.has_key('preview'):
                self._do_save(req, db, ticket)
            else:
                # Use user supplied values
                ticket.populate(req.args)
                self._validate_ticket(req, ticket)

                req.hdf['ticket.action'] = action
                req.hdf['ticket.ts'] = req.args.get('ts')
                req.hdf['ticket.reassign_owner'] = req.args.get('reassign_owner') \
                                                   or req.authname
                req.hdf['ticket.resolve_resolution'] = req.args.get('resolve_resolution')
                comment = req.args.get('comment')
                if comment:
                    req.hdf['ticket.comment'] = comment
                    # Wiki format a preview of comment
                    req.hdf['ticket.comment_preview'] = wiki_to_html(
                        comment, self.env, req, db)
        else:
            req.hdf['ticket.reassign_owner'] = req.authname
            # Store a timestamp in order to detect "mid air collisions"
            req.hdf['ticket.ts'] = ticket.time_changed

        self._insert_ticket_data(req, db, ticket,
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

        return 'ticket.cs', None

    # ITimelineEventProvider methods

    def get_timeline_filters(self, req):
        if req.perm.has_permission('TICKET_VIEW'):
            yield ('ticket', 'Ticket changes')
            if self.timeline_details:
                yield ('ticket_details', 'Ticket details', False)

    def get_timeline_events(self, req, start, stop, filters):
        format = req.args.get('format')

        status_map = {'new': ('newticket', 'created'),
                      'reopened': ('newticket', 'reopened'),
                      'closed': ('closedticket', 'closed'),
                      'edit': ('editedticket', 'updated')}

        href = format == 'rss' and req.abs_href or req.href

        def produce((id, t, author, type, summary), status, fields,
                    comment, cid):
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
            if format == 'rss':
                title = 'Ticket #%s (%s %s): %s' % \
                        (id, type.lower(), verb, summary)
            else:
                title = Markup('Ticket <em title="%s">#%s</em> (%s) %s by %s',
                               summary, id, type, verb, author)
            ticket_href = href.ticket(id)
            if cid:
                ticket_href += '#comment:' + cid
            if status == 'new':
                message = summary
            else:
                message = Markup(info)
                if comment:
                    if format == 'rss':
                        message += wiki_to_html(comment, self.env, req, db,
                                                absurls=True)
                    else:
                        message += wiki_to_oneliner(comment, self.env, db,
                                                    shorten=True)
            return kind, ticket_href, title, t, author, message

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
                    return Markup('ticket %s', html.EM('#', id))
                att = AttachmentModule(self.env)
                for event in att.get_timeline_events(req, db, 'ticket',
                                                     format, start, stop,
                                                     display):
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

        description = wiki_to_html(ticket['description'], self.env, req, db)
        req.hdf['ticket.description.formatted'] = unicode(description)

        for change in self.grouped_changelog_entries(ticket, db):
            changes.append(change)
            # compute a change summary
            change_summary = {}
            # wikify comment
            if 'comment' in change:
                comment = change['comment']
                change['comment'] = unicode(wiki_to_html(
                    comment, self.env, req, db, absurls=True))
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
        req.hdf['ticket.changes'] = changes
        return (req.hdf.render('ticket_rss.cs'), 'application/rss+xml')


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

        self._validate_ticket(req, ticket)

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
        cnum = req.args.get('cnum')        
        replyto = req.args.get('replyto')
        internal_cnum = cnum
        if cnum and replyto: # record parent.child relationship
            internal_cnum = '%s.%s' % (replyto, cnum)
        ticket.save_changes(get_reporter_id(req, 'author'),
                            req.args.get('comment'), when=now, db=db,
                            cnum=internal_cnum)
        db.commit()

        try:
            tn = TicketNotifyEmail(self.env)
            tn.notify(ticket, req, newticket=False, modtime=now)
        except Exception, e:
            self.log.exception("Failure sending notification on change to "
                               "ticket #%s: %s" % (ticket.id, e))

        fragment = cnum and '#comment:'+cnum or ''
        req.redirect(req.href.ticket(ticket.id) + fragment)

    def _insert_ticket_data(self, req, db, ticket, reporter_id):
        """Insert ticket data into the hdf"""
        replyto = req.args.get('replyto')
        req.hdf['title'] = '#%d (%s)' % (ticket.id, ticket['summary'])
        req.hdf['ticket'] = ticket.values
        req.hdf['ticket'] = {
            'id': ticket.id,
            'href': req.href.ticket(ticket.id),
            'replyto': replyto
            }

        # -- Ticket fields
        
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
        req.hdf['ticket.description.formatted'] = wiki_to_html(
            ticket['description'], self.env, req, db)

        req.hdf['ticket.opened'] = format_datetime(ticket.time_created)
        req.hdf['ticket.opened_delta'] = pretty_timedelta(ticket.time_created)
        if ticket.time_changed != ticket.time_created:
            req.hdf['ticket'] = {
                'lastmod': format_datetime(ticket.time_changed),
                'lastmod_delta': pretty_timedelta(ticket.time_changed)
                }

        # -- Ticket Change History

        def quote_original(author, original, link):
            if not 'comment' in req.args: # i.e. the comment was not yet edited
                req.hdf['ticket.comment'] = '\n'.join(
                    ['Replying to [%s %s]:' % (link, author)] +
                    ['> %s' % line for line in original.splitlines()] + [''])

        if replyto == 'description':
            quote_original(ticket['reporter'], ticket['description'],
                           'ticket:%d' % ticket.id)
        replies = {}
        changes = []
        cnum = 0
        for change in self.grouped_changelog_entries(ticket, db):
            changes.append(change)
            # wikify comment
            comment = ''
            if 'comment' in change:
                comment = change['comment']
                change['comment'] = wiki_to_html(comment, self.env, req, db)
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
        req.hdf['ticket'] = {
            'changes': changes,
            'replies': replies,
            'cnum': cnum + 1
           }

        # -- Ticket Attachments

        req.hdf['ticket.attachments'] = attachments_to_hdf(self.env, req, db,
                                                           'ticket', ticket.id)
        if req.perm.has_permission('TICKET_APPEND'):
            req.hdf['ticket.attach_href'] = req.href.attachment('ticket',
                                                                ticket.id)

        # Add the possible actions to hdf
        actions = TicketSystem(self.env).get_available_actions(ticket, req.perm)
        for action in actions:
            req.hdf['ticket.actions.' + action] = '1'

    def grouped_changelog_entries(self, ticket, db, when=0):
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
                current = {
                    'http_date': http_date(date),
                    'date': format_datetime(date),
                    'author': author,
                    'fields': {},
                    'permanent': permanent
                }
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
