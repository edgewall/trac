# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2005 Edgewall Software
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

"""Management of permissions."""

from trac.config import ExtensionOption, OrderedExtensionsOption
from trac.core import *
from trac.resource import Resource
from trac.util.compat import set
from trac.util.translation import _

__all__ = ['IPermissionRequestor', 'IPermissionStore',
           'IPermissionGroupProvider', 'PermissionError', 'PermissionSystem']


class PermissionError(StandardError):
    """Insufficient permissions to complete the operation"""

    def __init__ (self, action=None, resource=None):
        StandardError.__init__(self)
        self.action = action
        self.resource = resource

    def __str__ (self):
        if self.action:
            if self.resource:
                return _('%(perm)s privileges are required to perform '
                         'this operation on %(resource)s',
                         perm=self.action, resource=self.resource)
            else:
                return _('%(perm)s privileges are required to perform '
                         'this operation', perm=self.action)
        else:
            return _('Insufficient privileges to perform this operation.')


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

    def get_users_with_permissions(self, permissions):
        """Retrieve a list of users that have any of the specified permissions.

        Users are returned as a list of usernames.
        """

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
		 policy in the chain will be used, and so on.
    
	Note that when checking a permission on a realm resource (i.e. when
	`.id` is `None`), the `IPermissionPolicy` will return:

	 * `True` if the action is by default permitted for resources in
	   that realm (the permission could still be denied for individual
	   resources)
	 * `False` if the action is by default not permitted for resources
	   in that realm (the permission could still be granted for individual
	   resources)
	 * `None` if no decision can be made without a more specific resource 

	Note that performing permission checks on realm resources may seem
	redundant for now as the action name itself contains the realm, but
	this will probably change in the future (e.g. `'VIEW' in ...`).
        """


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
        subjects = set([username])
        for provider in self.group_providers:
            subjects.update(provider.get_permission_groups(username))

        actions = set([])
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        cursor.execute("SELECT username,action FROM permission")
        rows = cursor.fetchall()
        while True:
            num_users = len(subjects)
            num_actions = len(actions)
            for user, action in rows:
                if user in subjects:
                    if action.isupper() and action not in actions:
                        actions.add(action)
                    if not action.isupper() and action not in subjects:
                        # action is actually the name of the permission group
                        # here
                        subjects.add(action)
            if num_users == len(subjects) and num_actions == len(actions):
                break
        return list(actions)

    def get_users_with_permissions(self, permissions):
        """Retrieve a list of users that have any of the specified permissions
        
        Users are returned as a list of usernames.
        """
        # get_user_permissions() takes care of the magic 'authenticated' group.
        # The optimized loop we had before didn't.  This is very inefficient,
        # but it works.
        db = self.env.get_db_cnx()
        cursor = db.cursor()
        result = set()
        users = set([u[0] for u in self.env.get_known_users()])
        for user in users:
            userperms = self.get_user_permissions(user)
            for group in permissions:
                if group in userperms:
                    result.add(user)
        return list(result)

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


class DefaultPermissionPolicy(Component):
    """Default permission policy using the IPermissionStore system."""

    implements(IPermissionPolicy)

    # IPermissionPolicy methods

    def check_permission(self, action, username, resource, perm):
        return PermissionSystem(self.env). \
               get_user_permissions(username).get(action, None)


class PermissionSystem(Component):
    """Sub-system that manages user permissions."""

    implements(IPermissionRequestor)

    requestors = ExtensionPoint(IPermissionRequestor)

    store = ExtensionOption('trac', 'permission_store', IPermissionStore,
                            'DefaultPermissionStore',
        """Name of the component implementing `IPermissionStore`, which is used
        for managing user and group permissions.""")

    policies = OrderedExtensionsOption('trac', 'permission_policies',
        IPermissionPolicy,
        'DefaultPermissionPolicy, LegacyAttachmentPolicy',
        False,
        """List of components implementing `IPermissionPolicy`, in the order in
        which they will be applied. These components manage fine-grained access
        control to Trac resources.
        Defaults to the DefaultPermissionPolicy (pre-0.11 behavior) and
        LegacyAttachmentPolicy (map ATTACHMENT_* permissions to realm specific
        ones)""")

    # Public API

    def grant_permission(self, username, action):
        """Grant the user with the given name permission to perform to specified
        action."""
        if action.isupper() and action not in self.get_actions():
            raise TracError(_('%(name)s is not a valid action.', name=action))

        self.store.grant_permission(username, action)

    def revoke_permission(self, username, action):
        """Revokes the permission of the specified user to perform an action."""
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

    def get_users_with_permission(self, permission):
        """Return all users that have the specified permission.
        
        Users are returned as a list of user names.
        """
        # this should probably be cached
        parent_map = {}
        for requestor in self.requestors:
            for action in requestor.get_permission_actions():
                for child in action[1]:
                    parent_map.setdefault(child, []).append(action[0])

        satisfying_perms = {}
        def _append_with_parents(action):
            if action in satisfying_perms:
                return # avoid unneccesary work and infinite loops
            satisfying_perms[action] = True
            if action in parent_map:
                map(_append_with_parents, parent_map[action])
        _append_with_parents(permission)

        return self.store.get_users_with_permissions(satisfying_perms.keys())

    def expand_actions(self, actions):
        """Helper method for expanding all meta actions."""
        meta = {}
        for requestor in self.requestors:
            for m in requestor.get_permission_actions():
                if isinstance(m, tuple):
                    meta[m[0]] = m[1]
        expanded_actions = set(actions)

        def expand_action(action):
            actions = meta.get(action, [])
            expanded_actions.update(actions)
            [expand_action(a) for a in actions]

        [expand_action(a) for a in actions]
        return expanded_actions

    def check_permission(self, action, username=None, resource=None, perm=None):
        """Return True if permission to perform action for the given resource
        is allowed."""
        if username is None:
            username = 'anonymous'
        for policy in self.policies:
            decision = policy.check_permission(action, username, resource,
                                               perm)
            if decision is not None:
                if not decision:
                    self.log.debug("%s denies %s performing %s on %r" %
                                   (policy.__class__.__name__, username,
                                    action, resource))
                return decision
        self.log.debug("No policy allowed %s performing %s on %r" %
                       (username, action, resource))
        return False

    # IPermissionRequestor methods

    def get_permission_actions(self):
        """Implement the global `TRAC_ADMIN` meta permission.
        
        Implements also the `EMAIL_VIEW` permission which allows for
        showing email addresses even if `[trac] show_email_addresses`
        is `false`.
        """
        actions = ['EMAIL_VIEW']
        for requestor in [r for r in self.requestors if r is not self]:
            for action in requestor.get_permission_actions():
                if isinstance(action, tuple):
                    actions.append(action[0])
                else:
                    actions.append(action)
        return [('TRAC_ADMIN', actions), 'EMAIL_VIEW']


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

    def __init__(self, env, username=None, resource=None, cache=None,
                 groups=None):
        self.env = env
        self.username = username or 'anonymous'
        self._resource = resource
        self._cache = cache is not None and cache or {}

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
        resource = Resource(realm_or_resource, id, version)
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
        if action == action.lower(): # 'view' -> '<REALM>_VIEW' for now
            action = (resource.realm+'_'+action).upper()
        key = (self.username, hash(resource), action)
        try:
            return self._cache[key]
        except KeyError:
            perm = self
            if resource is not self._resource:
                perm = PermissionCache(self.env, self.username, resource,
                                       self._cache)
            decision = PermissionSystem(self.env). \
                       check_permission(action, perm.username, resource, perm)
            self._cache[key] = decision
            return decision
    __contains__ = has_permission

    def require(self, action, realm_or_resource=None, id=False, version=False):
        resource = self._normalize_resource(realm_or_resource, id, version)
        if not self._has_permission(action, resource):
            raise PermissionError(action, resource)
    assert_permission = require

    def permissions(self):
        """Deprecated (but still used by the HDF compatibility layer)"""
        self.env.log.warning('perm.permissions() is deprecated and '
                             'is only present for HDF compatibility')
        perm = PermissionSystem(self.env)
        actions = perm.get_user_permissions(self.username)
        return [action for action in actions if action in self]
