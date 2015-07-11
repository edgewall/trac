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

from trac.upgrades import backup_config_file


def do_upgrade(env, ver, cursor):
    """Move options from [trac] section to more appropriately-named sections.
    """
    config = env.config

    config.set('svn', 'authz_file',
               config.get('trac', 'authz_file'))
    config.set('svn', 'authz_module_name',
               config.get('trac', 'authz_module_name'))
    config.set('versioncontrol', 'default_repository_type',
               config.get('trac', 'repository_type', 'svn'))

    config.remove('trac', 'authz_file')
    config.remove('trac', 'authz_module_name')
    config.remove('trac', 'repository_type')
    backup_config_file(env, '.db39.bak')
    config.save()
