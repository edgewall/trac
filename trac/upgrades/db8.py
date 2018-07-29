# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2018 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

import time

d = {'now':time.time()}
sql = [
#-- Separate between due and completed time for milestones.
"""CREATE TEMPORARY TABLE milestone_old AS SELECT * FROM milestone;""",
"""DROP TABLE milestone;""",
"""CREATE TABLE milestone (
         name            text PRIMARY KEY,
         due             integer, -- Due date/time
         completed       integer, -- Completed date/time
         description     text
);""",
"""INSERT INTO milestone(name,due,completed,description)
SELECT name,time,time,descr FROM milestone_old WHERE time <= %(now)s;""" % d,
"""INSERT INTO milestone(name,due,description)
SELECT name,time,descr FROM milestone_old WHERE time > %(now)s;""" % d
]


def do_upgrade(env, ver, cursor):
    for s in sql:
        cursor.execute(s)
