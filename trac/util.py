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

import os
import sys
import time
import tempfile
import StringIO
from types import *
from UserDict import UserDict
from UserList import UserList

TRUE =  ['yes', '1', 1, 'true',  'on',  'aye']
FALSE = ['no',  '0', 0, 'false', 'off', 'nay']

CRLF = '\r\n'

def svn_date_to_string(date, pool):
    from svn import util
    date_seconds = util.svn_time_from_cstring(date,
                                              pool) / 1000000
    return time.strftime('%x %X', time.localtime(date_seconds))

def enum_selector (db, sql, name, selected=None,default_empty=0):
    out = StringIO.StringIO()
    out.write ('<select size="1" name="%s">' % name)

    cursor = db.cursor ()
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

def wiki_escape_newline(text):
    return text.replace(os.linesep, '[[BR]]' + os.linesep)

def escape(text):
    """Escapes &, <, > and \""""
    if not text:
        return ''
    return str(text).replace('&', '&amp;') \
                    .replace('<', '&lt;') \
                    .replace('>', '&gt;') \
                    .replace('"', '&#34;')

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

def lstrip(text, skip):
    """Python2.1 doesn't support custom skip characters"""
    while text:
        if text[0] in skip:
            text = text[1:]
        else:
            break
    return text

def rstrip(text, skip):
    """Python2.1 doesn't support custom skip characters"""
    while text:
        if text[-1] in skip:
            text = text[:-1]
        else:
            break
    return text

def to_utf8(text, charset='iso-8859-15'):
    """Convert a string to utf-8, assume the encoding is either utf-8 or latin1"""
    try:
        # Do nothing if it's already utf-8
        u = unicode(text, 'utf-8')
        return text
    except UnicodeError:
        try:
            # Use the user supplied charset if possible
            u = unicode(text, charset)
        except UnicodeError:
            # This should always work
            u = unicode(text, 'iso-8859-15')
        return u.encode('utf-8')

def href_join(u1, *tail):
    """Join a list of url components and removes redundant '/' characters"""
    for u2 in tail:
        u1 = rstrip(u1, '/') + '/' + lstrip(u2, '/')
    return u1

def sql_escape(text):
    """
    Escapes the given string so that it can be safely used in an SQL
    statement
    """
    return text.replace("'", "''").replace("\\", "\\\\")

def add_to_hdf(obj, hdf, prefix):
    """
    Adds an object to the given HDF under the specified prefix.
    Lists and dictionaries are expanded, all other objects are added
    as strings.
    """
    if type(obj) is DictType or isinstance(obj, UserDict):
        for k in obj.keys():
            add_to_hdf(obj[k], hdf, '%s.%s' % (prefix, k))
    elif type(obj) is ListType or isinstance(obj, UserList):
        for i in range(len(obj)):
            add_to_hdf(obj[i], hdf, '%s.%d' % (prefix, i))
    else:
        hdf.setValue(prefix, str(obj))

def sql_to_hdf (db, sql, hdf, prefix):
    """
    executes a sql query and insert the first result column
    into the hdf at the given prefix
    """
    cursor = db.cursor ()
    cursor.execute (sql)
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

def shorten_line(text, maxlen = 75):
    if not text:
        return ''
    i = text.find('[[BR]]')
    j = text.find('\n')
    if i > -1 and i < maxlen:
        shortline = text[:i]+' ...'
    elif j > -1 and j < maxlen:
        shortline = text[:j]+' ...'
    elif len(text) < maxlen:
        shortline = text
    else:
        i = text[:maxlen].rfind(' ')
        if i == -1:
            i = maxlen
        shortline = text[:i]+' ...'
    return shortline

def hex_entropy(bytes=32):
    import md5
    import random
    return md5.md5(str(random.random() + time.time())).hexdigest()[:bytes]

def pretty_size(size):
    if size < 1024:
        return '%d bytes' % size
    elif size < 1024 * 1024:
        return '%d kB' % (size / 1024)
    else:
        return '%d MB' % (size / 1024 / 1024)

def pretty_timedelta(time1, time2=None):
    """Calculate time delta (inaccurately, only for decorative purposes ;-) for
    prettyprinting. If time1 is None, the current time is used."""
    if not time1: time1 = time.time()
    if not time2: time2 = time.time()
    if time1 > time2:
        time2, time1 = time1, time2
    units = ((3600 * 24 * 365, 'year',   'years'),
             (3600 * 24 * 30,  'month',  'months'),
             (3600 * 24 * 7,   'week',   'weeks'),
             (3600 * 24,       'day',    'days'),
             (3600,            'hour',   'hours'),
             (60,              'minute', 'minutes'))
    age_s = int(time2 - time1)
    if age_s < 60:
        return '%i second%s' % (age_s, age_s > 1 and 's' or '')
    for u, unit, unit_plural in units:
        r = float(age_s) / float(u)
        if r >= 0.9:
            r = int(round(r))
            return '%d %s' % (r, r == 1 and unit or unit_plural)
    return ''

def create_unique_file(path):
    """Create a new file. An index is added if the path exists"""
    parts = os.path.splitext(path)
    idx = 1
    while 1:
        try:
            flags = os.O_CREAT + os.O_WRONLY + os.O_EXCL
            if hasattr(os, 'O_BINARY'):
                flags += os.O_BINARY
            return path, os.fdopen(os.open(path, flags), 'w')
        except OSError:
            idx += 1
            # A sanity check
            if idx > 100:
                raise Exception('Failed to create unique name: ' + path)
            path = '%s.%d%s' % (parts[0], idx, parts[1])

def get_reporter_id(req):
    name = req.session.get('name', None)
    email = req.session.get('email', None)
    
    if req.authname != 'anonymous':
        return req.authname
    elif name and email:
        return '%s <%s>' % (name, email)
    elif not name and email:
        return email
    else:
        return req.authname

def get_date_format_hint():
    t = time.localtime(0)
    t = (1999, 10, 29, t[3], t[4], t[5], t[6], t[7], t[8])
    tmpl = time.strftime('%x', t)
    return tmpl.replace('1999', 'YYYY', 1).replace('99', 'YY', 1) \
               .replace('10', 'MM', 1).replace('29', 'DD', 1)

def get_datetime_format_hint():
    t = time.localtime(0)
    t = (1999, 10, 29, 23, 59, 58, t[6], t[7], t[8])
    tmpl = time.strftime('%x %X', t)
    return tmpl.replace('1999', 'YYYY', 1).replace('99', 'YY', 1) \
               .replace('10', 'MM', 1).replace('29', 'DD', 1) \
               .replace('23', 'hh', 1).replace('59', 'mm', 1) \
               .replace('58', 'ss', 1)


class TracError(Exception):
    def __init__(self, message, title=None, show_traceback=0):
        Exception.__init__(self, message)
        self.message = message
        self.title = title
        self.show_traceback = show_traceback


class NaivePopen:
   """
   This is a deadlock-safe version of popen that returns
   an object with errorlevel, out (a string) and err (a string).
   (capturestderr may not work under windows.)
   Example: print Popen3('grep spam','\n\nhere spam\n\n').out
   """
   def __init__(self,command,input=None,capturestderr=None):
       outfile=tempfile.mktemp()
       command="( %s ) > %s" % (command,outfile)
       if input:
           infile=tempfile.mktemp()
           open(infile,"w").write(input)
           command=command+" <"+infile
       if capturestderr:
           errfile=tempfile.mktemp()
           command=command+" 2>"+errfile
       self.errorlevel=os.system(command) >> 8
       self.out=open(outfile,"r").read()
       os.remove(outfile)
       if input:
           os.remove(infile)
       self.err = None
       if capturestderr:
           self.err=open(errfile,"r").read()
           os.remove(errfile)


def mydict(items):
    """dict() doesn't exist in python 2.1"""
    d = {}           
    for k, v in items:
        d[k] = v
    return d


if __name__ == '__main__ ':
    pass
    #print pre

