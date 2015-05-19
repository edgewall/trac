from trac.db import DatabaseManager


def do_upgrade(env, ver, cursor):
    """Convert time values from integer seconds to integer microseconds."""
    tables = [
        ('attachment', {'time': ('int', 'int64')}),
        ('wiki', {'time': ('int', 'int64')}),
        ('revision', {'time': ('int', 'int64')}),
        ('ticket', {'time': ('int', 'int64'),
                    'changetime': ('int', 'int64')}),
        ('ticket_change', {'time': ('int', 'int64')}),
        ('milestone', {'due': ('int', 'int64'),
                       'completed': ('int', 'int64')}),
        ('version', {'time': ('int', 'int64')}),
    ]
    
    db_connector, _ = DatabaseManager(env).get_connector()
    db = env.get_db_cnx()
    for table, columns in tables:
        # Alter column types
        for sql in db_connector.alter_column_types(table, columns):
            cursor.execute(sql)
        
        # Convert timestamps to microseconds
        cursor.execute("UPDATE %s SET %s" % (table,
                        ', '.join("%s=%s*1000000" % (column, column)
                                  for column in columns)))
    
    # Convert comment edit timestamps to microseconds
    cursor.execute("UPDATE ticket_change SET newvalue=%s*1000000 "
                   "WHERE field %s" % (db.cast('newvalue', 'int64'),
                                       db.like()),
                   ('_comment%',))
