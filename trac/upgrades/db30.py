# -*- coding: utf-8 -*-
#
# Copyright (C) 2013 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

from trac.upgrades import backup_config_file
from trac.util.text import printout
from trac.util.translation import _


_old_default = ['DefaultPermissionPolicy', 'LegacyAttachmentPolicy']
_new_default = ['ReadonlyWikiPolicy'] + _old_default


def do_upgrade(env, version, cursor):
    """Automatically append ReadonlyWikiPolicy if permission_policies is
    the default value. Otherwise, echo a message about the need to manually
    add ReadonlyWikiPolicy to the list of permission_policies."""

    policies = [p.strip() for p in
                env.config.getlist('trac', 'permission_policies')]
    if policies == _old_default:
        backup_config_file(env, '.db30.bak')
        env.config.set('trac', 'permission_policies', ', '.join(_new_default))
        env.config.save()
        env.log.info("Enabled ReadonlyWikiPolicy.")
    elif 'ReadonlyWikiPolicy' not in policies:
        env.log.info("ReadonlyWikiPolicy must be manually enabled.")
        # TRANSLATOR: Wrap message to 80 columns
        printout(_("""\
Notice: To enable the readonly wiki attribute, trac.ini must be manually
edited to add ReadonlyWikiPolicy to the list of permission_policies in
the [trac] section.

For more details see: http://trac.edgewall.org/wiki/ReadonlyWikiPolicy
"""))
    else:
        env.log.info("ReadonlyWikiPolicy already enabled.")
