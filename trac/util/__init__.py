# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2006 Edgewall Software
# Copyright (C) 2003-2004 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2006 Matthew Good <trac@matt-good.net>
# Copyright (C) 2005-2006 Christian Boos <cboos@neuf.fr>
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
#         Matthew Good <trac@matt-good.net>

import locale
import md5
import os
import re
import sys
import time
import tempfile
from urllib import quote, unquote, urlencode

# Imports for backward compatibility
from trac.core import TracError
from trac.util.markup import escape, unescape, Markup, Deuglifier

CRLF = '\r\n'

try:
    reversed = reversed
except NameError:
    def reversed(x):
        if hasattr(x, 'keys'):
            raise ValueError('mappings do not support reverse iteration')
        i = len(x)
        while i > 0:
            i -= 1
            yield x[i]

try:
    sorted = sorted
except NameError:
    def sorted(iterable, cmp=None, key=None, reverse=False):
        """Partial implementation of the "sorted" function from Python 2.4"""
        if key is None:
            lst = list(iterable)
        else:
            lst = [(key(val), idx, val) for idx, val in enumerate(iterable)]
        lst.sort()
        if key is None:
            if reverse:
                return lst[::-1]
            return lst
        if reverse:
            lst = reversed(lst)
        return [i[-1] for i in lst]

def to_utf8(text, charset='iso-8859-15'):
    """Convert a string to UTF-8, assuming the encoding is either UTF-8, ISO
    Latin-1, or as specified by the optional `charset` parameter.

    ''Deprecated in 0.10. You should use `unicode` strings only.''
    """
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

def to_unicode(text, charset=None, lossy=True):
    """Convert a `str` object to an `unicode` object.

    If `charset` is not specified, we'll make some guesses,
    first trying the UTF-8 encoding then trying the locale
    preferred encoding (this differs from the `unicode` function
    which only tries with the locale preferred encoding, in 'strict'
    mode).

    If the `lossy` argument is `True`, which is the default, then
    we use the 'replace' mode:

    If the `lossy` argument is `False`, we fallback to the 'iso-8859-15'
    charset in case of an error (encoding a `str` using 'iso-8859-15'
    will always work, as there's one Unicode character for each byte of
    the input).
    """
    if not isinstance(text, str):
        if isinstance(text, Exception):
            # two possibilities for storing unicode strings in exception data:
            try:
                # custom __str__ method on the exception (e.g. PermissionError)
                return unicode(text)
            except UnicodeError:
                # unicode arguments given to the exception (e.g. parse_date)
                return ' '.join([to_unicode(arg) for arg in text.args])
        return unicode(text)
    errors = lossy and 'replace' or 'strict'
    try:
        if charset:
            return unicode(text, charset, errors)
        else:
            try:
                return unicode(text, 'utf-8')
            except UnicodeError:
                return unicode(text, locale.getpreferredencoding(), errors)
    except UnicodeError:
        return unicode(text, 'iso-8859-15')

def shorten_line(text, maxlen = 75):
    if len(text or '') < maxlen:
        return text
    shortline = text[:maxlen]
    cut = shortline.rfind(' ') + 1 or shortline.rfind('\n') + 1 or maxlen
    shortline = text[:cut]+' ...'
    return shortline

DIGITS = re.compile(r'(\d+)')
def embedded_numbers(s):
    """Comparison function for natural order sorting based on
    http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/214202."""
    pieces = DIGITS.split(s)
    pieces[1::2] = map(int, pieces[1::2])
    return pieces

def hex_entropy(bytes=32):
    import md5
    import random
    return md5.md5(str(random.random())).hexdigest()[:bytes]

def pretty_size(size):
    if size is None:
        return ''

    jump = 512
    if size < jump:
        return '%d bytes' % size

    units = ['kB', 'MB', 'GB', 'TB']
    i = 0
    while size >= jump and i < len(units):
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
    encoding = locale.getpreferredencoding()
    if sys.platform != 'win32':
        encoding = locale.getlocale(locale.LC_TIME)[1] or encoding
        # the above is broken on win32, e.g. we'd get '437' instead of 'cp437'
    return unicode(text, encoding, 'replace')

def format_date(t=None, format='%x', gmt=False):
    return format_datetime(t, format, gmt)

def format_time(t=None, format='%X', gmt=False):
    return format_datetime(t, format, gmt)

def get_date_format_hint():
    t = time.localtime(0)
    t = (1999, 10, 29, t[3], t[4], t[5], t[6], t[7], t[8])
    tmpl = format_date(t)
    return tmpl.replace('1999', 'YYYY', 1).replace('99', 'YY', 1) \
               .replace('10', 'MM', 1).replace('29', 'DD', 1)

def get_datetime_format_hint():
    t = time.localtime(0)
    t = (1999, 10, 29, 23, 59, 58, t[6], t[7], t[8])
    tmpl = format_datetime(t)
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
    return '%s, %02d %s %04d %02d:%02d:%02d GMT' % (
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


class NaivePopen:
    """This is a deadlock-safe version of popen that returns an object with
    errorlevel, out (a string) and err (a string).

    The optional `input`, which must be a `str` object, is first written
    to a temporary file from which the process will read.
    
    (`capturestderr` may not work under Windows 9x.)

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

def doctrim(docstring):
    """Handling Docstring Indentation.

    Picked from PEP 257.
    """
    if not docstring:
        return ''
    # Convert tabs to spaces (following the normal Python rules)
    # and split into a list of lines:
    lines = docstring.expandtabs().splitlines()
    # Determine minimum indentation (first line doesn't count):
    indent = sys.maxint
    for line in lines[1:]:
        stripped = line.lstrip()
        if stripped:
            indent = min(indent, len(line) - len(stripped))
    # Remove indentation (first line is special):
    trimmed = [lines[0].strip()]
    if indent < sys.maxint:
        for line in lines[1:]:
            trimmed.append(line[indent:].rstrip())
    # Strip off trailing and leading blank lines:
    while trimmed and not trimmed[-1]:
        trimmed.pop()
    while trimmed and not trimmed[0]:
        trimmed.pop(0)
    # Return a single string:
    return '\n'.join(trimmed)


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

def unicode_quote(value):
    """A unicode aware version of urllib.quote"""
    return quote(value.encode('utf-8'))

def unicode_unquote(value):
    """A unicode aware version of urllib.unquote.
    
    Take `str` value previously obtained by `unicode_quote`.
    """
    return unquote(value).decode('utf-8')

def unicode_urlencode(params):
    """A unicode aware version of urllib.urlencode"""
    if isinstance(params, dict):
        params = params.items()
    return urlencode([(k, isinstance(v, unicode) and v.encode('utf-8') or v)
                      for k, v in params])
