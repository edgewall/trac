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

import re
from datetime import datetime

from genshi.builder import tag

from trac.config import *
from trac.context import IContextProvider, Context
from trac.core import *
from trac.perm import IPermissionRequestor, PermissionSystem
from trac.util import Ranges
from trac.util.text import shorten_line
from trac.util.datefmt import utc
from trac.wiki import IWikiSyntaxProvider, Formatter


class ITicketChangeListener(Interface):
    """Extension point interface for components that require notification when
    tickets are created, modified, or deleted."""

    def ticket_created(ticket):
        """Called when a ticket is created."""

    def ticket_changed(ticket, comment, author, old_values):
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


class TicketContext(Context):
    """Context used for describing Ticket resources."""

    realm = 'ticket'

    # methods reimplemented from Context

    def get_resource(self):
        from trac.ticket.model import Ticket
        return Ticket(self.env, self.id and int(self.id) or None, self.db)

    def name(self):
        return 'Ticket ' + self.shortname()

    def shortname(self):
        return '#%s' % self.id

    def summary(self):
        summary = self.resource['summary']
        status = self.resource['status']
        if status == 'closed':
            status += ':' + self.resource['resolution']
        return "%s (%s)" % (shorten_line(summary), status)        


class TicketSystem(Component):
    implements(IPermissionRequestor, IWikiSyntaxProvider, IContextProvider)

    change_listeners = ExtensionPoint(ITicketChangeListener)

    restrict_owner = BoolOption('ticket', 'restrict_owner', 'false',
        """Make the owner field of tickets use a drop-down menu. See
        [TracTickets#Assign-toasDrop-DownList Assign-to as Drop-Down List]
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
        return [action for action in actions.get(ticket['status'] or 'new',
                                                 ['leave'])
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
            perm = PermissionSystem(self.env)
            field['options'] = perm.get_users_with_permission('TICKET_MODIFY')
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
                field['optional'] = True
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
                if '' in field['options']:
                    field['optional'] = True
                    field['options'].remove('')
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
            r"(?P<it_ticket>%s)%s" % (Formatter.INTERTRAC_SCHEME,
                                      Ranges.RE_STR),
            lambda x, y, z: self._format_link(x, 'ticket', y[1:], y, z))

    def _format_link(self, formatter, ns, target, label, fullmatch=None):
        intertrac = formatter.shorthand_intertrac_helper(ns, target, label,
                                                         fullmatch)
        if intertrac:
            return intertrac
        try:
            link, params, fragment = formatter.split_link(target)
            r = Ranges(link)
            if len(r) == 1:
                ctx = formatter.context('ticket', r.a)
                try:
                    status = ctx.resource['status']
                    return tag.a(label, class_=('%s ticket' % status),
                                 title=ctx.summary(),
                                 href=ctx.resource_href() + params + fragment)
                except TracError:
                    pass
                return tag.a(label, class_='missing ticket', 
                             href=ctx.resource_href(), rel="nofollow")
            else:
                ranges = str(r)
                if params:
                    params = '&' + params[1:]
                return tag.a(label, title='Tickets '+ranges,
                             href=formatter.href.query(id=ranges) + params)
        except ValueError:
            pass
        return tag.a(label, class_='missing ticket')

    def _format_comment_link(self, formatter, ns, target, label):
        context = None
        if ':' in target:
            elts = target.split(':')
            if len(elts) == 3:
                cnum, realm, id = elts
                if cnum != 'description' and cnum and not cnum[0].isdigit():
                    realm, id, cnum = elts # support old comment: style
                context = formatter.context(realm, id)
        else:
            context = formatter.context
            cnum = target

        if context:
            return tag.a(label, href=("%s#comment:%s" %
                                      (context.resource_href(), cnum)),
                         title="Comment %s for %s" % (cnum, context.name()))
        else:
            return label
 
    # IContextProvider methods

    def get_context_classes(self):
        yield TicketContext
