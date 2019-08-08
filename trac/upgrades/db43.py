# -*- coding: utf-8 -*-
#
# Copyright (C) 2017-2019 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/.

from trac.upgrades import backup_config_file
from trac.util.text import printout
from trac.util.translation import _


_old_default = ['ReadonlyWikiPolicy', 'DefaultPermissionPolicy',
                'LegacyAttachmentPolicy']
_new_default = ['DefaultWikiPolicy', 'DefaultTicketPolicy',
                'DefaultPermissionPolicy', 'LegacyAttachmentPolicy']


def do_upgrade(env, version, cursor):
    """Automatically append DefaultWikiPolicy and DefaultTicketPolicy
    if permission_policies is the default value. Otherwise, echo a message
    about the need to manually add DefaultWikiPolicy and DefaultTicketPolicy
    to the list of permission_policies.
    """

    policies = env.config.getlist('trac', 'permission_policies')
    if policies == _old_default:
        backup_config_file(env, '.db43.bak')
        env.config.set('trac', 'permission_policies', ', '.join(_new_default))
        env.config.save()
        env.log.info("Enabled DefaultWikiPolicy and DefaultTicketPolicy.")
    else:
        print_upgrade_msg = False
        if 'DefaultWikiPolicy' not in policies:
            env.log.info("DefaultWikiPolicy must be manually enabled.")
            # TRANSLATOR: Wrap message to 80 columns
            printout(_("""\
Notice: To enable the default permission policy for the *wiki* system,
trac.ini must be manually edited to add DefaultWikiPolicy to the list
of permission_policies in the [trac] section.
"""))
            print_upgrade_msg = True
        else:
            env.log.info("DefaultWikiPolicy already enabled.")
        if 'DefaultTicketPolicy' not in policies:
            env.log.info("DefaultTicketPolicy must be manually enabled.")
            # TRANSLATOR: Wrap message to 80 columns
            printout(_("""\
Notice: To enable the default permission policy for the *ticket* system,
trac.ini must be manually edited to add DefaultTicketPolicy to the list
of permission_policies in the [trac] section.
"""))
            print_upgrade_msg = True
        else:
            env.log.info("DefaultTicketPolicy already enabled.")
        if print_upgrade_msg:
            printout(_("""\
For more details see: https://trac.edgewall.org/wiki/TracUpgrade
"""))
