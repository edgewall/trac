# svntrac
#
# Copyright (C) 2003 Xyche Software
# Copyright (C) 2003 Jonas Borgström <jonas@xyche.com>
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
# Author: Jonas Borgström <jonas@xyche.com>

from util import *
from Module import Module
import db
import perm

import StringIO
import time

class Timeline (Module):
    template_name = 'timeline.template'

    MAX_MESSAGE_LEN = 75

    def __init__(self, config, args, pool):
        Module.__init__(self, config, args, pool)
        
    def get_info (self, start, stop):
        cnx = db.get_connection()
        cursor = cnx.cursor ()

        # 1: change set
        # 2: new tickets
        # 3: closed tickets

        cursor.execute ("SELECT time, rev AS data, 1 AS type, message "
                        "FROM revision WHERE time>=%s AND time<=%s UNION ALL "
                        "SELECT time, id AS data, 2 AS type, summary AS message "
                        "FROM ticket WHERE time>=%s AND time<=%s UNION ALL "
                        "SELECT time, ticket AS data, 3 AS type, '' AS message "
                        "FROM ticket_change WHERE field='status' "
                        "AND newvalue='closed' AND time>=%s AND time<=%s "
                        "ORDER BY time DESC, message, type",
                        start, stop, start, stop, start, stop)
        return cursor.fetchall()
        
    def day_separator(self, out, date):
        if date < self.current_day:
            self.current_day = (date / 86400) * 86400 + time.timezone
            out.write ('<tr>')
            out.write ('<td colspan="2" class="timeline-day">%s</td>'
                       % time.strftime('%A, %F', time.localtime(date)))
            out.write ('</tr>')

    def print_changeset (self, out, item):
        date = int(item['time'])
        self.day_separator (out, date)
            
        out.write ('<tr>')
        out.write ('<td>%s</td><td>change set [<a href="%s">%s</a>]: %s</td>'
                   % (time.strftime('%H:%M', time.localtime(date)),
                      changeset_href (item['data']),
                      item['data'], get_first_line(item['message'],
                                                   self.MAX_MESSAGE_LEN)))
        out.write ('</tr>')
        
    def print_new_ticket (self, out, item):
        date = int(item['time'])
        self.day_separator (out, date)
            
        out.write ('<tr>')
        out.write ('<td>%s</td><td>ticket <a href="%s">#%s</a> created: %s</td>'
                   % (time.strftime('%H:%M', time.localtime(date)),
                      ticket_href (item['data']), item['data'],
                      get_first_line(item['message'], self.MAX_MESSAGE_LEN)))
        out.write ('</tr>')
        
    def print_closed_ticket (self, out, item):
        date = int(item['time'])
        self.day_separator (out, date)
            
        out.write ('<tr>')
        out.write ('<td>%s</td><td>ticket <a href="%s">#%s</a> closed</td>'
                   % (time.strftime('%H:%M', time.localtime(date)),
                      ticket_href (item['data']), item['data']))
        out.write ('</tr>')
        
    def render (self):
        perm.assert_permission (perm.TIMELINE_VIEW)

        out = StringIO.StringIO()
        stop  = int(time.time() - time.timezone)
        start = stop - 90 * 86400
        
        info = self.get_info (start, stop)

        self.current_day = stop + 1

        for item in info:
            if item['type'] == '1':
                self.print_changeset (out, item)
            elif item['type'] == '2':
                self.print_new_ticket (out, item)
            elif item['type'] == '3':
                self.print_closed_ticket (out, item)

        self.namespace['content']  = out.getvalue()
