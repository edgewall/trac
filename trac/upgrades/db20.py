# -*- coding: utf-8 -*-
#
# Copyright (C) 2007-2013 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

from trac.versioncontrol.cache import CACHE_YOUNGEST_REV

def do_upgrade(env, ver, cursor):
    """Modify the repository cache scheme (if needed)

    Now we use the 'youngest_rev' entry in the system table
    to explicitly store the youngest rev in the cache.
    """
    youngest = ''
    cursor.execute("SELECT value FROM system WHERE name='repository_dir'")
    for repository_dir, in cursor:
        if repository_dir.startswith('svn:'):
            cursor.execute("SELECT rev FROM revision "
                           "ORDER BY -LENGTH(rev), rev DESC LIMIT 1")
            row = cursor.fetchone()
            youngest = row and row[0] or ''
        else:
            print('Please perform a "repository resync" after this upgrade.')

    # deleting first, for the 0.11dev and 0.10.4dev users
    cursor.execute("DELETE FROM system WHERE name=%s",
                   (CACHE_YOUNGEST_REV,))
    cursor.execute("INSERT INTO system (name, value) VALUES (%s, %s)",
                   (CACHE_YOUNGEST_REV, youngest))
