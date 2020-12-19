# -*- coding: utf-8 -*-
#
# Copyright (C) 2007-2020 Edgewall Software
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

from collections import OrderedDict

from trac.core import Component, implements
from trac.perm import IPermissionRequestor
from trac.ticket.api import ITicketActionController
from trac.ticket.default_workflow import ConfigurableTicketWorkflow
from trac.util import to_list
from trac.util.html import tag

revision = "$Rev$"
url = "$URL$"


class CodeReviewActionController(Component):
    """Support for simple code reviews.

    The action that supports the `code_review` operation will present
    an extra choice for the review decision. Depending on that decision,
    a specific state will be selected.

    Example (from the enterprise-review-workflow.ini):
    {{{#!ini
    request_review = in_work -> in_review
    review = in_review -> *
    review.operations = code_review
    review.code_review =
      approve -> in_QA,
      approve as noted -> post_review,
      request changes -> in_work
    }}}

    Don't forget to add the `CodeReviewActionController` to the workflow
    option in the `[ticket]` section in TracIni. When added to the default
    value of `workflow`, the line will look like this:
    {{{#!ini
    workflow = ConfigurableTicketWorkflow,CodeReviewActionController
    }}}
    """

    implements(IPermissionRequestor, ITicketActionController)

    # IPermissionRequestor methods

    def get_permission_actions(self):
        return ['TICKET_REVIEW']

    # ITicketActionController methods

    def get_ticket_actions(self, req, ticket):
        # The review action is available in those status where it has been
        # configured, for those users who have the TICKET_REVIEW permission, as
        # long as they are not the owner of the ticket (you can't review your
        # own work).
        actions_we_handle = []
        if req.authname != ticket['owner'] and \
                    'TICKET_REVIEW' in req.perm(ticket.resource):
            controller = ConfigurableTicketWorkflow(self.env)
            actions_we_handle = controller.get_actions_by_operation_for_req(
                req, ticket, 'code_review')
        self.log.debug('code review handles actions: %r', actions_we_handle)
        return actions_we_handle

    def get_all_status(self):
        all_status = set()
        controller = ConfigurableTicketWorkflow(self.env)
        for weight, action \
                in controller.get_actions_by_operation('code_review'):
            review_options = self._get_review_options(action)
            all_status.update(iter(review_options.values()))
        return all_status

    def render_ticket_action_control(self, req, ticket, action):
        id, selected = self._get_selected(req, action)

        review_options = self._get_review_options(action)
        actions = ConfigurableTicketWorkflow(self.env).actions

        label = actions[action]['label']
        control = tag(["as: ",
                       tag.select([
                           tag.option(option,
                                      selected=(option == selected or None))
                           for option in review_options],
                           name=id, id=id)])
        if selected:
            new_status = self._get_new_status(req, action, review_options)
            hint = "Next status will be '%s'" % new_status
        else:
            hint = "Next status will be one of " + \
                   ', '.join("'%s'" % st for st in review_options.values())
        return label, control, hint

    def get_ticket_changes(self, req, ticket, action):
        new_status = self._get_new_status(req, action)
        return {'status': new_status or 'new'}

    def apply_action_side_effects(self, req, ticket, action):
        pass

    # Internal methods

    def _get_selected(self, req, action):
        id = 'action_%s_code_review' % action
        return id, req.args.get(id)

    def _get_review_options(self, action):
        values = self.config.getlist('ticket-workflow', action + '.code_review')
        return OrderedDict(to_list(v, sep='->') for v in values)

    def _get_new_status(self, req, action, review_options=None):
        selected = self._get_selected(req, action)[1]
        if not review_options:
            review_options = self._get_review_options(action)
        return review_options[selected]
