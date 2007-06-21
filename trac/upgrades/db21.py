
def do_upgrade(env, ver, cursor):
    """Upgrade the reports to better handle the new workflow capabilities"""
    db = env.get_db_cnx()
    owner = db.concat('owner', "' *'")
    reports = list(cursor.execute('SELECT id, query, description FROM report'))
    for report, query, description in reports:
        # All states other than 'closed' are "active".
        query = query.replace("IN ('new', 'assigned', 'reopened')",
                              "<> 'closed'")
        # Add a status column instead of adding an '*' to the owner's name for
        # the 'assigned' state.
        query = query.replace("(CASE status WHEN 'assigned' THEN %s "
                              "ELSE owner END) AS owner" % owner, "owner, status")
        description = description.replace(" * If a ticket has been accepted, "
                                          "a '*' is appended after the "
                                          "owner's name\n",
                                          '')
        cursor.execute("UPDATE report SET query=%s, description=%s "
                       "WHERE id=%s", (query, description, report))
