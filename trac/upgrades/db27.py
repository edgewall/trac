# -*- coding: utf-8 -*-
#
# Copyright (C) 2012-2013 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

from trac.db import Table, Column, DatabaseManager

def do_upgrade(env, ver, cursor):
    """Modify the cache table to use an integer id."""
    # No need to keep the previous content
    cursor.execute("DROP TABLE cache")

    table = Table('cache', key='id')[
        Column('id', type='int'),
        Column('generation', type='int'),
        Column('key'),
    ]
    db_connector, _ = DatabaseManager(env).get_connector()
    for stmt in db_connector.to_sql(table):
        cursor.execute(stmt)
