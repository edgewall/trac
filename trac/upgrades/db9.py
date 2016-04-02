# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2013 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

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
