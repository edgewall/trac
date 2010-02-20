from trac.db import Table, Column, Index, DatabaseManager

def do_upgrade(env, ver, cursor):
    cursor.execute("CREATE TEMPORARY TABLE session_old AS SELECT * FROM session")
    cursor.execute("DROP TABLE session")

    db = env.get_db_cnx()
    session_table = Table('session', key=('sid', 'authenticated', 'var_name'))[
        Column('sid'),
        Column('authenticated', type='int'),
        Column('var_name'),
        Column('var_value')]
    db_backend, _ = DatabaseManager(env).get_connector()
    for stmt in db_backend.to_sql(session_table):
        cursor.execute(stmt)

    cursor.execute("INSERT INTO session (sid,authenticated,var_name,var_value) "
                   "SELECT sid,authenticated,var_name,var_value "
                   "FROM session_old")
    cursor.execute("DROP TABLE session_old")
