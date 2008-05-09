sql = [
#-- Remove empty values from the milestone list
"""DELETE FROM milestone WHERE COALESCE(name,'')='';""",
#-- Add a description column to the version table, and remove unnamed versions
"""CREATE TEMPORARY TABLE version_old AS SELECT * FROM version;""",
"""DROP TABLE version;""",
"""CREATE TABLE version (
        name            text PRIMARY KEY,
        time            integer,
        description     text
);""",
"""INSERT INTO version(name,time,description)
    SELECT name,time,'' FROM version_old WHERE COALESCE(name,'')<>'';""",
#-- Add a description column to the component table, and remove unnamed components
"""CREATE TEMPORARY TABLE component_old AS SELECT * FROM component;""",
"""DROP TABLE component;""",
"""CREATE TABLE component (
        name            text PRIMARY KEY,
        owner           text,
        description     text
);""",
"""INSERT INTO component(name,owner,description)
    SELECT name,owner,'' FROM component_old WHERE COALESCE(name,'')<>'';""",
"""DROP TABLE version_old;""",
"""DROP TABLE component_old;"""
]

def do_upgrade(env, ver, cursor):
    for s in sql:
        cursor.execute(s)
