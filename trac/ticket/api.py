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

import re

from trac.config import *
from trac.core import *
from trac.perm import IPermissionRequestor, PermissionSystem
from trac.Search import ISearchSource, search_to_sql, shorten_result
from trac.util.text import shorten_line
from trac.util.markup import html, Markup
from trac.wiki import IWikiSyntaxProvider, Formatter


class ITicketChangeListener(Interface):
    """Extension point interface for components that require notification when
    tickets are created, modified, or deleted."""

    def ticket_created(ticket):
        """Called when a ticket is created."""

    def ticket_changed(ticket, comment, old_values):
        """Called when a ticket is modified.
        
        `old_values` is a dictionary containing the previous values of the
        fields that have changed.
        """

    def ticket_deleted(ticket):
        """Called when a ticket is deleted."""


class ITicketManipulator(Interface):
    """Miscellaneous manipulation of ticket workflow features."""

    def prepare_ticket(req, ticket, fields, actions):
        """Not currently called, but should be provided for future
        compatibility."""

    def validate_ticket(req, ticket):
        """Validate a ticket after it's been populated from user input.
        
        Must return a list of `(field, message)` tuples, one for each problem
        detected. `field` can be `None` to indicate an overall problem with the
        ticket. Therefore, a return value of `[]` means everything is OK."""


class TicketSystem(Component):
    implements(IPermissionRequestor, IWikiSyntaxProvider, ISearchSource)

    change_listeners = ExtensionPoint(ITicketChangeListener)

    restrict_owner = BoolOption('ticket', 'restrict_owner', 'false',
        """Make the owner field of tickets use a drop-down menu. See
        [wiki:TracTickets#AssigntoasDropDownList AssignToAsDropDownList]
        (''since 0.9'').""")

    # Public API

    def get_available_actions(self, ticket, perm_):
        """Returns the actions that can be performed on the ticket."""
        actions = {
            'new':      ['leave', 'resolve', 'reassign', 'accept'],
            'assigned': ['leave', 'resolve', 'reassign'          ],
            'reopened': ['leave', 'resolve', 'reassign'          ],
            'closed':   ['leave',                        'reopen']
        }
        perms = {'resolve': 'TICKET_MODIFY', 'reassign': 'TICKET_MODIFY',
                 'accept': 'TICKET_MODIFY', 'reopen': 'TICKET_CREATE'}
        return [action for action in actions.get(ticket['status'], ['leave'])
                if action not in perms or perm_.has_permission(perms[action])]

    def get_ticket_fields(self):
        """Returns the list of fields available for tickets."""
        from trac.ticket import model

        db = self.env.get_db_cnx()
        fields = []

        # Basic text fields
        for name in ('summary', 'reporter'):
            field = {'name': name, 'type': 'text', 'label': name.title()}
            fields.append(field)

        # Owner field, can be text or drop-down depending on configuration
        field = {'name': 'owner', 'label': 'Owner'}
        if self.restrict_owner:
            field['type'] = 'select'
            users = []
            perm = PermissionSystem(self.env)
            for username, name, email in self.env.get_known_users(db):
                if perm.get_user_permissions(username).get('TICKET_MODIFY'):
                    users.append(username)
            field['options'] = users
            field['optional'] = True
        else:
            field['type'] = 'text'
        fields.append(field)

        # Description
        fields.append({'name': 'description', 'type': 'textarea',
                       'label': 'Description'})

        # Default select and radio fields
        selects = [('type', model.Type), ('status', model.Status),
                   ('priority', model.Priority), ('milestone', model.Milestone),
                   ('component', model.Component), ('version', model.Version),
                   ('severity', model.Severity), ('resolution', model.Resolution)]
        for name, cls in selects:
            options = [val.name for val in cls.select(self.env, db=db)]
            if not options:
                # Fields without possible values are treated as if they didn't
                # exist
                continue
            field = {'name': name, 'type': 'select', 'label': name.title(),
                     'value': self.config.get('ticket', 'default_' + name),
                     'options': options}
            if name in ('status', 'resolution'):
                field['type'] = 'radio'
            elif name in ('milestone', 'version'):
                field['optional'] = True
            fields.append(field)

        # Advanced text fields
        for name in ('keywords', 'cc', ):
            field = {'name': name, 'type': 'text', 'label': name.title()}
            fields.append(field)

        for field in self.get_custom_fields():
            if field['name'] in [f['name'] for f in fields]:
                self.log.warning('Duplicate field name "%s" (ignoring)',
                                 field['name'])
                continue
            if not re.match('^[a-zA-Z][a-zA-Z0-9_]+$', field['name']):
                self.log.warning('Invalid name for custom field: "%s" '
                                 '(ignoring)', field['name'])
                continue
            field['custom'] = True
            fields.append(field)

        return fields

    def get_custom_fields(self):
        fields = []
        config = self.config['ticket-custom']
        for name in [option for option, value in config.options()
                     if '.' not in option]:
            field = {
                'name': name,
                'type': config.get(name),
                'order': config.getint(name + '.order', 0),
                'label': config.get(name + '.label') or name.capitalize(),
                'value': config.get(name + '.value', '')
            }
            if field['type'] == 'select' or field['type'] == 'radio':
                field['options'] = config.getlist(name + '.options', sep='|')
            elif field['type'] == 'textarea':
                field['width'] = config.getint(name + '.cols')
                field['height'] = config.getint(name + '.rows')
            fields.append(field)

        fields.sort(lambda x, y: cmp(x['order'], y['order']))
        return fields

    # IPermissionRequestor methods

    def get_permission_actions(self):
        return ['TICKET_APPEND', 'TICKET_CREATE', 'TICKET_CHGPROP',
                'TICKET_VIEW',
                ('TICKET_MODIFY', ['TICKET_APPEND', 'TICKET_CHGPROP']),  
                ('TICKET_ADMIN', ['TICKET_CREATE', 'TICKET_MODIFY',  
                                  'TICKET_VIEW'])]

    # IWikiSyntaxProvider methods

    def get_link_resolvers(self):
        return [('bug', self._format_link),
                ('ticket', self._format_link),
                ('comment', self._format_comment_link)]

    def get_wiki_syntax(self):
        yield (
            # matches #... but not &#... (HTML entity)
            r"!?(?<!&)#"
            # optional intertrac shorthand #T... + digits
            r"(?P<it_ticket>%s)\d+" % Formatter.INTERTRAC_SCHEME,
            lambda x, y, z: self._format_link(x, 'ticket', y[1:], y, z))

    def _format_link(self, formatter, ns, target, label, fullmatch=None):
        intertrac = formatter.shorthand_intertrac_helper(ns, target, label,
                                                         fullmatch)
        if intertrac:
            return intertrac
        try:
            cursor = formatter.db.cursor()
            cursor.execute("SELECT summary,status FROM ticket WHERE id=%s",
                           (str(int(target)),))
            row = cursor.fetchone()
            if row:
                return html.A(label, class_='%s ticket' % row[1],
                              title=shorten_line(row[0]) + ' (%s)' % row[1],
                              href=formatter.href.ticket(target))
        except ValueError:
            pass
        return html.A(label, class_='missing ticket', rel='nofollow',
                      href=formatter.href.ticket(target))

    def _format_comment_link(self, formatter, ns, target, label):
        type, id, cnum = 'ticket', '1', 0
        href = None
        if ':' in target:
            elts = target.split(':')
            if len(elts) == 3:
                type, id, cnum = elts
                href = formatter.href(type, id)
        else:
            # FIXME: the formatter should know which object the text being
            #        formatted belongs to
            if formatter.req:
                path_info = formatter.req.path_info.strip('/').split('/', 2)
                if len(path_info) == 2:
                    type, id = path_info[:2]
                    href = formatter.href(type, id)
                    cnum = target
        if href:
            return html.A(label, href="%s#comment:%s" % (href, cnum),
                          title="Comment %s for %s:%s" % (cnum, type, id))
        else:
            return label
 
    # ISearchSource methods

    def get_search_filters(self, req):
        if req.perm.has_permission('TICKET_VIEW'):
            yield ('ticket', 'Tickets')

    def get_search_results(self, req, terms, filters):
        if not 'ticket' in filters:
            return
        db = self.env.get_db_cnx()
        sql, args = search_to_sql(db, ['b.newvalue'], terms)
        sql2, args2 = search_to_sql(db, ['summary', 'keywords', 'description',
                                         'reporter', 'cc'], terms)
        cursor = db.cursor()
        cursor.execute("SELECT DISTINCT a.summary,a.description,a.reporter, "
                       "a.keywords,a.id,a.time,a.status FROM ticket a "
                       "LEFT JOIN ticket_change b ON a.id = b.ticket "
                       "WHERE (b.field='comment' AND %s ) OR %s" % (sql, sql2),
                       args + args2)
        for summary, desc, author, keywords, tid, date, status in cursor:
            ticket = '#%d: ' % tid
            if status == 'closed':
                ticket = Markup('<span style="text-decoration: line-through">'
                                '#%s</span>: ', tid)
            yield (req.href.ticket(tid),
                   ticket + shorten_line(summary),
                   date, author, shorten_result(desc, terms))
