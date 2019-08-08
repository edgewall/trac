# -*- coding: utf-8 -*-
#
# Copyright (C) 2012-2019 Edgewall Software
# Copyright (C) 2012 Franz Mayer <franz.mayer@gefasoft.de>
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
from trac.resource import ResourceNotFound
from trac.ticket.api import ITicketActionController
from trac.ticket.default_workflow import ConfigurableTicketWorkflow
from trac.ticket.model import Milestone
from trac.util import to_list
from trac.util.translation import _
from trac.web.chrome import add_warning

revision = "$Rev$"
url = "$URL$"


class MilestoneOperation(Component):
    """Sets milestone for specified resolutions.

    Example:
    {{{#!ini
    [ticket-workflow]
    resolve.operations = set_resolution,set_milestone
    resolve.milestone = invalid,wontfix,duplicate,worksforme -> rejected
    }}}

    When setting resolution to `duplicate` the milestone will
    automatically change to `rejected`. If user changes milestone
    manually when resolving the ticket, this workflow operation has
    ''no effect''.

    Don't forget to add `MilestoneOperation` to the `workflow` option
    in the `[ticket]` section of TracIni. When added to the default
    value of `workflow`, the line will look like this:
    {{{#!ini
    [ticket]
    workflow = ConfigurableTicketWorkflow,MilestoneOperation
    }}}
    """

    implements(ITicketActionController)

    def get_ticket_actions(self, req, ticket):
        controller = ConfigurableTicketWorkflow(self.env)
        return controller.get_actions_by_operation_for_req(req, ticket,
                                                           'set_milestone')

    def get_all_status(self):
        return []

    def render_ticket_action_control(self, req, ticket, action):
        actions = ConfigurableTicketWorkflow(self.env).actions
        label = actions[action]['label']
        hint = None
        old_milestone = ticket._old.get('milestone')
        if old_milestone is None:
            resolutions, milestone = \
                self._get_resolutions_and_milestone(action)
            if resolutions:
                try:
                    Milestone(self.env, milestone)
                except ResourceNotFound:
                    pass
                else:
                    res_hint = ', '.join("'%s'" % r for r in resolutions)
                    hint = _("For resolution %(resolutions)s the milestone "
                             "will be set to '%(milestone)s'.",
                             resolutions=res_hint, milestone=milestone)
        return label, None, hint

    def get_ticket_changes(self, req, ticket, action):
        old_milestone = ticket._old.get('milestone')
        if old_milestone is None:
            new_milestone = self._get_resolutions_and_milestone(action)[1]
            try:
                Milestone(self.env, new_milestone)
            except ResourceNotFound:
                add_warning(req, _("Milestone %(name)s does not exist.",
                                   name=new_milestone))
            else:
                self.log.info("Changed milestone from %s to %s",
                              old_milestone, new_milestone)
                return {'milestone': new_milestone}
        return {}

    def apply_action_side_effects(self, req, ticket, action):
        pass

    def _get_resolutions_and_milestone(self, action):
        transitions = self.config.get('ticket-workflow', action + '.milestone')
        milestone = None
        resolutions = []
        try:
            transition = to_list(transitions, sep='->')
        except ValueError:
            pass
        else:
            if len(transition) == 2:
                resolutions = to_list(transition[0])
                milestone = transition[1]
        return resolutions, milestone
