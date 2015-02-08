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

from trac.ticket.default_workflow import get_workflow_config
from trac.upgrades import backup_config_file

new_actions = {
    'create': {
        '': '<none> -> new',
        'default': 1,
    },
    'create_and_assign': {
        '': '<none> -> assigned',
        'label': 'assign',
        'permissions': 'TICKET_MODIFY',
        'operations': 'may_set_owner'
    }
}


def do_upgrade(env, version, cursor):
    """Add 'create' actions to ticket-workflow (ticket #2045).
    """
    save = False
    all_actions = get_workflow_config(env.config)
    all_states = list(set(
        [state for action in all_actions.itervalues()
               for state in action['oldstates']] +
        [action['newstate'] for action in all_actions.itervalues()]))

    for action, attributes in new_actions.items():
        if action == 'create_and_assign' and 'assigned' not in all_states:
            continue
        if action not in env.config['ticket-workflow']:
            for attr, value in attributes.items():
                key = action + ('.' + attr if attr else '')
                env.config.set('ticket-workflow', key, value)
            save = True
        else:
            env.log.info("Couldn't add ticket action '%s' because it "
                         "already exists.", action)
    if save:
        backup_config_file(env, '.db33.bak')
        env.config.save()
