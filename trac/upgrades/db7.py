# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2018 Edgewall Software
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
#-- Add readonly flag to 'wiki'
"""CREATE TEMPORARY TABLE wiki_old AS SELECT * FROM wiki;""",
"""DROP TABLE wiki;""",
"""CREATE TABLE wiki (
         name            text,
         version         integer,
         time            integer,
         author          text,
         ipnr            text,
         text            text,
         comment         text,
         readonly        integer,
         UNIQUE(name,version)
);""",
"""INSERT INTO wiki(name,version,time,author,ipnr,text,comment,readonly) SELECT name,version,time,author,ipnr,text,comment,0 FROM wiki_old;"""
]

def do_upgrade(env, ver, cursor):
    for s in sql:
        cursor.execute(s)
