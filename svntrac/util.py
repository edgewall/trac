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

import sys
import time
import StringIO
from svn import util
from db import get_connection
from xml.sax import saxutils


def time_to_string(date):
    date = time.asctime(time.localtime(date))
    return date[4:-8]

def format_date(date, pool):
    date = util.svn_time_from_cstring(date, pool)
    return time_to_string (date / 1000000)

def log_href (path, rev = None):
    if not rev:
        return 'svntrac.cgi?mode=log&path=%s' % path
    else:
        return 'svntrac.cgi?mode=log&path=%s&rev=%s' % (path, rev)
        
def file_href (path, rev):
    return 'svntrac.cgi?mode=file&path=%s&rev=%s' % (path, rev)

def browser_href (path):
    return 'svntrac.cgi?mode=browser&path=%s' % path

def login_href ():
    return 'svntrac_auth.cgi'

def timeline_href ():
    return 'svntrac.cgi?mode=timeline'

def changeset_href (rev):
    return 'svntrac.cgi?mode=changeset&rev=%s' % rev

def ticket_href (ticket):
    return 'svntrac.cgi?mode=ticket&id=%s' % ticket

def newticket_href ():
    return 'svntrac.cgi?mode=newticket'

def wiki_href (page = None, version=None):
    if page and version:
        return 'svntrac.cgi?mode=wiki&page=%s&version=%s' % (page, version)
    if page:
        return 'svntrac.cgi?mode=wiki&page=%s' % page
    else:
        return 'svntrac.cgi?mode=wiki'

def report_href (report=None, action=None):
    if report and action:
        return 'svntrac.cgi?mode=report&id=%s&action=%s' % (report, action)
    if report:
        return 'svntrac.cgi?mode=report&id=%s' % report
    elif action:
        return 'svntrac.cgi?mode=report&action=%s' % action
    else:
        return 'svntrac.cgi?mode=report'

def redirect (url):
    """
    redirects the user agent to a different url
    """
    print 'Location: %s\r\n\r\n' % url
    sys.exit(0)

def enum_selector (sql, name, selected=None,default_empty=0):
    out = StringIO.StringIO()
    out.write ('<select size="1" name="%s">' % name)

    cnx = get_connection()
    cursor = cnx.cursor ()
    cursor.execute (sql)

    if default_empty:
        out.write ('<option></option>')
    while 1:
	row = cursor.fetchone()
        if not row:
            break
        if selected == row[0]:
            out.write ('<option selected>%s</option>' % row[0])
        else:
            out.write ('<option>%s</option>' % row[0])

    out.write ('</select>')
    return out.getvalue()

def escape(text, param={'"':'&#34;'}):
    """Escapes &, <, > and \""""
    return saxutils.escape(text, param)

def get_first_line(text, maxlen):
    """
    returns the first line of text. If the line is longer then
    maxlen characters it is truncated. The line is also html escaped.
    """
    lines = text.splitlines()
    line  = lines[0]
    if len(lines) > 1:
        return escape(line[:maxlen] + '...')
    elif len(line) > maxlen-3:
        return escape(line[:maxlen] + '...')
    else:
        return escape(line)
