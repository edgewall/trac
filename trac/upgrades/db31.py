# -*- coding: utf-8 -*-
#
# Copyright (C) 2014 Edgewall Software
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


def do_upgrade(env, version, cursor):
    """Move definition of default repository from [trac] repository_dir to
    [repositories] section.
    """
    backup_config_file(env, '.db31.bak')
    repository_dir = env.config.get('trac', 'repository_dir')
    if repository_dir:
        if not env.config.get('repositories', '.dir') and \
                not env.config.get('repositories', '.alias'):
            env.config.set('repositories', '.dir', repository_dir)
            env.log.info("Moved configuration options for default repository "
                         "to [repositories] section of trac.ini")
        else:
            env.log.info("[trac] repository_dir = %s discarded from "
                         "configuration because [repositories] "
                         "'.dir' or '.alias' already exists.", repository_dir)
    env.config.remove('trac', 'repository_dir')
    env.config.save()
