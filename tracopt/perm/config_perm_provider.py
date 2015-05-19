# -*- coding: utf-8 -*-
#
# Copyright (C) 2009 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

from trac.core import *
from trac.perm import IPermissionRequestor


class ExtraPermissionsProvider(Component):
    """Extra permission provider.
    
    This component provides a way to add arbitrary permissions to a Trac
    environment. This can be useful for adding new permissions to use for
    workflow actions, for example.
    
    To add new permissions, create a new section `[extra-permissions]` in
    your `trac.ini`. Every entry in that section defines a meta-permission
    and a comma-separated list of permissions. For example:
    {{{
    [extra-permissions]
    extra_admin = extra_view, extra_modify, extra_delete
    }}}
    This entry will define three new permissions `EXTRA_VIEW`, `EXTRA_MODIFY`
    and `EXTRA_DELETE`, as well as a meta-permissions `EXTRA_ADMIN` that
    grants all three permissions.
    
    If you don't want a meta-permission, start the meta-name with an
    underscore (`_`):
    {{{
    [extra-permissions]
    _perms = extra_view, extra_modify
    }}}
    """
    implements(IPermissionRequestor)
    
    def get_permission_actions(self):
        permissions = {}
        for meta, perms in self.config.options('extra-permissions'):
            perms = [each.strip().upper() for each in perms.split(',')]
            for perm in perms:
                permissions.setdefault(perm, [])
            meta = meta.strip().upper()
            if meta and not meta.startswith('_'):
                permissions.setdefault(meta, []).extend(perms)
        return [v and (k, v) or k for k, v in permissions.iteritems()]
