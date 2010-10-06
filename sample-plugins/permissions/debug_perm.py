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
