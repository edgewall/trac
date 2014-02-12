# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2013 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

sql = """
CREATE TABLE ticket_custom (
       ticket               integer,
       name             text,
       value            text,
       UNIQUE(ticket,name)
);
"""

def do_upgrade(env, ver, cursor):
    cursor.execute(sql)
