# -*- coding: utf-8 -*-
#
# Copyright (C) 2015 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import os

from trac.upgrades import backup_config_file


def do_upgrade(env, version, cursor):
    """Change [authz_policy] authz_file to be relative to the `conf`
    directory.
    """
    authz_file = env.config.get('authz_policy', 'authz_file')
    if authz_file and not os.path.isabs(authz_file):
        parts = os.path.split(authz_file)
        if len(parts) == 2 and parts[0] == 'conf':
            env.config.set('authz_policy', 'authz_file', parts[1])
            backup_config_file(env, '.db36.bak')
            env.config.save()
