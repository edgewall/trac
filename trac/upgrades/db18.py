# -*- coding: utf-8 -*-
#
# Copyright (C) 2006-2013 Edgewall Software
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
    cursor.execute("CREATE TEMPORARY TABLE session_old AS SELECT * FROM session")
    cursor.execute("DROP TABLE session")
    cursor.execute("CREATE TEMPORARY TABLE ticket_change_old AS SELECT * FROM ticket_change")
    cursor.execute("DROP TABLE ticket_change")

    # A more normalized session schema where the attributes are stored in
    # a separate table
    tables = [Table('session', key=('sid', 'authenticated'))[
                Column('sid'),
                Column('authenticated', type='int'),
                Column('last_visit', type='int'),
                Index(['last_visit']),
                Index(['authenticated'])],
              Table('session_attribute', key=('sid', 'authenticated', 'name'))[
                Column('sid'),
                Column('authenticated', type='int'),
                Column('name'),
                Column('value')],
              Table('ticket_change', key=('ticket', 'time', 'field'))[
                Column('ticket', type='int'),
                Column('time', type='int'),
                Column('author'),
                Column('field'),
                Column('oldvalue'),
                Column('newvalue'),
                Index(['ticket']),
                Index(['time'])]]

    db_connector, _ = DatabaseManager(env).get_connector()
    for table in tables:
        for stmt in db_connector.to_sql(table):
            cursor.execute(stmt)

    # Add an index to the temporary table to speed up the conversion
    cursor.execute("CREATE INDEX session_old_sid_idx ON session_old(sid)")
    # Insert the sessions into the new table
    cursor.execute("""
        INSERT INTO session (sid, last_visit, authenticated)
        SELECT distinct s.sid,COALESCE(%s,0),s.authenticated
        FROM session_old AS s LEFT JOIN session_old AS s2
        ON (s.sid=s2.sid AND s2.var_name='last_visit')
        WHERE s.sid IS NOT NULL
        """ % env.get_read_db().cast('s2.var_value', 'int'))
    cursor.execute("""
        INSERT INTO session_attribute (sid, authenticated, name, value)
        SELECT s.sid, s.authenticated, s.var_name, s.var_value
        FROM session_old s
        WHERE s.var_name <> 'last_visit' AND s.sid IS NOT NULL
        """)

    # Insert ticket change data into the new table
    cursor.execute("""
        INSERT INTO ticket_change (ticket, time, author, field, oldvalue,
                                   newvalue)
        SELECT ticket, time, author, field, oldvalue, newvalue
        FROM ticket_change_old
        """)

    cursor.execute("DROP TABLE session_old")
    cursor.execute("DROP TABLE ticket_change_old")
