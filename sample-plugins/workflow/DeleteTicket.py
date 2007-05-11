from genshi.builder import tag

from trac.core import implements,Component
from trac.ticket.api import ITicketActionController
from trac.perm import IPermissionRequestor

class DeleteTicketActionController(Component):
    """Provides the admin with a way to delete a ticket.

    Illustrates how to create an action controller with side-effects.

    Don't forget to add `DeleteTicketActionController` to the workflow
    option in [ticket].
    If there is no workflow option, the line will look like this:

    workflow = DefaultTicketActionController,DeleteTicketActionController
    """

    implements(ITicketActionController, IPermissionRequestor)

    # IPermissionRequestor methods

    def get_permission_actions(self):
        return ['TICKET_DELETE']

    # ITicketActionController methods

    def get_ticket_actions(self, req, ticket):
        actions = []
        if 'TICKET_DELETE' in req.perm:
            actions.append((0,'delete'))
        return actions

    def get_all_states(self):
        return []

    def render_ticket_action_control(self, req, ticket, action):
        control = None
        if action == 'delete':
            control = ('delete ticket', '') 
        return control

    def get_ticket_changes(self, req, ticket, action):
        description = ''
        if action == 'delete':
            description = tag.p('This ticket will be deleted.')
        return {}, description

    def apply_action_side_effects(self, req, ticket, action):
        if action == 'delete':
            ticket.delete()
