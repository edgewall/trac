from trac.db import Table, Column, Index, DatabaseManager
from trac.core import TracError
from trac.versioncontrol.cache import CACHE_YOUNGEST_REV

def do_upgrade(env, ver, cursor):
    """Modify the repository cache scheme (if needed)

    Now we use the 'youngest_rev' entry in the system table
    to explicitly store the youngest rev in the cache.
    """
    db = env.get_db_cnx()
    try:
        repos = env.get_repository()
        youngest = repos.get_youngest_rev_in_cache(db) or ''
    except TracError: # no repository available
        youngest = ''
    # deleting first, for the 0.11dev and 0.10.4dev users
    cursor.execute("DELETE FROM system WHERE name=%s",
                   (CACHE_YOUNGEST_REV,))
    cursor.execute("INSERT INTO system (name, value) VALUES (%s, %s)",
                   (CACHE_YOUNGEST_REV, youngest))
        
