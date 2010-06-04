# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2009 Edgewall Software
# Copyright (C) 2003-2004 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2006 Matthew Good <trac@matt-good.net>
# Copyright (C) 2005-2006 Christian Boos <cboos@neuf.fr>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.
#
# Author: Jonas Borgström <jonas@edgewall.com>
#         Matthew Good <trac@matt-good.net>
#         Christian Boos <cboos@neuf.fr>

import __builtin__
import locale
import os
import re
import sys
from urllib import quote, quote_plus, unquote, urlencode

from trac.util.translation import _


CRLF = '\r\n'

class Empty(unicode):
    """A special tag object evaluating to the empty string"""
    __slots__ = []

empty = Empty()

del Empty # shouldn't be used outside of Trac core


# -- Unicode

def to_unicode(text, charset=None):
    """Convert input to an `unicode` object.

    For a `str` object, we'll first try to decode the bytes using the given
    `charset` encoding (or UTF-8 if none is specified), then we fall back to
    the latin1 encoding which might be correct or not, but at least preserves
    the original byte sequence by mapping each byte to the corresponding
    unicode code point in the range U+0000 to U+00FF.

    Otherwise, a simple `unicode()` conversion is attempted, with some special
    care taken for `Exception` objects.
    """
    if isinstance(text, str):
        try:
            return unicode(text, charset or 'utf-8')
        except UnicodeDecodeError:
            return unicode(text, 'latin1')
    elif isinstance(text, Exception):
        # two possibilities for storing unicode strings in exception data:
        try:
            # custom __str__ method on the exception (e.g. PermissionError)
            return unicode(text)
        except UnicodeError:
            # unicode arguments given to the exception (e.g. parse_date)
            return ' '.join([to_unicode(arg) for arg in text.args])
    return unicode(text)

def exception_to_unicode(e, traceback=False):
    message = '%s: %s' % (e.__class__.__name__, to_unicode(e))
    if traceback:
        from trac.util import get_last_traceback
        traceback_only = get_last_traceback().split('\n')[:-2]
        message = '\n%s\n%s' % (to_unicode('\n'.join(traceback_only)), message)
    return message

_js_quote = {'\\': '\\\\', '"': '\\"', '\b': '\\b', '\f': '\\f',
             '\n': '\\n', '\r': '\\r', '\t': '\\t', "'": "\\'"}
for i in range(0x20) + [ord(c) for c in '&<>']:
    _js_quote.setdefault(chr(i), '\\u%04x' % i)
_js_quote_re = re.compile(r'[\x00-\x1f\\"\b\f\n\r\t\'&<>]')

def javascript_quote(text):
    """Quote strings for inclusion in javascript"""
    if not text:
        return ''
    def replace(match):
        return _js_quote[match.group(0)]
    return _js_quote_re.sub(replace, text)

def unicode_quote(value, safe='/'):
    """A unicode aware version of urllib.quote"""
    return quote(value.encode('utf-8'), safe)

def unicode_quote_plus(value):
    """A unicode aware version of urllib.quote"""
    return quote_plus(value.encode('utf-8'))

def unicode_unquote(value):
    """A unicode aware version of urllib.unquote.
    
    Take `str` value previously obtained by `unicode_quote`.
    """
    return unquote(value).decode('utf-8')

def unicode_urlencode(params):
    """A unicode aware version of urllib.urlencode.
    
    Values set to `empty` are converted to the key alone, without the
    equal sign.
    """
    if isinstance(params, dict):
        params = params.iteritems()
    l = []
    for k, v in params:
        k = quote_plus(str(k))
        if v is empty:
            l.append(k)
        elif isinstance(v, unicode):
            l.append(k + '=' + quote_plus(v.encode('utf-8')))
        else:
            l.append(k + '=' + quote_plus(str(v)))
    return '&'.join(l)

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


class unicode_passwd(unicode):
    """Conceal the actual content of the string when `repr` is called."""
    def __repr__(self):
        return '*******'

def console_print(out, *args, **kwargs):
    cons_charset = getattr(out, 'encoding', None)
    # Windows returns 'cp0' to indicate no encoding
    if cons_charset in (None, 'cp0'):
        cons_charset = 'utf-8'
    out.write(' '.join([to_unicode(a).encode(cons_charset, 'replace') 
                        for a in args]))
    if kwargs.get('newline', True):
        out.write('\n')

def printout(*args, **kwargs):
    console_print(sys.stdout, *args, **kwargs)

def printerr(*args, **kwargs):
    console_print(sys.stderr, *args, **kwargs)

def raw_input(prompt):
    printout(prompt, newline=False)
    return to_unicode(__builtin__.raw_input(), sys.stdin.encoding)

# -- Plain text formatting

def print_table(data, headers=None, sep='  ', out=None):
    if out is None:
        out = sys.stdout
    charset = getattr(out, 'encoding', None) or 'utf-8'
    data = list(data)
    if headers:
        data.insert(0, headers)
    elif not data:
        return

    num_cols = len(data[0]) # assumes all rows are of equal length
    col_width = []
    for idx in range(num_cols):
        col_width.append(max([len(unicode(d[idx] or '')) for d in data]))

    out.write('\n')
    for ridx, row in enumerate(data):
        for cidx, cell in enumerate(row):
            if headers and ridx == 0:
                sp = ('%%%ds' % len(sep)) % ' '  # No separator in header
            else:
                sp = sep
            if cidx + 1 == num_cols:
                sp = '' # No separator after last column

            line = (u'%%-%ds%s' % (col_width[cidx], sp)) % (cell or '')
            if isinstance(line, unicode):
                line = line.encode(charset, 'replace')
            out.write(line)

        out.write('\n')
        if ridx == 0 and headers:
            out.write(''.join(['-' for x in xrange(0, len(sep) * cidx +
                                                      sum(col_width))]))
            out.write('\n')

    out.write('\n')

def shorten_line(text, maxlen=75):
    if len(text or '') < maxlen:
        return text
    cut = max(text.rfind(' ', 0, maxlen), text.rfind('\n', 0, maxlen))
    if cut < 0:
        cut = maxlen
    return text[:cut] + ' ...'

def wrap(t, cols=75, initial_indent='', subsequent_indent='',
         linesep=os.linesep):
    try:
        import textwrap
        t = t.strip().replace('\r\n', '\n').replace('\r', '\n')
        wrapper = textwrap.TextWrapper(cols, replace_whitespace=0,
                                       break_long_words=0,
                                       initial_indent=initial_indent,
                                       subsequent_indent=subsequent_indent)
        wrappedLines = []
        for line in t.split('\n'):
            wrappedLines += wrapper.wrap(line.rstrip()) or ['']
        return linesep.join(wrappedLines)

    except ImportError:
        return t

def obfuscate_email_address(address):
    if address:
        at = address.find('@')
        if at != -1:
            return address[:at] + u'@\u2026' + \
                   (address[-1] == '>' and '>' or '')
    return address

def breakable_path(path):
    """Make a path breakable after path separators, and conversely, avoid
    breaking at spaces.
    """
    if not path:
        return path
    prefix = ''
    if path.startswith('/'):    # Avoid breaking after a leading /
        prefix = '/'
        path = path[1:]
    return prefix + path.replace('/', u'/\u200b').replace('\\', u'\\\u200b') \
                        .replace(' ', u'\u00a0')

def normalize_whitespace(text, to_space=u'\u00a0', remove=u'\u200b'):
    """Normalize whitespace in a string, by replacing special spaces by normal
    spaces and removing zero-width spaces."""
    if not text:
        return text
    for each in to_space:
        text = text.replace(each, ' ')
    for each in remove:
        text = text.replace(each, '')
    return text

# -- Conversion

def pretty_size(size, format='%.1f'):
    if size is None:
        return ''

    jump = 1024
    if size < jump:
        return _('%(size)s bytes', size=size)

    units = ['KB', 'MB', 'GB', 'TB']
    i = 0
    while size >= jump and i < len(units):
        i += 1
        size /= 1024.

    return (format + ' %s') % (size, units[i - 1])

def expandtabs(s, tabstop=8, ignoring=None):
    if '\t' not in s:
        return s
    if ignoring is None:
        return s.expandtabs(tabstop)

    outlines = []
    for line in s.split('\n'):
        if '\t' not in line:
            outlines.append(line)
            continue
        p = 0
        s = []
        for c in line:
            if c == '\t':
                n = tabstop - p % tabstop
                s.append(' ' * n)
                p += n
            elif not ignoring or c not in ignoring:
                p += 1
                s.append(c)
            else:
                s.append(c)
        outlines.append(''.join(s))
    return '\n'.join(outlines)

