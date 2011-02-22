from trac.db import Table, Column, DatabaseManager

def do_upgrade(env, ver, cursor):
    """Modify the cache table to use an integer id."""
    # No need to keep the previous content
    cursor.execute("DROP TABLE cache")

    table = Table('cache', key='id')[
        Column('id', type='int'),
        Column('generation', type='int'),
        Column('key'),
    ]
    db_connector, _ = DatabaseManager(env).get_connector()
    for stmt in db_connector.to_sql(table):
        cursor.execute(stmt)
