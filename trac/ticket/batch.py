# -*- coding: utf-8 -*-
#
# Copyright (C) 2010 Brian Meeker
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.
#
# Author: Brian Meeker <meeker.brian@gmail.com>

import re

from trac.core import *
from trac.notification.api import NotificationSystem
from trac.perm import IPermissionRequestor
from trac.ticket.api import ITicketManipulator, TicketSystem
from trac.ticket.model import Ticket
from trac.ticket.notification import BatchTicketChangeEvent
from trac.util import to_list
from trac.util.datefmt import datetime_now, utc
from trac.util.html import tag
from trac.util.text import exception_to_unicode, to_unicode
from trac.util.translation import _, tag_
from trac.web.api import HTTPBadRequest, IRequestFilter, IRequestHandler
from trac.web.chrome import add_warning, add_script_data


class BatchModifyModule(Component):
    """Ticket batch modification module.

    This component allows multiple tickets to be modified in one request from
    the custom query page. For users with the TICKET_BATCH_MODIFY permission
    it will add a [TracBatchModify batch modify] section underneath custom
    query results. Users can choose which tickets and fields they wish to
    modify.
    """

    implements(IPermissionRequestor, IRequestFilter, IRequestHandler)

    is_valid_default_handler = False
    ticket_manipulators = ExtensionPoint(ITicketManipulator)

    list_separator_re = re.compile(r'[;\s,]+')
    list_connector_string = ', '

    # IRequestHandler methods

    def match_request(self, req):
        return req.path_info == '/batchmodify'

    def process_request(self, req):
        if req.method != 'POST':
            raise HTTPBadRequest(_("Invalid request arguments."))
        req.perm.assert_permission('TICKET_BATCH_MODIFY')

        comment = req.args.get('batchmod_value_comment', '')
        action = req.args.get('action')

        # Get new ticket values from POST request.
        new_values = {}
        for field in TicketSystem(self.env).get_ticket_fields():
            name = field['name']
            if name not in ('id', 'resolution', 'status', 'owner', 'time',
                            'changetime', 'summary', 'description') + \
                           (('reporter',) if 'TICKET_ADMIN' not in req.perm
                                          else ()) \
                    and field['type'] != 'textarea':
                arg_name = 'batchmod_value_' + name
                if arg_name in req.args:
                    new_values[name] = req.args.get(arg_name)

        selected_tickets = to_list(req.args.get('selected_tickets', ''))
        self._save_ticket_changes(req, selected_tickets, new_values, comment,
                                  action)

        # Always redirect back to the query page we came from
        req.redirect(req.args.get('query_href') or req.href.query())

    # IRequestFilter methods

    def pre_process_request(self, req, handler):
        return handler

    def post_process_request(self, req, template, data, metadata):
        if req.path_info == '/query' and data is not None and \
                'TICKET_BATCH_MODIFY' in req.perm('ticket'):
            self.add_template_data(req, data, data['tickets'])
        return template, data, metadata

    # IPermissionRequestor methods

    def get_permission_actions(self):
        return ['TICKET_BATCH_MODIFY',
                ('TICKET_BATCH_MODIFY', ['TICKET_MODIFY']),
                ('TICKET_ADMIN', ['TICKET_BATCH_MODIFY'])]

    def add_template_data(self, req, data, tickets):
        data['batch_modify'] = True
        data['query_href'] = req.session['query_href'] or req.href.query()
        data['action_controls'] = self._get_action_controls(req, tickets)
        batch_list_modes = [
            {'name': _("add"), 'value': "+"},
            {'name': _("remove"), 'value': "-"},
            {'name': _("add / remove"), 'value': "+-"},
            {'name': _("set to"), 'value': "="},
        ]
        add_script_data(req, batch_list_modes=batch_list_modes,
                        batch_list_properties=self._get_list_fields())

    def _get_list_fields(self):
        return [f['name']
                for f in TicketSystem(self.env).get_ticket_fields()
                if f['type'] == 'text' and f.get('format') == 'list']

    def _get_action_controls(self, req, ticket_data):
        tickets = [Ticket(self.env, t['id']) for t in ticket_data]
        action_weights = {}
        action_tickets = {}
        for t in tickets:
            for ctrl in TicketSystem(self.env).action_controllers:
                for weight, action in ctrl.get_ticket_actions(req, t) or []:
                    if action in action_weights:
                        action_weights[action] = max(action_weights[action],
                                                     weight)
                        action_tickets[action].append(t)
                    else:
                        action_weights[action] = weight
                        action_tickets[action] = [t]

        sorted_actions = [a for a, w
                            in sorted(action_weights.iteritems(),
                                      key=lambda item: (item[1], item[0]),
                                      reverse=True)]

        action_controls = []
        for action in sorted_actions:
            first_label = None
            hints = []
            widgets = []
            ticket = action_tickets[action][0]
            for controller in self._get_action_controllers(req, ticket,
                                                           action):
                label, widget, hint = controller.render_ticket_action_control(
                    req, ticket, action)
                if not first_label:
                    first_label = label
                widgets.append(widget)
                hints.append(hint)
            action_controls.append((action, first_label, tag(widgets), hints))
        return action_controls

    def _get_action_controllers(self, req, ticket, action):
        """Generator yielding the controllers handling the given `action`"""
        for controller in TicketSystem(self.env).action_controllers:
            actions = [a for w, a in
                       controller.get_ticket_actions(req, ticket) or []]
            if action in actions:
                yield controller

    def _get_updated_ticket_values(self, req, ticket, new_values):
        list_fields = self._get_list_fields()
        _values = new_values.copy()
        for field in list_fields:
            mode = req.args.get('batchmod_mode_' + field)
            if mode:
                old = ticket[field] if field in ticket else ''
                new = req.args.get('batchmod_primary_' + field, '')
                new2 = req.args.get('batchmod_secondary_' + field, '')
                _values[field] = self._change_list(old, new, new2, mode)
        return _values

    def _save_ticket_changes(self, req, selected_tickets, new_values, comment,
                             action):
        """Save changes to tickets."""
        valid = True
        for manipulator in self.ticket_manipulators:
            if hasattr(manipulator, 'validate_comment'):
                for message in manipulator.validate_comment(req, comment):
                    valid = False
                    add_warning(req, tag_("The ticket comment is invalid: "
                                          "%(message)s",
                                          message=message))

        tickets = []
        for id_ in selected_tickets:
            t = Ticket(self.env, id_)
            values = self._get_updated_ticket_values(req, t, new_values)
            for ctlr in self._get_action_controllers(req, t, action):
                values.update(ctlr.get_ticket_changes(req, t, action))
            t.populate(values)
            for manipulator in self.ticket_manipulators:
                for field, message in manipulator.validate_ticket(req, t):
                    valid = False
                    if field:
                        add_warning(req, tag_("The ticket field %(field)s is "
                                              "invalid: %(message)s",
                                              field=tag.strong(field),
                                              message=message))
                    else:
                        add_warning(req, message)
            tickets.append(t)

        if not valid:
            return

        when = datetime_now(utc)
        with self.env.db_transaction:
            for t in tickets:
                t.save_changes(req.authname, comment, when=when)
                for ctlr in self._get_action_controllers(req, t, action):
                    ctlr.apply_action_side_effects(req, t, action)

        event = BatchTicketChangeEvent(selected_tickets, when,
                                       req.authname, comment, new_values,
                                       action)
        try:
            NotificationSystem(self.env).notify(event)
        except Exception as e:
            self.log.error("Failure sending notification on ticket batch"
                           "change: %s", exception_to_unicode(e))
            add_warning(req,
                        tag_("The changes have been saved, but an error "
                             "occurred while sending notifications: "
                             "%(message)s", message=to_unicode(e)))

    def _change_list(self, old_list, new_list, new_list2, mode):
        def _to_list(s):
            return [i.strip() for i in self.list_separator_re.split(s) if i]

        changed_list = _to_list(old_list)
        new_list = _to_list(new_list)
        new_list2 = _to_list(new_list2)

        if mode == '=':
            changed_list = new_list
        elif mode == '+':
            for entry in new_list:
                if entry not in changed_list:
                    changed_list.append(entry)
        elif mode == '-':
            for entry in new_list:
                while entry in changed_list:
                    changed_list.remove(entry)
        elif mode == '+-':
            for entry in new_list:
                if entry not in changed_list:
                    changed_list.append(entry)
            for entry in new_list2:
                while entry in changed_list:
                    changed_list.remove(entry)
        return self.list_connector_string.join(changed_list)
