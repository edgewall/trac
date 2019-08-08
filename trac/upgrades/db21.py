# -*- coding: utf-8 -*-
#
# Copyright (C) 2007-2019 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/.

from trac.ticket.default_workflow import load_workflow_config_snippet
from trac.util.text import printout


def do_upgrade(env, ver, cursor):
    """Upgrade the workflow."""

    # Upgrade the reports to better handle the new workflow capabilities.
    with env.db_query as db:
        owner = db.concat('owner', "' *'")
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

    # Upgrade the workflow.
    if 'ticket-workflow' not in env.config:
        load_workflow_config_snippet(env.config, 'original-workflow.ini')
        env.config.save()
        info_message = """

==== Upgrade Notice ====

The ticket Workflow is now configurable.

Your environment has been upgraded, but configured to use the original
workflow. It is recommended that you look at changing this configuration
to use basic-workflow.

Read TracWorkflow for more information
(don't forget to 'wiki upgrade' as well)

"""
        env.log.info(info_message.replace('\n', ' ').replace('==', ''))
        printout(info_message)
