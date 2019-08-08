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

import re

from trac.upgrades import backup_config_file


def do_upgrade(env, version, cursor):
    """Change [notification] ticket_subject_template and [notification]
    batch_subject_template to use syntax compatible with Jinja2.
    """

    config = env.config
    section = 'notification'
    re_template_var = re.compile(r'\$([\w.]+)')

    def update_template(name):
        old_value = config.get(section, name)
        if old_value:
            if re_template_var.match(old_value):
                new_value = re_template_var.sub(r'${\1}', old_value)
                env.log.info("Replaced value of [%s] %s: %s -> %s",
                             section, name, old_value, new_value)
                config.set(section, name, new_value)
                return True
        return False

    updated = update_template('ticket_subject_template')
    updated |= update_template('batch_subject_template')
    if updated:
        backup_config_file(env, '.db45.bak')
        config.save()
