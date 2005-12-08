# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2003-2004 Edgewall Software
# Copyright (C) 2003-2004 Jonas Borgström <jonas@edgewall.com>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For exact contribution history, see the revision
# history and logs, available at http://projects.edgewall.com/trac/.
#
# Author: Jonas Borgström <jonas@edgewall.com>

import os
import sys
import time
import tempfile
import re
import md5

CRLF = '\r\n'

def escape(text, quotes=True):
    """
    Escapes &, <, > and \" so they are safe to include in HTML output. Quotes
    are only escaped if the `quotes` parameter is `True`; this is only
    necessary for text that is supposed to be inserted in attributes of HTML
    tags.
    """
    if not text:
        return ''
    text = str(text).replace('&', '&amp;') \
                    .replace('<', '&lt;') \
                    .replace('>', '&gt;')
    if quotes:
        text = text.replace('"', '&#34;')
    return text

def unescape(text):
    """
    Reverse-escapes &, <, > and \".
    """
    if not text:
        return ''
    return str(text).replace('&#34;', '"') \
                    .replace('&gt;', '>') \
                    .replace('&lt;', '<') \
                    .replace('&amp;', '&') 

def to_utf8(text, charset='iso-8859-15'):
    """Convert a string to UTF-8, assuming the encoding is either UTF-8, ISO
    Latin-1, or as specified by the optional `charset` parameter."""
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

def shorten_line(text, maxlen = 75):
    if not text:
        return ''
    elif len(text) < maxlen:
        shortline = text
    else:
        last_cut = i = j = -1
        cut = 0
        while cut < maxlen and cut > last_cut:
            last_cut = cut
            i = text.find('[[BR]]', i+1)
            j = text.find('\n', j+1)
            cut = max(i,j)
        if last_cut > 0:
            shortline = text[:last_cut]+' ...'
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
    if size is None:
        return ''

    jump = 512
    if size < jump:
        return '%d bytes' % size

    units = ['kB', 'MB', 'GB', 'TB']
    i = 0
    while size > jump and i < len(units):
        i += 1
        size /= 1024.

    return '%.1f %s' % (size, units[i - 1])

def pretty_timedelta(time1, time2=None, resolution=None):
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
    if resolution and age_s < resolution:
        return ''
    if age_s < 60:
        return '%i second%s' % (age_s, age_s != 1 and 's' or '')
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

# Date/time utilities

def format_datetime(t=None, format='%x %X', gmt=False):
    if t is None:
        t = time.time()
    if not isinstance(t, (list, tuple, time.struct_time)):
        if gmt:
            t = time.gmtime(int(t))
        else:
            t = time.localtime(int(t))

    text = time.strftime(format, t)
    return to_utf8(text)

def format_date(t=None, format='%x', gmt=False):
    return format_datetime(t, format, gmt)

def format_time(t=None, format='%X', gmt=False):
    return format_datetime(t, format, gmt)

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

def http_date(t=None):
    """Format t as a rfc822 timestamp"""
    if t is None:
        t = time.time()
    if not isinstance(t, (list, tuple, time.struct_time)):
        t = time.gmtime(int(t))
    weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep',
              'Oct', 'Nov', 'Dec']
    return '%s, %d %s %04d %02d:%02d:%02d GMT' % (
           weekdays[t.tm_wday], t.tm_mday, months[t.tm_mon - 1], t.tm_year,
           t.tm_hour, t.tm_min, t.tm_sec)

def parse_date(text):
    seconds = None
    text = text.strip()
    for format in ['%x %X', '%x, %X', '%X %x', '%X, %x', '%x', '%c',
                   '%b %d, %Y']:
        try:
            date = time.strptime(text, format)
            seconds = time.mktime(date)
            break
        except ValueError:
            continue
    if seconds == None:
        raise ValueError, '%s is not a known date format.' % text
    return seconds


class TracError(Exception):
    def __init__(self, message, title=None, show_traceback=0):
        Exception.__init__(self, message)
        self.message = message
        self.title = title
        self.show_traceback = show_traceback


class NaivePopen:
    """This is a deadlock-safe version of popen that returns an object with
    errorlevel, out (a string) and err (a string).
    
    (capturestderr may not work under Windows 9x.)

    Example: print Popen3('grep spam','\n\nhere spam\n\n').out
    """
    def __init__(self, command, input=None, capturestderr=None):
        outfile = tempfile.mktemp()
        command = '( %s ) > %s' % (command, outfile)
        if input:
            infile = tempfile.mktemp()
            tmp = open(infile, 'w')
            tmp.write(input)
            tmp.close()
            command = command + ' <' + infile
        if capturestderr:
            errfile = tempfile.mktemp()
            command = command + ' 2>' + errfile
        try:
            self.err = None
            self.errorlevel = os.system(command) >> 8
            outfd = file(outfile, 'r')
            self.out = outfd.read()
            outfd.close()
            if capturestderr:
                errfd = file(errfile,'r')
                self.err = errfd.read()
                errfd.close()
        finally:
            if os.path.isfile(outfile):
                os.remove(outfile)
            if input and os.path.isfile(infile):
                os.remove(infile)
            if capturestderr and os.path.isfile(errfile):
                os.remove(errfile)


def wrap(t, cols=75, initial_indent='', subsequent_indent='',
         linesep=os.linesep):
    try:
        import textwrap
        t = t.strip().replace('\r\n', '\n').replace('\r', '\n')
        wrapper = textwrap.TextWrapper(cols, replace_whitespace = 0,
                                       break_long_words = 0,
                                       initial_indent = initial_indent,
                                       subsequent_indent = subsequent_indent)
        wrappedLines = []
        for line in t.split('\n'):
            wrappedLines += wrapper.wrap(line.rstrip()) or ['']
        return linesep.join(wrappedLines)

    except ImportError:
        return t


def safe__import__(module_name):
    """
    Safe imports: rollback after a failed import.
    
    Initially inspired from the RollbackImporter in PyUnit,
    but it's now much simpler and works better for our needs.
    
    See http://pyunit.sourceforge.net/notes/reloading.html
    """
    already_imported = sys.modules.copy()
    try:
        return __import__(module_name, globals(), locals(), [])
    except Exception, e:
        for modname in sys.modules.copy():
            if not already_imported.has_key(modname):
                del(sys.modules[modname])
        raise e


class Deuglifier(object):
    def __new__(cls):
        self = object.__new__(cls)
        if not hasattr(cls, '_compiled_rules'):
            cls._compiled_rules = re.compile('(?:' + '|'.join(cls.rules()) + ')')
        self._compiled_rules = cls._compiled_rules
        return self
    
    def format(self, indata):
        return re.sub(self._compiled_rules, self.replace, indata)

    def replace(self, fullmatch):
        for mtype, match in fullmatch.groupdict().items():
            if match:
                if mtype == 'font':
                    return '<span>'
                elif mtype == 'endfont':
                    return '</span>'
                return '<span class="code-%s">' % mtype

# Original license for md5crypt:
# Based on FreeBSD src/lib/libcrypt/crypt.c 1.2
#
# "THE BEER-WARE LICENSE" (Revision 42):
# <phk@login.dknet.dk> wrote this file.  As long as you retain this notice you
# can do whatever you want with this stuff. If we meet some day, and you think
# this stuff is worth it, you can buy me a beer in return.   Poul-Henning Kamp

def md5crypt(password, salt, magic='$1$'):
    # /* The password first, since that is what is most unknown */
    # /* Then our magic string */
    # /* Then the raw salt */
    m = md5.new()
    m.update(password + magic + salt)

    # /* Then just as many characters of the MD5(pw,salt,pw) */
    mixin = md5.md5(password + salt + password).digest()
    for i in range(0, len(password)):
        m.update(mixin[i % 16])

    # /* Then something really weird... */
    # Also really broken, as far as I can tell.  -m
    i = len(password)
    while i:
        if i & 1:
            m.update('\x00')
        else:
            m.update(password[0])
        i >>= 1

    final = m.digest()

    # /* and now, just to make sure things don't run too fast */
    for i in range(1000):
        m2 = md5.md5()
        if i & 1:
            m2.update(password)
        else:
            m2.update(final)

        if i % 3:
            m2.update(salt)

        if i % 7:
            m2.update(password)

        if i & 1:
            m2.update(final)
        else:
            m2.update(password)

        final = m2.digest()

    # This is the bit that uses to64() in the original code.

    itoa64 = './0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'

    rearranged = ''
    for a, b, c in ((0, 6, 12), (1, 7, 13), (2, 8, 14), (3, 9, 15), (4, 10, 5)):
        v = ord(final[a]) << 16 | ord(final[b]) << 8 | ord(final[c])
        for i in range(4):
            rearranged += itoa64[v & 0x3f]; v >>= 6

    v = ord(final[11])
    for i in range(2):
        rearranged += itoa64[v & 0x3f]; v >>= 6

    return magic + salt + '$' + rearranged
