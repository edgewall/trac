"""ExtraPermissionsProvider

Provides a way to add arbitrary permissions to a Trac environment; which is
useful for adding new permissions to use for workflow actions.

Adding to your trac.ini:
[trac]
extra_perms = some,extra, permissions

... will add EXTRAPERM_SOME, EXTRAPERM_EXTRA, EXTRAPERM_PERMISSIONS, and
EXTRAPERM_ADMIN as permissions to the environment.
(EXTRAPERM_ADMIN is added even if no permissions are specified in the
trac.ini.)
"""
from trac.core import Component, implements
from trac.perm import IPermissionRequestor

class ExtraPermissionsProvider(Component):
    implements(IPermissionRequestor)
    def get_permission_actions(self):
        extra_perms = self.config.get('trac', 'extra_perms')
        extra_perms = [e.strip().upper() for e in extra_perms.split(',')]
        extra_perms = ['EXTRAPERM_' + e for e in extra_perms if e and e != 'ADMIN']
        all_perms = extra_perms + [('EXTRAPERM_ADMIN', extra_perms)]
        return all_perms

