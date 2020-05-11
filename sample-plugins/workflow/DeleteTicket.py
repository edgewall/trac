# -*- coding: utf-8 -*-
#
# Copyright (C) 2007-2020 Edgewall Software
# Copyright (C) 2007 Eli Carter <retracile@gmail.com>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/.

from trac.core import implements,Component
from trac.ticket.api import ITicketActionController
from trac.perm import IPermissionRequestor

revision = "$Rev$"
url = "$URL$"

class DeleteTicketActionController(Component):
    """Provides the admin with a way to delete a ticket.

    Illustrates how to create an action controller with side-effects.

    Don't forget to add `DeleteTicketActionController` to the workflow
    option in the `[ticket]` section in TracIni.
    If there is no other workflow option, the line will look like this:
    {{{
    workflow = ConfigurableTicketWorkflow,DeleteTicketActionController
    }}}
    """

    implements(ITicketActionController, IPermissionRequestor)

    # IPermissionRequestor methods

    def get_permission_actions(self):
        return ['TICKET_DELETE']

    # ITicketActionController methods

    def get_ticket_actions(self, req, ticket):
        actions = []
        if 'TICKET_DELETE' in req.perm(ticket.resource):
            actions.append((0,'delete'))
        return actions

    def get_all_status(self):
        return []

    def render_ticket_action_control(self, req, ticket, action):
        return ("delete ticket", '', "This ticket will be deleted.")

    def get_ticket_changes(self, req, ticket, action):
        return {}

    def apply_action_side_effects(self, req, ticket, action):
        # Be paranoid here, as this should only be called when
        # action is delete...
        if action == 'delete':
            ticket.delete()
