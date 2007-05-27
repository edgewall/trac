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

Each section of the config is a glob to match against a Trac resource
descriptor. These descriptors are in the form:

    <realm>:<id>@<version>[/<realm>:<id>@<version> ...]

Resources are ordered left to right, from parent to child. If any component is
inapplicable, * is substituted.

eg. An attachment on WikiStart:

    wiki:WikiStart@117/attachment/FOO.JPG@*

or the Wiki module as a whole:

    wiki:*@*


Sections are checked against the current Trac resource **IN ORDER** of
appearance in the configuration file. ORDER IS CRITICAL.

Once a section matches, the current username is matched, **IN ORDER**, against
the keys of the section. If a key is prefixed with a @ it is treated as a
group. The username will match any of 'anonymous', 'authenticated', <username>
or '*', using normal Trac permission rules.

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
    def check_permission(self, username, action, context):
        if self.authz_file and not self.authz_mtime or \
                os.path.getmtime(self.authz_file) > self.authz_mtime:
            self.parse_authz()
        ctx_key = self.flatten_context(context)
        permissions = self.authz_permissions(ctx_key, username)
        if permissions is None:
            return None
        elif permissions:
            permissions = PermissionSystem(self.env).expand_actions(permissions)
        return action in permissions

    # Internal methods
    def parse_authz(self):
        self.env.log.debug('Parsing authz security policy %s' % self.authz_file)
        self.authz = ConfigObj(self.authz_file)
        self.groups_by_user = {}
        for group, users in self.authz.get('groups', {}).iteritems():
            if isinstance(users, basestring):
                users = [users]
            for user in users:
                self.groups_by_user.setdefault(user, set()).add('@' + group)
        self.authz_mtime = os.path.getmtime(self.authz_file)

    def flatten_context(self, context):
        def flatten(context):
            # XXX Use of root realm is inconsistent. Sometimes it is the parent
            # object, other times not. XXX
            if not context or not (context.realm or context.id):
                return []
            parent = flatten(context.parent)
            return parent + ['%s:%s@%s' % (context.realm or '*',
                                           context.id or '*',
                                           context.version or '*')]
        return '/'.join(flatten(context))

    def authz_permissions(self, ctx_key, username):
        valid_users = ['*', 'anonymous']
        if username and username != 'anonymous':
            valid_users += ['authenticated', username]
        for ctx_glob in [a for a in self.authz.sections if a != 'groups']:
            if fnmatch(ctx_key, ctx_glob):
                section = self.authz[ctx_glob]
                for who, permissions in section.iteritems():
                    if who in valid_users or \
                            who in self.groups_by_user.get(username, []):
                        #self.env.log.debug('%s matched section %s' % (ctx_key, ctx_glob))
                        if isinstance(permissions, basestring):
                            return [permissions]
                        else:
                            return permissions
        return None
