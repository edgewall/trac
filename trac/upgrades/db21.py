
def do_upgrade(env, ver, cursor):
    """Upgrade the reports to better handle the new workflow capabilities"""
    db = env.get_db_cnx()
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
            cursor.execute("UPDATE report SET query=%s, description=%s "
                           "WHERE id=%s", (q, d, report))
