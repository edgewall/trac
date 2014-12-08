# -*- coding: utf-8 -*-
#
# Copyright (C) 2014 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

from trac.db import Table, Column, Index, DatabaseManager


def do_upgrade(env, version, cursor):
    """Add the notify_subscription table."""
    table = Table('notify_subscription', key='id')[
                Column('id', auto_increment=True),
                Column('time', type='int64'),
                Column('changetime', type='int64'),
                Column('class'),
                Column('sid'),
                Column('authenticated', type='int'),
                Column('distributor'),
                Column('format'),
                Column('priority', type='int'),
                Column('adverb'),
                Index(['sid', 'authenticated']),
                Index(['class'])]

    DatabaseManager(env).create_tables([table])
