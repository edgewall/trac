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

from genshi.builder import tag

from trac.core import Component, implements
from trac.ticket.api import ITicketActionController, TicketSystem
from trac.perm import IPermissionRequestor

revision = "$Rev$"
url = "$URL$"

class StatusFixerActionController(Component):
    """Provides the admin with a way to correct a ticket's status.

    This plugin is especially useful when you made changes to your workflow,
    and some ticket status are no longer valid. The tickets that are in those
    status can then be set to some valid state.

    Don't forget to add `StatusFixerActionController` to the workflow
    option in the `[ticket]` section in TracIni.
    If there is no other workflow option, the line will look like this:
    {{{
    workflow = ConfigurableTicketWorkflow,StatusFixerActionController
    }}}
    """

    implements(ITicketActionController, IPermissionRequestor)

    # IPermissionRequestor methods

    def get_permission_actions(self):
        return ['TICKET_STATUSFIX']

    # ITicketActionController methods

    def get_ticket_actions(self, req, ticket):
        actions = []
        if 'TICKET_STATUSFIX' in req.perm(ticket.resource):
            actions.append((0, 'force_status'))
        return actions

    def get_all_status(self):
        """Return all the status that are present in the database,
        so that queries for status no longer in use can be made.
        """
        return [status for status, in
                self.env.db_query("SELECT DISTINCT status FROM ticket")]

    def render_ticket_action_control(self, req, ticket, action):
        # Need to use the list of all status so you can't manually set
        # something to an invalid state.
        selected_value = req.args.get('force_status_value', 'new')
        all_status = TicketSystem(self.env).get_all_status()
        render_control = tag.select(
            [tag.option(x, selected=(x == selected_value and 'selected' or
                                     None)) for x in all_status],
            id='force_status_value', name='force_status_value')
        return ("force status to", render_control,
                "The next status will be the selected one")

    def get_ticket_changes(self, req, ticket, action):
        return {'status': req.args.get('force_status_value')}

    def apply_action_side_effects(self, req, ticket, action):
        pass
