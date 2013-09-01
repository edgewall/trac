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
#-- Remove empty values from the milestone list
"""DELETE FROM milestone WHERE COALESCE(name,'')='';""",
#-- Add a description column to the version table, and remove unnamed versions
"""CREATE TEMPORARY TABLE version_old AS SELECT * FROM version;""",
"""DROP TABLE version;""",
"""CREATE TABLE version (
        name            text PRIMARY KEY,
        time            integer,
        description     text
);""",
"""INSERT INTO version(name,time,description)
    SELECT name,time,'' FROM version_old WHERE COALESCE(name,'')<>'';""",
#-- Add a description column to the component table, and remove unnamed components
"""CREATE TEMPORARY TABLE component_old AS SELECT * FROM component;""",
"""DROP TABLE component;""",
"""CREATE TABLE component (
        name            text PRIMARY KEY,
        owner           text,
        description     text
);""",
"""INSERT INTO component(name,owner,description)
    SELECT name,owner,'' FROM component_old WHERE COALESCE(name,'')<>'';""",
"""DROP TABLE version_old;""",
"""DROP TABLE component_old;"""
]

def do_upgrade(env, ver, cursor):
    for s in sql:
        cursor.execute(s)
