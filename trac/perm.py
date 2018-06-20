# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2009 Edgewall Software
# Copyright (C) 2003-2004 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
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
#         Christopher Lenz <cmlenz@gmx.de>

from __future__ import print_function

import csv
import os
from itertools import groupby

from trac.admin import AdminCommandError, IAdminCommandProvider, get_dir_list
from trac.cache import cached
from trac.config import ExtensionOption, OrderedExtensionsOption
from trac.core import *
from trac.resource import Resource, get_resource_name
from trac.util import file_or_std
from trac.util.datefmt import time_now
from trac.util.text import path_to_unicode, print_table, printout, \
                           stream_encoding, to_unicode, wrap
from trac.util.translation import _, N_

__all__ = ['IPermissionRequestor', 'IPermissionStore', 'IPermissionPolicy',
           'IPermissionGroupProvider', 'PermissionError', 'PermissionSystem']


class PermissionError(TracBaseError):
    """Insufficient permissions to perform the operation."""

    title = N_("Forbidden")

    def __init__(self, action=None, resource=None, env=None, msg=None):
        self.action = action
        self.resource = resource
        self.env = env
        if self.action:
            if self.resource and self.resource.id:
                msg = _("%(perm)s privileges are required to perform "
                        "this operation on %(resource)s. You don't have the "
                        "required permissions.",
                        perm=self.action,
                        resource=get_resource_name(self.env, self.resource))
            else:
                msg = _("%(perm)s privileges are required to perform this "
                        "operation. You don't have the required "
                        "permissions.", perm=self.action)
        elif msg is None:
            msg = _("Insufficient privileges to perform this operation.")
        super(PermissionError, self).__init__(msg)

    @property
    def message(self):
        return self.args[0]


class PermissionExistsError(TracError):
    """Thrown when a unique key constraint is violated."""


class IPermissionRequestor(Interface):
    """Extension point interface for components that define actions."""

    def get_permission_actions():
        """Return a list of actions defined by this component.

        The items in the list may either be simple strings, or
        `(string, sequence)` tuples. The latter are considered to be "meta
        permissions" that group several simple actions under one name for
        convenience, adding to it if another component already defined that
        name.
        """


class IPermissionStore(Interface):
    """Extension point interface for components that provide storage and
    management of permissions.
    """

    def get_user_permissions(username):
        """Return a list of permissions for the specified user.
        """

    def get_users_with_permissions(permissions):
        """Return a list of users that have any of the specified
        permissions.
        """

    def get_all_permissions():
        """Return all permissions for all users.

        The permissions are returned as a list of (subject, action)
        formatted tuples.
        """

    def grant_permission(username, action):
        """Grant a user permission to perform an action."""

    def revoke_permission(username, action):
        """Revokes the permission of the given user to perform an action."""


class IPermissionGroupProvider(Interface):
    """Extension point interface for components that provide information
    about user groups.
    """

    def get_permission_groups(username):
        """Return a list of names of the groups that the user with the
        specified name is a member of.
        """


class IPermissionPolicy(Interface):
    """A security policy provider used for fine grained permission checks."""

    def check_permission(action, username, resource, perm):
        """Check that the action can be performed by username on the resource

        :param action: the name of the permission
        :param username: the username string or 'anonymous' if there's no
                         authenticated user
        :param resource: the resource on which the check applies.
                         Will be `None`, if the check is a global one and
                         not made on a resource in particular
        :param perm: the permission cache for that username and resource,
                     which can be used for doing secondary checks on other
                     permissions. Care must be taken to avoid recursion.

        :return: `True` if action is allowed, `False` if action is denied,
                 or `None` if indifferent. If `None` is returned, the next
                 policy in the chain will be consulted.

        Note that when checking a permission on a realm resource (i.e. when
        `.id` is `None`), this usually corresponds to some preliminary check
        done before making a fine-grained check on some resource.
        Therefore the `IPermissionPolicy` should be conservative and return:

         * `True` if the action *can* be allowed for some resources in
           that realm. Later, for specific resource, the policy will be able
           to return `True` (allow), `False` (deny) or `None` (don't decide).
         * `None` if the action *can not* be performed for *some* resources.
           This corresponds to situation where the policy is only interested
           in returning `False` or `None` on specific resources.
         * `False` if the action *can not* be performed for *any* resource
           in that realm (that's a very strong decision as that will usually
           prevent any fine-grained check to even happen).

        Note that performing permission checks on realm resources may seem
        redundant for now as the action name itself contains the realm, but
        this will probably change in the future (e.g. `'VIEW' in ...`).
        """


class DefaultPermissionStore(Component):
    """Default implementation of permission storage and group management.

    This component uses the `permission` table in the database to store both
    permissions and groups.
    """
    implements(IPermissionGroupProvider, IPermissionStore)

    group_providers = ExtensionPoint(IPermissionGroupProvider)

    # IPermissionGroupProvider methods

    def get_permission_groups(self, username):
        """Return a list of names of the groups that the user with the
        specified name is a member of.
        """
        return sorted(self._get_actions_and_groups({username})[1])

    # IPermissionStore methods

    def get_user_permissions(self, username):
        """Retrieve a list of permissions for the given user.

        The permissions are stored in the database as (username, action)
        records. There's simple support for groups by using lowercase
        names for the action column: such a record represents a group and
        not an actual permission, and declares that the user is part of
        that group.
        """
        subjects = {username}
        for provider in self.group_providers:
            if provider is not self:
                subjects.update(provider.get_permission_groups(username) or [])
        return sorted(self._get_actions_and_groups(subjects)[0])

    def get_users_with_permissions(self, permissions):
        """Retrieve a list of users that have any of the specified
        permissions

        Users are returned as a list of usernames.
        """
        # get_user_permissions() takes care of the magic 'authenticated'
        # group. The optimized loop we had before didn't. This is very
        # inefficient, but it works.
        result = set()
        users = {u[0] for u in self.env.get_known_users()}
        for user in users:
            user_perms = self.get_user_permissions(user)
            for group in permissions:
                if group in user_perms:
                    result.add(user)
        return sorted(result)

    def get_all_permissions(self):
        """Return all permissions for all users.

        The permissions are returned as a list of (subject, action)
        formatted tuples.
        """
        return self._all_permissions

    def grant_permission(self, username, action):
        """Grants a user the permission to perform the specified action."""
        self.env.db_transaction("INSERT INTO permission VALUES (%s, %s)",
                                (username, action))
        self.log.info("Granted permission for %s to %s", action, username)

        # Invalidate cached property
        del self._all_permissions

    def revoke_permission(self, username, action):
        """Revokes a users' permission to perform the specified action."""
        self.env.db_transaction(
                "DELETE FROM permission WHERE username=%s AND action=%s",
                (username, action))
        self.log.info("Revoked permission for %s to %s", action, username)

        # Invalidate cached property
        del self._all_permissions

    @cached
    def _all_permissions(self):
        return sorted(self.env.db_query("""
                          SELECT username, action FROM permission
                          """))

    def _get_actions_and_groups(self, subjects):
        """Get actions and groups for `subjects`, an iterable of username
        and groups that username is a member of.
        """
        actions = set()
        groups = set()
        perms = self._all_permissions
        while True:
            num_users = len(subjects)
            num_actions = len(actions)
            for user, action in perms:
                if user in subjects:
                    if action.isupper():
                        actions.add(action)
                    if not action.isupper():  # permission group
                        subjects.add(action)
                        groups.add(action)
            if num_users == len(subjects) and num_actions == len(actions):
                break
        return actions, groups


class DefaultPermissionGroupProvider(Component):
    """Permission group provider providing the basic builtin permission
    groups 'anonymous' and 'authenticated'.
    """

    required = True

    implements(IPermissionGroupProvider)

    def get_permission_groups(self, username):
        groups = ['anonymous']
        if username and username != 'anonymous':
            groups.append('authenticated')
        return groups


class DefaultPermissionPolicy(Component):
    """Default permission policy using the IPermissionStore system."""

    implements(IPermissionPolicy)

    # Number of seconds a cached user permission set is valid for.
    CACHE_EXPIRY = 5
    # How frequently to clear the entire permission cache
    CACHE_REAP_TIME = 60

    def __init__(self):
        self.permission_cache = {}
        self.last_reap = time_now()

    # IPermissionPolicy methods

    def check_permission(self, action, username, resource, perm):
        now = time_now()

        if now - self.last_reap > self.CACHE_REAP_TIME:
            self.permission_cache = {}
            self.last_reap = time_now()

        timestamp, permissions = \
            self.permission_cache.get(username, (0, None))

        # Cache hit?
        if now - timestamp > self.CACHE_EXPIRY:
            # No, pull permissions from database.
            permissions = PermissionSystem(self.env). \
                          get_user_permissions(username)
            self.permission_cache[username] = (now, permissions)

        return action in permissions or None


class PermissionSystem(Component):
    """Permission management sub-system."""

    required = True

    implements(IPermissionRequestor)

    requestors = ExtensionPoint(IPermissionRequestor)
    group_providers = ExtensionPoint(IPermissionGroupProvider)

    store = ExtensionOption('trac', 'permission_store', IPermissionStore,
                            'DefaultPermissionStore',
        """Name of the component implementing `IPermissionStore`, which is
        used for managing user and group permissions.""")

    policies = OrderedExtensionsOption('trac', 'permission_policies',
        IPermissionPolicy,
        'DefaultWikiPolicy, DefaultTicketPolicy, DefaultPermissionPolicy, '
        'LegacyAttachmentPolicy',
        False,
        """List of components implementing `IPermissionPolicy`, in the order
        in which they will be applied. These components manage fine-grained
        access control to Trac resources.""")

    # Number of seconds a cached user permission set is valid for.
    CACHE_EXPIRY = 5
    # How frequently to clear the entire permission cache
    CACHE_REAP_TIME = 60

    def __init__(self):
        self.permission_cache = {}
        self.last_reap = time_now()

    # Public API

    def grant_permission(self, username, action):
        """Grant the user with the given name permission to perform to
        specified action.

        :raises PermissionExistsError: if user already has the permission
                                       or is a member of the group.

        :since 1.3.1: raises PermissionExistsError rather than IntegrityError
        """
        if action.isupper() and action not in self.get_actions():
            raise TracError(_('%(name)s is not a valid action.', name=action))
        elif not action.isupper() and action.upper() in self.get_actions():
            raise TracError(_("Permission %(name)s differs from a defined "
                              "action by casing only, which is not allowed.",
                              name=action))

        try:
            self.store.grant_permission(username, action)
        except self.env.db_exc.IntegrityError:
            if action in self.get_actions():
                raise PermissionExistsError(
                    _("The user %(user)s already has permission %(action)s.",
                      user=username, action=action))
            else:
                raise PermissionExistsError(
                    _("The user %(user)s is already in the group %(group)s.",
                      user=username, group=action))

    def revoke_permission(self, username, action):
        """Revokes the permission of the specified user to perform an
        action."""
        self.store.revoke_permission(username, action)

    def get_actions_dict(self, skip=None):
        """Get all actions from permission requestors as a `dict`.

        The keys are the action names. The values are the additional actions
        granted by each action. For simple actions, this is an empty list.
        For meta actions, this is the list of actions covered by the action.

        :since 1.0.17: added `skip` argument.
        """
        actions = {}
        for requestor in self.requestors:
            if requestor is skip:
                continue
            for action in requestor.get_permission_actions() or []:
                if isinstance(action, tuple):
                    actions.setdefault(action[0], []).extend(action[1])
                else:
                    actions.setdefault(action, [])
        return actions

    def get_actions(self, skip=None):
        """Get a list of all actions defined by permission requestors."""
        actions = set()
        for requestor in self.requestors:
            if requestor is skip:
                continue
            for action in requestor.get_permission_actions() or []:
                if isinstance(action, tuple):
                    actions.add(action[0])
                else:
                    actions.add(action)
        return sorted(actions)

    def get_groups_dict(self):
        """Get all groups as a `dict`.

        The keys are the group names. The values are the group members.

        :since: 1.1.3
        """
        groups = sorted((p for p in self.get_all_permissions()
                           if not p[1].isupper()), key=lambda p: p[1])

        return {k: sorted(i[0] for i in list(g))
                for k, g in groupby(groups, key=lambda p: p[1])}

    def get_users_dict(self):
        """Get all users as a `dict`.

        The keys are the user names. The values are the actions possessed
        by the user.

        :since: 1.1.3
        """
        perms = sorted((p for p in self.get_all_permissions()
                          if p[1].isupper()), key=lambda p: p[0])

        return {k: sorted(i[1] for i in list(g))
                for k, g in groupby(perms, key=lambda p: p[0])}

    def get_user_permissions(self, username=None, undefined=False,
                             expand_meta=True):
        """Return the permissions of the specified user.

        The return value is a dictionary containing all the actions
        granted to the user mapped to `True`.

        :param undefined: if `True`, include actions that are not defined
            in any of the `IPermissionRequestor` implementations.
        :param expand_meta: if `True`, expand meta permissions.

        :since 1.3.1: added the `undefined` parameter.
        :since 1.3.3: added the `expand_meta` parameter.
        """
        if not username:
            # Return all permissions available in the system
            return dict.fromkeys(self.get_actions(), True)

        # Return all permissions that the given user has
        actions = self.get_actions_dict()
        user_permissions = self.store.get_user_permissions(username) or []
        if expand_meta:
            return {p: True for p in self.expand_actions(user_permissions)
                            if undefined or p in actions}
        else:
            return {p: True for p in user_permissions
                            if undefined or p in actions}

    def get_permission_groups(self, username):
        """Return a sorted list of groups that `username` belongs to.

        Groups are recursively expanded such that if `username` is a
        member of `group1` and `group1` is a member of `group2`, both
        `group1` and `group2` will be returned.

        :since: 1.3.3
        """
        user_groups = set()
        for provider in self.group_providers:
            user_groups.update(provider.get_permission_groups(username) or [])

        return sorted(user_groups)

    def get_all_permissions(self):
        """Return all permissions for all users.

        The permissions are returned as a list of (subject, action)
        formatted tuples.
        """
        return self.store.get_all_permissions() or []

    def get_users_with_permission(self, permission):
        """Return all users that have the specified permission.

        Users are returned as a list of user names.
        """
        now = time_now()
        if now - self.last_reap > self.CACHE_REAP_TIME:
            self.permission_cache = {}
            self.last_reap = now
        timestamp, permissions = self.permission_cache.get(permission,
                                                           (0, None))
        if now - timestamp <= self.CACHE_EXPIRY:
            return permissions

        parent_map = {}
        for parent, children in self.get_actions_dict().iteritems():
            for child in children:
                parent_map.setdefault(child, set()).add(parent)

        satisfying_perms = set()
        def append_with_parents(action):
            if action not in satisfying_perms:
                satisfying_perms.add(action)
                for action in parent_map.get(action, ()):
                    append_with_parents(action)
        append_with_parents(permission)

        perms = self.store.get_users_with_permissions(satisfying_perms) or []
        self.permission_cache[permission] = (now, perms)
        return perms

    def expand_actions(self, actions):
        """Helper method for expanding all meta actions."""
        all_actions = self.get_actions_dict()
        expanded_actions = set()
        def expand_action(action):
            if action not in expanded_actions:
                expanded_actions.add(action)
                for a in all_actions.get(action, ()):
                    expand_action(a)
        for a in actions:
            expand_action(a)
        return sorted(expanded_actions)

    def check_permission(self, action, username=None, resource=None,
                         perm=None):
        """Return True if permission to perform action for the given
        resource is allowed.
        """
        if username is None:
            username = 'anonymous'
        if resource and resource.realm is None:
            resource = None
        for policy in self.policies:
            decision = policy.check_permission(action, username, resource,
                                               perm)
            if decision is not None:
                self.log.debug("%s %s %s performing %s on %r",
                               policy.__class__.__name__,
                               'allows' if decision else 'denies',
                               username, action, resource)
                return decision
        self.log.debug("No policy allowed %s performing %s on %r",
                       username, action, resource)
        return False

    # IPermissionRequestor methods

    def get_permission_actions(self):
        """Implement the global `TRAC_ADMIN` meta permission.
        """
        actions = self.get_actions(skip=self)
        return [('TRAC_ADMIN', actions)]


class PermissionCache(object):
    """Cache that maintains the permissions of a single user.

    Permissions are usually checked using the following syntax:

        'WIKI_MODIFY' in perm

    One can also apply more fine grained permission checks and
    specify a specific resource for which the permission should be available:

        'WIKI_MODIFY' in perm('wiki', 'WikiStart')

    If there's already a `page` object available, the check is simply:

        'WIKI_MODIFY' in perm(page.resource)

    If instead of a check, one wants to assert that a given permission is
    available, the following form should be used:

        perm.require('WIKI_MODIFY')

        or

        perm('wiki', 'WikiStart').require('WIKI_MODIFY')

        or

        perm(page.resource).require('WIKI_MODIFY')

    When using `require`,  a `PermissionError` exception is raised if the
    permission is missing.
    """

    __slots__ = ('env', 'username', '_resource', '_cache')

    def __init__(self, env, username=None, resource=None, cache=None,
                 groups=None):
        self.env = env
        self.username = username or 'anonymous'
        self._resource = resource
        if cache is None:
            cache = {}
        self._cache = cache

    def _normalize_resource(self, realm_or_resource, id, version):
        if realm_or_resource:
            return Resource(realm_or_resource, id, version)
        else:
            return self._resource

    def __call__(self, realm_or_resource, id=False, version=False):
        """Convenience function for using thus:
            'WIKI_VIEW' in perm(context)
        or
            'WIKI_VIEW' in perm(realm, id, version)
        or
            'WIKI_VIEW' in perm(resource)

        """
        resource = Resource(realm_or_resource, id, version) \
                   if realm_or_resource else None
        if resource and self._resource and resource == self._resource:
            return self
        else:
            return PermissionCache(self.env, self.username, resource,
                                   self._cache)

    def has_permission(self, action, realm_or_resource=None, id=False,
                       version=False):
        resource = self._normalize_resource(realm_or_resource, id, version)
        return self._has_permission(action, resource)

    def _has_permission(self, action, resource):
        key = (self.username, hash(resource), action)
        cached = self._cache.get(key)
        if cached:
            cache_decision, cache_resource = cached
            if resource == cache_resource:
                return cache_decision
        # Avoid recursion in policies that call has_permission.
        self._cache[key] = (False, resource)
        perm = self
        if resource is not self._resource:
            perm = PermissionCache(self.env, self.username, resource,
                                   self._cache)
        decision = PermissionSystem(self.env). \
                   check_permission(action, perm.username, resource, perm)
        self._cache[key] = (decision, resource)
        return decision

    __contains__ = has_permission

    def require(self, action, realm_or_resource=None, id=False, version=False,
                message=None):
        resource = self._normalize_resource(realm_or_resource, id, version)
        if not self._has_permission(action, resource):
            if message is None:
                raise PermissionError(action, resource, self.env)
            else:
                raise PermissionError(msg=message)
    assert_permission = require


class PermissionAdmin(Component):
    """trac-admin command provider for permission system administration."""

    implements(IAdminCommandProvider)

    # IAdminCommandProvider methods

    def get_admin_commands(self):
        yield ('permission list', '[user]',
               "List permission rules",
               self._complete_list, self._do_list)
        yield ('permission add', '<user> <action> [action] [...]',
               "Add a new permission rule",
               self._complete_add, self._do_add)
        yield ('permission remove', '<user> <action> [action] [...]',
               "Remove a permission rule",
               self._complete_remove, self._do_remove)
        yield ('permission export', '[file]',
               "Export permission rules to a file or stdout as CSV",
               self._complete_import_export, self._do_export)
        yield ('permission import', '[file]',
               "Import permission rules from a file or stdin as CSV",
               self._complete_import_export, self._do_import)

    def get_user_list(self):
        return {user for (user, action)
                     in PermissionSystem(self.env).get_all_permissions()}

    def get_user_perms(self, user):
        return [action for (subject, action)
                       in PermissionSystem(self.env).get_all_permissions()
                       if subject == user]

    def _complete_list(self, args):
        if len(args) == 1:
            return self.get_user_list()

    def _complete_add(self, args):
        if len(args) == 1:
            return self.get_user_list()
        elif len(args) >= 2:
            return (set(PermissionSystem(self.env).get_actions())
                    - set(self.get_user_perms(args[0])) - set(args[1:-1]))

    def _complete_remove(self, args):
        if len(args) == 1:
            return self.get_user_list()
        elif len(args) >= 2:
            return set(self.get_user_perms(args[0])) - set(args[1:-1])

    def _complete_import_export(self, args):
        if len(args) == 1:
            return get_dir_list(args[-1])

    def _do_list(self, user=None):
        permsys = PermissionSystem(self.env)
        if user:
            rows = []
            perms = permsys.get_user_permissions(user, undefined=True)
            for action in perms:
                if perms[action]:
                    rows.append((user, action))
        else:
            rows = permsys.get_all_permissions()
        rows.sort()
        print_table(rows, [_('User'), _('Action')])
        print()
        printout(_("Available actions:"))
        actions = permsys.get_actions()
        actions.sort()
        text = ', '.join(actions)
        printout(wrap(text, initial_indent=' ', subsequent_indent=' ',
                      linesep='\n'))
        print()

    def _do_add(self, user, *actions):
        permsys = PermissionSystem(self.env)
        if user.isupper():
            raise AdminCommandError(_("All upper-cased tokens are reserved "
                                      "for permission names"))

        def grant_actions_atomically(actions):
            action = None
            try:
                with self.env.db_transaction:
                    for action in actions:
                        permsys.grant_permission(user, action)
            except PermissionExistsError as e:
                printout(e)
                return action
            except TracError as e:
                raise AdminCommandError(e)

        # An exception rolls back the atomic transaction so it's
        # necessary to retry the transaction after removing the
        # failed action from the list.
        actions_to_grant = list(actions)
        while actions_to_grant:
            action_that_failed = grant_actions_atomically(actions_to_grant)
            if action_that_failed is None:
                break
            else:
                actions_to_grant.remove(action_that_failed)

    def _do_remove(self, user, *actions):
        permsys = PermissionSystem(self.env)
        rows = permsys.get_all_permissions()
        for action in actions:
            found = False
            for u, a in rows:
                if user in (u, '*') and action in (a, '*'):
                    permsys.revoke_permission(u, a)
                    found = True
            if not found:
                if user in self.get_user_list() and \
                        action in permsys.get_user_permissions(user):
                    msg = _("Cannot remove permission %(action)s for user "
                            "%(user)s. The permission is granted through "
                            "a meta-permission or group.", action=action,
                            user=user)
                elif action in permsys.get_actions():
                    msg = _("Cannot remove permission %(action)s for user "
                            "%(user)s. The user has not been granted the "
                            "permission.", action=action, user=user)
                else:
                    msg = _("%(name)s is not a valid action.", name=action)
                raise AdminCommandError(msg)

    def _do_export(self, filename=None):
        try:
            with file_or_std(filename, 'wb') as f:
                encoding = stream_encoding(f)
                linesep = os.linesep if filename else '\n'
                writer = csv.writer(f, lineterminator=linesep)
                users = self.get_user_list()
                for user in sorted(users):
                    actions = sorted(self.get_user_perms(user))
                    writer.writerow([s.encode(encoding, 'replace')
                                     for s in [user] + actions])
        except IOError as e:
            raise AdminCommandError(
                _("Cannot export to %(filename)s: %(error)s",
                  filename=path_to_unicode(filename or 'stdout'),
                  error=e.strerror))

    def _do_import(self, filename=None):
        permsys = PermissionSystem(self.env)
        linesep = os.linesep if filename else '\n'
        try:
            with file_or_std(filename, 'rb') as f:
                encoding = stream_encoding(f)
                reader = csv.reader(f, lineterminator=linesep)
                for row in reader:
                    if len(row) < 2:
                        raise AdminCommandError(
                            _("Invalid row %(line)d. Expected <user>, "
                              "<action>, [action], [...]",
                              line=reader.line_num))
                    user = to_unicode(row[0], encoding)
                    actions = [to_unicode(action, encoding)
                               for action in row[1:]]
                    if user.isupper():
                        raise AdminCommandError(
                            _("Invalid user %(user)s on line %(line)d: All "
                              "upper-cased tokens are reserved for "
                              "permission names.",
                              user=user, line=reader.line_num))
                    old_actions = self.get_user_perms(user)
                    for action in set(actions) - set(old_actions):
                        permsys.grant_permission(user, action)
        except csv.Error as e:
            raise AdminCommandError(
                _("Cannot import from %(filename)s line %(line)d: %(error)s ",
                  filename=path_to_unicode(filename or 'stdin'),
                  line=reader.line_num, error=e))
        except IOError as e:
            raise AdminCommandError(
                _("Cannot import from %(filename)s: %(error)s",
                  filename=path_to_unicode(filename or 'stdin'),
                  error=e.strerror))
