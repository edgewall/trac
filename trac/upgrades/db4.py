sql = """
DROP TABLE milestone;

CREATE TABLE milestone (
        name             text PRIMARY KEY,
        title            text,
        time             int,
        description      text
);

CREATE TABLE session (
         sid             text,
         username        text,
         var_name        text,
         var_value       text,
         UNIQUE(sid,var_name)
);

CREATE INDEX session_idx ON session(sid,var_name);
"""

def do_upgrade(env, ver, cursor):
    milestones = fetch_milestones(env, cursor)
    cursor.execute(sql)
    readd_milestones(env, cursor, milestones)
#    env.save_config()

def fetch_milestones(env, cursor):
    cursor.execute('SELECT name, time FROM milestone')
    milestones = []
    while 1:
        row = cursor.fetchone()
        if not row:
            break
        milestone = {
            'name': row['name'],
            'time': int(row['time'])
        }
        milestones.append(milestone)
    return milestones

def readd_milestones(env, cursor, milestones):
    for m in milestones:
        cursor.execute("INSERT INTO milestone (name, time) "
                       "VALUES (%s, %d)", m['name'], m['time'])
