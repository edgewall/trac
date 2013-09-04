# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2013 Edgewall Software
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
#-- Add unique id, descr to 'milestone'
"""CREATE TEMPORARY TABLE milestone_old AS SELECT * FROM milestone;""",
"""DROP TABLE milestone;""",
"""CREATE TABLE milestone (
         id              integer PRIMARY KEY,
         name            text,
         time            integer,
         descr           text,
         UNIQUE(name)
);""",
"""
INSERT INTO milestone(name,time, descr) SELECT name,time,'' FROM milestone_old;""",
"""DROP TABLE milestone_old;""",
]
def do_upgrade(env, ver, cursor):
    for s in sql:
        cursor.execute(s)
