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
import pkg_resources
import re
from StringIO import StringIO
import time

from genshi.core import Markup
from genshi.builder import tag

from trac.attachment import AttachmentModule
from trac.config import BoolOption, Option, IntOption
from trac.context import Context
from trac.core import *
from trac.mimeview.api import Mimeview, IContentConverter
from trac.search import ISearchSource, search_to_sql, shorten_result
from trac.ticket import Milestone, Ticket, TicketSystem, ITicketManipulator
from trac.ticket import ITicketActionController
from trac.ticket.notification import TicketNotifyEmail
from trac.timeline.api import ITimelineEventProvider, TimelineEvent
from trac.util import get_reporter_id
from trac.util.compat import any
from trac.util.datefmt import to_timestamp, utc
from trac.util.text import CRLF, shorten_line, obfuscate_email_address
from trac.util.presentation import separated
from trac.util.translation import _
from trac.versioncontrol.diff import get_diff_options, diff_blocks
from trac.web import IRequestHandler
from trac.web.chrome import add_link, add_script, add_stylesheet, Chrome, \
                            INavigationContributor, ITemplateProvider

class InvalidTicket(TracError):
    """Exception raised when a ticket fails validation."""
    title = "Invalid Ticket"


def cc_list(cc_field):
    """Split a CC: value in a list of addresses.

    TODO: will become `CcField.cc_list(value)
    """
    return [cc.strip() for cc in cc_field.split(',') if cc]


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
        """Default component for newly created tickets""")

    timeline_details = BoolOption('timeline', 'ticket_show_details', 'false',
        """Enable the display of all ticket changes in the timeline
        (''since 0.9'').""")

    max_description_size = IntOption('ticket', 'max_description_size', 262144,
        """Don't accept tickets with a too big description.
        (''since 0.11'').""")

    timeline_newticket_formatter = Option('timeline', 'newticket_formatter',
                                          'oneliner',
        """Which formatter flavor (e.g. 'default' or 'oneliner') should be
        used when presenting the description for new tickets.
        If 'oneliner', the [timeline] abbreviated_messages option applies.
        (''since 0.11'').""")

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
                   tag.a(_('New Ticket'), href=req.href.newticket(),
                         accesskey=7))

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
            yield ('ticket', _('Ticket changes'))
            if self.timeline_details:
                yield ('ticket_details', _('Ticket details'), False)

    def get_timeline_events(self, req, start, stop, filters):
        ts_start = to_timestamp(start)
        ts_stop = to_timestamp(stop)

        status_map = {'new': ('newticket', 'created'),
                      'reopened': ('reopenedticket', 'reopened'),
                      'closed': ('closedticket', 'closed'),
                      'edit': ('editedticket', 'updated')}
        context = Context(self.env, req)
        description = {}

        def produce((id, ts, author, type, summary, description),
                    status, fields, comment, cid):
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
            markup = message = None
            if status == 'new':
                message = description
            else:
                markup = info
                message = comment
            t = datetime.fromtimestamp(ts, utc)
            event = TimelineEvent(self, kind)
            event.set_changeinfo(t, author)
            event.add_markup(title=title, header=markup)
            event.add_wiki(ctx, body=message)
            if cid:
                event.href_fragment = '#comment:' + cid
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
                           % (ts_start, ts_stop))
            previous_update = None
            for id,t,author,type,summary,field,oldvalue,newvalue in cursor:
                if not previous_update or (id,t,author) != previous_update[:3]:
                    if previous_update:
                        ev = produce(previous_update, status, fields,
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
                ev = produce(previous_update, status, fields, comment, cid)
                if ev:
                    yield ev

            # New tickets
            if 'ticket' in filters:
                cursor.execute("SELECT id,time,reporter,type,summary,"
                               "description"
                               "  FROM ticket WHERE time>=%s AND time<=%s",
                               (ts_start, ts_stop))
                for row in cursor:
                    yield produce(row, 'new', {}, None, None)

            # Attachments
            if 'ticket_details' in filters:
                for event in AttachmentModule(self.env) \
                        .get_timeline_events(context('ticket'), start, stop):
                    yield event

    def event_formatter(self, event, key):
        flavor = 'oneliner'
        if event.kind == 'newticket':
            flavor = self.timeline_newticket_formatter
        return (flavor, {})

    # Internal methods

    def _get_action_controllers(self, req, ticket, action):
        """Generator yielding the controllers handling the given `action`"""
        for controller in TicketSystem(self.env).action_controllers:
            actions = [a for w,a in controller.get_ticket_actions(req, ticket)]
            if action in actions:
                yield controller

    def _process_newticket_request(self, req):
        context = Context(self.env, req)('ticket')
        req.perm.require('TICKET_CREATE')

        if req.method == 'POST' and 'field_owner' in req.args and \
               'TICKET_MODIFY' not in req.perm:
            del req.args['field_owner']

        ticket = context.resource
        self._populate(req, ticket)
        reporter_id = req.args.get('field_reporter') or \
                      get_reporter_id(req, 'author')
        ticket.values['reporter'] = reporter_id

        valid = None
        if req.method == 'POST' and not 'preview' in req.args:
            valid = self._validate_ticket(req, ticket)
            if valid:
                self._do_create(context) # redirected if successful
            # else fall through in a preview
            req.args['preview'] = True

        # don't validate for new tickets and don't validate twice
        if valid is None and 'preview' in req.args:
            valid = self._validate_ticket(req, ticket)
            
        # Preview a new ticket
        data = {
            'ticket': ticket,
            'context': context,
            'author_id': reporter_id,
            'actions': [],
            'version': None,
            'description_change': None,
            'valid': valid
        }

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
        req.perm.require('TICKET_VIEW')
        action = req.args.get('action', ('history' in req.args and 'history' or
                                         'view'))
        id = int(req.args.get('id'))
        context = Context(self.env, req)('ticket', id)
        ticket = context.resource

        data = {'ticket': ticket, 'context': context, 'comment': None}

        if action in ('history', 'diff'):
            field = req.args.get('field')
            if field:
                text_fields = [field]
            else:
                text_fields = [field['name'] for field in ticket.fields if
                               field['type'] == 'textarea']
            if action == 'history':
                return self._render_history(context, data, text_fields)
            elif action == 'diff':
                return self._render_diff(context, data, text_fields)
        elif req.method == 'POST': # 'Preview' or 'Submit'
            self._populate(req, ticket)
            valid = self._validate_ticket(req, ticket)

            # Do any action on the ticket?
            actions = TicketSystem(self.env).get_available_actions(req, ticket)
            if action not in actions:
                raise TracError('Invalid action "%s"' % action)
                # (this should never happen in normal situations)
            field_changes, problems = self.get_ticket_changes(req, ticket,
                                                              action)
            if problems:
                valid = False
                for problem in problems:
                    req.warning(problem)
                    req.warning(tag(tag.p('Please review your configuration, '
                                          'probably starting with'),
                                    tag.pre('[trac]\nworkflow = ...\n'),
                                    tag.p('in your ', tag.tt('trac.ini'), '.'))
                                )
            if 'preview' not in req.args:
                if valid:
                    self._apply_ticket_changes(ticket, field_changes)
                    self._do_save(context, action) # redirected if successful
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

        self._insert_ticket_data(context, data, get_reporter_id(req, 'author'),
                                 field_changes)

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
                     conversion[4], conversion[0])

        return 'ticket.html', data, None

    def _populate(self, req, ticket):
        ticket.populate(dict([(k[6:],v) for k,v in req.args.iteritems()
                              if k.startswith('field_')]))

    def _get_history(self, context):
        ticket = context.resource
        history = []
        for change in self.rendered_changelog_entries(context):
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
        data.update({'title': _('Ticket History'), 'history': history})

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
                rev, shortrev = _('Version %(num)s') % {'num': v}, 'v%d' % v
            else:
                rev, shortrev = _('Initial Version'), 'initial'
            return {'path':  path, 'rev': rev, 'shortrev': shortrev,
                    'href': context.resource_href(version=v)}

        # -- prop changes
        props = []
        for k, v in new_ticket.iteritems():
            if k not in text_fields:
                old, new = old_ticket[k], new_ticket[k]
                if old != new:
                    props.append({'name': k,
                                  'old': {'name': k, 'value': old},
                                  'new': {'name': k, 'value': new}})
        changes.append({'props': props, 'diffs': [],
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

            changes.append({'diffs': diffs, 'props': [],
                            'new': version_info(new_version, field),
                            'old': version_info(old_version, field)})

        # -- prev/up/next links
        if prev_version:
            add_link(req, 'prev', req.href.ticket(ticket.id, action='diff',
                                                  version=prev_version),
                     _('Version %(num)s') % {'num': prev_version})
        add_link(req, 'up', req.href.ticket(ticket.id, action='history'),
                 'Ticket History')
        if next_version:
            add_link(req, 'next', req.href.ticket(ticket.id, action='diff',
                                                  version=next_version),
                     _('Version %(num)s') % {'num': next_version})

        add_stylesheet(req, 'common/css/diff.css')
        add_script(req, 'common/js/diff.js')

        data.update({
            'title': _('Ticket Diff'),
            'old_version': old_version, 'new_version': new_version,
            'changes': changes, 'diff': diff_data,
            'num_changes': num_changes, 'change': new_change,
            'old_ticket': old_ticket, 'new_ticket': new_ticket,
            'longcol': '', 'shortcol': ''
        })

        return 'diff_view.html', data, None

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
        context = Context(self.env, req)('ticket', ticket.id)
        changes = []
        change_summary = {}

        for change in self.rendered_changelog_entries(context):
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

        data = {'ticket': ticket, 'context': context, 'changes': changes}
        output = Chrome(self.env).render_template(req, 'ticket.rss', data,
                                                  'application/rss+xml')
        return output, 'application/rss+xml'

    # Ticket validation and changes
    
    def _validate_ticket(self, req, ticket):
        valid = True

        # If the ticket has been changed, check the proper permission
        if ticket.exists and ticket._old:
            if 'TICKET_CHGPROP' not in req.perm:
                req.warning(_("No permission to change ticket fields."))
                ticket.values = ticket._old
                valid = False
            else: # TODO: field based checking
                if 'description' in ticket._old or \
                       'field_reporter' in ticket._old:
                    if 'TICKET_ADMIN' not in req.perm:
                        req.warning(_("No permissions to change ticket fields."))
                        ticket.values = ticket._old
                        valid = False

        comment = req.args.get('comment')
        if comment:
            if not ('TICKET_CHGPROP' in req.perm or \
                    'TICKET_APPEND' in req.perm):
                req.warning(_("No permissions to add a comment."))
                valid = False

        # Mid air collision?
        if ticket.exists and (ticket._old or comment):
            if req.args.get('ts') != str(ticket.time_changed):
                req.warning(_("Sorry, can not save your changes. "
                              "This ticket has been modified by someone else "
                              "since you started"))
                valid = False

        # Always require a summary
        if not ticket['summary']:
            req.warning(_('Tickets must contain a summary.'))
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
                        req.warning('"%s" is not a valid value for '
                                    'the %s field.' % (value, name))
                        valid = False
                elif not field.get('optional', False):
                    req.warning('field %s must be set' % name)
                    valid = False

        # Validate description length
        if len(ticket['description'] or '') > self.max_description_size:
            req.warning(_('Ticket description is too big (must be less than'
                          ' %(num)s bytes)') % {
                'num': self.max_description_size
            })
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
                    req.warning(_("The ticket field '%(field)s' is invalid: "
                                  "%(message)s") % {
                        'field': field, 'message': message
                    })
                else:
                    req.warning(message)
        return valid

    def _do_create(self, context):
        req = context.req
        ticket = context.resource

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

    def _do_save(self, context, action):
        req = context.req
        ticket = context.resource

        cnum = req.args.get('cnum')
        replyto = req.args.get('replyto')
        internal_cnum = cnum
        if cnum and replyto: # record parent.child relationship
            internal_cnum = '%s.%s' % (replyto, cnum)

        # -- Save changes
        
        now = datetime.now(utc)
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

            for controller in self._get_action_controllers(req, ticket,
                                                           action):
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
        fields = []
        for field in ticket.fields:
            name = field['name']
            type_ = field['type']

            # per type settings
            if type_ in ('radio', 'select'):
                if ticket.exists:
                    value = ticket.values.get(name)
                    options = field['options']
                    if value and not value in options:
                        # Current ticket value must be visible,
                        # even if it's not among the possible values
                        options.append(value)
            elif type_ == 'checkbox':
                value = ticket.values.get(name)
                if value in ('1', '0'):
                    field['rendered'] = value == '1' and _('yes') or _('no')
                    
            # per field settings
            if name in ('summary', 'reporter', 'description', 'status',
                        'resolution'):
                field['skip'] = True
            elif name == 'owner':
                field['skip'] = True
                if not ticket.exists:
                    field['label'] = 'Assign to'
                    if 'TICKET_MODIFY' in req.perm:
                        field['skip'] = False
            elif name == 'milestone':
                if not ticket.exists or 'TICKET_ADMIN' not in req.perm:
                    field['options'] = [opt for opt in field['options'] if not
                                        Milestone(self.env, opt).is_completed]
                from trac.ticket.roadmap import MilestoneModule
                milestone = ticket[name]
                href = req.href.milestone(milestone)
                field['rendered'] = MilestoneModule(self.env) \
                                    .render_milestone_link(href, milestone,
                                                           milestone)
            elif name == 'cc':
                if not (Chrome(self.env).show_email_addresses or \
                        'EMAIL_VIEW' in req.perm):
                    field['rendered'] = ', '.join(
                        [obfuscate_email_address(cc)
                         for cc in cc_list(ticket[name])])
                    
            # ensure sane defaults
            field.setdefault('optional', False)
            field.setdefault('options', [])
            field.setdefault('skip', False)
            fields.append(field)
        return fields
        
    def _insert_ticket_data(self, context, data, author_id, field_changes):
        """Insert ticket data into the template `data`"""
        req = context.req
        ticket = context.resource

        replyto = req.args.get('replyto')
        version = req.args.get('version', None)

        data['replyto'] = replyto
        if version is not None:
            try:
                version = int(version)
            except ValueError:
                version = None
        data['version'] = version
        data['description_change'] = None

        data['author_id'] = author_id

        # -- Ticket fields
        
        fields = self._prepare_fields(req, ticket)

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
        for change in self.rendered_changelog_entries(context):
            # change['permanent'] is false for attachment changes; true for
            # other changes.
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
                    if replyto == str(cnum):
                        quote_original(change['author'], change['comment'],
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

        if version is not None: ### FIXME
            ticket.values.update(values)

        data.update({
            'fields': fields, 'changes': changes,
            'replies': replies, 'cnum': cnum + 1,
            'attachments': AttachmentModule(self.env).attachment_list(context),
            'action_controls': action_controls,
            'action': selected_action,
            'change_preview': change_preview
        })

    def rendered_changelog_entries(self, context, when=None):
        """Iterate on changelog entries, consolidating related changes
        in a `dict` object.
        """
        types = {}
        for f in context.resource.fields:
            types[f['name']] = f['type']
        for group in self.grouped_changelog_entries(context.resource, None,
                                                    when):
            for field, changes in group['fields'].iteritems():
                # per type special rendering of diffs
                type_ = types.get(field)
                new, old = changes['new'], changes['old']
                if type_ == 'checkbox':
                    changes['rendered'] = new == '1' and "set" or "unset"
                elif type_ == 'textarea':
                    link = 'diff'
                    if 'cnum' in group:
                        href = context.resource_href(action='diff',
                                                     version=group['cnum'])
                        link = tag.a(link, href=href)

                    changes['rendered'] = tag('(', link, ')')

                # per name special rendering of diffs
                old_list, new_list = None, None
                sep = ', '
                if field == 'cc':
                    old_list, new_list = cc_list(old), cc_list(new)
                    if not (Chrome(self.env).show_email_addresses or \
                            'EMAIL_VIEW' in context.req.perm):
                        old_list = [obfuscate_email_address(cc)
                                    for cc in old_list]
                        new_list = [obfuscate_email_address(cc)
                                    for cc in new_list]
                elif field == 'keywords':
                    old_list, new_list = old.split(), new.split()
                    sep = ' '

                if (old_list, new_list) != (None, None):
                    added = [tag.em(x) for x in new_list if x not in old_list]
                    remvd = [tag.em(x) for x in old_list if x not in new_list]
                    added = added and tag(separated(added, sep), " added")
                    remvd = remvd and tag(separated(remvd, sep), " removed")
                    if added or remvd:
                        changes['rendered'] = tag(added,
                                                  added and remvd and '; ',
                                                  remvd)
            yield group

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
            else:
                current['fields'][field] = {'old': old, 'new': new}
        if current:
            yield current
