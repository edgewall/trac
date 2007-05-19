from genshi.builder import tag

from trac.core import Component, implements
from trac.ticket.api import ITicketActionController, TicketSystem
from trac.perm import IPermissionRequestor

class StatusFixerActionController(Component):
    """Provides the admin with a way to correct a ticket's status.

    This plugin is especially useful when you made changes to your workflow,
    and some ticket states are no longer valid. The tickets that are in those
    states can then be set to some valid state.

    Don't forget to add `StatusFixerActionController` to the workflow
    option in [ticket].
    If there is no workflow option, the line will look like this:

    workflow = DefaultTicketActionController,StatusFixerActionController
    """

    implements(ITicketActionController, IPermissionRequestor)

    # IPermissionRequestor methods

    def get_permission_actions(self):
        return ['TICKET_STATUSFIX']

    # ITicketActionController methods

    def get_ticket_actions(self, req, ticket):
        actions = []
        if 'TICKET_STATUSFIX' in req.perm:
            actions.append((0, 'force_status'))
        return actions

    def get_all_status(self):
        """We return all the states that are used in the database so that the
        user can query for used, but invalid, states."""
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute('SELECT DISTINCT status FROM ticket')
        all_states = [row[0] for row in cursor]
        cursor.close()
        return all_states

    def render_ticket_action_control(self, req, ticket, action):
        # Need to use the list of all states so you can't manually set
        # something to an invalid state.
        selected_value = req.args.get('force_status_value', 'new')
        all_states = TicketSystem(self.env).get_all_status()
        render_control = tag.select(
            [tag.option(x, selected=(x == selected_value and 'selected' or
                                     None)) for x in all_states],
            id='force_status_value', name='force_status_value')
        return ('force status to:', render_control) 

    def get_ticket_changes(self, req, ticket, action):
        return {'status': req.args.get('force_status_value')}

    def apply_action_side_effects(self, req, ticket, action):
        pass
