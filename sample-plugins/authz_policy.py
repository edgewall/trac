# -*- coding: utf-8 -*-
#
# Copyright (C) 2007 Edgewall Software
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


"""Permission policy enforcement through an authz-like configuration file.
Refer to SVN documentation for syntax of the authz file. Groups are supported.

Note that this plugin requires the `configobj` package:

    http://www.voidspace.org.uk/python/configobj.html
    
You should be able to install it by doing a simple `easy_install configobj`


Enabling this policy requires listing it in the trac.ini:

[trac]
permission_policies = AuthzPolicy, DefaultPermissionPolicy

[authz_policy]
authz_file = conf/authzpolicy.conf


This means that the AuthzPolicy permissions will be checked first, and only
if no rule is found will the DefaultPermissionPolicy be used.

The authzpolicy.conf file is a .ini style configuration file.

 - Each section of the config is a glob pattern used to match against a Trac
resource descriptor. These descriptors are in the form:

     <realm>:<id>@<version>[/<realm>:<id>@<version> ...]

   Resources are ordered left to right, from parent to child.
   If any component is inapplicable, * is substituted.

   e.g. An attachment on WikiStart:

     wiki:WikiStart@117/attachment/FOO.JPG@*

   any of the following sections would match it:

     [wiki:*]
     [wiki:WikiStart*]
     [wiki:WikiStart@*]
     [wiki:WikiStart@*/attachment/*]

   but be careful, not this one:

     [wiki:WikiStart@117/attachment/FOO.JPG]

   as the above won't match the @ part in the attachment resource descriptor.


 - Sections are checked against the current Trac resource **IN ORDER** of
   appearance in the configuration file. ORDER IS CRITICAL.

 - Once a section matches, the current username is matched, **IN ORDER**,
   against the keys of the section. If a key is prefixed with a @, it is
   treated as a group. The username will match any of 'anonymous',
   'authenticated', <username> or '*', using normal Trac permission rules.

Example configuration:

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
    anonymous = BROWSER_VIEW, CHANGESET_VIEW, FILE_VIEW, LOG_VIEW, MILESTONE_VIEW, POLL_VIEW, REPORT_SQL_VIEW, REPORT_VIEW, ROADMAP_VIEW, SEARCH_VIEW, TICKET_CREATE, TICKET_MODIFY, TICKET_VIEW, TIMELINE_VIEW, WIKI_CREATE, WIKI_MODIFY, WIKI_VIEW
    # Give authenticated users some extra permissions
    authenticated = REPO_SEARCH, XML_RPC


"""

import os
from fnmatch import fnmatch
from trac.core import *
from trac.config import Option
from trac.util.compat import set
from trac.perm import PermissionSystem, IPermissionPolicy
from configobj import ConfigObj


class AuthzPolicy(Component):
    implements(IPermissionPolicy)

    authz_file = Option('authz_policy', 'authz_file', None,
                        'Location of authz policy configuration file.')

    authz = None
    authz_mtime = None

    # IPermissionPolicy methods
    
    def check_permission(self, action, username, resource, perm):
        if self.authz_file and not self.authz_mtime or \
                os.path.getmtime(self.get_authz_file()) > self.authz_mtime:
            self.parse_authz()
        resource_key = self.normalise_resource(resource)
        self.env.log.debug('Checking %s on %s', action, resource_key)
        permissions = self.authz_permissions(resource_key, username)
        if permissions is None:
            return None
        elif permissions:
            permissions = PermissionSystem(self.env).expand_actions(permissions)
        return action in permissions

    # Internal methods

    def get_authz_file(self):
        f = self.authz_file
        return os.path.isabs(f) and f or os.path.join(self.env.path, f)

    def parse_authz(self):
        self.env.log.debug('Parsing authz security policy %s' %
                           self.get_authz_file())
        self.authz = ConfigObj(self.get_authz_file())
        self.groups_by_user = {}
        for group, users in self.authz.get('groups', {}).iteritems():
            if isinstance(users, basestring):
                users = [users]
            for user in users:
                self.groups_by_user.setdefault(user, set()).add('@' + group)
        self.authz_mtime = os.path.getmtime(self.get_authz_file())

    def normalise_resource(self, resource):
        def flatten(resource):
            if not resource or not (resource.realm or resource.id):
                return []
            # XXX Due to the mixed functionality in resource we can end up with
            # ticket, ticket:1, ticket:1@10. This code naively collapses all
            # subsets of the parent resource into one. eg. ticket:1@10
            parent = resource.parent
            while parent and (resource.realm == parent.realm or \
                    (resource.realm == parent.realm and resource.id == parent.id)):
                parent = parent.parent
            if parent:
                parent = flatten(parent)
            else:
                parent = []
            return parent + ['%s:%s@%s' % (resource.realm or '*',
                                           resource.id or '*',
                                           resource.version or '*')]
        return '/'.join(flatten(resource))

    def authz_permissions(self, resource_key, username):
        # TODO: Handle permission negation in sections. eg. "if in this
        # ticket, remove TICKET_MODIFY"
        valid_users = ['*', 'anonymous']
        if username and username != 'anonymous':
            valid_users += ['authenticated', username]
        for resource_glob in [a for a in self.authz.sections if a != 'groups']:
            if fnmatch(resource_key, resource_glob):
                section = self.authz[resource_glob]
                for who, permissions in section.iteritems():
                    if who in valid_users or \
                            who in self.groups_by_user.get(username, []):
                        #self.env.log.debug('%s matched section %s' % (resource_key, resource_glob))
                        if isinstance(permissions, basestring):
                            return [permissions]
                        else:
                            return permissions
        return None
