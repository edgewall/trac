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
import textwrap
from urllib import quote, quote_plus, unquote
from unicodedata import east_asian_width

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


def path_to_unicode(path):
    """Convert a filesystem path to unicode, using the filesystem encoding."""
    if isinstance(path, str):
        try:
            return unicode(path, sys.getfilesystemencoding())
        except UnicodeDecodeError:
            return unicode(path, 'latin1')
    return unicode(path)


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
    """A unicode aware version of `urllib.quote`

    :param value: anything that converts to a `str`. If `unicode`
                  input is given, it will be UTF-8 encoded.
    :param safe: as in `quote`, the characters that would otherwise be
                 quoted but shouldn't here (defaults to '/')
    """
    return quote(isinstance(value, unicode) and value.encode('utf-8') or
                 str(value), safe)


def unicode_quote_plus(value, safe=''):
    """A unicode aware version of `urllib.quote_plus`.

    :param value: anything that converts to a `str`. If `unicode`
                  input is given, it will be UTF-8 encoded.
    :param safe: as in `quote_plus`, the characters that would
                 otherwise be quoted but shouldn't here (defaults to
                 '/')
    """
    return quote_plus(isinstance(value, unicode) and value.encode('utf-8') or
                      str(value), safe)


def unicode_unquote(value):
    """A unicode aware version of `urllib.unquote`.
    
    :param str: UTF-8 encoded `str` value (for example, as obtained by
                `unicode_quote`).
    :rtype: `unicode`
    """
    return unquote(value).decode('utf-8')


def unicode_urlencode(params, safe=''):
    """A unicode aware version of `urllib.urlencode`.
    
    Values set to `empty` are converted to the key alone, without the
    equal sign.
    """
    if isinstance(params, dict):
        params = params.iteritems()
    l = []
    for k, v in params:
        if v is empty:
            l.append(unicode_quote_plus(k, safe))
        else:
            l.append(unicode_quote_plus(k, safe) + '=' + 
                     unicode_quote_plus(v, safe))
    return '&'.join(l)


_qs_quote_safe = ''.join(chr(c) for c in xrange(0x21, 0x7f))

def quote_query_string(text):
    """Quote strings for query string
    """
    return unicode_quote_plus(text, _qs_quote_safe)

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

def text_width(text, ambiwidth=1):
    """Determine the column width of `text` in Unicode characters.

    The characters in the East Asian Fullwidth (F) or East Asian Wide (W)
    have a column width of 2. The other characters in the East Asian
    Halfwidth (H) or East Asian Narrow (Na) have a column width of 1.

    That `ambiwidth` parameter is used for the column width of the East
    Asian Ambiguous (A). If `1`, the same width as characters in US-ASCII.
    This is expected by most users. If `2`, twice the width of US-ASCII
    characters. This is expected by CJK users.

    cf. http://www.unicode.org/reports/tr11/.
    """
    twice = ('FW', 'FWA')[ambiwidth == 2]
    return sum([(1, 2)[east_asian_width(chr) in twice]
                for chr in to_unicode(text)])

_default_ambiwidth = 1  # Default width of East Asian Ambiguous (A)
if os.name == 'nt':
    try:
        # `ctypes` is available since Python 2.5
        import ctypes
        codepage = ctypes.windll.kernel32.GetConsoleOutputCP()
    except ImportError:
        # Try to retrieve the codepage from stderr and stdout
        codepage = (sys.stderr.encoding or sys.stdout.encoding or '')[2:]
        codepage = codepage.isdigit() and int(codepage) or 0

    if codepage in (932,  # Japanese (Shift-JIS)
                    936,  # Chinese Simplified (GB2312)
                    949,  # Korean (Unified Hangul Code)
                    950): # Chinese Traditional (Big5)
        _default_ambiwidth = 2
    del codepage
else:
    if re.match(r'zh|ja|kr', os.environ.get('LANG') or '', re.IGNORECASE):
        _default_ambiwidth = 2


def print_table(data, headers=None, sep='  ', out=None, ambiwidth=None):
    """Print `data` as a table in the terminal.

    That `ambiwidth` parameter is used for the column width of the East
    Asian Ambiguous (A). If None, detect ambiwidth with the locale settings.
    If others, pass to the `ambiwidth` parameter of `text_width`.
    """
    if out is None:
        out = sys.stdout
    charset = getattr(out, 'encoding', None) or 'utf-8'
    if ambiwidth is None:
        ambiwidth = _default_ambiwidth
    data = list(data)
    if headers:
        data.insert(0, headers)
    elif not data:
        return

    # Convert to an unicode object with `to_unicode`. If None, convert to a
    # empty string.
    def to_text(val):
        if val is None:
            return u''
        return to_unicode(val)

    def tw(text):
        return text_width(text, ambiwidth=ambiwidth)

    # Convert each cell to an unicode object
    data = [[to_text(cell) for cell in row] for row in data]

    num_cols = len(data[0]) # assumes all rows are of equal length
    col_width = [max(tw(row[idx]) for row in data)
                 for idx in xrange(num_cols)]

    out.write('\n')
    for ridx, row in enumerate(data):
        for cidx, cell in enumerate(row):
            if headers and ridx == 0:
                sp = '%*s' % (tw(sep), ' ') # No separator in header
            else:
                sp = sep
            if cidx + 1 == num_cols:
                sp = '' # No separator after last column

            line = u'%-*s%s' % (col_width[cidx] - tw(cell) + len(cell),
                                cell, sp)
            line = line.encode(charset, 'replace')
            out.write(line)

        out.write('\n')
        if ridx == 0 and headers:
            out.write('-' * (tw(sep) * cidx + sum(col_width)))
            out.write('\n')

    out.write('\n')


def shorten_line(text, maxlen=75):
    if len(text or '') < maxlen:
        return text
    cut = max(text.rfind(' ', 0, maxlen), text.rfind('\n', 0, maxlen))
    if cut < 0:
        cut = maxlen
    return text[:cut] + ' ...'


class UnicodeTextWrapper(textwrap.TextWrapper):
    breakable_char_ranges = [
        (0x1100, 0x11FF),   # Hangul Jamo
        (0x2E80, 0x2EFF),   # CJK Radicals Supplement
        (0x3000, 0x303F),   # CJK Symbols and Punctuation
        (0x3040, 0x309F),   # Hiragana
        (0x30A0, 0x30FF),   # Katakana
        (0x3130, 0x318F),   # Hangul Compatibility Jamo
        (0x3190, 0x319F),   # Kanbun
        (0x31C0, 0x31EF),   # CJK Strokes
        (0x3200, 0x32FF),   # Enclosed CJK Letters and Months
        (0x3300, 0x33FF),   # CJK Compatibility
        (0x3400, 0x4DBF),   # CJK Unified Ideographs Extension A
        (0x4E00, 0x9FFF),   # CJK Unified Ideographs
        (0xA960, 0xA97F),   # Hangul Jamo Extended-A
        (0xAC00, 0xD7AF),   # Hangul Syllables
        (0xD7B0, 0xD7FF),   # Hangul Jamo Extended-B
        (0xF900, 0xFAFF),   # CJK Compatibility Ideographs
        (0xFE30, 0xFE4F),   # CJK Compatibility Forms
        (0xFF00, 0xFFEF),   # Halfwidth and Fullwidth Forms
        (0x20000, 0x2FFFF, u'[\uD840-\uD87F][\uDC00-\uDFFF]'), # Plane 2
        (0x30000, 0x3FFFF, u'[\uD880-\uD8BF][\uDC00-\uDFFF]'), # Plane 3
    ]

    split_re = None
    breakable_re = None

    @classmethod
    def _init_patterns(cls):
        char_ranges = []
        surrogate_pairs = []
        for val in cls.breakable_char_ranges:
            try:
                high = unichr(val[0])
                low = unichr(val[1])
                char_ranges.append(u'%s-%s' % (high, low))
            except ValueError:
                # Narrow build, `re` cannot use characters >= 0x10000
                surrogate_pairs.append(val[2])
        char_ranges = u''.join(char_ranges)
        if surrogate_pairs:
            pattern = u'(?:[%s]|%s)+' % (char_ranges,
                                         u'|'.join(surrogate_pairs))
        else:
            pattern = u'[%s]+' % char_ranges

        cls.split_re = re.compile(
            ur'(\s+|' +                                 # any whitespace
            pattern + u'|' +                            # breakable text
            ur'[^\s\w]*\w+[^0-9\W]-(?=\w+[^0-9\W])|' +  # hyphenated words
            ur'(?<=[\w\!\"\'\&\.\,\?])-{2,}(?=\w))',    # em-dash
            re.UNICODE)
        cls.breakable_re = re.compile(ur'\A' + pattern, re.UNICODE)

    def __init__(self, cols, replace_whitespace=0, break_long_words=0,
                 initial_indent='', subsequent_indent='', ambiwidth=1):
        textwrap.TextWrapper.__init__(
                self, cols, replace_whitespace=0, break_long_words=0,
                initial_indent=initial_indent,
                subsequent_indent=subsequent_indent)
        self.ambiwidth = ambiwidth
        if self.split_re is None:
            self._init_patterns()

    def _split(self, text):
        chunks = self.split_re.split(to_unicode(text))
        chunks = filter(None, chunks)
        return chunks

    def _text_width(self, text):
        return text_width(text, ambiwidth=self.ambiwidth)

    def _wrap_chunks(self, chunks):
        lines = []
        chunks.reverse()
        text_width = self._text_width

        while chunks:
            cur_line = []
            cur_width = 0

            if lines:
                indent = self.subsequent_indent
            else:
                indent = self.initial_indent
            width = self.width - text_width(indent)

            if chunks[-1].strip() == '' and lines:
                del chunks[-1]

            while chunks:
                chunk = chunks[-1]
                w = text_width(chunk)
                if cur_width + w <= width:
                    cur_line.append(chunks.pop())
                    cur_width += w
                elif self.breakable_re.match(chunk):
                    left_space = width - cur_width
                    for i in xrange(len(chunk)):
                        w = text_width(chunk[i])
                        if left_space < w:
                            break
                        left_space -= w
                    if i > 0:
                        cur_line.append(chunk[:i])
                        chunk = chunk[i:]
                        chunks[-1] = chunk
                    w = text_width(chunk)
                    break
                else:
                    break

            if chunks and w > width:
                self._handle_long_word(chunks, cur_line, cur_width, width)

            if cur_line and cur_line[-1].strip() == '':
                del cur_line[-1]

            if cur_line:
                lines.append(indent + ''.join(cur_line))

        return lines


def wrap(t, cols=75, initial_indent='', subsequent_indent='',
         linesep=os.linesep, ambiwidth=1):
    """Wraps the single paragraph in `t`, which contains unicode characters.
    The every line is at most `cols` characters long.

    That `ambiwidth` parameter is used for the column width of the East
    Asian Ambiguous (A). If `1`, the same width as characters in US-ASCII.
    This is expected by most users. If `2`, twice the width of US-ASCII
    characters. This is expected by CJK users.
    """
    t = t.strip().replace('\r\n', '\n').replace('\r', '\n')
    wrapper = UnicodeTextWrapper(cols, replace_whitespace=0,
                                 break_long_words=0,
                                 initial_indent=initial_indent,
                                 subsequent_indent=subsequent_indent,
                                 ambiwidth=ambiwidth)
    wrappedLines = []
    for line in t.split('\n'):
        wrappedLines += wrapper.wrap(line.rstrip()) or ['']
    return linesep.join(wrappedLines)


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


def fix_eol(text, eol):
    """Fix end-of-lines in a text."""
    lines = text.splitlines()
    lines.append('')
    return eol.join(lines)

def unicode_to_base64(text, strip_newlines=True):
    """Safe conversion of ``text`` to base64 representation using
    utf-8 bytes.  

    Strips newlines from output unless ``strip_newlines`` is `False`.
    """
    text = to_unicode(text)
    if strip_newlines:
        return text.encode('utf-8').encode('base64').replace('\n', '')
    return text.encode('utf-8').encode('base64')

def unicode_from_base64(text):
    """Safe conversion of ``text`` to unicode based on utf-8 bytes."""
    return text.decode('base64').decode('utf-8')
