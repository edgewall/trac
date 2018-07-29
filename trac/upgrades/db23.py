# -*- coding: utf-8 -*-
#
# Copyright (C) 2009-2018 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

from trac.db import Table, Column, Index, DatabaseManager

def do_upgrade(env, ver, cursor):
    # Make changeset cache multi-repository aware
    cursor.execute("CREATE TEMPORARY TABLE rev_old "
                   "AS SELECT * FROM revision")
    cursor.execute("DROP TABLE revision")
    cursor.execute("CREATE TEMPORARY TABLE nc_old "
                   "AS SELECT * FROM node_change")
    cursor.execute("DROP TABLE node_change")

    tables = [Table('repository', key=('id', 'name'))[
                Column('id'),
                Column('name'),
                Column('value')],
              Table('revision', key=('repos', 'rev'))[
                Column('repos'),
                Column('rev', key_size=20),
                Column('time', type='int'),
                Column('author'),
                Column('message'),
                Index(['repos', 'time'])],
              Table('node_change', key=('repos', 'rev', 'path', 'change_type'))[
                Column('repos', key_size=56),
                Column('rev', key_size=20),
                Column('path', key_size=255),
                Column('node_type', size=1),
                Column('change_type', size=1, key_size=2),
                Column('base_path'),
                Column('base_rev'),
                Index(['repos', 'rev'])]]

    db_connector, _ = DatabaseManager(env)._get_connector()
    for table in tables:
        for stmt in db_connector.to_sql(table):
            cursor.execute(stmt)

    cursor.execute("INSERT INTO revision (repos,rev,time,author,message) "
                   "SELECT '',rev,time,author,message FROM rev_old")
    cursor.execute("DROP TABLE rev_old")
    cursor.execute("INSERT INTO node_change (repos,rev,path,node_type,"
                   "change_type,base_path,base_rev) "
                   "SELECT '',rev,path,node_type,change_type,base_path,"
                   "base_rev FROM nc_old")
    cursor.execute("DROP TABLE nc_old")

    cursor.execute("INSERT INTO repository (id,name,value) "
                   "SELECT '',name,value FROM system "
                   "WHERE name IN ('repository_dir', 'youngest_rev')")
    cursor.execute("DELETE FROM system "
                   "WHERE name IN ('repository_dir', 'youngest_rev')")
