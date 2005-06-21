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

from trac import perm, util
from trac.core import *


class TicketSystem(Component):

    def get_available_actions(self, ticket, perm_):
        """Returns the actions that can be performed on the ticket."""
        actions = {
            'new':      ['leave', 'resolve', 'reassign', 'accept'],
            'assigned': ['leave', 'resolve', 'reassign'          ],
            'reopened': ['leave', 'resolve', 'reassign'          ],
            'closed':   ['leave',                        'reopen']
        }
        perms = {'resolve': perm.TICKET_MODIFY, 'reassign': perm.TICKET_CHGPROP,
                 'accept': perm.TICKET_CHGPROP, 'reopen': perm.TICKET_CREATE}
        return [action for action in actions.get(ticket['status'], ['leave'])
                if action not in perms or perm_.has_permission(perms[action])]

    def get_ticket_fields(self):
        """Returns the list of fields available for tickets."""
        from trac.ticket import model
        from trac.Milestone import Milestone

        db = self.env.get_db_cnx()
        fields = []

        # Basic text fields
        for name in ('summary', 'reporter'):
            field = {'name': name, 'type': 'text', 'label': name.title()}
            fields.append(field)

        # Owner field, can be text or drop-down depending on configuration
        field = {'name': 'owner', 'label': 'Owner'}
        if self.config.get('ticket', 'restrict_owner').lower() in util.TRUE:
            field['type'] = 'select'
            users = []
            for username, name, email in self.env.get_known_users(db):
                users.append(username)
            field['options'] = users
        else:
            field['type'] = 'text'
        fields.append(field)

        # Description
        fields.append({'name': 'description', 'type': 'textarea',
                       'label': 'Description'})

        # Default select and radio fields
        selects = [('type', model.Type), ('status', model.Status),
                   ('priority', model.Priority), ('milestone', Milestone),
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
            fields.append(field)

        # Advanced text fields
        for name in ('keywords', 'cc', ):
            field = {'name': name, 'type': 'text', 'label': name.title()}
            fields.append(field)

        custom_fields = self.get_custom_fields()
        for field in custom_fields:
            field['custom'] = True

        return fields + custom_fields

    def get_custom_fields(self):
        fields = []
        for name in [option for option, value
                     in self.config.options('ticket-custom')
                     if '.' not in option]:
            field = {
                'name': name,
                'type': self.config.get('ticket-custom', name),
                'order': int(self.config.get('ticket-custom', name + '.order', '0')),
                'label': self.config.get('ticket-custom', name + '.label', ''),
                'value': self.config.get('ticket-custom', name + '.value', '')
            }
            if field['type'] == 'select' or field['type'] == 'radio':
                options = self.config.get('ticket-custom', name + '.options')
                field['options'] = [value.strip() for value in options.split('|')]
            elif field['type'] == 'textarea':
                field['width'] = self.config.get('ticket-custom', name + '.cols')
                field['height'] = self.config.get('ticket-custom', name + '.rows')
            fields.append(field)

        fields.sort(lambda x, y: cmp(x['order'], y['order']))
        return fields
