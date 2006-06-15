import time

d = {'now':time.time()}
sql = [
#-- Separate between due and completed time for milestones.
"""CREATE TEMPORARY TABLE milestone_old AS SELECT * FROM milestone;""",
"""DROP TABLE milestone;""",
"""CREATE TABLE milestone (
         name            text PRIMARY KEY,
         due             integer, -- Due date/time
         completed       integer, -- Completed date/time
         description     text
);""",
"""INSERT INTO milestone(name,due,completed,description)
SELECT name,time,time,descr FROM milestone_old WHERE time <= %(now)s;""" % d,
"""INSERT INTO milestone(name,due,description)
SELECT name,time,descr FROM milestone_old WHERE time > %(now)s;""" % d
]

def do_upgrade(env, ver, cursor):
    for s in sql:
        cursor.execute(s)
