import time

sql = [
#-- Remove the unused lock table
"""DROP TABLE lock;""",
#-- Separate anonymous from authenticated sessions.
"""CREATE TEMPORARY TABLE session_old AS SELECT * FROM session;""",
"""DELETE FROM session;""",
"""INSERT INTO session (username,var_name,var_value)
  SELECT username,var_name,var_value FROM session_old
  WHERE sid IN (SELECT DISTINCT sid FROM session_old
    WHERE username!='anonymous' AND var_name='last_visit'
    GROUP BY username ORDER BY var_value DESC);""",
"""INSERT INTO session (sid,username,var_name,var_value)
  SELECT sid,username,var_name,var_value FROM session_old
  WHERE username='anonymous';""",
"""DROP TABLE session_old;"""
]

def do_upgrade(env, ver, cursor):
    for s in sql:
        cursor.execute(s)
