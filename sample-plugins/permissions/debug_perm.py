# -*- coding: utf-8 -*-
#
# Copyright (C) 2007-2018 Edgewall Software
# Copyright (C) 2007 Christian Boos <cboos@edgewall.org>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

from trac.core import *
from trac.perm import IPermissionPolicy, PermissionCache
from trac.resource import Resource

revision = "$Rev$"
url = "$URL$"

class DebugPolicy(Component):
    """Verify the well-formedness of the permission checks.

    **This plugin is only useful for Trac Development.**

    Once this plugin is enabled, you'll have to insert it at the appropriate
    place in your list of permission policies, e.g.
    {{{
    [trac]
    permission_policies = DebugPolicy, SecurityTicketsPolicy, AuthzPolicy,
                          DefaultPermissionPolicy, LegacyAttachmentPolicy
    }}}
    """

    implements(IPermissionPolicy)

    # IPermissionPolicy methods

    def check_permission(self, action, username, resource, perm):
        if resource:
            assert resource is None or isinstance(resource, Resource)
        assert isinstance(perm, PermissionCache)
        self.log.info("does '%s' have %s on %r?", username, action, resource)
