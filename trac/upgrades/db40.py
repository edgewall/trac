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


def do_upgrade(env, version, cursor):
    """Add notification-subscriber section.
    """
    if 'notification-subscriber' in env.config:
        env.log.info("Couldn't add notification-subscriber section because "
                     "it already exists.")
        return

    env.config.set('notification-subscriber', 'always_notify_cc',
                   'CarbonCopySubscriber')
    if env.config.getbool('notification', 'always_notify_owner', False):
        env.config.set('notification-subscriber', 'always_notify_owner',
                       'TicketOwnerSubscriber')
    if env.config.getbool('notification', 'always_notify_reporter', False):
        env.config.set('notification-subscriber', 'always_notify_reporter',
                       'TicketReporterSubscriber')
    if env.config.getbool('notification', 'always_notify_updater', True):
        env.config.set('notification-subscriber', 'always_notify_updater',
                       'TicketUpdaterSubscriber')
        env.config.set('notification-subscriber',
                       'always_notify_previous_updater',
                       'TicketPreviousUpdatersSubscriber')

    env.config.remove('notification', 'always_notify_owner')
    env.config.remove('notification', 'always_notify_reporter')
    env.config.remove('notification', 'always_notify_updater')

    backup_config_file(env, '.db40.bak')
    env.config.save()
