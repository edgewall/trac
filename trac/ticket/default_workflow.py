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

import io
from ConfigParser import ParsingError, RawConfigParser
from collections import defaultdict
from functools import partial
from pkg_resources import resource_filename

from trac.api import IEnvironmentSetupParticipant
from trac.config import ConfigSection, Configuration, ConfigurationError
from trac.core import *
from trac.perm import PermissionCache, PermissionSystem
from trac.resource import ResourceNotFound
from trac.ticket.api import ITicketActionController, TicketSystem
from trac.ticket.model import Component as TicketComponent, Resolution
from trac.util import exception_to_unicode, get_reporter_id, sub_val, to_list
from trac.util.html import tag
from trac.util.presentation import separated
from trac.util.translation import _, tag_, cleandoc_
from trac.versioncontrol.api import RepositoryManager
from trac.web.chrome import Chrome, add_script, add_script_data
from trac.wiki.formatter import MacroError, ProcessorError
from trac.wiki.macros import WikiMacroBase, parse_args


# -- Utilities for the ConfigurableTicketWorkflow

def parse_workflow_config(rawactions):
    """Given a list of options from [ticket-workflow]"""

    required_attrs = {
        'oldstates': [],
        'newstate': '',
        'name': '',
        'label': '',
        'default': 0,
        'operations': [],
        'permissions': [],
    }
    optional_attrs = {
        'set_owner': [],
        'set_resolution': [],
    }
    known_attrs = required_attrs.copy()
    known_attrs.update(optional_attrs)

    actions = defaultdict(dict)
    for option, value in rawactions:
        parts = option.split('.')
        name = parts[0]
        if len(parts) == 1:
            try:
                # Base name, of the syntax: old,states,here -> newstate
                oldstates, newstate = [x.strip() for x in value.split('->')]
            except ValueError:
                continue  # Syntax error, a warning will be logged later
            actions[name]['oldstates'] = to_list(oldstates)
            actions[name]['newstate'] = newstate
        else:
            attribute = parts[1]
            if attribute not in known_attrs or \
                    isinstance(known_attrs[attribute], str):
                actions[name][attribute] = value
            elif isinstance(known_attrs[attribute], int):
                actions[name][attribute] = int(value)
            elif isinstance(known_attrs[attribute], list):
                actions[name][attribute] = to_list(value)

    for action, attributes in actions.items():
        if 'label' not in attributes:
            if 'name' in attributes:  # backwards-compatibility, #11828
                attributes['label'] = attributes['name']
            else:
                attributes['label'] = action.replace("_", " ").strip()
        for key, val in required_attrs.items():
            attributes.setdefault(key, val)

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
        """)

    def __init__(self):
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

    def environment_needs_upgrade(self):
        pass

    def upgrade_environment(self):
        pass

    # ITicketActionController methods

    def get_ticket_actions(self, req, ticket):
        """Returns a list of (weight, action) tuples that are valid for this
        request and this ticket."""
        # Get the list of actions that can be performed

        # Determine the current status of this ticket.  If this ticket is in
        # the process of being modified, we need to base our information on the
        # pre-modified state so that we don't try to do two (or more!) steps at
        # once and get really confused.
        ticket_status = ticket._old.get('status', ticket['status'])
        exists = ticket_status is not None
        ticket_owner = ticket._old.get('owner', ticket['owner'])
        author = get_reporter_id(req, 'author')

        resource = ticket.resource
        allowed_actions = []
        for action_name, action_info in self.actions.items():
            operations = action_info['operations']
            newstate = action_info['newstate']
            # Exclude action that is effectively a No-op.
            if len(operations) == 1 and \
                    operations[0] == 'set_owner_to_self' and \
                    ticket_owner == author and ticket_status == newstate:
                continue
            oldstates = action_info['oldstates']
            if exists and oldstates == ['*'] or ticket_status in oldstates:
                # This action is valid in this state.  Check permissions.
                if self._is_action_allowed(req, action_info, resource):
                    allowed_actions.append((action_info['default'],
                                            action_name))
        # Append special `_reset` action if status is invalid.
        if exists and '_reset' in self.actions and \
                ticket_status not in TicketSystem(self.env).get_all_status():
            reset = self.actions['_reset']
            if self._is_action_allowed(req, reset, resource):
                allowed_actions.append((reset['default'], '_reset'))
        return allowed_actions

    def _is_action_allowed(self, req, action, resource):
        """Returns `True` if the workflow action is allowed for the `resource`.
        """
        perm_cache = req.perm(resource)
        required_perms = action['permissions']
        if required_perms:
            for permission in required_perms:
                if permission in perm_cache:
                    break
            else:
                return False
        return True

    def get_all_status(self):
        """Return a list of all states described by the configuration.

        """
        all_status = set()
        for attributes in self.actions.values():
            all_status.update(attributes['oldstates'])
            all_status.add(attributes['newstate'])
        all_status.discard('*')
        all_status.discard('')
        all_status.discard(None)
        return all_status

    def render_ticket_action_control(self, req, ticket, action):

        self.log.debug('render_ticket_action_control: action "%s"', action)

        this_action = self.actions[action]
        status = this_action['newstate']
        operations = this_action['operations']
        ticket_owner = ticket._old.get('owner', ticket['owner'])
        ticket_status = ticket._old.get('status', ticket['status'])
        author = get_reporter_id(req, 'author')
        author_info = partial(Chrome(self.env).authorinfo, req,
                              resource=ticket.resource)
        format_author = partial(Chrome(self.env).format_author, req,
                                resource=ticket.resource)
        formatted_current_owner = author_info(ticket_owner)
        exists = ticket_status is not None

        ticket_system = TicketSystem(self.env)
        control = []  # default to nothing
        hints = []
        if 'reset_workflow' in operations:
            control.append(_("from invalid state"))
            hints.append(_("Current state no longer exists"))
        if 'del_owner' in operations:
            hints.append(_("The ticket will be disowned"))
        if 'set_owner' in operations or 'may_set_owner' in operations:
            owners = self.get_allowed_owners(req, ticket, this_action)

            if 'set_owner' in operations:
                default_owner = author
            elif 'may_set_owner' in operations:
                if not exists:
                    default_owner = ticket_system.default_owner
                else:
                    default_owner = ticket_owner or None
                if owners is not None and default_owner not in owners:
                    owners.insert(0, default_owner)
            else:
                # Protect against future modification for case that another
                # operation is added to the outer conditional
                raise AssertionError(operations)

            id = 'action_%s_reassign_owner' % action

            if not owners:
                owner = req.args.get(id, default_owner)
                control.append(
                    tag_("to %(owner)s",
                         owner=tag.input(type='text', id=id, name=id,
                                         value=owner)))
                if not exists or ticket_owner is None:
                    hints.append(_("The owner will be the specified user"))
                else:
                    hints.append(tag_("The owner will be changed from "
                                      "%(current_owner)s to the specified "
                                      "user",
                                      current_owner=formatted_current_owner))
            elif len(owners) == 1:
                owner = tag.input(type='hidden', id=id, name=id,
                                  value=owners[0])
                formatted_new_owner = author_info(owners[0])
                control.append(tag_("to %(owner)s",
                                    owner=tag(formatted_new_owner, owner)))
                if not exists or ticket_owner is None:
                    hints.append(tag_("The owner will be %(new_owner)s",
                                      new_owner=formatted_new_owner))
                elif ticket['owner'] != owners[0]:
                    hints.append(tag_("The owner will be changed from "
                                      "%(current_owner)s to %(new_owner)s",
                                      current_owner=formatted_current_owner,
                                      new_owner=formatted_new_owner))
            else:
                selected_owner = req.args.get(id, default_owner)
                control.append(tag_("to %(owner)s", owner=tag.select(
                    [tag.option(label, value=value if value is not None else '',
                                selected=(value == selected_owner or None))
                     for label, value in sorted((format_author(owner), owner)
                                                for owner in owners)],
                    id=id, name=id)))
                if not exists or ticket_owner is None:
                    hints.append(_("The owner will be the selected user"))
                else:
                    hints.append(tag_("The owner will be changed from "
                                      "%(current_owner)s to the selected user",
                                      current_owner=formatted_current_owner))
        elif 'set_owner_to_self' in operations:
            formatted_author = author_info(author)
            if not exists or ticket_owner is None:
                hints.append(tag_("The owner will be %(new_owner)s",
                                  new_owner=formatted_author))
            elif ticket_owner != author:
                hints.append(tag_("The owner will be changed from "
                                  "%(current_owner)s to %(new_owner)s",
                                  current_owner=formatted_current_owner,
                                  new_owner=formatted_author))
            elif ticket_status != status:
                hints.append(tag_("The owner will remain %(current_owner)s",
                                  current_owner=formatted_current_owner))
        if 'set_resolution' in operations:
            resolutions = [r.name for r in Resolution.select(self.env)]
            if 'set_resolution' in this_action:
                valid_resolutions = set(resolutions)
                resolutions = this_action['set_resolution']
                if any(x not in valid_resolutions for x in resolutions):
                    raise ConfigurationError(_(
                        "Your workflow attempts to set a resolution but uses "
                        "undefined resolutions (configuration issue, please "
                        "contact your Trac admin)."))
            if not resolutions:
                raise ConfigurationError(_(
                    "Your workflow attempts to set a resolution but none is "
                    "defined (configuration issue, please contact your Trac "
                    "admin)."))
            id = 'action_%s_resolve_resolution' % action
            if len(resolutions) == 1:
                resolution = tag.input(type='hidden', id=id, name=id,
                                       value=resolutions[0])
                control.append(tag_("as %(resolution)s",
                                    resolution=tag(resolutions[0],
                                                   resolution)))
                hints.append(tag_("The resolution will be set to %(name)s",
                                  name=resolutions[0]))
            else:
                selected_option = req.args.get(id,
                                               ticket_system.default_resolution)
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
            control.append(tag_("as %(status)s", status=ticket_status))
            if len(operations) == 1:
                hints.append(tag_("The owner will remain %(current_owner)s",
                                  current_owner=formatted_current_owner)
                             if ticket_owner else
                             _("The ticket will remain with no owner"))
        elif not operations:
            if status != '*':
                if ticket['status'] is None:
                    hints.append(tag_("The status will be '%(name)s'",
                                      name=status))
                else:
                    hints.append(tag_("Next status will be '%(name)s'",
                                      name=status))
        return (this_action['label'], tag(separated(control, ' ')),
                tag(separated(hints, '. ', '.') if hints else ''))

    def get_ticket_changes(self, req, ticket, action):
        this_action = self.actions[action]

        # Enforce permissions
        if not self._is_action_allowed(req, this_action, ticket.resource):
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
            elif operation in ('set_owner', 'may_set_owner'):
                set_owner = this_action.get('set_owner')
                newowner = req.args.get('action_%s_reassign_owner' % action,
                                        set_owner[0] if set_owner else '')
                # If there was already an owner, we get a list, [new, old],
                # but if there wasn't we just get new.
                if type(newowner) == list:
                    newowner = newowner[0]
                updated['owner'] = self._sub_owner_keyword(newowner, ticket)
            elif operation == 'set_owner_to_self':
                updated['owner'] = get_reporter_id(req, 'author')
            elif operation == 'del_resolution':
                updated['resolution'] = ''
            elif operation == 'set_resolution':
                set_resolution = this_action.get('set_resolution')
                newresolution = req.args.get('action_%s_resolve_resolution'
                                             % action,
                                             set_resolution[0]
                                             if set_resolution else '')
                updated['resolution'] = newresolution

            # reset_workflow is just a no-op here, so we don't look for it.
            # leave_status is just a no-op here, so we don't look for it.

        # Set owner to component owner for 'new' ticket if:
        #  - ticket doesn't exist and owner is < default >
        #  - component is changed
        #  - owner isn't explicitly changed
        #  - ticket owner is equal to owner of previous component
        #  - new component has an owner
        if not ticket.exists and 'owner' not in updated:
            updated['owner'] = self._sub_owner_keyword(ticket['owner'], ticket)
        elif ticket['status'] == 'new' and \
                'component' in ticket.values and \
                'component' in ticket._old and \
                'owner' not in updated:
            try:
                old_comp = TicketComponent(self.env, ticket._old['component'])
            except ResourceNotFound:
                # If the old component has been removed from the database
                # we just leave the owner as is.
                pass
            else:
                old_owner = old_comp.owner or ''
                current_owner = ticket['owner'] or ''
                if old_owner == current_owner:
                    new_comp = TicketComponent(self.env, ticket['component'])
                    if new_comp.owner:
                        updated['owner'] = new_comp.owner

        return updated

    def apply_action_side_effects(self, req, ticket, action):
        pass

    # Public methods (for other ITicketActionControllers that want to use
    #                 our config file and provide an operation for an action)

    def get_all_actions(self):
        actions = parse_workflow_config(self.ticket_workflow_section.options())

        has_new_state = any('new' in [a['newstate']] + a['oldstates']
                            for a in actions.itervalues())
        if has_new_state:
            # Special action that gets enabled if the current status no
            # longer exists, as no other action can then change its state.
            # (#5307/#11850)
            reset = {
                'default': 0,
                'label': 'Reset',
                'newstate': 'new',
                'oldstates': [],
                'operations': ['reset_workflow'],
                'permissions': ['TICKET_ADMIN']
            }
            for key, val in reset.items():
                actions['_reset'].setdefault(key, val)

        for name, info in actions.iteritems():
            for val in ('<none>', '< none >'):
                sub_val(actions[name]['oldstates'], val, None)
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
                      self._is_action_allowed(req, info, ticket.resource)]
        return actions

    # Public methods

    def get_allowed_owners(self, req, ticket, action):
        """Returns users listed in the `set_owner` field of the action or
        possessing the `TICKET_MODIFY` permission if `set_owner` is not
        specified.

        This method can be overridden in a subclasses in order to
        customize the list of users that populate the assign-to select
        box.

        :since: 1.3.2
        """
        if 'set_owner' in action:
            return self._to_users(action['set_owner'], ticket)
        elif TicketSystem(self.env).restrict_owner:
            users = PermissionSystem(self.env)\
                    .get_users_with_permission('TICKET_MODIFY')
            cache = partial(PermissionCache, self.env, resource=ticket.resource)
            return sorted(u for u in users
                            if 'TICKET_MODIFY' in cache(username=u))

    # Internal methods

    def _sub_owner_keyword(self, owner, ticket):
        """Substitute keywords from the default_owner field.

        < default > -> component owner
        """
        if owner in ('< default >', '<default>'):
            default_owner = ''
            if ticket['component']:
                try:
                    component = TicketComponent(self.env, ticket['component'])
                except ResourceNotFound:
                    pass  # No such component exists
                else:
                    default_owner = component.owner  # May be empty
            return default_owner
        return owner

    def _to_users(self, users_perms_and_groups, ticket):
        """Finds all users contained in the list of `users_perms_and_groups`
        by recursive lookup of users when a `group` is encountered.
        """
        ps = PermissionSystem(self.env)
        groups = ps.get_groups_dict()

        def append_owners(users_perms_and_groups):
            for user_perm_or_group in users_perms_and_groups:
                if user_perm_or_group == 'authenticated':
                    owners.update({u[0] for u in self.env.get_known_users()})
                elif user_perm_or_group.isupper():
                    perm = user_perm_or_group
                    for user in ps.get_users_with_permission(perm):
                        if perm in PermissionCache(self.env, user,
                                                   ticket.resource):
                            owners.add(user)
                elif user_perm_or_group not in groups:
                    owners.add(user_perm_or_group)
                else:
                    append_owners(groups[user_perm_or_group])

        owners = set()
        append_owners(users_perms_and_groups)

        return sorted(owners)


class WorkflowMacro(WikiMacroBase):
    _domain = 'messages'
    _description = cleandoc_(
    """Render a workflow graph.

    This macro accepts a TracWorkflow configuration and renders the states
    and transitions as a directed graph. If no parameters are given, the
    current ticket workflow is rendered.

    In [WikiProcessors WikiProcessor] mode the `width` and `height`
    arguments can be specified (Defaults: `width = 800` and `height = 600`).

    The repository-scoped path of a workflow file can be specified as either
    a macro or !WikiProcessor `file` argument. The file revision can be
    specified by appending `@<rev>` to the path. The `file` argument value
    must be enclosed in single or double quotes. //(Since 1.3.2)//.

    Examples:
    {{{
    [[Workflow()]]

    [[Workflow(go = here -> there; return = there -> here)]]

    [[Workflow(file=/contrib/workflow/enterprise-workflow.ini@1)]]

    {{{#!Workflow file="/contrib/workflow/enterprise-workflow.ini"
    }}}

    {{{#!Workflow width=700 height=700
    leave = * -> *
    leave.operations = leave_status
    leave.default = 1

    create = <none> -> new
    create.default = 1

    create_and_assign = <none> -> assigned
    create_and_assign.label = assign
    create_and_assign.permissions = TICKET_MODIFY
    create_and_assign.operations = may_set_owner

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

    def expand_macro(self, formatter, name, content, args=None):
        if content is not None:
            content = content.strip()
        if not args and not content:
            raw_actions = self.config.options('ticket-workflow')
        else:
            is_macro = args is None
            if is_macro:
                kwargs = parse_args(content)[1]
                file = kwargs.get('file')
            else:
                file = args.get('file')
                if not file and not content:
                    raise ProcessorError("Invalid argument(s).")

            if file:
                print(file)
                text = RepositoryManager(self.env).read_file_by_path(file)
                if text is None:
                    raise ProcessorError(
                        tag_("The file %(file)s does not exist.",
                             file=tag.code(file)))
            elif is_macro:
                text = '\n'.join(line.lstrip() for line in content.split(';'))
            else:
                text = content

            if '[ticket-workflow]' not in text:
                text = '[ticket-workflow]\n' + text
            parser = RawConfigParser()
            try:
                parser.readfp(io.StringIO(text))
            except ParsingError as e:
                if is_macro:
                    raise MacroError(exception_to_unicode(e))
                else:
                    raise ProcessorError(exception_to_unicode(e))
            raw_actions = list(parser.items('ticket-workflow'))
        actions = parse_workflow_config(raw_actions)
        states = list(
            {state for action in actions.itervalues()
                   for state in action['oldstates']} |
            {action['newstate'] for action in actions.itervalues()})
        action_labels = [attrs['label'] for attrs in actions.values()]
        action_names = list(actions)
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
