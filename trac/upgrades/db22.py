from trac.db import Table, Column, DatabaseManager

def do_upgrade(env, ver, cursor):
    """Add the cache table."""
    table = Table('cache', key='key')[
        Column('key'),
        Column('generation')
    ]
    db_connector, _ = DatabaseManager(env)._get_connector()
    for stmt in db_connector.to_sql(table):
        cursor.execute(stmt)
