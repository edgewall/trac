# -*- coding: utf-8 -*-
#
# Copyright (C) 2002-2013 Edgewall Software
# Copyright (C) 2012 Franz Mayer <franz.mayer@gefasoft.de>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

from genshi.builder import tag

from trac.core import Component, implements
from trac.resource import ResourceNotFound
from trac.ticket.api import ITicketActionController
from trac.ticket.default_workflow import ConfigurableTicketWorkflow
from trac.ticket.model import Milestone
from trac.util.translation import _
from trac.web.chrome import add_warning

revision = "$Rev$"
url = "$URL$"

class MilestoneOperation(Component):
    """Sets milestone for specific status.

=== Example ===
{{{
[ticket-workflow]
resolve.operations = set_resolution,set_milestone
resolve.milestone = invalid,wontfix,duplicate,worksforme->rejected
}}}

When setting status to `duplicate` the milestone will automatically change
to `rejected`.

'''Note:''' if user has changed milestone manually, this workflow operation
has ''no effect''!

=== Configuration ===
Don't forget to add `MilestoneOperation` to the workflow option
in `[ticket]` section. If there is no workflow option, the line will look
like this:
{{{
[ticket]
workflow = ConfigurableTicketWorkflow,MilestoneOperation
}}}
"""

    implements(ITicketActionController)

    def get_ticket_actions(self, req, ticket):
        actions_we_handle = []
        if req.authname != 'anonymous' and \
                    'TICKET_MODIFY' in req.perm(ticket.resource):
            controller = ConfigurableTicketWorkflow(self.env)
            actions_we_handle = controller.get_actions_by_operation_for_req(
                req, ticket, 'set_milestone')
        self.log.debug('set_milestone handles actions: %r', actions_we_handle)
        return actions_we_handle

    def get_all_status(self):
        return []

    def render_ticket_action_control(self, req, ticket, action):
        actions = ConfigurableTicketWorkflow(self.env).actions
        label = actions[action]['name']
        res_ms = self.__get_resolution_milestone_dict(ticket, action)
        resolutions = ''
        milestone = None
        for i, resolution in enumerate(res_ms):
            if i > 0:
                resolutions = "%s, '%s'" % (resolutions, resolution)
            else:
                resolutions = "'%s'" % resolution
                milestone = res_ms[resolution]
        hint = None
        if res_ms:
            try:
                Milestone(self.env, milestone)
            except ResourceNotFound:
                pass
            else:
                hint = _("For resolution %(resolutions)s the milestone will "
                         "be set to '%(milestone)s'.",
                         resolutions=resolutions, milestone=milestone)
        return (label, None, hint)

    def get_ticket_changes(self, req, ticket, action):
        if action == 'resolve' and \
                req.args and 'action_resolve_resolve_resolution' in req.args:
            old_milestone = ticket._old.get('milestone') or None
            user_milestone = ticket['milestone'] or None
            # If there's no user defined milestone, we try to set it
            # using the defined resolution -> milestone mapping.
            if old_milestone is None:
                new_status = req.args['action_resolve_resolve_resolution']
                new_milestone = self.__get_new_milestone(ticket, action,
                                                         new_status)
                # ... but we don't reset it to None unless it was None
                if new_milestone is not None or user_milestone is None:
                    try:
                        milestone = Milestone(self.env, new_milestone)
                        self.log.info('changed milestone from %s to %s',
                                      old_milestone, new_milestone)
                        return {'milestone': new_milestone}
                    except ResourceNotFound:
                        add_warning(req, _("Milestone %(name)s does not exist.",
                                           name=new_milestone))
        return {}

    def apply_action_side_effects(self, req, ticket, action):
        pass

    def __get_new_milestone(self, ticket, action, new_status):
        """Determines the new status"""
        if new_status:
            res_ms = self.__get_resolution_milestone_dict(ticket, action)
            return res_ms.get(new_status)

    def __get_resolution_milestone_dict(self, ticket, action):
        transitions = self.config.get('ticket-workflow',
                                      action + '.milestone').strip()
        transition = [x.strip() for x in transitions.split('->')]
        res_milestone = {}
        if len(transition) == 2:
            resolutions = [y.strip() for y in transition[0].split(',')]
            for res in resolutions:
                res_milestone[res] = transition[1]
        return res_milestone
