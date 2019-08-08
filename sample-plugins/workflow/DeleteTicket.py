# -*- coding: utf-8 -*-
#
# Copyright (C) 2007-2019 Edgewall Software
# Copyright (C) 2007 Eli Carter <retracile@gmail.com>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/.

from trac.core import Component, implements
from trac.perm import IPermissionRequestor
from trac.ticket.api import ITicketActionController
from trac.util.translation import _

revision = "$Rev$"
url = "$URL$"


class DeleteTicketActionController(Component):
    """Delete ticket using a workflow action.

    Illustrates how to create an `ITicketActionController` with side-effects.

    Add `DeleteTicketActionController` to the workflow option in the
    `[ticket]` section in TracIni. When added to the default value of
    `workflow`, the line will look like this:
    {{{#!ini
    workflow = ConfigurableTicketWorkflow,DeleteTicketActionController
    }}}
    """

    implements(IPermissionRequestor, ITicketActionController)

    # IPermissionRequestor methods

    def get_permission_actions(self):
        return ['TICKET_DELETE']

    # ITicketActionController methods

    def get_ticket_actions(self, req, ticket):
        actions = []
        if ticket.exists and 'TICKET_DELETE' in req.perm(ticket.resource):
            actions.append((0, 'delete'))
        return actions

    def get_all_status(self):
        return []

    def render_ticket_action_control(self, req, ticket, action):
        return 'delete', None, _("The ticket will be deleted.")

    def get_ticket_changes(self, req, ticket, action):
        return {}

    def apply_action_side_effects(self, req, ticket, action):
        if action == 'delete':
            ticket.delete()
