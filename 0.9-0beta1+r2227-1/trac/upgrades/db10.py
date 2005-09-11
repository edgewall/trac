sql = [
#-- Make the node_change table contain more information, and force a resync
"""DROP TABLE revision;""",
"""DROP TABLE node_change;""",
"""CREATE TABLE revision (
    rev             text PRIMARY KEY,
    time            integer,
    author          text,
    message         text
);""",
"""CREATE TABLE node_change (
    rev             text,
    path            text,
    kind            char(1), -- 'D' for directory, 'F' for file
    change          char(1),
    base_path       text,
    base_rev        text,
    UNIQUE(rev, path, change)
);"""
]

def do_upgrade(env, ver, cursor):
    for s in sql:
        cursor.execute(s)
    print 'Please perform a "resync" after this upgrade.'
