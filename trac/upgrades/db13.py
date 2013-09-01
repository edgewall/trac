# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2013 Edgewall Software
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
#-- Add ticket_type to 'ticket', remove the unused 'url' column
"""CREATE TEMPORARY TABLE ticket_old AS SELECT * FROM ticket;""",
"""DROP TABLE ticket;""",
"""CREATE TABLE ticket (
        id              integer PRIMARY KEY,
        type            text,           -- the nature of the ticket
        time            integer,        -- the time it was created
        changetime      integer,
        component       text,
        severity        text,
        priority        text,
        owner           text,           -- who is this ticket assigned to
        reporter        text,
        cc              text,           -- email addresses to notify
        version         text,           --
        milestone       text,           --
        status          text,
        resolution      text,
        summary         text,           -- one-line summary
        description     text,           -- problem description (long)
        keywords        text
);""",
"""INSERT INTO ticket(id, type, time, changetime, component, severity, priority,
                   owner, reporter, cc, version, milestone, status, resolution,
                   summary, description, keywords)
  SELECT id, 'defect', time, changetime, component, severity, priority, owner,
         reporter, cc, version, milestone, status, resolution, summary,
         description, keywords FROM ticket_old
  WHERE COALESCE(severity,'') <> 'enhancement';""",
"""INSERT INTO ticket(id, type, time, changetime, component, severity, priority,
                   owner, reporter, cc, version, milestone, status, resolution,
                   summary, description, keywords)
  SELECT id, 'enhancement', time, changetime, component, 'normal', priority,
         owner, reporter, cc, version, milestone, status, resolution, summary,
         description, keywords FROM ticket_old
  WHERE severity = 'enhancement';""",
"""INSERT INTO enum (type, name, value) VALUES ('ticket_type', 'defect', '1');""",
"""INSERT INTO enum (type, name, value) VALUES ('ticket_type', 'enhancement', '2');""",
"""INSERT INTO enum (type, name, value) VALUES ('ticket_type', 'task', '3');""",
"""DELETE FROM enum WHERE type = 'severity' AND name = 'enhancement';""",
"""DROP TABLE ticket_old;""",
]

def do_upgrade(env, ver, cursor):
    for s in sql:
        cursor.execute(s)

    # -- upgrade reports (involve a rename)
    cursor.execute("SELECT id,sql FROM report")
    reports = {}
    for id, rsql in cursor:
        reports[id] = rsql
    for id, rsql in reports.items():
        parts = rsql.split('ORDER BY', 1)
        ending = len(parts)>1 and 'ORDER BY'+parts[1] or ''
        cursor.execute("UPDATE report SET sql=%s WHERE id=%s",
                       (parts[0].replace('severity,',
                                         't.type AS type, severity,') + ending,
                        id))
