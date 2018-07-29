# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2018 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

sql = [
"""CREATE TEMPORARY TABLE node_change_old AS SELECT * FROM node_change;""",
"""DROP TABLE node_change;""",
"""CREATE TABLE node_change (
    rev             text,
    path            text,
    kind            char(1),
    change          char(1),
    base_path       text,
    base_rev        text,
    UNIQUE(rev, path, change)
);""",
"""INSERT INTO node_change (rev,path,kind,change,base_path,base_rev)
    SELECT rev,path,kind,change,base_path,base_rev FROM node_change_old;""",
"""DROP TABLE node_change_old;"""
]

def do_upgrade(env, ver, cursor):
    # Wiki pages were accidentially created with the version number starting at
    # 0 instead of 1; This should fix that
    cursor.execute("SELECT name, version FROM wiki WHERE name IN "
                   "(SELECT name FROM wiki WHERE version=0) ORDER BY name,"
                   "version DESC")
    result = cursor.fetchall()
    if result:
        cursor.executemany("UPDATE wiki SET version=version+1 WHERE name=%s "
                           "and version=%s",
                           [tuple(row) for row in result])

    # Correct difference between db_default.py and upgrades/db10.py: The
    # 'change' was missing from the uniqueness constraint
    for s in sql:
        cursor.execute(s)
