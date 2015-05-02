# -*- coding: utf-8 -*-
#
# Copyright (C) 2015 Edgewall Software
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
from trac.web.chrome import default_mainnav_order, default_metanav_order


def do_upgrade(env, version, cursor):
    """Move [trac] mainnav and [trac] metanav to .order attributes
    of the [mainnav] and [metanav] sections.
    """

    config = env.config

    def move_nav_order_options(section, default):
        default = config.getlist('trac', section) or default
        for i, name in enumerate(default, 1):
            config.set(section, name + '.order', float(i))
        config.remove('trac', section)

    move_nav_order_options('mainnav', default_mainnav_order)
    move_nav_order_options('metanav', default_metanav_order)

    backup_config_file(env, '.db41.bak')
    config.save()
