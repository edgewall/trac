# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2018 Edgewall Software
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

import contextlib
import copy
import re

from genshi.builder import tag

from trac.cache import cached
from trac.config import (
    BoolOption, ConfigSection, ListOption, Option, OrderedExtensionsOption
)
from trac.core import *
from trac.perm import IPermissionRequestor, PermissionCache, PermissionSystem
from trac.resource import IResourceManager
from trac.util import Ranges, as_bool, as_int
from trac.util.text import shorten_line
from trac.util.translation import _, N_, deactivate, gettext, reactivate
from trac.wiki import IWikiSyntaxProvider, WikiParser


class TicketFieldList(list):
    """Improved ticket field list, allowing access by name."""
    __slots__ = ['_map']

    def __init__(self, *args):
        super(TicketFieldList, self).__init__(*args)
        self._map = dict((value['name'], value) for value in self)

    def append(self, value):
        super(TicketFieldList, self).append(value)
        self._map[value['name']] = value

    def by_name(self, name, default=None):
        return self._map.get(name, default)

    def __copy__(self):
        return TicketFieldList(self)

    def __deepcopy__(self, memo):
        return TicketFieldList(copy.deepcopy(value, memo) for value in self)


class ITicketActionController(Interface):
    """Extension point interface for components willing to participate
    in the ticket workflow.

    This is mainly about controlling the changes to the ticket ''status'',
    though not restricted to it.
    """

    def get_ticket_actions(req, ticket):
        """Return an iterable of `(weight, action)` tuples corresponding to
        the actions that are contributed by this component. The list is
        dependent on the current state of the ticket and the actual request
        parameter.

        `action` is a key used to identify that particular action.
        (note that 'history' and 'diff' are reserved and should not be used
        by plugins)

        The actions will be presented on the page in descending order of the
        integer weight. The first action in the list is used as the default
        action.

        When in doubt, use a weight of 0.
        """

    def get_all_status():
        """Returns an iterable of all the possible values for the ''status''
        field this action controller knows about.

        This will be used to populate the query options and the like.
        It is assumed that the terminal status of a ticket is 'closed'.
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

    def ticket_comment_modified(ticket, cdate, author, comment, old_comment):
        """Called when a ticket comment is modified."""

    def ticket_change_deleted(ticket, cdate, changes):
        """Called when a ticket change is deleted.

        `changes` is a dictionary of tuple `(oldvalue, newvalue)`
        containing the ticket change of the fields that have changed."""


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


class IMilestoneChangeListener(Interface):
    """Extension point interface for components that require notification
    when milestones are created, modified, or deleted."""

    def milestone_created(milestone):
        """Called when a milestone is created."""

    def milestone_changed(milestone, old_values):
        """Called when a milestone is modified.

        `old_values` is a dictionary containing the previous values of the
        milestone properties that changed. Currently those properties can be
        'name', 'due', 'completed', or 'description'.
        """

    def milestone_deleted(milestone):
        """Called when a milestone is deleted."""


class TicketSystem(Component):
    implements(IPermissionRequestor, IWikiSyntaxProvider, IResourceManager)

    change_listeners = ExtensionPoint(ITicketChangeListener)
    milestone_change_listeners = ExtensionPoint(IMilestoneChangeListener)

    realm = 'ticket'

    ticket_custom_section = ConfigSection('ticket-custom',
        """In this section, you can define additional fields for tickets. See
        TracTicketsCustomFields for more details.""")

    action_controllers = OrderedExtensionsOption('ticket', 'workflow',
        ITicketActionController, default='ConfigurableTicketWorkflow',
        include_missing=False,
        doc="""Ordered list of workflow controllers to use for ticket actions.
            """)

    restrict_owner = BoolOption('ticket', 'restrict_owner', 'false',
        """Make the owner field of tickets use a drop-down menu.
        Be sure to understand the performance implications before activating
        this option. See
        [TracTickets#Assign-toasDrop-DownList Assign-to as Drop-Down List].

        Please note that e-mail addresses are '''not''' obfuscated in the
        resulting drop-down menu, so this option should not be used if
        e-mail addresses must remain protected.
        """)

    default_version = Option('ticket', 'default_version', '',
        """Default version for newly created tickets.""")

    default_type = Option('ticket', 'default_type', 'defect',
        """Default type for newly created tickets.""")

    default_priority = Option('ticket', 'default_priority', 'major',
        """Default priority for newly created tickets.""")

    default_milestone = Option('ticket', 'default_milestone', '',
        """Default milestone for newly created tickets.""")

    default_component = Option('ticket', 'default_component', '',
        """Default component for newly created tickets.""")

    default_severity = Option('ticket', 'default_severity', '',
        """Default severity for newly created tickets.""")

    default_summary = Option('ticket', 'default_summary', '',
        """Default summary (title) for newly created tickets.""")

    default_description = Option('ticket', 'default_description', '',
        """Default description for newly created tickets.""")

    default_keywords = Option('ticket', 'default_keywords', '',
        """Default keywords for newly created tickets.""")

    default_owner = Option('ticket', 'default_owner', '< default >',
        """Default owner for newly created tickets.""")

    default_cc = Option('ticket', 'default_cc', '',
        """Default cc: list for newly created tickets.""")

    default_resolution = Option('ticket', 'default_resolution', 'fixed',
        """Default resolution for resolving (closing) tickets.""")

    allowed_empty_fields = ListOption('ticket', 'allowed_empty_fields',
        'milestone, version', doc=
        """Comma-separated list of `select` fields that can have
        an empty value. (//since 1.1.2//)""")

    def __init__(self):
        self.log.debug('action controllers for ticket workflow: %r',
                       [c.__class__.__name__ for c in self.action_controllers])

    # Public API

    def get_available_actions(self, req, ticket):
        """Returns a sorted list of available actions"""
        # The list should not have duplicates.
        actions = {}
        for controller in self.action_controllers:
            weighted_actions = controller.get_ticket_actions(req, ticket) or []
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
            valid_states.update(controller.get_all_status() or [])
        return sorted(valid_states)

    def get_ticket_field_labels(self):
        """Produce a (name,label) mapping from `get_ticket_fields`."""
        labels = dict((f['name'], f['label'])
                      for f in self.get_ticket_fields())
        labels['attachment'] = _("Attachment")
        return labels

    def get_ticket_fields(self):
        """Returns list of fields available for tickets.

        Each field is a dict with at least the 'name', 'label' (localized)
        and 'type' keys.
        It may in addition contain the 'custom' key, the 'optional' and the
        'options' keys. When present 'custom' and 'optional' are always `True`.
        """
        fields = copy.deepcopy(self.fields)
        label = 'label' # workaround gettext extraction bug
        for f in fields:
            f[label] = gettext(f[label])
        return fields

    def reset_ticket_fields(self):
        """Invalidate ticket field cache."""
        del self.fields

    @cached
    def fields(self):
        """Return the list of fields available for tickets."""
        from trac.ticket import model

        fields = TicketFieldList()

        # Basic text fields
        fields.append({'name': 'summary', 'type': 'text',
                       'label': N_('Summary')})
        fields.append({'name': 'reporter', 'type': 'text',
                       'label': N_('Reporter')})

        # Owner field, by default text but can be changed dynamically
        # into a drop-down depending on configuration (restrict_owner=true)
        fields.append({'name': 'owner', 'type': 'text',
                       'label': N_('Owner')})

        # Description
        fields.append({'name': 'description', 'type': 'textarea',
                       'format': 'wiki', 'label': N_('Description')})

        # Default select and radio fields
        selects = [('type', N_('Type'), model.Type),
                   ('status', N_('Status'), model.Status),
                   ('priority', N_('Priority'), model.Priority),
                   ('milestone', N_('Milestone'), model.Milestone),
                   ('component', N_('Component'), model.Component),
                   ('version', N_('Version'), model.Version),
                   ('severity', N_('Severity'), model.Severity),
                   ('resolution', N_('Resolution'), model.Resolution)]
        for name, label, cls in selects:
            options = [val.name for val in cls.select(self.env)]
            if not options:
                # Fields without possible values are treated as if they didn't
                # exist
                continue
            field = {'name': name, 'type': 'select', 'label': label,
                     'value': getattr(self, 'default_' + name, ''),
                     'options': options}
            if name in ('status', 'resolution'):
                field['type'] = 'radio'
                field['optional'] = True
            elif name in self.allowed_empty_fields:
                field['optional'] = True
            fields.append(field)

        # Advanced text fields
        fields.append({'name': 'keywords', 'type': 'text', 'format': 'list',
                       'label': N_('Keywords')})
        fields.append({'name': 'cc', 'type': 'text',  'format': 'list',
                       'label': N_('Cc')})

        # Date/time fields
        fields.append({'name': 'time', 'type': 'time',
                       'format': 'relative', 'label': N_('Created')})
        fields.append({'name': 'changetime', 'type': 'time',
                       'format': 'relative', 'label': N_('Modified')})

        for field in self.custom_fields:
            if field['name'] in [f['name'] for f in fields]:
                self.log.warning('Duplicate field name "%s" (ignoring)',
                                 field['name'])
                continue
            fields.append(field)

        return fields

    reserved_field_names = ['report', 'order', 'desc', 'group', 'groupdesc',
                            'col', 'row', 'format', 'max', 'page', 'verbose',
                            'comment', 'or', 'id', 'time', 'changetime',
                            'owner', 'reporter', 'cc', 'summary',
                            'description', 'keywords']

    def get_custom_fields(self):
        return copy.deepcopy(self.custom_fields)

    @cached
    def custom_fields(self):
        """Return the list of custom ticket fields available for tickets."""
        fields = TicketFieldList()
        config = self.ticket_custom_section
        for name in [option for option, value in config.options()
                     if '.' not in option]:
            field = {
                'name': name,
                'custom': True,
                'type': config.get(name),
                'order': config.getint(name + '.order', 0),
                'label': config.get(name + '.label') or
                         name.replace("_", " ").strip().capitalize(),
                'value': config.get(name + '.value', '')
            }
            if field['type'] == 'select' or field['type'] == 'radio':
                field['options'] = config.getlist(name + '.options', sep='|')
                if '' in field['options'] or \
                        field['name'] in self.allowed_empty_fields:
                    field['optional'] = True
                    if '' in field['options']:
                        field['options'].remove('')
            elif field['type'] == 'checkbox':
                field['value'] = '1' if as_bool(field['value']) else '0'
            elif field['type'] == 'text':
                field['format'] = config.get(name + '.format', 'plain')
            elif field['type'] == 'textarea':
                field['format'] = config.get(name + '.format', 'plain')
                field['height'] = config.getint(name + '.rows')
            elif field['type'] == 'time':
                field['format'] = config.get(name + '.format', 'datetime')

            if field['name'] in self.reserved_field_names:
                self.log.warning('Field name "%s" is a reserved name '
                                 '(ignoring)', field['name'])
                continue
            if not re.match('^[a-zA-Z][a-zA-Z0-9_]+$', field['name']):
                self.log.warning('Invalid name for custom field: "%s" '
                                 '(ignoring)', field['name'])
                continue

            fields.append(field)

        fields.sort(lambda x, y: cmp((x['order'], x['name']),
                                     (y['order'], y['name'])))
        return fields

    def get_field_synonyms(self):
        """Return a mapping from field name synonyms to field names.
        The synonyms are supposed to be more intuitive for custom queries."""
        # i18n TODO - translated keys
        return {'created': 'time', 'modified': 'changetime'}

    def eventually_restrict_owner(self, field, ticket=None):
        """Restrict given owner field to be a list of users having
        the TICKET_MODIFY permission (for the given ticket)
        """
        if self.restrict_owner:
            field['type'] = 'select'
            field['options'] = self.get_allowed_owners(ticket)
            field['optional'] = True

    def get_allowed_owners(self, ticket=None):
        """Returns a list of permitted ticket owners (those possessing the
        TICKET_MODIFY permission). Returns `None` if the option `[ticket]`
        `restrict_owner` is `False`.

        If `ticket` is not `None`, fine-grained permission checks are used
        to determine the allowed owners for the specified resource.

        :since: 1.0.3
        """
        if self.restrict_owner:
            allowed_owners = []
            for user in PermissionSystem(self.env) \
                        .get_users_with_permission('TICKET_MODIFY'):
                if not ticket or \
                        'TICKET_MODIFY' in PermissionCache(self.env, user,
                                                           ticket.resource):
                    allowed_owners.append(user)
            allowed_owners.sort()
            return allowed_owners

    # IPermissionRequestor methods

    def get_permission_actions(self):
        return ['TICKET_APPEND', 'TICKET_CREATE', 'TICKET_CHGPROP',
                'TICKET_VIEW', 'TICKET_EDIT_CC', 'TICKET_EDIT_DESCRIPTION',
                'TICKET_EDIT_COMMENT',
                ('TICKET_MODIFY', ['TICKET_APPEND', 'TICKET_CHGPROP']),
                ('TICKET_ADMIN', ['TICKET_CREATE', 'TICKET_MODIFY',
                                  'TICKET_VIEW', 'TICKET_EDIT_CC',
                                  'TICKET_EDIT_DESCRIPTION',
                                  'TICKET_EDIT_COMMENT'])]

    # IWikiSyntaxProvider methods

    def get_link_resolvers(self):
        return [('bug', self._format_link),
                ('issue', self._format_link),
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
                ticket = formatter.resource(self.realm, num)
                from trac.ticket.model import Ticket
                if Ticket.id_is_valid(num) and \
                        'TICKET_VIEW' in formatter.perm(ticket):
                    # TODO: attempt to retrieve ticket view directly,
                    #       something like: t = Ticket.view(num)
                    for type, summary, status, resolution in \
                            self.env.db_query("""
                            SELECT type, summary, status, resolution
                            FROM ticket WHERE id=%s
                            """, (str(num),)):
                        description = self.format_summary(summary, status,
                                                          resolution, type)
                        title = '#%s: %s' % (num, description)
                        href = formatter.href.ticket(num) + params + fragment
                        return tag.a(label, title=title, href=href,
                                     class_='%s ticket' % status)
            else:
                ranges = str(r)
                if params:
                    params = '&' + params[1:]
                label_wrap = label.replace(',', u',\u200b')
                ranges_wrap = ranges.replace(',', u', ')
                return tag.a(label_wrap,
                             title=_("Tickets %(ranges)s", ranges=ranges_wrap),
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
                id = as_int(id, None)
                if realm in ('bug', 'issue'):
                    realm = 'ticket'
                resource = formatter.resource(realm, id)
        else:
            resource = formatter.resource
            cnum = target

        if resource and resource.id and resource.realm == self.realm and \
                cnum and (cnum.isdigit() or cnum == 'description'):
            href = title = class_ = None
            if self.resource_exists(resource):
                from trac.ticket.model import Ticket
                ticket = Ticket(self.env, resource.id)
                if cnum != 'description' and not ticket.get_change(cnum):
                    title = _("ticket comment does not exist")
                    class_ = 'missing ticket'
                elif 'TICKET_VIEW' in formatter.perm(resource):
                    href = formatter.href.ticket(resource.id) + \
                           "#comment:%s" % cnum
                    if resource.id != formatter.resource.id:
                        summary = self.format_summary(ticket['summary'],
                                                      ticket['status'],
                                                      ticket['resolution'],
                                                      ticket['type'])
                        if cnum == 'description':
                            title = _("Description for #%(id)s: %(summary)s",
                                      id=resource.id, summary=summary)
                        else:
                            title = _("Comment %(cnum)s for #%(id)s: "
                                      "%(summary)s", cnum=cnum,
                                      id=resource.id, summary=summary)
                        class_ = ticket['status'] + ' ticket'
                    else:
                        title = _("Description") if cnum == 'description' \
                                                 else _("Comment %(cnum)s",
                                                        cnum=cnum)
                        class_ = 'ticket'
                else:
                    title = _("no permission to view ticket")
                    class_ = 'forbidden ticket'
            else:
                title = _("ticket does not exist")
                class_ = 'missing ticket'
            return tag.a(label, class_=class_, href=href, title=title)
        return label

    # IResourceManager methods

    def get_resource_realms(self):
        yield self.realm

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

    def resource_exists(self, resource):
        """
        >>> from trac.test import EnvironmentStub
        >>> from trac.resource import Resource, resource_exists
        >>> env = EnvironmentStub()

        >>> resource_exists(env, Resource('ticket', 123456))
        False

        >>> from trac.ticket.model import Ticket
        >>> t = Ticket(env)
        >>> int(t.insert())
        1
        >>> resource_exists(env, t.resource)
        True
        """
        try:
            id_ = int(resource.id)
        except (TypeError, ValueError):
            return False
        if self.env.db_query("SELECT id FROM ticket WHERE id=%s", (id_,)):
            if resource.version is None:
                return True
            revcount = self.env.db_query("""
                SELECT count(DISTINCT time) FROM ticket_change WHERE ticket=%s
                """, (id_,))
            return revcount[0][0] >= resource.version
        else:
            return False


@contextlib.contextmanager
def translation_deactivated(ticket=None):
    t = deactivate()
    if ticket is not None:
        ts = TicketSystem(ticket.env)
        translated_fields = ticket.fields
        ticket.fields = ts.get_ticket_fields()
    try:
        yield
    finally:
        if ticket is not None:
            ticket.fields = translated_fields
        reactivate(t)
