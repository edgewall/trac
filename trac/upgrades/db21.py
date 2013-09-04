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


def do_upgrade(env, ver, cursor):
    """Upgrade the reports to better handle the new workflow capabilities"""
    owner = env.get_read_db().concat('owner', "' *'")
    cursor.execute('SELECT id, query, description FROM report')
    reports = cursor.fetchall()
    for report, query, description in reports:
        q, d = query, description
        if query:
            # All states other than 'closed' are "active".
            q = q.replace("IN ('new', 'assigned', 'reopened')", "<> 'closed'")
            # Add a status column instead of adding an '*' to the owner's name
            # for the 'assigned' state.
            q = q.replace("(CASE status WHEN 'assigned' THEN %s "
                          "ELSE owner END) AS owner" % owner, "owner, status")
        if description:
            d = d.replace(" * If a ticket has been accepted, a '*' is"
                          " appended after the owner's name\n", '')
        if q != query or d != description:
            cursor.execute("""
                UPDATE report SET query=%s, description=%s WHERE id=%s
                """, (q, d, report))
