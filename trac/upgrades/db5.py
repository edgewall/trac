import time

sql = """
-- Add unique id, descr to 'milestone'
CREATE TEMP TABLE milestone_old AS SELECT * FROM milestone;
DROP TABLE milestone;
CREATE TABLE milestone (
         id              integer PRIMARY KEY,
         name            text,
         time            integer,
         descr           text,
         UNIQUE(name)
);
INSERT INTO milestone(name,time, descr) SELECT name,time,'' FROM milestone_old;

"""

def do_upgrade(env, ver, cursor):
    cursor.execute(sql)
#    env.save_config()
