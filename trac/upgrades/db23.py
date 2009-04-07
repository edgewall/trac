from trac.db import Table, Column, Index, DatabaseManager

def do_upgrade(env, ver, cursor):
    # ---- begin MultiRepos compatibility code -- remove on trunk ----
    try:
        cursor.execute("SELECT * FROM repository")
        # it worked, which means we previously executed this upgrade as 
        # db22.py. 
        # So let's execute the "new" db22.py which introduced the cache.
        from trac.upgrades import db22
        db22.do_upgrade(env, ver, cursor)
    except Exception, e:
        # no repository table yet, do the actual repository cache upgrade
        _do_upgrade(env, ver, cursor)

def _do_upgrade(env, ver, cursor):
    # ---- end MultiRepos compatibility code -- remove on trunk ----
    # Make changeset cache multi-repository aware
    cursor.execute("CREATE TEMPORARY TABLE rev_old "
                   "AS SELECT * FROM revision")
    cursor.execute("DROP TABLE revision")
    cursor.execute("CREATE TEMPORARY TABLE nc_old "
                   "AS SELECT * FROM node_change")
    cursor.execute("DROP TABLE node_change")
    
    tables = [Table('repository', key=('id', 'name'))[
                Column('id'),
                Column('name'),
                Column('value')],
              Table('revision', key=('repos', 'rev'))[
                Column('repos'),
                Column('rev'),
                Column('time', type='int'),
                Column('author'),
                Column('message'),
                Index(['repos', 'time'])],
              Table('node_change', key=('repos', 'rev', 'path', 'change_type'))[
                Column('repos'),
                Column('rev'),
                Column('path'),
                Column('node_type', size=1),
                Column('change_type', size=1),
                Column('base_path'),
                Column('base_rev'),
                Index(['repos', 'rev'])]]
    
    db_connector, _ = DatabaseManager(env)._get_connector()
    for table in tables:
        for stmt in db_connector.to_sql(table):
            cursor.execute(stmt)
    
    cursor.execute("INSERT INTO revision (repos,rev,time,author,message) "
                   "SELECT '',rev,time,author,message FROM rev_old")
    cursor.execute("DROP TABLE rev_old")
    cursor.execute("INSERT INTO node_change (repos,rev,path,node_type,"
                   "change_type,base_path,base_rev) "
                   "SELECT '',rev,path,node_type,change_type,base_path,"
                   "base_rev FROM nc_old")
    cursor.execute("DROP TABLE nc_old")
    
    cursor.execute("INSERT INTO repository (id,name,value) "
                   "SELECT '',name,value FROM system "
                   "WHERE name IN ('repository_dir', 'youngest_rev')")
    cursor.execute("DELETE FROM system "
                   "WHERE name IN ('repository_dir', 'youngest_rev')")
