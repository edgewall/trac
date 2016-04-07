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
from trac.versioncontrol.api import DbRepositoryProvider, RepositoryManager


def do_upgrade(env, version, cursor):
    """Replace list of repositories in [trac] repository_sync_per_request
    with boolean values [repositories] <repos>.sync_per_request.
    """
    repos_sync_per_request = \
        env.config.getlist('trac', 'repository_sync_per_request')
    backup_config_file(env, '.db32.bak')
    if repos_sync_per_request:
        rm = RepositoryManager(env)
        db_provider = env[DbRepositoryProvider]

        trac_ini_repo_names = []
        for name, _ in rm.get_repositories():
            trac_ini_repo_names.append(name)
        for repos in rm.get_all_repositories().values():
            sync_per_request = (repos['name'] or '(default)') \
                               in repos_sync_per_request
            if sync_per_request:
                if repos['name'] in trac_ini_repo_names:
                    env.config.set('repositories',
                                   repos['name'] + '.sync_per_request',
                                   'true')
                else:
                    changes = {'sync_per_request': sync_per_request}
                    db_provider.modify_repository(repos['name'], changes)
        env.log.info("Enabled sync_per_request for the following "
                     "repositories: %s", ', '.join(repos_sync_per_request))

    env.config.remove('trac', 'repository_sync_per_request')
    env.config.save()
    env.log.info("Removed [trac] repository_sync_per_request option")
