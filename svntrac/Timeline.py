# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2003 Edgewall Software
# Copyright (C) 2003 Jonas Borgström <jonas@edgewall.com>
#
# svntrac is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version.
#
# svntrac is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#
# Author: Jonas Borgström <jonas@edgewall.com>

from util import *
from Href import href
from Module import Module
import db
import perm

import time

class Timeline (Module):
    template_name = 'timeline.cs'

    MAX_MESSAGE_LEN = 75

    def __init__(self, config, args, pool):
        Module.__init__(self, config, args, pool)
        
    def get_info (self, start, stop):
        cnx = db.get_connection()
        cursor = cnx.cursor ()

        # 1: change set
        # 2: new tickets
        # 3: closed tickets
        # 4: reopened tickets

        cursor.execute ("SELECT time, rev AS data, 1 AS type, message, author "
                        "FROM revision WHERE time>=%s AND time<=%s UNION ALL "
                        "SELECT time, id AS data, 2 AS type, "
                        "summary AS message, reporter AS author "
                        "FROM ticket WHERE time>=%s AND time<=%s UNION ALL "
                        "SELECT time, ticket AS data, 3 AS type, "
                        "'' AS message, author "
                        "FROM ticket_change WHERE field='status' "
                        "AND newvalue='closed' AND time>=%s AND time<=%s UNION ALL "
                        "SELECT time, ticket AS data, 4 AS type, "
                        "'' AS message, author "
                        "FROM ticket_change WHERE field='status' "
                        "AND newvalue='reopened' AND time>=%s AND time<=%s "
                        "ORDER BY time DESC, message, type",
                        start, stop, start, stop, start, stop, start, stop)

        # Make the data more HDF-friendly
        info = []
        while 1:
            row = cursor.fetchone()
            if not row:
                break
            t = time.localtime(int(row['time']))
            item = {'time': time.strftime('%H:%M', t),
                    'date': time.strftime('%D, %F', t),
                    'data': row['data'],
                    'type': row['type'],
                    'message': row['message'],
                    'author': row['author']}
            if row['type'] == '1':
                item['changeset_href'] = href.changeset(int(row['data']))
            else:
                item['ticket_href'] = href.ticket(int(row['data']))
            info.append(item)
        return info
        
    def render (self):
        perm.assert_permission(perm.TIMELINE_VIEW)

        stop  = int(time.time() - time.timezone)
        start = stop - 90 * 86400
        
        info = self.get_info (start, stop)

        add_dictlist_to_hdf(info, self.cgi.hdf, 'timeline.items')

