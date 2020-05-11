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

from trac.core import implements,Component
from trac.ticket.api import ITicketActionController
from trac.ticket.default_workflow import ConfigurableTicketWorkflow
from trac.ticket.model import Priority, Ticket
#from trac.perm import IPermissionRequestor # (TODO)

revision = "$Rev$"
url = "$URL$"

class VoteOperation(Component):
    """Provides a simplistic vote feature.

    This is a sample action controller illustrating how to create additional
    ''operations''.

    Don't forget to add `VoteOperation` to the workflow
    option in the `[ticket]` section in TracIni.
    If there is no other workflow option, the line will look like this:
    {{{
    workflow = ConfigurableTicketWorkflow,VoteOperation
    }}}
    """

    implements(ITicketActionController)

    def get_ticket_actions(self, req, ticket):
        controller = ConfigurableTicketWorkflow(self.env)
        return controller.get_actions_by_operation_for_req(req, ticket, 'vote')

    def get_all_status(self):
        return []

    def render_ticket_action_control(self, req, ticket, action):
        id = 'vote_%s_result' % (action, )
        selected_value = req.args.get(id, 'for')
        options = ['for', 'against']
        return ("vote",
                tag.select([tag.option(x, selected=(x == selected_value or
                                                    None))
                            for x in options], name=id, id=id),
                "Vote on the issue, raising or lowering its priority")

    def get_ticket_changes(self, req, ticket, action):
        id = 'vote_%s_result' % (action, )
        selected = req.args.get(id, 'for')
        priorities = list(Priority.select(self.env))
        orig_ticket = Ticket(self.env, ticket.id)
        current_priority = int(Priority(self.env, name=
                                        orig_ticket['priority']).value)
        if selected == 'for':
            # priorities are 1-based, not 0-based
            new_value = max(1, current_priority - 1)
        else:
            maxval = max([int(p.value) for p in priorities])
            new_value = min(maxval, current_priority + 1)
        return {'priority': [p.name for p in priorities
                             if int(p.value) == new_value][0]}

    def apply_action_side_effects(self, req, ticket, action):
        pass
