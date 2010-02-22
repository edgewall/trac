
def do_upgrade(env, ver, cursor):
    """Zero-pad Subversion revision numbers in the cache."""
    cursor.execute("""
        SELECT id, value FROM repository WHERE name='repository_dir'
        """)
    for id in [id for id, dir in cursor if dir.startswith('svn:')]:
        cursor.execute("SELECT DISTINCT rev FROM revision WHERE repos=%s",
                       (id,))
        for rev in set(row[0] for row in cursor):
            cursor.execute("""
                UPDATE revision SET rev=%s WHERE repos=%s AND rev=%s
                """, ('%010d' % int(rev), id, rev))
        
        cursor.execute("SELECT DISTINCT rev FROM node_change WHERE repos=%s",
                       (id,))
        for rev in set(row[0] for row in cursor):
            cursor.execute("""
                UPDATE node_change SET rev=%s WHERE repos=%s AND rev=%s
                """, ('%010d' % int(rev), id, rev))
