# -*- coding: utf-8 -*-
#
# Copyright (C) 2015 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

from trac.db.api import DatabaseManager
from trac.db.schema import Column, Index, Table


def do_upgrade(env, ver, cursor):
    """Add an auto-increment primary key to `node_change` table and indices
    (repos, rev, path) and (repos, path, rev) (#3676).
    """
    db_connector, _ = DatabaseManager(env)._get_connector()
    table = Table('node_change', key='id')[
        Column('id', auto_increment=True),
        Column('repos', type='int'),
        Column('rev', key_size=40),
        Column('path', key_size=255),
        Column('node_type', size=1),
        Column('change_type', size=1),
        Column('base_path'),
        Column('base_rev'),
        Index(['repos', 'rev', 'path']),
        Index(['repos', 'path', 'rev'])]

    with env.db_transaction:
        cursor.execute("""CREATE TEMPORARY TABLE node_change_old AS
                          SELECT * FROM node_change""")
        cursor.execute("DROP TABLE node_change")

        for stmt in db_connector.to_sql(table):
            cursor.execute(stmt)

        cursor.execute("""\
            INSERT INTO node_change
            (repos,rev,path,node_type,change_type,base_path,base_rev)
            SELECT repos,rev,path,node_type,change_type,base_path,base_rev
            FROM node_change_old""")
        cursor.execute("DROP TABLE node_change_old")
