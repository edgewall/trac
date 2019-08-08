# -*- coding: utf-8 -*-
#
# Copyright (C) 2007-2019 Edgewall Software
# Copyright (C) 2007 Christian Boos <cboos@edgewall.org>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/.

from fnmatch import fnmatchcase

from trac.config import Option
from trac.core import *
from trac.perm import IPermissionPolicy

revision = "$Rev$"
url = "$URL$"

class PublicWikiPolicy(Component):
    """Allow public access to some wiki pages.

    This is a sample permission policy plugin illustrating how to check
    permission on realms.

    Don't forget to integrate that plugin in the appropriate place in the
    list of permission policies:
    {{{
    [trac]
    permission_policies = PublicWikiPolicy, DefaultPermissionPolicy
    }}}

    Then you can configure which pages you want to make public:
    {{{
    [public_wiki]
    view = Public*
    modify = PublicSandbox/*
    }}}

    """

    implements(IPermissionPolicy)

    view = Option('public_wiki', 'view', 'Public*',
            """Case-sensitive glob pattern used for granting view permission on
            all Wiki pages matching it.""")

    modify = Option('public_wiki', 'modify', 'Public*',
            """Case-sensitive glob pattern used for granting modify permissions
            on all Wiki pages matching it.""")

    def check_permission(self, action, username, resource, perm):
        if resource: # fine-grained permission check
            if resource.realm == 'wiki': # wiki realm or resource
                if resource.id: # ... it's a resource
                    if action == 'WIKI_VIEW': # (think 'VIEW' here)
                        pattern = self.view
                    else:
                        pattern = self.modify
                    if fnmatchcase(resource.id, pattern):
                        return True
                else: # ... it's a realm
                    return True
                    # this policy ''may'' grant permissions on some wiki pages
        else: # coarse-grained permission check
            #
            # support for the legacy permission checks: no resource specified
            # and realm information in the action name itself.
            #
            if action.startswith('WIKI_'):
                return True
                # this policy ''may'' grant permissions on some wiki pages
