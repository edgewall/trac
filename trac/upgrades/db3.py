sql = """
--- Real db_version 2 -> 3 upgrade stuff should go here
"""

def do_upgrade(env, ver, cursor):
    cursor.execute(sql)
    
