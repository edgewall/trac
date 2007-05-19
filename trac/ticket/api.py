# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2006 Edgewall Software
# Copyright (C) 2003-2005 Jonas Borgström <jonas@edgewall.com>
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
# Author: Jonas Borgström <jonas@edgewall.com>

import re
from datetime import datetime

from genshi.builder import tag

from trac.config import *
from trac.context import IContextProvider, Context
from trac.core import *
from trac.perm import IPermissionRequestor, PermissionSystem, PermissionError
from trac.util import Ranges
from trac.util.text import shorten_line
from trac.util.datefmt import utc
from trac.util.compat import set, sorted
from trac.wiki import IWikiSyntaxProvider, WikiParser


class ITicketActionController(Interface):
    """Extension point interface for components willing to participate
    in ticket the workflow.

    This is mainly about controlling the changes to the ticket ''status'',
    though not restricted to it.
    """

    def get_ticket_actions(req, ticket):
        """Return an iterable of `(weight, action)` tuples corresponding to
        the actions that are contributed by this component.
        That list may vary given the current state of the ticket and the
        actual request parameter.

        `action` is a key used to identify that particular action.
        
        The actions will be presented on the page in descending order of the
        integer weight. When in doubt, use a weight of 0."""

    def get_all_status():
        """Returns an iterable of all the possible values for the ''status''
        field this action controller knows about.

        This will be used to populate the query options and the like.
        It is assumed that the initial status of a ticket is 'new' and
        the terminal status of a ticket is 'closed'.
        """

    def render_ticket_action_control(req, ticket, action):
        """Return a tuple in the form of `(label, control)`

        `control` is the markup for the action control and `label` is a
        short text used to present that action.
        If given, `hint` should explain what will happen if this action is
        taken.
        
        This method will only be called if the controller claimed to handle
        the given `action` in the call to `get_ticket_actions`.
        """

    def get_ticket_changes(req, ticket, action):
        """Return a tuple of `(changes, description)`

        `changes` is a dictionary with all the changes to the ticket's fields
        that should happen with this action.
        `description` is a description of any side-effects that are triggered
        by this change.

        This function must not have any side-effects because it is also
        called on preview."""

    def apply_action_side_effects(req, ticket, action):
        """The changes returned by `get_ticket_changes` have been made, any
        changes outside of the ticket fields should be done here.

        This is never called in preview."""


# -- Utilities for the DefaultTicketActionController

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


class DefaultTicketActionController(Component):
    """Default ticket action controller that loads workflow actions from
    config."""
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
        operations = this_action['operations']

        control = [] # default to nothing
        if 'set_owner' in operations:
            id = action + '_reassign_owner'
            selected_owner = req.args.get(id, req.authname)
            if self.config.getbool('ticket', 'restrict_owner'):
                perm = PermissionSystem(self.env)
                options = perm.get_users_with_permission('TICKET_MODIFY')
                control.append(tag.select(
                    [tag.option(x, selected=(x == selected_owner or None))
                     for x in options],
                    id=id, name=id))
            else:
                control.append(tag.input(type='text', id=id, name=id,
                    value=req.args.get(id, req.authname)))
        if 'set_resolution' in operations:
            options = [val.name for val in model.Resolution.select(self.env)]
            id = action + '_resolve_resolution'
            selected_option = req.args.get(id, 'fixed')
            control.append(tag(['as:', tag.select(
                [tag.option(x, selected=(x == selected_option or None))
                 for x in options],
                id=id, name=id)]))
        if 'leave_status' in operations:
            control.append('as ' + ticket['status'])
        return (this_action['name'], tag(*control))

    def get_ticket_changes(self, req, ticket, action):
        # Any action we don't recognize, we ignore.
        try:
            this_action = self.actions[action]
        except KeyError:
            # Not one of our actions, ignore it.
            return {}, ''

        # Enforce permissions
        if not self._has_perms_for_action(req, this_action):
            # The user does not have any of the listed permissions, so we won't
            # do anything.
            return {}, ''

        updated = {}
        # Status changes
        status = this_action['newstate']
        if status != '*':
            updated['status'] = status

        for operation in this_action['operations']:
            if operation == 'del_owner':
                updated['owner'] = ''
            elif operation == 'set_owner':
                newowner = req.args.get(action + '_reassign_owner')
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
                newresolution = req.args.get(action + '_resolve_resolution')
                updated['resolution'] = newresolution

            # leave_status and hidden are just no-ops here, so we don't look
            # for them.
        return updated, ''

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


class ITicketChangeListener(Interface):
    """Extension point interface for components that require notification
    when tickets are created, modified, or deleted."""

    def ticket_created(ticket):
        """Called when a ticket is created."""

    def ticket_changed(ticket, comment, author, old_values):
        """Called when a ticket is modified.
        
        `old_values` is a dictionary containing the previous values of the
        fields that have changed.
        """

    def ticket_deleted(ticket):
        """Called when a ticket is deleted."""


class ITicketManipulator(Interface):
    """Miscellaneous manipulation of ticket workflow features."""

    def prepare_ticket(req, ticket, fields, actions):
        """Not currently called, but should be provided for future
        compatibility."""

    def validate_ticket(req, ticket):
        """Validate a ticket after it's been populated from user input.
        
        Must return a list of `(field, message)` tuples, one for each problem
        detected. `field` can be `None` to indicate an overall problem with the
        ticket. Therefore, a return value of `[]` means everything is OK."""


class TicketContext(Context):
    """Context used for describing Ticket resources."""

    realm = 'ticket'

    # methods reimplemented from Context

    def get_resource(self):
        from trac.ticket.model import Ticket
        return Ticket(self.env, self.id and int(self.id) or None, self.db)

    def name(self):
        return 'Ticket ' + self.shortname()

    def shortname(self):
        return '#%s' % self.id

    def summary(self):
        args = [self.resource[f] for f in ('summary', 'status',
                                           'resolution', 'type')]
        return self.format_summary(*args)

    def format_summary(self, summary, status=None, resolution=None, type=None):
        summary = shorten_line(summary)
        if type:
            summary = type + ': ' + summary
        if status:
            if status == 'closed' and resolution:
                status += ': ' + resolution
            return "%s (%s)" % (summary, status)
        else:
            return summary
        


class TicketSystem(Component):
    implements(IPermissionRequestor, IWikiSyntaxProvider, IContextProvider)

    change_listeners = ExtensionPoint(ITicketChangeListener)
    action_controllers = OrderedExtensionsOption('ticket', 'workflow',
        ITicketActionController, default='DefaultTicketActionController',
        include_missing=False,
        doc="""Ordered list of workflow controllers to use for ticket actions
            (''since 0.11'').""")

    restrict_owner = BoolOption('ticket', 'restrict_owner', 'false',
        """Make the owner field of tickets use a drop-down menu. See
        [TracTickets#Assign-toasDrop-DownList Assign-to as Drop-Down List]
        (''since 0.9'').""")

    # Public API

    def get_available_actions(self, req, ticket):
        """Returns a sorted list of available actions"""
        # The list should not have duplicates.
        actions = {}
        self.log.debug('action controllers: %s' % (self.action_controllers,))
        for controller in self.action_controllers:
            weighted_actions = controller.get_ticket_actions(req, ticket)
            for weight, action in weighted_actions:
                if action in actions:
                    actions[action] = max(actions[action], weight)
                else:
                    actions[action] = weight
        all_weighted_actions = [(weight, action) for action, weight in
                                actions.items()]
        return [x[1] for x in sorted(all_weighted_actions, reverse=True)]

    def get_all_status(self):
        """Returns a sorted list of all the states all of the action
        controllers know about."""
        valid_states = set()
        for controller in self.action_controllers:
            valid_states.update(controller.get_all_status())
        return sorted(valid_states)

    def get_ticket_fields(self):
        """Returns the list of fields available for tickets."""
        from trac.ticket import model

        db = self.env.get_db_cnx()
        fields = []

        # Basic text fields
        for name in ('summary', 'reporter'):
            field = {'name': name, 'type': 'text', 'label': name.title()}
            fields.append(field)

        # Owner field, can be text or drop-down depending on configuration
        field = {'name': 'owner', 'label': 'Owner'}
        if self.restrict_owner:
            field['type'] = 'select'
            perm = PermissionSystem(self.env)
            field['options'] = perm.get_users_with_permission('TICKET_MODIFY')
            field['optional'] = True
        else:
            field['type'] = 'text'
        fields.append(field)

        # Description
        fields.append({'name': 'description', 'type': 'textarea',
                       'label': 'Description'})

        # Default select and radio fields
        selects = [('type', model.Type),
                   ('status', model.Status),
                   ('priority', model.Priority),
                   ('milestone', model.Milestone),
                   ('component', model.Component),
                   ('version', model.Version),
                   ('severity', model.Severity),
                   ('resolution', model.Resolution)]
        for name, cls in selects:
            options = [val.name for val in cls.select(self.env, db=db)]
            if not options:
                # Fields without possible values are treated as if they didn't
                # exist
                continue
            field = {'name': name, 'type': 'select', 'label': name.title(),
                     'value': self.config.get('ticket', 'default_' + name),
                     'options': options}
            if name in ('status', 'resolution'):
                field['type'] = 'radio'
                field['optional'] = True
            elif name in ('milestone', 'version'):
                field['optional'] = True
            fields.append(field)

        # Advanced text fields
        for name in ('keywords', 'cc', ):
            field = {'name': name, 'type': 'text', 'label': name.title()}
            fields.append(field)

        for field in self.get_custom_fields():
            if field['name'] in [f['name'] for f in fields]:
                self.log.warning('Duplicate field name "%s" (ignoring)',
                                 field['name'])
                continue
            if not re.match('^[a-zA-Z][a-zA-Z0-9_]+$', field['name']):
                self.log.warning('Invalid name for custom field: "%s" '
                                 '(ignoring)', field['name'])
                continue
            field['custom'] = True
            fields.append(field)

        return fields

    def get_custom_fields(self):
        fields = []
        config = self.config['ticket-custom']
        for name in [option for option, value in config.options()
                     if '.' not in option]:
            field = {
                'name': name,
                'type': config.get(name),
                'order': config.getint(name + '.order', 0),
                'label': config.get(name + '.label') or name.capitalize(),
                'value': config.get(name + '.value', '')
            }
            if field['type'] == 'select' or field['type'] == 'radio':
                field['options'] = config.getlist(name + '.options', sep='|')
                if '' in field['options']:
                    field['optional'] = True
                    field['options'].remove('')
            elif field['type'] == 'textarea':
                field['width'] = config.getint(name + '.cols')
                field['height'] = config.getint(name + '.rows')
            fields.append(field)

        fields.sort(lambda x, y: cmp(x['order'], y['order']))
        return fields

    # IPermissionRequestor methods

    def get_permission_actions(self):
        return ['TICKET_APPEND', 'TICKET_CREATE', 'TICKET_CHGPROP',
                'TICKET_VIEW',
                ('TICKET_MODIFY', ['TICKET_APPEND', 'TICKET_CHGPROP']),  
                ('TICKET_ADMIN', ['TICKET_CREATE', 'TICKET_MODIFY',  
                                  'TICKET_VIEW'])]

    # IWikiSyntaxProvider methods

    def get_link_resolvers(self):
        return [('bug', self._format_link),
                ('ticket', self._format_link),
                ('comment', self._format_comment_link)]

    def get_wiki_syntax(self):
        yield (
            # matches #... but not &#... (HTML entity)
            r"!?(?<!&)#"
            # optional intertrac shorthand #T... + digits
            r"(?P<it_ticket>%s)%s" % (WikiParser.INTERTRAC_SCHEME,
                                      Ranges.RE_STR),
            lambda x, y, z: self._format_link(x, 'ticket', y[1:], y, z))

    def _format_link(self, formatter, ns, target, label, fullmatch=None):
        intertrac = formatter.shorthand_intertrac_helper(ns, target, label,
                                                         fullmatch)
        if intertrac:
            return intertrac
        try:
            link, params, fragment = formatter.split_link(target)
            r = Ranges(link)
            if len(r) == 1:
                num = r.a
                ctx = formatter.context('ticket', num)
                if 0 < num <= 1L << 31: # TODO: implement ctx.exists()
                    # status = ctx.resource['status']  -> currently expensive
                    cursor = formatter.db.cursor() 
                    cursor.execute("SELECT type,summary,status,resolution "
                                   "FROM ticket WHERE id=%s", (str(num),)) 
                    for type, summary, status, resolution in cursor:
                        title = ctx.format_summary(summary, status, resolution,
                                                   type)
                        return tag.a(label, class_='%s ticket' % status, 
                                     title=title,
                                     href=(ctx.resource_href() + params +
                                           fragment))
                    else: 
                        return tag.a(label, class_='missing ticket',  
                                     href=ctx.resource_href(), rel="nofollow")
            else:
                ranges = str(r)
                if params:
                    params = '&' + params[1:]
                return tag.a(label, title='Tickets '+ranges,
                             href=formatter.href.query(id=ranges) + params)
        except ValueError:
            pass
        return tag.a(label, class_='missing ticket')

    def _format_comment_link(self, formatter, ns, target, label):
        context = None
        if ':' in target:
            elts = target.split(':')
            if len(elts) == 3:
                cnum, realm, id = elts
                if cnum != 'description' and cnum and not cnum[0].isdigit():
                    realm, id, cnum = elts # support old comment: style
                context = formatter.context(realm, id)
        else:
            context = formatter.context
            cnum = target

        if context:
            return tag.a(label, href=("%s#comment:%s" %
                                      (context.resource_href(), cnum)),
                         title="Comment %s for %s" % (cnum, context.name()))
        else:
            return label
 
    # IContextProvider methods

    def get_context_classes(self):
        yield TicketContext
