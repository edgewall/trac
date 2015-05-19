sql = """
CREATE TABLE ticket_custom (
       ticket               integer,
       name             text,
       value            text,
       UNIQUE(ticket,name)
);
"""

def do_upgrade(env, ver, cursor):
    cursor.execute(sql)

