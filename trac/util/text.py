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
#         Christian Boos <cboos@neuf.fr>

import locale
import os
import sys
from urllib import quote, unquote, urlencode


CRLF = '\r\n'

# -- Unicode

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


# -- Plain text formatting

def shorten_line(text, maxlen=75):
    if len(text or '') < maxlen:
        return text
    shortline = text[:maxlen]
    cut = shortline.rfind(' ') + 1 or shortline.rfind('\n') + 1 or maxlen
    shortline = text[:cut]+' ...'
    return shortline

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


# -- Conversion

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
