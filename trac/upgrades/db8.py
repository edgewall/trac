import time

d = {'now':time.time()}
sql = """
-- Separate between due and completed time for milestones.
CREATE TEMP TABLE milestone_old AS SELECT * FROM milestone;
DROP TABLE milestone;
CREATE TABLE milestone (
         name            text,
         due             integer, -- Due date/time
         completed       integer, -- Completed date/time
         description     text,
         UNIQUE(name)
);
INSERT INTO milestone(name,due,completed,description)
SELECT name,time,time,descr FROM milestone_old WHERE time <= %(now)s;
INSERT INTO milestone(name,due,description)
SELECT name,time,descr FROM milestone_old WHERE time > %(now)s;
""" % d

def do_upgrade(env, ver, cursor):
    cursor.execute(sql)
