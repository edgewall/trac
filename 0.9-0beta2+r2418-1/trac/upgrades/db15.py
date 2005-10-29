from trac.db import Table, Column, Index

def do_upgrade(env, ver, cursor):
    cursor.execute("CREATE TEMP TABLE session_old AS SELECT * FROM session")
    cursor.execute("DROP TABLE session")

    db = env.get_db_cnx()
    session_table = Table('session', key=('sid', 'authenticated', 'var_name'))[
        Column('sid'),
        Column('authenticated', type='int'),
        Column('var_name'),
        Column('var_value')]
    for stmt in db.to_sql(session_table):
        cursor.execute(stmt)

    cursor.execute("INSERT INTO session (sid,authenticated,var_name,var_value) "
                   "SELECT sid,authenticated,var_name,var_value "
                   "FROM session_old")
