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
