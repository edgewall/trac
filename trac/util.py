# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2003, 2004 Edgewall Software
# Copyright (C) 2003, 2004 Jonas Borgström <jonas@edgewall.com>
#
# Trac is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version.
#
# Trac is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#
# Author: Jonas Borgström <jonas@edgewall.com>

import sys
import time
import StringIO
from types import *
from db import get_connection
from xml.sax import saxutils

def svn_date_to_string(date, pool):
    from svn import util
    date_seconds = util.svn_time_from_cstring(date,
                                              pool) / 1000000
    return time.asctime(time.localtime(date_seconds))[4:-8]

def redirect (url):
    """
    redirects the user agent to a different url
    """
    import neo_cgi
    neo_cgi.CGI().redirectUri(url)
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
    if not text:
        return ''
    elif type(text) is StringType:
        return saxutils.escape(text, param)
    else:
        return text

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

def href_join(u1, *tail):
    for u2 in tail:
        if u1[-1] == '/' and u2[0] != '/' or \
            u1[-1] != '/' and u2[0] == '/':
                u1 = u1 + u2
        else:
            u1 = u1 + '/' + u2
    return u1

def dict_get_with_default(dict, key, default):
    """Returns dict[key] if it exists else default"""
    if dict.has_key(key):
        return dict[key]
    else:
        return default


def add_dictlist_to_hdf(list, hdf, prefix):
    idx = 0
    for item in list:
        for key in item.keys():
            hdf.setValue('%s.%d.%s' % (prefix, idx, key), str(item[key]))
        idx = idx + 1

def add_dict_to_hdf(dict, hdf, prefix):
    for key in dict.keys():
        hdf.setValue('%s.%s' % (prefix, key), str(dict[key]))

def sql_to_hdf (sql, hdf, prefix):
    """
    executes a sql query and insert the first result column
    into the hdf at the given prefix
    """
    cnx = get_connection()
    cursor = cnx.cursor ()
    cursor.execute (sql)
#    cursor.execute ('SELECT type, name, value FROM enum ORDER BY type,value,name')
    idx = 0
    while 1:
        row = cursor.fetchone()
        if not row:
            break
        hdf.setValue('%s.%d.name' % (prefix, idx), row[0])
        idx = idx + 1

def hdf_add_if_missing(hdf, prefix, value):
    """Loop through the hdf values and add @value if id doesn't exist"""
    node = hdf.getObj(prefix + '.0')
    i = 0
    while node:
        child = node.child()
        if child and child.value() == value:
            return
        node = node.next()
        i += 1
    hdf.setValue(prefix + '.%d.name' % i, value)
        
