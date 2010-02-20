from trac.db import Table, Column, Index, DatabaseManager

def do_upgrade(env, ver, cursor):
    """Rename the column `sql` in the `report` table for compatibity with MySQL.
    """
    cursor.execute("CREATE TEMPORARY TABLE report_old AS SELECT * FROM report")
    cursor.execute("DROP TABLE report")

    table = Table('report', key='id')[
        Column('id', auto_increment=True),
        Column('author'),
        Column('title'),
        Column('query'),
        Column('description')
    ]
    db_connector, _ = DatabaseManager(env).get_connector()
    for stmt in db_connector.to_sql(table):
        cursor.execute(stmt)

    cursor.execute("INSERT INTO report (id,author,title,query,description) "
                   "SELECT id,author,title,sql,description FROM report_old")
    cursor.execute("DROP TABLE report_old")
