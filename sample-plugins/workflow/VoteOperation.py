from genshi.builder import tag

from trac.core import implements,Component
from trac.ticket.api import ITicketActionController, DefaultTicketActionController
from trac.ticket.model import Priority, Ticket
#from trac.perm import IPermissionRequestor # (TODO)

class VoteOperation(Component):
    """Provides a simplistic vote feature.

    This is a sample action controller illustrating how to create additional
    ''operations''.

    Don't forget to add `VoteOperation` to the workflow option in [ticket].
    If there is no workflow option, the line will look like this:

    workflow = DefaultTicketActionController,VoteOperation
    """
    

    implements(ITicketActionController)

    def get_ticket_actions(self, req, ticket):
        controller = DefaultTicketActionController(self.env)
        return controller.get_actions_by_operation_for_req(req, ticket, 'vote')

    def get_all_states(self):
        return []

    def render_ticket_action_control(self, req, ticket, action):
        control = None
        if action in [x[1] for x in self.get_ticket_actions(req, ticket)]:
            id = 'vote_%s_result' % (action, )
            selected_value = req.args.get(id, 'for')
            options = ['for', 'against']
            control = ('vote', tag.select(
                [tag.option(x, selected=(x == selected_value or None))
                 for x in options],
                name=id, id=id))
        return control

    def get_ticket_changes(self, req, ticket, action):
        updated = {}
        if action in [x[1] for x in self.get_ticket_actions(req, ticket)]:
            id = 'vote_%s_result' % (action, )
            selected = req.args.get(id, 'for')
            priorities = list(Priority.select(self.env))
            orig_ticket = Ticket(self.env, ticket.id)
            current_priority = int(Priority(self.env, name=orig_ticket['priority']).value)
            if selected == 'for':
                # priorities are 1-based, not 0-based
                new_value = max(1, current_priority - 1)
            else:
                maxval = max([int(p.value) for p in priorities])
                new_value = min(maxval, current_priority + 1)
            new_priority = [p.name for p in priorities if int(p.value) == new_value][0]
            updated['priority'] = new_priority
        return updated, ''

    def apply_action_side_effects(self, req, ticket, action):
        pass
