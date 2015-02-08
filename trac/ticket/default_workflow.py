# -*- coding: utf-8 -*-
#
# Copyright (C) 2006-2009 Edgewall Software
# Copyright (C) 2006 Alec Thomas
# Copyright (C) 2007 Eli Carter
# Copyright (C) 2007 Christian Boos <cboos@edgewall.org>
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

from ConfigParser import ParsingError, RawConfigParser
from StringIO import StringIO
from collections import defaultdict
from functools import partial
from pkg_resources import resource_filename

from genshi.builder import tag

from trac.config import Configuration, ConfigSection
from trac.core import *
from trac.env import IEnvironmentSetupParticipant
from trac.perm import PermissionSystem
from trac.ticket.api import ITicketActionController, TicketSystem
from trac.ticket.model import Resolution
from trac.util import get_reporter_id, to_list
from trac.util.presentation import separated
from trac.util.translation import _, tag_, cleandoc_
from trac.web.chrome import Chrome, add_script, add_script_data
from trac.wiki.formatter import system_message
from trac.wiki.macros import WikiMacroBase

# -- Utilities for the ConfigurableTicketWorkflow

def parse_workflow_config(rawactions):
    """Given a list of options from [ticket-workflow]"""

    default = {
        'oldstates': [],
        'newstate': '',
        'name': '',
        'default': 0,
        'operations': [],
        'permissions': []
    }

    actions = defaultdict(lambda: default.copy())
    for option, value in rawactions:
        parts = option.split('.')
        name = parts[0]
        if len(parts) == 1:
            # Base name, of the syntax: old,states,here -> newstate
            try:
                oldstates, newstate = [x.strip() for x in value.split('->')]
            except ValueError:
                continue  # Syntax error, a warning will be logged later
            actions[name]['oldstates'] = to_list(oldstates)
            actions[name]['newstate'] = newstate
        else:
            attribute = parts[1]
            if attribute == 'default':
                actions[name][attribute] = int(value)
            elif attribute in ('operations', 'permissions'):
                actions[name][attribute] = to_list(value)
            else:
                actions[name][attribute] = value
    for name, attrs in actions.iteritems():
        if not attrs.get('name'):
            attrs['name'] = name
    return actions


def get_workflow_config(config):
    """Usually passed self.config, this will return the parsed ticket-workflow
    section.
    """
    raw_actions = list(config.options('ticket-workflow'))
    actions = parse_workflow_config(raw_actions)
    return actions

def load_workflow_config_snippet(config, filename):
    """Loads the ticket-workflow section from the given file (expected to be in
    the 'workflows' tree) into the provided config.
    """
    filename = resource_filename('trac.ticket', 'workflows/%s' % filename)
    new_config = Configuration(filename)
    for name, value in new_config.options('ticket-workflow'):
        config.set('ticket-workflow', name, value)


class ConfigurableTicketWorkflow(Component):
    """Ticket action controller which provides actions according to a
    workflow defined in trac.ini.

    The workflow is defined in the `[ticket-workflow]` section of the
    [wiki:TracIni#ticket-workflow-section trac.ini] configuration file.
    """

    implements(IEnvironmentSetupParticipant, ITicketActionController)

    ticket_workflow_section = ConfigSection('ticket-workflow',
        """The workflow for tickets is controlled by plugins. By default,
        there's only a `ConfigurableTicketWorkflow` component in charge.
        That component allows the workflow to be configured via this section
        in the `trac.ini` file. See TracWorkflow for more details.

        (''since 0.11'')""")

    def __init__(self, *args, **kwargs):
        self.actions = self.get_all_actions()
        self.log.debug('Workflow actions at initialization: %s\n',
                       self.actions)

    # IEnvironmentSetupParticipant methods

    def environment_created(self):
        """When an environment is created, we provide the basic-workflow,
        unless a ticket-workflow section already exists.
        """
        if 'ticket-workflow' not in self.config.sections():
            load_workflow_config_snippet(self.config, 'basic-workflow.ini')
            self.config.save()
            self.actions = self.get_all_actions()

    def environment_needs_upgrade(self, db):
        """The environment needs an upgrade if there is no [ticket-workflow]
        section in the config.
        """
        return not list(self.config.options('ticket-workflow'))

    def upgrade_environment(self, db):
        """Insert a [ticket-workflow] section using the original-workflow"""
        load_workflow_config_snippet(self.config, 'original-workflow.ini')
        self.config.save()
        self.actions = self.get_all_actions()
        info_message = """

==== Upgrade Notice ====

The ticket Workflow is now configurable.

Your environment has been upgraded, but configured to use the original
workflow. It is recommended that you look at changing this configuration to use
basic-workflow.

Read TracWorkflow for more information (don't forget to 'wiki upgrade' as well)

"""
        self.log.info(info_message.replace('\n', ' ').replace('==', ''))
        print info_message

    # ITicketActionController methods

    def get_ticket_actions(self, req, ticket):
        """Returns a list of (weight, action) tuples that are valid for this
        request and this ticket."""
        # Get the list of actions that can be performed

        # Determine the current status of this ticket.  If this ticket is in
        # the process of being modified, we need to base our information on the
        # pre-modified state so that we don't try to do two (or more!) steps at
        # once and get really confused.
        status = ticket._old.get('status', ticket['status']) or 'new'

        ticket_perm = req.perm(ticket.resource)
        allowed_actions = []
        for action_name, action_info in self.actions.items():
            oldstates = action_info['oldstates']
            if oldstates == ['*'] or status in oldstates:
                # This action is valid in this state.  Check permissions.
                required_perms = action_info['permissions']
                if self._is_action_allowed(ticket_perm, required_perms):
                    allowed_actions.append((action_info['default'],
                                            action_name))
        # Append special `_reset` action if status is invalid.
        if status not in TicketSystem(self.env).get_all_status() + \
                         ['new', 'closed']:
            required_perms = self.actions['_reset'].get('permissions')
            if self._is_action_allowed(ticket_perm, required_perms):
                default = self.actions['_reset'].get('default')
                allowed_actions.append((default, '_reset'))
        return allowed_actions

    def _is_action_allowed(self, ticket_perm, required_perms):
        if not required_perms:
            return True
        for permission in required_perms:
            if permission in ticket_perm:
                return True
        return False

    def get_all_status(self):
        """Return a list of all states described by the configuration.

        """
        all_status = set()
        for attributes in self.actions.values():
            all_status.update(attributes['oldstates'])
            all_status.add(attributes['newstate'])
        all_status.discard('*')
        all_status.discard('')
        return all_status

    def render_ticket_action_control(self, req, ticket, action):

        self.log.debug('render_ticket_action_control: action "%s"', action)

        this_action = self.actions[action]
        status = this_action['newstate']
        operations = this_action['operations']
        current_owner = ticket._old.get('owner', ticket['owner'])
        author = get_reporter_id(req, 'author')
        format_author = partial(Chrome(self.env).format_author, req)
        formatted_current_owner = format_author(current_owner or _("(none)"))

        control = []  # default to nothing
        hints = []
        if 'reset_workflow' in operations:
            control.append(_("from invalid state"))
            hints.append(_("Current state no longer exists"))
        if 'del_owner' in operations:
            hints.append(_("The ticket will be disowned"))
        if 'set_owner' in operations:
            id = 'action_%s_reassign_owner' % action

            if 'set_owner' in this_action:
                owners = [x.strip() for x in
                          this_action['set_owner'].split(',')]
            elif self.config.getbool('ticket', 'restrict_owner'):
                perm = PermissionSystem(self.env)
                owners = perm.get_users_with_permission('TICKET_MODIFY')
                owners.sort()
            else:
                owners = None

            if owners is None:
                owner = req.args.get(id, author)
                control.append(tag_("to %(owner)s",
                                    owner=tag.input(type='text', id=id,
                                                    name=id, value=owner)))
                hints.append(_("The owner will be changed from "
                               "%(current_owner)s to the specified user",
                               current_owner=formatted_current_owner))
            elif len(owners) == 1:
                owner = tag.input(type='hidden', id=id, name=id,
                                  value=owners[0])
                formatted_new_owner = format_author(owners[0])
                control.append(tag_("to %(owner)s",
                                    owner=tag(formatted_new_owner, owner)))
                if ticket['owner'] != owners[0]:
                    hints.append(_("The owner will be changed from "
                                   "%(current_owner)s to %(selected_owner)s",
                                   current_owner=formatted_current_owner,
                                   selected_owner=formatted_new_owner))
            else:
                selected_owner = req.args.get(id, req.authname)
                control.append(tag_("to %(owner)s", owner=tag.select(
                    [tag.option(x, value=x,
                                selected=(x == selected_owner or None))
                     for x in owners],
                    id=id, name=id)))
                hints.append(_("The owner will be changed from "
                               "%(current_owner)s to the selected user",
                               current_owner=formatted_current_owner))
        elif 'set_owner_to_self' in operations and \
                ticket._old.get('owner', ticket['owner']) != author:
            hints.append(_("The owner will be changed from %(current_owner)s "
                           "to %(authname)s",
                           current_owner=formatted_current_owner,
                           authname=format_author(author)))
        if 'set_resolution' in operations:
            if 'set_resolution' in this_action:
                resolutions = [x.strip() for x in
                               this_action['set_resolution'].split(',')]
            else:
                resolutions = [r.name for r in Resolution.select(self.env)]
            if not resolutions:
                raise TracError(_("Your workflow attempts to set a resolution "
                                  "but none is defined (configuration issue, "
                                  "please contact your Trac admin)."))
            id = 'action_%s_resolve_resolution' % action
            if len(resolutions) == 1:
                resolution = tag.input(type='hidden', id=id, name=id,
                                       value=resolutions[0])
                control.append(tag_("as %(resolution)s",
                                    resolution=tag(resolutions[0],
                                                   resolution)))
                hints.append(_("The resolution will be set to %(name)s",
                               name=resolutions[0]))
            else:
                selected_option = req.args.get(id,
                        TicketSystem(self.env).default_resolution)
                control.append(tag_("as %(resolution)s",
                                    resolution=tag.select(
                    [tag.option(x, value=x,
                                selected=(x == selected_option or None))
                     for x in resolutions],
                    id=id, name=id)))
                hints.append(_("The resolution will be set"))
        if 'del_resolution' in operations:
            hints.append(_("The resolution will be deleted"))
        if 'leave_status' in operations:
            control.append(_("as %(status)s",
                             status= ticket._old.get('status',
                                                     ticket['status'])))
            if len(operations) == 1:
                hints.append(_("The owner will remain %(current_owner)s",
                               current_owner=formatted_current_owner)
                             if current_owner else
                             _("The ticket will remain with no owner"))
        else:
            if status != '*':
                hints.append(_("Next status will be '%(name)s'", name=status))
        return (this_action.get('name', action), tag(separated(control, ' ')),
                '. '.join(hints) + '.' if hints else '')

    def get_ticket_changes(self, req, ticket, action):
        this_action = self.actions[action]

        # Enforce permissions
        if not self._has_perms_for_action(req, this_action, ticket.resource):
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
                newowner = req.args.get('action_%s_reassign_owner' % action,
                                    this_action.get('set_owner', '').strip())
                # If there was already an owner, we get a list, [new, old],
                # but if there wasn't we just get new.
                if type(newowner) == list:
                    newowner = newowner[0]
                updated['owner'] = newowner
            elif operation == 'set_owner_to_self':
                updated['owner'] = get_reporter_id(req, 'author')
            elif operation == 'del_resolution':
                updated['resolution'] = ''
            elif operation == 'set_resolution':
                newresolution = req.args.get('action_%s_resolve_resolution' % \
                                             action,
                                this_action.get('set_resolution', '').strip())
                updated['resolution'] = newresolution

            # reset_workflow is just a no-op here, so we don't look for it.
            # leave_status is just a no-op here, so we don't look for it.
        return updated

    def apply_action_side_effects(self, req, ticket, action):
        pass

    def _has_perms_for_action(self, req, action, resource):
        required_perms = action['permissions']
        if required_perms:
            for permission in required_perms:
                if permission in req.perm(resource):
                    break
            else:
                # The user does not have any of the listed permissions
                return False
        return True

    # Public methods (for other ITicketActionControllers that want to use
    #                 our config file and provide an operation for an action)

    def get_all_actions(self):
        actions = parse_workflow_config(self.ticket_workflow_section.options())

        # Special action that gets enabled if the current status no longer
        # exists, as no other action can then change its state. (#5307/#11850)
        if '_reset' not in actions:
            reset = {
                'default': 0,
                'name': 'reset',
                'newstate': 'new',
                'oldstates': [],
                'operations': ['reset_workflow'],
                'permissions': ['TICKET_ADMIN']
            }
            for key, val in reset.items():
                actions['_reset'][key] = val

        for name, info in actions.iteritems():
            if not info['newstate']:
                self.log.warning("Ticket workflow action '%s' doesn't define "
                                 "any transitions", name)
        return actions

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
        returned.
        """
        # Be sure to look at the original status.
        status = ticket._old.get('status', ticket['status'])
        actions = [(info['default'], action)
                   for action, info in self.actions.items()
                   if operation in info['operations'] and
                      ('*' in info['oldstates'] or
                       status in info['oldstates']) and
                      self._has_perms_for_action(req, info, ticket.resource)]
        return actions


class WorkflowMacro(WikiMacroBase):
    _domain = 'messages'
    _description = cleandoc_(
    """Render a workflow graph.

    This macro accepts a TracWorkflow configuration and renders the states
    and transitions as a directed graph. If no parameters are given, the
    current ticket workflow is rendered. In WikiProcessors mode the `width`
    and `height` arguments can be specified.

    (Defaults: `width = 800` and `heigth = 600`)

    Examples:
    {{{
        [[Workflow()]]

        [[Workflow(go = here -> there; return = there -> here)]]

        {{{
        #!Workflow width=700 height=700
        leave = * -> *
        leave.operations = leave_status
        leave.default = 1

        accept = new,assigned,accepted,reopened -> accepted
        accept.permissions = TICKET_MODIFY
        accept.operations = set_owner_to_self

        resolve = new,assigned,accepted,reopened -> closed
        resolve.permissions = TICKET_MODIFY
        resolve.operations = set_resolution

        reassign = new,assigned,accepted,reopened -> assigned
        reassign.permissions = TICKET_MODIFY
        reassign.operations = set_owner

        reopen = closed -> reopened
        reopen.permissions = TICKET_CREATE
        reopen.operations = del_resolution
        }}}
    }}}
    """)

    def expand_macro(self, formatter, name, text, args):
        if not text:
            raw_actions = self.config.options('ticket-workflow')
        else:
            if args is None:
                text = '\n'.join([line.lstrip() for line in text.split(';')])
            if '[ticket-workflow]' not in text:
                text = '[ticket-workflow]\n' + text
            parser = RawConfigParser()
            try:
                parser.readfp(StringIO(text))
            except ParsingError, e:
                return system_message(_("Error parsing workflow."),
                                      unicode(e))
            raw_actions = list(parser.items('ticket-workflow'))
        actions = parse_workflow_config(raw_actions)
        states = list(set(
            [state for action in actions.itervalues()
                   for state in action['oldstates']] +
            [action['newstate'] for action in actions.itervalues()]))
        action_labels = [attrs.get('name') or name
                         for name, attrs in actions.items()]
        action_names = actions.keys()
        edges = []
        for name, action in actions.items():
            new_index = states.index(action['newstate'])
            name_index = action_names.index(name)
            for old_state in action['oldstates']:
                old_index = states.index(old_state)
                edges.append((old_index, new_index, name_index))

        args = args or {}
        width = args.get('width', 800)
        height = args.get('height', 600)
        graph = {'nodes': states, 'actions': action_labels, 'edges': edges,
                 'width': width, 'height': height}
        graph_id = '%012x' % id(graph)
        req = formatter.req
        add_script(req, 'common/js/excanvas.js', ie_if='IE')
        add_script(req, 'common/js/workflow_graph.js')
        add_script_data(req, {'graph_%s' % graph_id: graph})
        return tag(
            tag.div('', class_='trac-workflow-graph trac-noscript',
                    id='trac-workflow-graph-%s' % graph_id,
                    style="display:inline-block;width:%spx;height:%spx" %
                          (width, height)),
            tag.noscript(
                tag.div(_("Enable JavaScript to display the workflow graph."),
                        class_='system-message')))
