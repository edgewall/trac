# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2009 Edgewall Software
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
try:
    import threading
except ImportError:
    import dummy_threading as threading

from genshi.builder import tag

from trac.config import *
from trac.core import *
from trac.perm import IPermissionRequestor, PermissionCache, PermissionSystem
from trac.resource import IResourceManager
from trac.util import Ranges
from trac.util.compat import set, sorted
from trac.util.datefmt import utc
from trac.util.text import shorten_line, obfuscate_email_address
from trac.util.translation import _
from trac.wiki import IWikiSyntaxProvider, WikiParser


class ITicketActionController(Interface):
    """Extension point interface for components willing to participate
    in the ticket workflow.

    This is mainly about controlling the changes to the ticket ''status'',
    though not restricted to it.
    """

    def get_ticket_actions(req, ticket):
        """Return an iterable of `(weight, action)` tuples corresponding to
        the actions that are contributed by this component.
        That list may vary given the current state of the ticket and the
        actual request parameter.

        `action` is a key used to identify that particular action.
        (note that 'history' and 'diff' are reserved and should not be used
        by plugins)
        
        The actions will be presented on the page in descending order of the
        integer weight. The first action in the list is used as the default
        action.

        When in doubt, use a weight of 0."""

    def get_all_status():
        """Returns an iterable of all the possible values for the ''status''
        field this action controller knows about.

        This will be used to populate the query options and the like.
        It is assumed that the initial status of a ticket is 'new' and
        the terminal status of a ticket is 'closed'.
        """

    def render_ticket_action_control(req, ticket, action):
        """Return a tuple in the form of `(label, control, hint)`

        `label` is a short text that will be used when listing the action,
        `control` is the markup for the action control and `hint` should
        explain what will happen if this action is taken.
        
        This method will only be called if the controller claimed to handle
        the given `action` in the call to `get_ticket_actions`.

        Note that the radio button for the action has an `id` of
        `"action_%s" % action`.  Any `id`s used in `control` need to be made
        unique.  The method used in the default ITicketActionController is to
        use `"action_%s_something" % action`.
        """

    def get_ticket_changes(req, ticket, action):
        """Return a dictionary of ticket field changes.

        This method must not have any side-effects because it will also
        be called in preview mode (`req.args['preview']` will be set, then).
        See `apply_action_side_effects` for that. If the latter indeed triggers
        some side-effects, it is advised to emit a warning
        (`trac.web.chrome.add_warning(req, reason)`) when this method is called
        in preview mode.

        This method will only be called if the controller claimed to handle
        the given `action` in the call to `get_ticket_actions`.
        """

    def apply_action_side_effects(req, ticket, action):
        """Perform side effects once all changes have been made to the ticket.

        Multiple controllers might be involved, so the apply side-effects
        offers a chance to trigger a side-effect based on the given `action`
        after the new state of the ticket has been saved.

        This method will only be called if the controller claimed to handle
        the given `action` in the call to `get_ticket_actions`.
        """


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


class TicketSystem(Component):
    implements(IPermissionRequestor, IWikiSyntaxProvider, IResourceManager)

    change_listeners = ExtensionPoint(ITicketChangeListener)
    action_controllers = OrderedExtensionsOption('ticket', 'workflow',
        ITicketActionController, default='ConfigurableTicketWorkflow',
        include_missing=False,
        doc="""Ordered list of workflow controllers to use for ticket actions
            (''since 0.11'').""")

    restrict_owner = BoolOption('ticket', 'restrict_owner', 'false',
        """Make the owner field of tickets use a drop-down menu. See
        [TracTickets#Assign-toasDrop-DownList Assign-to as Drop-Down List]
        (''since 0.9'').""")

    _fields = None
    _custom_fields = None

    def __init__(self):
        self.log.debug('action controllers for ticket workflow: %r' % 
                [c.__class__.__name__ for c in self.action_controllers])
        self._fields_lock = threading.RLock()

    # Public API

    def get_available_actions(self, req, ticket):
        """Returns a sorted list of available actions"""
        # The list should not have duplicates.
        actions = {}
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
        # This is now cached - as it makes quite a number of things faster,
        # e.g. #6436
        if self._fields is None:
            self._fields_lock.acquire()
            try:
                if self._fields is None: # double-check (race after 1st check)
                    self._fields = self._get_ticket_fields()
            finally:
                self._fields_lock.release()
        return [f.copy() for f in self._fields]

    def reset_ticket_fields(self):
        self._fields_lock.acquire()
        try:
            self._fields = None
            self.config.touch() # brute force approach for now
        finally:
            self._fields_lock.release()

    def _get_ticket_fields(self):
        from trac.ticket import model

        db = self.env.get_db_cnx()
        fields = []

        # Basic text fields
        for name in ('summary', 'reporter'):
            field = {'name': name, 'type': 'text', 'label': name.title()}
            fields.append(field)

        # Owner field, by default text but can be changed dynamically 
        # into a drop-down depending on configuration (restrict_owner=true)
        field = {'name': 'owner', 'label': 'Owner'}
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
            if field['name'] in self.reserved_field_names:
                self.log.warning('Field name "%s" is a reserved name '
                                 '(ignoring)', field['name'])
                continue
            if not re.match('^[a-zA-Z][a-zA-Z0-9_]+$', field['name']):
                self.log.warning('Invalid name for custom field: "%s" '
                                 '(ignoring)', field['name'])
                continue
            field['custom'] = True
            fields.append(field)

        return fields

    reserved_field_names = ['report', 'order', 'desc', 'group', 'groupdesc',
                            'col', 'row', 'format', 'max', 'page', 'verbose']

    def get_custom_fields(self):
        if self._custom_fields is None:
            self._fields_lock.acquire()
            try:
                if self._custom_fields is None: # double-check
                    self._custom_fields = self._get_custom_fields()
            finally:
                self._fields_lock.release()
        return [f.copy() for f in self._custom_fields]

    def _get_custom_fields(self):
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
            elif field['type'] == 'text':
                field['format'] = config.get(name + '.format', 'plain')
            elif field['type'] == 'textarea':
                field['format'] = config.get(name + '.format', 'plain')
                field['width'] = config.getint(name + '.cols')
                field['height'] = config.getint(name + '.rows')
            fields.append(field)

        fields.sort(lambda x, y: cmp(x['order'], y['order']))
        return fields

    def eventually_restrict_owner(self, field, ticket=None):
        """Restrict given owner field to be a list of users having
        the TICKET_MODIFY permission (for the given ticket)
        """
        if self.restrict_owner:
            field['type'] = 'select'
            possible_owners = []
            for user in PermissionSystem(self.env) \
                    .get_users_with_permission('TICKET_MODIFY'):
                if not ticket or \
                        'TICKET_MODIFY' in PermissionCache(self.env, user,
                                                           ticket.resource):
                    possible_owners.append(user)
            possible_owners.sort()
            field['options'] = possible_owners
            field['optional'] = True

    # IPermissionRequestor methods

    def get_permission_actions(self):
        return ['TICKET_APPEND', 'TICKET_CREATE', 'TICKET_CHGPROP',
                'TICKET_VIEW', 'TICKET_EDIT_CC', 'TICKET_EDIT_DESCRIPTION',
                ('TICKET_MODIFY', ['TICKET_APPEND', 'TICKET_CHGPROP']),
                ('TICKET_ADMIN', ['TICKET_CREATE', 'TICKET_MODIFY',
                                  'TICKET_VIEW', 'TICKET_EDIT_CC',
                                  'TICKET_EDIT_DESCRIPTION'])]

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
                ticket = formatter.resource('ticket', num)
                from trac.ticket.model import Ticket
                if Ticket.id_is_valid(num) and \
                        'TICKET_VIEW' in formatter.perm(ticket):
                    # TODO: watch #6436 and when done, attempt to retrieve 
                    #       ticket directly (try: Ticket(self.env, num) ...)
                    cursor = formatter.db.cursor() 
                    cursor.execute("SELECT type,summary,status,resolution "
                                   "FROM ticket WHERE id=%s", (str(num),)) 
                    for type, summary, status, resolution in cursor:
                        title = self.format_summary(summary, status,
                                                    resolution, type)
                        href = formatter.href.ticket(num) + params + fragment
                        return tag.a(label, class_='%s ticket' % status, 
                                     title=title, href=href)
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
        resource = None
        if ':' in target:
            elts = target.split(':')
            if len(elts) == 3:
                cnum, realm, id = elts
                if cnum != 'description' and cnum and not cnum[0].isdigit():
                    realm, id, cnum = elts # support old comment: style
                resource = formatter.resource(realm, id)
        else:
            resource = formatter.resource
            cnum = target

        if resource:
            href = "%s#comment:%s" % (formatter.href.ticket(resource.id), cnum)
            title = _("Comment %(cnum)s for Ticket #%(id)s", cnum=cnum,
                      id=resource.id)
            return tag.a(label, href=href, title=title)
        else:
            return label
 
    # IResourceManager methods

    def get_resource_realms(self):
        yield 'ticket'

    def get_resource_description(self, resource, format=None, context=None,
                                 **kwargs):
        if format == 'compact':
            return '#%s' % resource.id
        elif format == 'summary':
            from trac.ticket.model import Ticket
            ticket = Ticket(self.env, resource.id)
            args = [ticket[f] for f in ('summary', 'status', 'resolution',
                                        'type')]
            return self.format_summary(*args)
        return _("Ticket #%(shortname)s", shortname=resource.id)

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
