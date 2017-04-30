# -*- coding: utf-8 -*-
#
# Copyright (C) 2007-2009 Edgewall Software
# Copyright (C) 2007 Alec Thomas <alec@swapoff.org>
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
# Author: Alec Thomas <alec@swapoff.org>

import os
from fnmatch import fnmatchcase
from itertools import groupby

from trac.config import ConfigurationError, ParsingError, PathOption, \
                        UnicodeConfigParser
from trac.core import Component, implements
from trac.perm import IPermissionPolicy, PermissionSystem
from trac.util import to_list
from trac.util.text import exception_to_unicode


class AuthzPolicy(Component):
    """Permission policy using an authz-like configuration file.

    Refer to SVN documentation for syntax of the authz file. Groups are
    supported.

    As the fine-grained permissions brought by this permission policy are
    often used in complement of the other permission policies (like the
    `DefaultPermissionPolicy`), there's no need to redefine all the
    permissions here. Only additional rights or restrictions should be added.

    === Installation ===
    Enabling this policy requires listing it in `trac.ini`::

      {{{
      [trac]
      permission_policies = AuthzPolicy, DefaultPermissionPolicy

      [authz_policy]
      authz_file = conf/authzpolicy.conf
      }}}

    This means that the `AuthzPolicy` permissions will be checked first, and
    only if no rule is found will the `DefaultPermissionPolicy` be used.


    === Configuration ===
    The `authzpolicy.conf` file is a `.ini` style configuration file.

     - Each section of the config is a glob pattern used to match against a
       Trac resource descriptor. These descriptors are in the form::

         {{{
         <realm>:<id>@<version>[/<realm>:<id>@<version> ...]
         }}}

       Resources are ordered left to right, from parent to child. If any
       component is inapplicable, `*` is substituted. If the version pattern is
       not specified explicitely, all versions (`@*`) is added implicitly

       Example: Match the WikiStart page::

         {{{
         [wiki:*]
         [wiki:WikiStart*]
         [wiki:WikiStart@*]
         [wiki:WikiStart]
         }}}

       Example: Match the attachment
       ``wiki:WikiStart@117/attachment/FOO.JPG@*`` on WikiStart::

         {{{
         [wiki:*]
         [wiki:WikiStart*]
         [wiki:WikiStart@*]
         [wiki:WikiStart@*/attachment/*]
         [wiki:WikiStart@117/attachment/FOO.JPG]
         }}}

     - Sections are checked against the current Trac resource '''IN ORDER''' of
       appearance in the configuration file. '''ORDER IS CRITICAL'''.

     - Once a section matches, the current username is matched, '''IN ORDER''',
       against the keys of the section. If a key is prefixed with a `@`, it is
       treated as a group. If a key is prefixed with a `!`, the permission is
       denied rather than granted. The username will match any of 'anonymous',
       'authenticated', <username> or '*', using normal Trac permission rules.

    Example configuration::

      {{{
      [groups]
      administrators = athomas

      [*/attachment:*]
      * = WIKI_VIEW, TICKET_VIEW

      [wiki:WikiStart@*]
      @administrators = WIKI_ADMIN
      anonymous = WIKI_VIEW
      * = WIKI_VIEW

      # Deny access to page templates
      [wiki:PageTemplates/*]
      * =

      # Match everything else
      [*]
      @administrators = TRAC_ADMIN
      anonymous = BROWSER_VIEW, CHANGESET_VIEW, FILE_VIEW, LOG_VIEW,
          MILESTONE_VIEW, POLL_VIEW, REPORT_SQL_VIEW, REPORT_VIEW,
          ROADMAP_VIEW, SEARCH_VIEW, TICKET_CREATE, TICKET_MODIFY,
          TICKET_VIEW, TIMELINE_VIEW,
          WIKI_CREATE, WIKI_MODIFY, WIKI_VIEW
      # Give authenticated users some extra permissions
      authenticated = REPO_SEARCH, XML_RPC
      }}}

    """
    implements(IPermissionPolicy)

    authz_file = PathOption('authz_policy', 'authz_file', '',
                            "Location of authz policy configuration file. "
                            "Non-absolute paths are relative to the "
                            "Environment `conf` directory.")

    def __init__(self):
        self.authz = None
        self.authz_mtime = None
        self.groups_by_user = {}

    # IPermissionPolicy methods

    def check_permission(self, action, username, resource, perm):
        if not self.authz_mtime or \
                os.path.getmtime(self.authz_file) != self.authz_mtime:
            self.parse_authz()
        resource_key = self.normalise_resource(resource)
        self.log.debug('Checking %s on %s', action, resource_key)
        permissions = self.authz_permissions(resource_key, username)
        if permissions is None:
            return None                 # no match, can't decide
        elif permissions == []:
            return False                # all actions are denied

        # FIXME: expand all permissions once for all
        ps = PermissionSystem(self.env)
        for deny, perms in groupby(permissions,
                                   key=lambda p: p.startswith('!')):
            if deny and action in ps.expand_actions(p[1:] for p in perms):
                return False            # action is explicitly denied
            elif action in ps.expand_actions(perms):
                return True             # action is explicitly granted

        return None                     # no match for action, can't decide

    # Internal methods

    def parse_authz(self):
        self.log.debug("Parsing authz security policy %s",
                       self.authz_file)

        if not self.authz_file:
            self.log.error("The `[authz_policy] authz_file` configuration "
                           "option in trac.ini is empty or not defined.")
            raise ConfigurationError()
        try:
            self.authz_mtime = os.path.getmtime(self.authz_file)
        except OSError as e:
            self.log.error("Error parsing authz permission policy file: %s",
                           exception_to_unicode(e))
            raise ConfigurationError()

        self.authz = UnicodeConfigParser(ignorecase_option=False)
        try:
            self.authz.read(self.authz_file)
        except ParsingError as e:
            self.log.error("Error parsing authz permission policy file: %s",
                           exception_to_unicode(e))
            raise ConfigurationError()
        groups = {}
        if self.authz.has_section('groups'):
            for group, users in self.authz.items('groups'):
                groups[group] = to_list(users)

        self.groups_by_user = {}

        def add_items(group, items):
            for item in items:
                if item.startswith('@'):
                    add_items(group, groups[item[1:]])
                else:
                    self.groups_by_user.setdefault(item, set()).add(group)

        for group, users in groups.iteritems():
            add_items('@' + group, users)

        all_actions = PermissionSystem(self.env).get_actions()
        for section in self.authz.sections():
            if section == 'groups':
                continue
            for _, actions in self.authz.items(section):
                for action in to_list(actions):
                    if action not in all_actions:
                        self.log.warning("The action %s in the [%s] section "
                                         "of %s is not a valid action.",
                                         action, section,
                                         os.path.basename(self.authz_file))

    def normalise_resource(self, resource):
        def to_descriptor(resource):
            id = resource.id
            return '%s:%s@%s' % (resource.realm or '*',
                                 id if id is not None else '*',
                                 resource.version or '*')

        def flatten(resource):
            if not resource:
                return ['*:*@*']
            descriptor = to_descriptor(resource)
            if not resource.realm and resource.id is None:
                return [descriptor]
            # XXX Due to the mixed functionality in resource we can end up with
            # ticket, ticket:1, ticket:1@10. This code naively collapses all
            # subsets of the parent resource into one. eg. ticket:1@10
            parent = resource.parent
            while parent and resource.realm == parent.realm:
                parent = parent.parent
            if parent:
                return flatten(parent) + [descriptor]
            else:
                return [descriptor]

        return '/'.join(flatten(resource))

    def authz_permissions(self, resource_key, username):
        # TODO: Handle permission negation in sections. eg. "if in this
        # ticket, remove TICKET_MODIFY"
        if username and username != 'anonymous':
            valid_users = ['*', 'authenticated', 'anonymous', username]
        else:
            valid_users = ['*', 'anonymous']
        for resource_section in [a for a in self.authz.sections()
                                   if a != 'groups']:
            resource_glob = resource_section
            if '@' not in resource_glob:
                resource_glob += '@*'

            if fnmatchcase(resource_key, resource_glob):
                for who, permissions in self.authz.items(resource_section):
                    permissions = to_list(permissions)
                    if who in valid_users or \
                            who in self.groups_by_user.get(username, []):
                        self.log.debug("%s matched section %s for user %s",
                                       resource_key, resource_glob, username)
                        if isinstance(permissions, basestring):
                            return [permissions]
                        else:
                            return permissions
        return None
