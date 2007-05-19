from genshi.builder import tag

from trac.core import implements,Component
from trac.ticket.api import ITicketActionController
from trac.ticket.default_workflow import ConfigurableTicketWorkflow
from trac.perm import IPermissionRequestor
from trac.config import Option, ListOption
from trac.util.compat import set

class CodeReviewActionController(Component):
    """Support for simple code reviews.

    The action that supports the `code_review` operation will present
    an extra choice for the review decision. Depending on that decision,
    a specific state will be selected.

    Example (from the enterprise-review-workflow.ini):

    review = in_review -> *
    review.name = review as
    review.operations = code_review
    review.code_review =
      approve -> in_QA,
      approve as noted -> post_review,
      request changes -> in_work

    Don't forget to add the `CodeReviewActionController` to the workflow
    option in [ticket].
    If there is no workflow option, the line will look like this:

    workflow = ConfigurableTicketWorkflow,CodeReviewActionController
    """

    implements(ITicketActionController, IPermissionRequestor)

    # IPermissionRequestor methods
    
    def get_permission_actions(self):
        return ['TICKET_REVIEW']

    # ITicketActionController methods
    
    def get_ticket_actions(self, req, ticket):
        # The review action is available in those states where it has been
        # configured, for those users who have the TICKET_REVIEW permission, as
        # long as they are not the owner of the ticket (you can't review your
        # own work!).
        actions_we_handle = []
        if req.authname != ticket['owner'] and 'TICKET_REVIEW' in req.perm:
            controller = ConfigurableTicketWorkflow(self.env)
            actions_we_handle = controller.get_actions_by_operation_for_req(req,
                                    ticket, 'code_review')
        self.log.debug('code review handles actions: %r' % actions_we_handle)
        return actions_we_handle

    def get_all_status(self):
        all_states = set()
        controller = ConfigurableTicketWorkflow(self.env)
        ouractions = controller.get_actions_by_operation('code_review')
        for weight, action in ouractions:
            raw_options = [x.strip() for x in
                           self.config.getlist('ticket-workflow',
                                               action + '.code_review')]
            states = [x.split('->')[1].strip() for x in raw_options]
            all_states.update(states)
        return all_states

    def render_ticket_action_control(self, req, ticket, action):
        control = None
        id = action + '_code_review_result'
        raw_options = [x.strip() for x in
                       self.config.getlist('ticket-workflow',
                                           action + '.code_review')]
        options = [x.split('->')[0].strip() for x in raw_options]

        selected_value = req.args.get(id, options[0])

        actions = ConfigurableTicketWorkflow(self.env).actions
        label = actions[action]['name']
        control = (label, tag(["as: ", tag.select(
            [tag.option(x, selected=(x == selected_value or None))
             for x in options],
            name=id, id=id)]))
        return control

    def get_ticket_changes(self, req, ticket, action):
        updated = {}
        grade = req.args.get(action + '_code_review_result')

        new_states = {}
        raw_options = [x.strip() for x in
                       self.config.getlist('ticket-workflow',
                                           action + '.code_review')]
        for raw_option in raw_options:
            option, state = [x.strip() for x in raw_option.split('->')]
            new_states[option] = state

        try:
            new_state = new_states[grade]
            updated['status'] = new_state
        except KeyError:
            pass # FIXME: should probably throw an error of some sort.
        return updated

    def apply_action_side_effects(self, req, ticket, action):
        pass
