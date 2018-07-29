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
"""CREATE TABLE session (
         sid             text,
         username        text,
         var_name        text,
         var_value       text,
         UNIQUE(sid,var_name)
);""",
"""CREATE INDEX session_idx ON session(sid,var_name);"""
]

def do_upgrade(env, ver, cursor):
    for s in sql:
        cursor.execute(s)
