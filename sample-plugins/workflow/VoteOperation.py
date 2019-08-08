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
from trac.ticket.api import ITicketActionController
from trac.ticket.default_workflow import ConfigurableTicketWorkflow
from trac.ticket.model import Priority
from trac.util.html import tag

revision = "$Rev$"
url = "$URL$"


class VoteOperation(Component):
    """Provides a simple vote feature.

    This is a sample action controller illustrating how to create
    additional ''operations''.

    Add the `vote` operation to a workflow action, for example:
    {{{#!ini
    vote = new -> new
    vote.operations = vote
    }}}

    Don't forget to add `VoteOperation` to the `workflow` option
    in the `[ticket]` section of TracIni. When added to the default
    value of `workflow`, the line will look like this:
    {{{#!ini
    workflow = ConfigurableTicketWorkflow,VoteOperation
    }}}
    """

    implements(ITicketActionController)

    vote_options = ('for', 'against')
    id_for_action = 'action_%s_vote'

    def get_ticket_actions(self, req, ticket):
        controller = ConfigurableTicketWorkflow(self.env)
        return controller.get_actions_by_operation_for_req(req, ticket, 'vote')

    def get_all_status(self):
        return []

    def render_ticket_action_control(self, req, ticket, action):
        id = self.id_for_action % action
        selected_value = req.args.get(id, self.vote_options[0])
        render_control = tag.select(
            [tag.option(x, selected=(x == selected_value or None))
             for x in self.vote_options], name=id, id=id)
        return ("vote", render_control,
                "Vote on the issue, raising or lowering its priority")

    def get_ticket_changes(self, req, ticket, action):
        id = self.id_for_action % action
        selected = req.args.get(id, self.vote_options[0])
        priorities = list(Priority.select(self.env))
        name_by_val = {int(p.value): p.name for p in priorities}
        ticket_priority_name = ticket._old.get('priority', ticket['priority'])
        ticket_priority = \
            [p for p in priorities if p.name == ticket_priority_name][0]
        if selected == self.vote_options[0]:
            max_val = max(name_by_val)
            new_val = min(max_val, int(ticket_priority.value) + 1)
        else:
            min_val = min(name_by_val)
            new_val = max(min_val, int(ticket_priority.value) - 1)

        return {'priority': name_by_val[new_val]}

    def apply_action_side_effects(self, req, ticket, action):
        pass
