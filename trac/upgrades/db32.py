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
from tracopt.versioncontrol.git.git_fs import GitwebProjectsRepositoryProvider


def do_upgrade(env, version, cursor):
    """Replace list of repositories in [trac] repository_sync_per_request
    with boolean values [repositories] <repos>.sync_per_request and a list
    of repositories in [gitweb-repositories] sync_per_request. Move and
    rename the Gitweb configuration options from the [git] section to
    the [gitweb-repositories] section.
    """
    backup_config_file(env, '.db32.bak')
    repos_sync_per_request = \
        env.config.getlist('trac', 'repository_sync_per_request', '(default)')

    for suffix in ('base', 'list', 'url'):
        option_name = 'projects_' + suffix
        env.config.set('gitweb-repositories', option_name,
                       env.config.get('git', option_name))
        env.config.remove('git', option_name)
        env.log.info("Moved [git] %s -> [gitweb-repositories] %s",
                     option_name, option_name)

    rm = RepositoryManager(env)
    if repos_sync_per_request:
        for name, _ in rm.get_repositories():
            sync_per_request = (name or '(default)') in repos_sync_per_request
            if sync_per_request:
                env.config.set('repositories', name + '.sync_per_request',
                               'true')
                env.log.info("Enabled sync_per_request for %s", name)

        gwrp = GitwebProjectsRepositoryProvider(env)
        gitweb_repo_names = [name for name, _ in gwrp.get_repositories()]
        sync_per_request = \
            ', '.join(set(gitweb_repo_names) & set(repos_sync_per_request))
        env.config.set('gitweb-repositories', 'sync_per_request',
                       sync_per_request)
        env.log.info("Enabled sync_per_request for %s", sync_per_request)

        db_provider = DbRepositoryProvider(env)
        for name, _ in db_provider.get_repositories():
            sync_per_request = (name or '(default)') in repos_sync_per_request
            changes = {'sync_per_request': sync_per_request}
            db_provider.modify_repository(name, changes)
            if sync_per_request:
                env.log.info("Enabled sync_per_request for %s", name)

    env.config.remove('trac', 'repository_sync_per_request')
    env.log.info("Removed [trac] repository_sync_per_request option")
    env.config.save()
    rm.reload_repositories()
