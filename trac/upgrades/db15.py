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

from trac.db import Table, Column, DatabaseManager

def do_upgrade(env, ver, cursor):
    cursor.execute("""
        CREATE TEMPORARY TABLE session_old AS SELECT * FROM session
        """)
    cursor.execute("DROP TABLE session")

    session_table = Table('session', key=('sid', 'authenticated', 'var_name'))[
        Column('sid'),
        Column('authenticated', type='int'),
        Column('var_name'),
        Column('var_value')]
    db_backend, _ = DatabaseManager(env).get_connector()
    for stmt in db_backend.to_sql(session_table):
        cursor.execute(stmt)

    cursor.execute("""
        INSERT INTO session (sid,authenticated,var_name,var_value)
        SELECT sid,authenticated,var_name,var_value FROM session_old
        """)
    cursor.execute("DROP TABLE session_old")
