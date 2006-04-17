# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2005 Edgewall Software
# Copyright (C) 2003-2004 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://projects.edgewall.com/trac/.
#
# Author: Jonas Borgström <jonas@edgewall.com>
#         Christopher Lenz <cmlenz@gmx.de>

"""Management of permissions."""

from trac.config import ExtensionOption
from trac.core import *

__all__ = ['IPermissionRequestor', 'IPermissionStore',
           'IPermissionGroupProvider', 'PermissionError', 'PermissionSystem']

class PermissionError(StandardError):
    """Insufficient permissions to complete the operation"""

    def __init__ (self, action):
        StandardError.__init__(self)
        self.action = action

    def __str__ (self):
        return '%s privileges are required to perform this operation' % self.action


class IPermissionRequestor(Interface):
    """Extension point interface for components that define actions."""

    def get_permission_actions():
        """Return a list of actions defined by this component.
        
        The items in the list may either be simple strings, or
        `(string, sequence)` tuples. The latter are considered to be "meta
        permissions" that group several simple actions under one name for
        convenience.
        """


class IPermissionStore(Interface):
    """Extension point interface for components that provide storage and
    management of permissions."""

    def get_user_permissions(username):
        """Return all permissions for the user with the specified name.
        
        The permissions are returned as a dictionary where the key is the name
        of the permission, and the value is either `True` for granted
        permissions or `False` for explicitly denied permissions."""

    def get_all_permissions():
        """Return all permissions for all users.

        The permissions are returned as a list of (subject, action)
        formatted tuples."""

    def grant_permission(username, action):
        """Grant a user permission to perform an action."""

    def revoke_permission(username, action):
        """Revokes the permission of the given user to perform an action."""


class IPermissionGroupProvider(Interface):
    """Extension point interface for components that provide information about
    user groups.
    """

    def get_permission_groups(username):
        """Return a list of names of the groups that the user with the specified
        name is a member of."""


class DefaultPermissionStore(Component):
    """Default implementation of permission storage and simple group management.
    
    This component uses the `PERMISSION` table in the database to store both
    permissions and groups.
    """
    implements(IPermissionStore)

    group_providers = ExtensionPoint(IPermissionGroupProvider)

    def get_user_permissions(self, username):
        """Retrieve the permissions for the given user and return them in a
        dictionary.
        
        The permissions are stored in the database as (username, action)
        records. There's simple support for groups by using lowercase names for
        the action column: such a record represents a group and not an actual
        permission, and declares that the user is part of that group.
        """
        subjects = [username]
        for provider in self.group_providers:
            subjects += list(provider.get_permission_groups(username))

        actions = []
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT username,action FROM permission")
        rows = cursor.fetchall()
        while True:
            num_users = len(subjects)
            num_actions = len(actions)
            for user, action in rows:
                if user in subjects:
                    if not action.islower() and action not in actions:
                        actions.append(action)
                    if action.islower() and action not in subjects:
                        # action is actually the name of the permission group
                        # here
                        subjects.append(action)
            if num_users == len(subjects) and num_actions == len(actions):
                break
        return [action for action in actions if not action.islower()]

    def get_all_permissions(self):
        """Return all permissions for all users.

        The permissions are returned as a list of (subject, action)
        formatted tuples."""
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT username,action FROM permission")
        return [(row[0], row[1]) for row in cursor]

    def grant_permission(self, username, action):
        """Grants a user the permission to perform the specified action."""
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("INSERT INTO permission VALUES (%s, %s)",
                       (username, action))
        self.log.info('Granted permission for %s to %s' % (action, username))
        db.commit()

    def revoke_permission(self, username, action):
        """Revokes a users' permission to perform the specified action."""
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("DELETE FROM permission WHERE username=%s AND action=%s",
                       (username, action))
        self.log.info('Revoked permission for %s to %s' % (action, username))
        db.commit()


class DefaultPermissionGroupProvider(Component):
    """Provides the basic builtin permission groups 'anonymous' and
    'authenticated'."""

    implements(IPermissionGroupProvider)

    def get_permission_groups(self, username):
        groups = ['anonymous']
        if username and username != 'anonymous':
            groups.append('authenticated')
        return groups


class PermissionSystem(Component):
    """Sub-system that manages user permissions."""

    implements(IPermissionRequestor)

    requestors = ExtensionPoint(IPermissionRequestor)

    store = ExtensionOption('trac', 'permission_store', IPermissionStore,
                            'DefaultPermissionStore',
        """Name of the component implementing `IPermissionStore`, which is used
        for managing user and group permissions.""")

    # Public API

    def grant_permission(self, username, action):
        """Grant the user with the given name permission to perform to specified
        action."""
        if action.isupper() and action not in self.get_actions():
            raise TracError, '%s is not a valid action.' % action

        self.store.grant_permission(username, action)

    def revoke_permission(self, username, action):
        """Revokes the permission of the specified user to perform an action."""
        # TODO: Validate that this permission does in fact exist
        if action.isupper() and action not in self.get_actions():
            raise TracError, '%s is not a valid action.' % action

        self.store.revoke_permission(username, action)

    def get_actions(self):
        actions = []
        for requestor in self.requestors:
            for action in requestor.get_permission_actions():
                if isinstance(action, tuple):
                    actions.append(action[0])
                else:
                    actions.append(action)
        return actions

    def get_user_permissions(self, username=None):
        """Return the permissions of the specified user.
        
        The return value is a dictionary containing all the actions as keys, and
        a boolean value. `True` means that the permission is granted, `False`
        means the permission is denied."""
        actions = []
        for requestor in self.requestors:
            actions += list(requestor.get_permission_actions())
        permissions = {}
        if username:
            # Return all permissions that the given user has
            meta = {}
            for action in actions:
                if isinstance(action, tuple):
                    name, value = action
                    meta[name] = value
            def _expand_meta(action):
                permissions[action] = True
                if meta.has_key(action):
                    [_expand_meta(perm) for perm in meta[action]]
            for perm in self.store.get_user_permissions(username):
                _expand_meta(perm)
        else:
            # Return all permissions available in the system
            for action in actions:
                if isinstance(action, tuple):
                    permissions[action[0]] = True
                else:
                    permissions[action] = True
        return permissions

    def get_all_permissions(self):
        """Return all permissions for all users.

        The permissions are returned as a list of (subject, action)
        formatted tuples."""
        return self.store.get_all_permissions()

    # IPermissionRequestor methods

    def get_permission_actions(self):
        """Implement the global `TRAC_ADMIN` meta permission."""
        actions = []
        for requestor in [r for r in self.requestors if r is not self]:
            for action in requestor.get_permission_actions():
                if isinstance(action, tuple):
                    actions.append(action[0])
                else:
                    actions.append(action)
        return [('TRAC_ADMIN', actions)]


class PermissionCache(object):
    """Cache that maintains the permissions of a single user."""

    def __init__(self, env, username):
        self.perms = PermissionSystem(env).get_user_permissions(username)

    def has_permission(self, action):
        return self.perms.has_key(action)

    def assert_permission(self, action):
        if not self.perms.has_key(action):
            raise PermissionError(action)

    def permissions(self):
        return self.perms.keys()


class NoPermissionCache(object):
    """Permission cache for ''anonymous requests''."""

    def has_permission(self, action):
        return False

    def assert_permission(self, action):
        raise PermissionError(action)

    def permissions(self):
        return []
