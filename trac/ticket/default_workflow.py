# -*- coding: utf-8 -*-
#
# Copyright (C) 2006-2007 Edgewall Software
# Copyright (C) 2006 Alec Thomas
# Copyright (C) 2007 Eli Carter
# Copyright (C) 2007 Christian Boos <cboos@neuf.fr>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.
#
# Author: Eli Carter

from genshi.builder import tag

from trac.core import *
from trac.perm import PermissionSystem
from trac.ticket.api import ITicketActionController
from trac.util.compat import set


# -- Utilities for the ConfigurableTicketWorkflow

def parse_workflow_config(rawactions):
    """Given a list of options from [ticket-workflow]"""
    actions = {}
    for option, value in rawactions:
        parts = option.split('.')
        action = parts[0]
        if action not in actions:
            actions[action] = {}
        if len(parts) == 1:
            # Base name, of the syntax: old,states,here -> newstate
            try:
                oldstates, newstate = [x.strip() for x in value.split('->')]
            except ValueError:
                raise Exception('Bad option "%s"' % (option, ))
            actions[action]['newstate'] = newstate
            actions[action]['oldstates'] = oldstates
        else:
            action, attribute = option.split('.')
            actions[action][attribute] = value
    # Fill in the defaults for every action, and normalize them to the desired
    # types
    for action, attributes in actions.items():
        # Default the 'name' attribute to the name used in the ini file
        if 'name' not in attributes:
            attributes['name'] = action
        # If not specified, an action is not the default.
        if 'default' not in attributes:
            attributes['default'] = 0
        else:
            attributes['default'] = int(attributes['default'])
        # If operations are not specified, that means no operations
        if 'operations' not in attributes:
            attributes['operations'] = []
        else:
            attributes['operations'] = attributes['operations'].split(',')
        # If no permissions are specified, then no permissions are needed
        if 'permissions' not in attributes:
            attributes['permissions'] = []
        else:
            attributes['permissions'] = attributes['permissions'].split(',')
        # Normalize the oldstates
        attributes['oldstates'] = [x.strip() for x in
                                   attributes['oldstates'].split(',')]
    return actions

def get_workflow_config(config):
    """Usually passed self.config, this will return the parsed ticket-workflow
    section.
    """
    # This is the default workflow used if there is no ticket-workflow section
    # in the ini.  This is the workflow Trac has historically had, warts and
    # all.
    default_workflow = [
        ('leave', '* -> *'),
        ('leave.default', '1'),
        ('leave.operations', 'leave_status'),

        ('accept', 'new -> assigned'),
        ('accept.permissions', 'TICKET_MODIFY'),
        ('accept.operations', 'set_owner_to_self'),

        ('resolve', 'new,assigned,reopened -> closed'),
        ('resolve.permissions', 'TICKET_MODIFY'),
        ('resolve.operations', 'set_resolution'),

        ('reassign', 'new,assigned,reopened -> new'),
        ('reassign.permissions', 'TICKET_MODIFY'),
        ('reassign.operations', 'set_owner'),

        ('reopen', 'closed -> reopened'),
        ('reopen.permissions', 'TICKET_CREATE'),
        ('reopen.operations', 'del_resolution'),
    ]
    raw_actions = list(config.options('ticket-workflow'))
    if not raw_actions:
        # Fallback to the default
        raw_actions = default_workflow
    actions = parse_workflow_config(raw_actions)
    return actions


class ConfigurableTicketWorkflow(Component):
    """Ticket action controller which provides actions according to a
    workflow defined in the TracIni configuration file, inside the
    [ticket-workflow] section.
    """
    
    def __init__(self, *args, **kwargs):
        Component.__init__(self, *args, **kwargs)
        self.actions = get_workflow_config(self.config)
        self.log.debug('%s\n' % str(self.actions))

    implements(ITicketActionController)

    # ITicketActionController methods

    def get_ticket_actions(self, req, ticket):
        """Returns a list of (weight, action) tuples that are valid for this
        request and this ticket."""
        # Get the list of actions that can be performed

        status = ticket['status'] or 'new'

        allowed_actions = []
        for action_name, action_info in self.actions.items():
            if 'hidden' in action_info['operations']:
                continue
            oldstates = action_info['oldstates']
            if oldstates == ['*'] or status in oldstates:
                # This action is valid in this state.  Check permissions.
                allowed = 0
                required_perms = action_info['permissions']
                if required_perms:
                    for permission in required_perms:
                        if permission in req.perm:
                            allowed = 1
                            break
                else:
                    allowed = 1
                if allowed:
                    allowed_actions.append((action_info['default'],
                                            action_name))
        return allowed_actions

    def get_all_status(self):
        """Return a list of all states described by the configuration.

        """
        all_status = set()
        for action_name, action_info in self.actions.items():
            all_status.update(action_info['oldstates'])
            all_status.add(action_info['newstate'])
        all_status.discard('*')
        return all_status
        
    def render_ticket_action_control(self, req, ticket, action):
        from trac.ticket import model

        self.log.debug('render_ticket_action_control: action "%s"' % action)

        this_action = self.actions[action]
        status = this_action['newstate']        
        operations = this_action['operations']

        control = [] # default to nothing
        hints = []
        if 'set_owner' in operations:
            id = action + '_reassign_owner'
            selected_owner = req.args.get(id, req.authname)

            if this_action.has_key('set_owner'):
                owners = [x.strip() for x in this_action['set_owner'].split(',')]
            elif self.config.getbool('ticket', 'restrict_owner'):
                perm = PermissionSystem(self.env)
                owners = perm.get_users_with_permission('TICKET_MODIFY')
            else:
                owners = None

            if owners == None:
                control.append(tag(['to ', tag.input(type='text', id=id, name=id,
                    value=req.args.get(id, req.authname))]))
                hints.append("The owner will change")
            elif len(owners) == 1:
                control.append(tag('to %s' % owners[0]))
                hints.append("The owner will change to %s" % owners[0])
            else:
                control.append(tag(['to ', tag.select(
                    [tag.option(x, selected=(x == selected_owner or None))
                     for x in owners],
                    id=id, name=id)]))
                hints.append("The owner will change")
        if 'set_resolution' in operations:
            if this_action.has_key('set_resolution'):
                resolutions = [x.strip() for x in this_action['set_resolution'].split(',')]
            else:
                resolutions = [val.name for val in model.Resolution.select(self.env)]
            if not resolutions:
                assert(resolutions)
            elif len(resolutions) == 1:
                control.append(tag('as %s' % resolutions[0]))
                hints.append("The resolution will be set to %s" % resolutions[0])
            else:
                id = action + '_resolve_resolution'
                selected_option = req.args.get(id, 'fixed')
                control.append(tag(['as ', tag.select(
                    [tag.option(x, selected=(x == selected_option or None))
                     for x in resolutions],
                    id=id, name=id)]))
                hints.append("The resolution will be set")
        if 'leave_status' in operations:
            control.append('as ' + ticket['status'])
        else:
            if status != '*':
                hints.append("Next status will be '%s'" % status)
        return (this_action['name'], tag(*control), '. '.join(hints))

    def get_ticket_changes(self, req, ticket, action):
        this_action = self.actions[action]

        # Enforce permissions
        if not self._has_perms_for_action(req, this_action):
            # The user does not have any of the listed permissions, so we won't
            # do anything.
            return {}

        updated = {}
        # Status changes
        status = this_action['newstate']
        if status != '*':
            updated['status'] = status

        for operation in this_action['operations']:
            if operation == 'del_owner':
                updated['owner'] = ''
            elif operation == 'set_owner':
                newowner = req.args.get(action + '_reassign_owner',
                                    this_action.get('set_owner', '').strip())
                # If there was already an owner, we get a list, [new, old],
                # but if there wasn't we just get new.
                if type(newowner) == list:
                    newowner = newowner[0]
                updated['owner'] = newowner
            elif operation == 'set_owner_to_self':
                updated['owner'] = req.authname

            if operation == 'del_resolution':
                updated['resolution'] = ''
            elif operation == 'set_resolution':
                newresolution = req.args.get(action + '_resolve_resolution',
                                this_action.get('set_resolution', '').strip())
                updated['resolution'] = newresolution

            # leave_status and hidden are just no-ops here, so we don't look
            # for them.
        return updated

    def apply_action_side_effects(self, req, ticket, action):
        pass

    def _has_perms_for_action(self, req, action):
        required_perms = action['permissions']
        if required_perms:
            for permission in required_perms:
                if permission in req.perm:
                    break
            else:
                # The user does not have any of the listed permissions
                return False
        return True

    # Public methods (for other ITicketActionControllers that want to use
    #                 our config file and provide an operation for an action)
    
    def get_actions_by_operation(self, operation):
        """Return a list of all actions with a given operation
        (for use in the controller's get_all_status())
        """
        actions = [(info['default'], action) for action, info
                   in self.actions.items()
                   if operation in info['operations']]
        return actions

    def get_actions_by_operation_for_req(self, req, ticket, operation):
        """Return list of all actions with a given operation that are valid
        in the given state for the controller's get_ticket_actions().

        If state='*' (the default), all actions with the given operation are
        returned (including those that are 'hidden').
        """
        actions = [(info['default'], action) for action, info
                   in self.actions.items()
                   if operation in info['operations'] and
                      ('*' in info['oldstates'] or
                       ticket['status'] in info['oldstates']) and
                      self._has_perms_for_action(req, info)]
        return actions

