# -*- coding: iso8859-1 -*-
"""
Lists tickets that match certain criteria. This macro accepts two parameters,
the second of which is optional.

The first parameter is the query itself, and uses the same syntax as for
"query:" wiki links. The second parameter determines how the list of tickets is
presented: the default presentation is to list the ticket ID next to the
summary, with each ticket on a separate line. If the second parameter is given
and set to 'compact' then the tickets are presented as a comma-separated list of
ticket IDs.
"""

import re
from StringIO import StringIO

from trac.Query import Query
from trac.util import escape, shorten_line


def execute(hdf, args, env):

    query_string = ''
    compact = 0
    argv = args.split(',')
    if len(argv) > 0:
        query_string = argv[0]
        if len(argv) > 1:
            if argv[1].strip().lower() == 'compact':
                compact = 1
        

    query = Query.from_string(env, query_string)
    query.order = 'id'

    buf = StringIO()
    db = env.get_db_cnx()
    tickets = query.execute(db)
    if tickets:
        if compact:
            first = 1
            for ticket in tickets:
                if not first:
                    buf.write(', ')
                else:
                    first = 0
                href = env.href.ticket(int(ticket['id']))
                summary = escape(shorten_line(ticket['summary']))
                class_name = 'ticket'
                if ticket['status'] in ('closed', 'new'):
                    class_name = '%s ticket' % ticket['status']
                    summary += ' (%s)' % ticket['status']
                buf.write('<a class="%s" href="%s" title="%s">#%s</a>' \
                          % (class_name, href, summary, ticket['id']))
        else:
            buf.write('<dl class="wiki compact">')
            for ticket in tickets:
                href = env.href.ticket(int(ticket['id']))
                buf.write('<dt><a href="%s">#%s</a></dt>' % (href, ticket['id']))
                buf.write('<dd>%s</dd>' % (escape(ticket['summary'])))
            buf.write('</dl>')

    return buf.getvalue()
