import time

sql = """
-- Add unique id, descr to 'milestone'
CREATE TEMP TABLE wiki_old AS SELECT * FROM wiki;
DROP TABLE wiki;
CREATE TABLE wiki (
         name            text,
         version         integer,
         time            integer,
         author          text,
         ipnr            text,
         text            text,
         comment         text,
         readonly        integer,
         UNIQUE(name,version)
);
INSERT INTO wiki(name,version,time,author,ipnr,text,comment,readonly) SELECT name,version,time,author,ipnr,text,comment,0 FROM wiki_old;

"""

def do_upgrade(env, ver, cursor):
    cursor.execute(sql)
