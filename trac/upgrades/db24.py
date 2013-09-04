# -*- coding: utf-8 -*-
#
# Copyright (C) 2009-2013 Edgewall Software
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
    # Change repository key from reponame to a surrogate id
    cursor.execute("SELECT id FROM repository "
                   "UNION SELECT repos AS id FROM revision "
                   "UNION SELECT repos AS id FROM node_change "
                   "ORDER BY id")
    id_name_list = [(i + 1, name) for i, (name,) in enumerate(cursor)]

    cursor.execute("CREATE TEMPORARY TABLE repo_old "
                   "AS SELECT * FROM repository")
    cursor.execute("DROP TABLE repository")
    cursor.execute("CREATE TEMPORARY TABLE rev_old "
                   "AS SELECT * FROM revision")
    cursor.execute("DROP TABLE revision")
    cursor.execute("CREATE TEMPORARY TABLE nc_old "
                   "AS SELECT * FROM node_change")
    cursor.execute("DROP TABLE node_change")

    tables = [Table('repository', key=('id', 'name'))[
                  Column('id', type='int'),
                  Column('name'),
                  Column('value')],
              Table('revision', key=('repos', 'rev'))[
                  Column('repos', type='int'),
                  Column('rev', key_size=20),
                  Column('time', type='int'),
                  Column('author'),
                  Column('message'),
                  Index(['repos', 'time'])],
              Table('node_change', key=('repos', 'rev', 'path', 'change_type'))[
                  Column('repos', type='int'),
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

    cursor.executemany("INSERT INTO repository (id,name,value) "
                       "VALUES (%s,'name',%s)", id_name_list)
    cursor.executemany("INSERT INTO repository (id,name,value) "
                       "SELECT %s,name,value FROM repo_old WHERE id=%s",
                       id_name_list)
    cursor.execute("DROP TABLE repo_old")
    cursor.executemany("INSERT INTO revision (repos,rev,time,author,message) "
                       "SELECT %s,rev,time,author,message FROM rev_old "
                       "WHERE repos=%s", id_name_list)
    cursor.execute("DROP TABLE rev_old")
    cursor.executemany("INSERT INTO node_change (repos,rev,path,node_type,"
                       "  change_type,base_path,base_rev) "
                       "SELECT %s,rev,path,node_type,change_type,base_path,"
                       "  base_rev FROM nc_old WHERE repos=%s", id_name_list)
    cursor.execute("DROP TABLE nc_old")
