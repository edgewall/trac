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
    """Add the notify_watch table."""
    table = Table('notify_watch', key='id')[
                Column('id', auto_increment=True),
                Column('sid'),
                Column('authenticated', type='int'),
                Column('class'),
                Column('realm'),
                Column('target'),
                Index(['sid', 'authenticated', 'class']),
                Index(['class', 'realm', 'target'])]

    DatabaseManager(env).create_tables([table])
