# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2018 Edgewall Software
# Copyright (C) 2003-2006 Jonas Borgström <jonas@edgewall.com>
# Copyright (C) 2006 Matthew Good <trac@matt-good.net>
# Copyright (C) 2005-2006 Christian Boos <cboos@edgewall.org>
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

import inspect
import math
import os
import re
import sys
import time
from datetime import tzinfo, timedelta, datetime, date
from locale import getlocale, LC_TIME

try:
    import babel
except ImportError:
    babel = None
else:
    from babel import Locale
    from babel.core import LOCALE_ALIASES, UnknownLocaleError
    from babel.dates import (
        format_datetime as babel_format_datetime,
        format_date as babel_format_date,
        format_time as babel_format_time,
        get_datetime_format, get_date_format,
        get_time_format, get_month_names,
        get_period_names as babel_get_period_names,
        get_day_names
    )
    if 'context' in inspect.getargspec(babel_get_period_names)[0]:
        def get_period_names(locale=None):
            return babel_get_period_names(context='format', locale=locale)
    else:
        get_period_names = babel_get_period_names

from trac.core import TracError
from trac.util.text import to_unicode, getpreferredencoding
from trac.util.translation import _, ngettext

# Date/time utilities

if os.name == 'nt':
    def _precise_now_windows():
        """Provide high-resolution system time if Windows 8+ and Windows
        Server 2012+.
        """
        import ctypes
        from ctypes.wintypes import DWORD, WORD

        kernel32 = ctypes.windll.kernel32
        GetLastError = kernel32.GetLastError
        SystemTimeToFileTime = kernel32.SystemTimeToFileTime
        try:
            # GetSystemTimePreciseAsFileTime is available under Windows 8+
            # and Windows Server 2012+
            GetSystemTimePreciseAsFileTime = \
                kernel32.GetSystemTimePreciseAsFileTime
            get_systime = GetSystemTimePreciseAsFileTime
            func_systime = 'GetSystemTimePreciseAsFileTime'
        except AttributeError:
            GetSystemTimePreciseAsFileTime = None
            get_systime = kernel32.GetSystemTimeAsFileTime
            func_systime = 'GetSystemTimeAsFileTime'

        class FILETIME(ctypes.Structure):
            _fields_ = [('dwLowDateTime', DWORD),
                        ('dwHighDateTime', DWORD)]

        class SYSTEMTIME(ctypes.Structure):
            _fields_ = [('wYear', WORD),
                        ('wMonth', WORD),
                        ('wDayOfWeek', WORD),
                        ('wDay', WORD),
                        ('wHour', WORD),
                        ('wMinute', WORD),
                        ('wSecond', WORD),
                        ('wMilliseconds', WORD)]

        def get_filetime_epoch():
            st = SYSTEMTIME()
            st.wYear = 1970
            st.wMonth = 1
            st.wDay = 1
            st.wDayOfWeek = 0
            st.wHour = st.wMinute = st.wSecond = st.wMilliseconds = 0
            ft = FILETIME()
            if SystemTimeToFileTime(ctypes.pointer(st), ctypes.pointer(ft)):
                return ft.dwHighDateTime * 0x100000000L + ft.dwLowDateTime
            else:
                raise RuntimeError('[LastError SystemTimeToFileTime %d]' %
                                   GetLastError())

        ft_epoch = get_filetime_epoch()

        def time_now():
            """Return the precise current time in seconds since the Epoch."""
            ft = FILETIME()
            if not get_systime(ctypes.pointer(ft)):
                raise RuntimeError('[LastError %s %d]' %
                                   (func_systime, GetLastError()))
            ft = ft.dwHighDateTime * 0x100000000L + ft.dwLowDateTime
            usec = (ft - ft_epoch) / 10L
            return usec / 1000000.0

        def datetime_now(tz=None):
            """Return new datetime with precise current time."""
            return datetime.fromtimestamp(time_now(), tz)

        return time_now, datetime_now

    time_now, datetime_now = _precise_now_windows()
else:
    time_now, datetime_now = time.time, datetime.now

# -- conversion

def to_datetime(t, tzinfo=None):
    """Convert ``t`` into a `datetime` object in the ``tzinfo`` timezone.

    If no ``tzinfo`` is given, the local timezone `localtz` will be used.

    ``t`` is converted using the following rules:

    * If ``t`` is already a `datetime` object,

     * if it is timezone-"naive", it is localized to ``tzinfo``
     * if it is already timezone-aware, ``t`` is mapped to the given
       timezone (`datetime.datetime.astimezone`)

    * If ``t`` is None, the current time will be used.
    * If ``t`` is a number, it is interpreted as a timestamp.

    Any other input will trigger a `TypeError`.

    All returned datetime instances are timezone aware and normalized.
    """
    tz = tzinfo or localtz
    if t is None:
        dt = datetime_now(tz)
    elif isinstance(t, datetime):
        if t.tzinfo:
            dt = t.astimezone(tz)
        else:
            dt = tz.localize(t)
    elif isinstance(t, date):
        dt = tz.localize(datetime(t.year, t.month, t.day))
    elif isinstance(t, (int, long, float)):
        if not (_min_ts <= t <= _max_ts):
            # Handle microsecond timestamps for 0.11 compatibility
            t *= 0.000001
        if t < 0 and isinstance(t, float):
            # Work around negative fractional times bug in Python 2.4
            # http://bugs.python.org/issue1646728
            frac, integer = math.modf(t)
            dt = datetime.fromtimestamp(integer - 1, tz) + \
                    timedelta(seconds=frac + 1)
        else:
            dt = datetime.fromtimestamp(t, tz)
    else:
        dt = None
    if dt:
        return tz.normalize(dt)
    raise TypeError('expecting datetime, int, long, float, or None; got %s' %
                    type(t))

def to_timestamp(dt):
    """Return the corresponding POSIX timestamp"""
    if dt:
        diff = dt - _epoc
        return diff.days * 86400 + diff.seconds
    else:
        return 0

def to_utimestamp(dt):
    """Return a microsecond POSIX timestamp for the given `datetime`."""
    if not dt:
        return 0
    diff = dt - _epoc
    return (diff.days * 86400000000L + diff.seconds * 1000000
            + diff.microseconds)

def from_utimestamp(ts):
    """Return the `datetime` for the given microsecond POSIX timestamp."""
    return _epoc + timedelta(microseconds=ts or 0)

# -- formatting

_units = (
    (3600*24*365, lambda r: ngettext('%(num)d year', '%(num)d years', r)),
    (3600*24*30,  lambda r: ngettext('%(num)d month', '%(num)d months', r)),
    (3600*24*7,   lambda r: ngettext('%(num)d week', '%(num)d weeks', r)),
    (3600*24,     lambda r: ngettext('%(num)d day', '%(num)d days', r)),
    (3600,        lambda r: ngettext('%(num)d hour', '%(num)d hours', r)),
    (60,          lambda r: ngettext('%(num)d minute', '%(num)d minutes', r)))

def pretty_timedelta(time1, time2=None, resolution=None):
    """Calculate time delta between two `datetime` objects.
    (the result is somewhat imprecise, only use for prettyprinting).

    If either `time1` or `time2` is None, the current time will be used
    instead.
    """
    time1 = to_datetime(time1)
    time2 = to_datetime(time2)
    if time1 > time2:
        time2, time1 = time1, time2

    diff = time2 - time1
    age_s = int(diff.days * 86400 + diff.seconds)
    if resolution and age_s < resolution:
        return ''
    if age_s <= 60 * 1.9:
        return ngettext('%(num)i second', '%(num)i seconds', age_s)
    for u, format_units in _units:
        r = float(age_s) / float(u)
        if r >= 1.9:
            r = int(round(r))
            return format_units(r)
    return ''


_BABEL_FORMATS = {
    'datetime': {'short': '%x %H:%M', 'medium': '%x %X', 'long': '%x %X',
                 'full': '%x %X'},
    'date': {'short': '%x', 'medium': '%x', 'long': '%x', 'full': '%x'},
    'time': {'short': '%H:%M', 'medium': '%X', 'long': '%X', 'full': '%X'},
}
_STRFTIME_HINTS = {'%x %X': 'datetime', '%x': 'date', '%X': 'time'}

def _format_datetime_without_babel(t, format):
    text = t.strftime(str(format))
    encoding = getlocale(LC_TIME)[1] or getpreferredencoding() \
               or sys.getdefaultencoding()
    return unicode(text, encoding, 'replace')

def _format_datetime_iso8601(t, format, hint):
    if format != 'full':
        t = t.replace(microsecond=0)
    text = t.isoformat()  # YYYY-MM-DDThh:mm:ss.SSSSSS±hh:mm
    if format == 'short':
        text = text[:16]  # YYYY-MM-DDThh:mm
    elif format == 'medium':
        text = text[:19]  # YYYY-MM-DDThh:mm:ss
    elif text.endswith('+00:00'):
        text = text[:-6] + 'Z'
    if hint == 'date':
        text = text.split('T', 1)[0]
    elif hint == 'time':
        text = text.split('T', 1)[1]
    return unicode(text, 'ascii')

def _format_datetime(t, format, tzinfo, locale, hint):
    t = to_datetime(t, tzinfo or localtz)

    if format == 'iso8601':
        return _format_datetime_iso8601(t, 'long', hint)
    if format in ('iso8601date', 'iso8601time'):
        return _format_datetime_iso8601(t, 'long', format[7:])
    if locale == 'iso8601':
        if format is None:
            format = 'long'
        elif format in _STRFTIME_HINTS:
            hint = _STRFTIME_HINTS[format]
            format = 'long'
        if format in ('short', 'medium', 'long', 'full'):
            return _format_datetime_iso8601(t, format, hint)
        return _format_datetime_without_babel(t, format)

    if babel and locale:
        if format is None:
            format = 'medium'
        elif format in _STRFTIME_HINTS:
            hint = _STRFTIME_HINTS[format]
            format = 'medium'
        if format in ('short', 'medium', 'long', 'full'):
            if hint == 'datetime':
                return babel_format_datetime(t, format, None, locale)
            if hint == 'date':
                return babel_format_date(t, format, locale)
            if hint == 'time':
                return babel_format_time(t, format, None, locale)

    format = _BABEL_FORMATS[hint].get(format, format)
    return _format_datetime_without_babel(t, format)

def format_datetime(t=None, format='%x %X', tzinfo=None, locale=None):
    """Format the `datetime` object `t` into an `unicode` string

    If `t` is None, the current time will be used.

    The formatting will be done using the given `format`, which consist
    of conventional `strftime` keys. In addition the format can be 'iso8601'
    to specify the international date format (compliant with RFC 3339).

    `tzinfo` will default to the local timezone if left to `None`.
    """
    return _format_datetime(t, format, tzinfo, locale, 'datetime')

def format_date(t=None, format='%x', tzinfo=None, locale=None):
    """Convenience method for formatting the date part of a `datetime` object.
    See `format_datetime` for more details.
    """
    return _format_datetime(t, format, tzinfo, locale, 'date')

def format_time(t=None, format='%X', tzinfo=None, locale=None):
    """Convenience method for formatting the time part of a `datetime` object.
    See `format_datetime` for more details.
    """
    return _format_datetime(t, format, tzinfo, locale, 'time')

def get_date_format_hint(locale=None):
    """Present the default format used by `format_date` in a human readable
    form.
    This is a format that will be recognized by `parse_date` when reading a
    date.
    """
    if locale == 'iso8601':
        return 'YYYY-MM-DD'
    if babel and locale:
        format = get_date_format('medium', locale=locale)
        return format.pattern
    return _libc_get_date_format_hint()

def _libc_get_date_format_hint(format=None):
    t = datetime(1999, 10, 29, tzinfo=utc)
    tmpl = format_date(t, tzinfo=utc)
    units = [('1999', 'YYYY'), ('99', 'YY'), ('10', 'MM'), ('29', 'dd')]
    if format:
        units = [(unit[0], '%(' + unit[1] + ')s') for unit in units]
    for unit in units:
        tmpl = tmpl.replace(unit[0], unit[1], 1)
    return tmpl

def get_datetime_format_hint(locale=None):
    """Present the default format used by `format_datetime` in a human readable
    form.
    This is a format that will be recognized by `parse_date` when reading a
    date.
    """
    if locale == 'iso8601':
        return u'YYYY-MM-DDThh:mm:ss±hh:mm'
    if babel and locale:
        date_pattern = get_date_format('medium', locale=locale).pattern
        time_pattern = get_time_format('medium', locale=locale).pattern
        format = get_datetime_format('medium', locale=locale)
        return format.replace('{0}', time_pattern) \
                     .replace('{1}', date_pattern)
    return _libc_get_datetime_format_hint()

def _libc_get_datetime_format_hint(format=None):
    t = datetime(1999, 10, 29, 23, 59, 58, tzinfo=utc)
    tmpl = format_datetime(t, tzinfo=utc)
    ampm = format_time(t, '%p', tzinfo=utc)
    units = []
    if ampm:
        units.append((ampm, 'a'))
    units.extend([('1999', 'YYYY'), ('99', 'YY'), ('10', 'MM'), ('29', 'dd'),
                  ('23', 'hh'), ('11', 'hh'), ('59', 'mm'), ('58', 'ss')])
    if format:
        units = [(unit[0], '%(' + unit[1] + ')s') for unit in units]
    for unit in units:
        tmpl = tmpl.replace(unit[0], unit[1], 1)
    return tmpl

def get_month_names_jquery_ui(req):
    """Get the month names for the jQuery UI datepicker library"""
    locale = req.lc_time
    if locale == 'iso8601':
        locale = req.locale
    if babel and locale:
        month_names = {}
        for width in ('wide', 'abbreviated'):
            names = get_month_names(width, locale=locale)
            month_names[width] = [names[i + 1] for i in xrange(12)]
        return month_names

    return {
        'wide': (
            'January', 'February', 'March', 'April', 'May', 'June', 'July',
            'August', 'September', 'October', 'November', 'December'),
        'abbreviated': (
            'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep',
            'Oct', 'Nov', 'Dec'),
    }

def get_day_names_jquery_ui(req):
    """Get the day names for the jQuery UI datepicker library"""
    locale = req.lc_time
    if locale == 'iso8601':
        locale = req.locale
    if babel and locale:
        day_names = {}
        for width in ('wide', 'abbreviated', 'narrow'):
            names = get_day_names(width, locale=locale)
            day_names[width] = [names[(i + 6) % 7] for i in xrange(7)]
        return day_names

    return {
        'wide': ('Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday',
                 'Friday', 'Saturday'),
        'abbreviated': ('Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'),
        'narrow': ('Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'),
    }

def get_date_format_jquery_ui(locale):
    """Get the date format for the jQuery UI datepicker library."""
    if locale == 'iso8601':
        return 'yy-mm-dd'
    if babel and locale:
        values = {'yyyy': 'yy', 'y': 'yy', 'M': 'm', 'MM': 'mm', 'MMM': 'M',
                  'd': 'd', 'dd': 'dd'}
        return get_date_format('medium', locale=locale).format % values

    t = datetime(1999, 10, 29, tzinfo=utc)
    tmpl = format_date(t, tzinfo=utc)
    return tmpl.replace('1999', 'yy', 1).replace('99', 'y', 1) \
               .replace('10', 'mm', 1).replace('29', 'dd', 1)

def get_time_format_jquery_ui(locale):
    """Get the time format for the jQuery UI timepicker addon."""
    if locale == 'iso8601':
        return 'HH:mm:ssZ'
    if babel and locale:
        values = {'h': 'h', 'hh': 'hh', 'H': 'H', 'HH': 'HH',
                  'm': 'm', 'mm': 'mm', 's': 's', 'ss': 'ss'}
        f = get_time_format('medium', locale=locale).format
        if '%(a)s' in f:
            t = datetime(1999, 10, 29, 23, 59, 58, tzinfo=utc)
            ampm = babel_format_datetime(t, 'a', None, locale)
            values['a'] = 'TT' if ampm[0].isupper() else 'tt'
        return f % values

    t = datetime(1999, 10, 29, 23, 59, 58, tzinfo=utc)
    tmpl = format_time(t, tzinfo=utc)
    ampm = format_time(t, '%p', tzinfo=utc)
    if ampm:
        tmpl = tmpl.replace(ampm, 'TT' if ampm[0].isupper() else 'tt', 1)
    return tmpl.replace('23', 'HH', 1).replace('11', 'hh', 1) \
               .replace('59', 'mm', 1).replace('58', 'ss', 1)

def get_timezone_list_jquery_ui(t=None):
    """Get timezone list for jQuery timepicker addon"""
    def utcoffset(tz, t):  # in minutes
        offset = t.astimezone(get_timezone(tz)).utcoffset()
        return offset.days * 24 * 60 + offset.seconds // 60
    def label(offset):
        sign = '-' if offset < 0 else '+'
        return '%s%02d:%02d' % (sign, abs(offset // 60), offset % 60)
    t = to_datetime(t, utc)
    offsets = set(utcoffset(tz, t) for tz in all_timezones)
    return [{'value': offset, 'label': label(offset)}
            for offset in sorted(offsets)]

def get_first_week_day_jquery_ui(req):
    """Get first week day for jQuery date picker"""
    locale = req.lc_time
    if locale == 'iso8601':
        return 1 # Monday
    if babel and locale:
        if not locale.territory:
            # search first locale which has the same `langauge` and territory
            # in preferred languages
            for l in req.languages:
                l = l.replace('-', '_').lower()
                if l.startswith(locale.language.lower() + '_'):
                    try:
                        l = Locale.parse(l)
                        if l.territory:
                            locale = l
                            break
                    except (UnknownLocaleError, ValueError):
                        pass
        if not locale.territory and locale.language in LOCALE_ALIASES:
            locale = Locale.parse(LOCALE_ALIASES[locale.language])
        return (locale.first_week_day + 1) % 7
    return 0 # Sunday

def get_timepicker_separator_jquery_ui(req):
    locale = req.lc_time
    if locale == 'iso8601':
        return 'T'
    if babel and locale:
        return get_datetime_format('medium', locale=locale) \
               .replace('{0}', '').replace('{1}', '')
    return ' '

def get_period_names_jquery_ui(req):
    # allow to use always English am/pm markers
    english_names = {'am': 'AM', 'pm': 'PM'}
    locale = req.lc_time
    if locale == 'iso8601':
        return {'am': [english_names['am']], 'pm': [english_names['pm']]}
    if babel and locale:
        names = get_period_names(locale=locale)
        return dict((period, [names[period], english_names[period]])
                    for period in ('am', 'pm'))
    else:
        # retrieve names of am/pm from libc
        names = {}
        for period, hour in (('am', 11), ('pm', 23)):
            t = datetime(1999, 10, 29, hour, tzinfo=utc)
            names[period] = [format_datetime(t, '%p', tzinfo=utc),
                             english_names[period]]
        return names

def is_24_hours(locale):
    """Returns `True` for 24 hour time formats."""
    if locale == 'iso8601':
        return True
    t = datetime(1999, 10, 29, 23, tzinfo=utc)
    tmpl = format_datetime(t, tzinfo=utc, locale=locale)
    return '23' in tmpl

def http_date(t=None):
    """Format `datetime` object `t` as a rfc822 timestamp"""
    t = to_datetime(t, utc)
    weekdays = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')
    months = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep',
              'Oct', 'Nov', 'Dec')
    return '%s, %02d %s %04d %02d:%02d:%02d GMT' % (
        weekdays[t.weekday()], t.day, months[t.month - 1], t.year,
        t.hour, t.minute, t.second)


# -- parsing

_ISO_8601_RE = re.compile(r'''
    (\d\d\d\d)(?:-?(\d\d)(?:-?(\d\d))?)?    # date
    (?:
        [T ]
        (\d\d)(?::?(\d\d)(?::?(\d\d)        # time
        (?:[,.](\d{1,6}))?)?)?              # microseconds
    )?
    (                                       # timezone
        Z                                   #   Z
      | ([-+])(\d\d):?(\d\d)?               #   ±hh:mm, ±hhmm, ±hh
    )?
    $''', re.VERBOSE)

def _parse_date_iso8601(text, tzinfo):
    match = _ISO_8601_RE.match(text)
    if match:
        try:
            g = match.groups()
            years = g[0]
            months = g[1] or '01'
            days = g[2] or '01'
            hours, minutes, seconds, useconds = [x or '00' for x in g[3:7]]
            useconds = (useconds + '000000')[:6]
            z = g[7]
            if z:
                tzsign = g[8]
                tzhours = int(g[9] or 0)
                tzminutes = int(g[10] or 0)
                if not (0 <= tzhours < 24 and 0 <= tzminutes < 60):
                    return None
                tz = tzhours * 60 + tzminutes
                if tz == 0:
                    tzinfo = utc
                else:
                    tzinfo = FixedOffset(-tz if tzsign == '-' else tz,
                                         '%s%02d:%02d' % (tzsign, tzhours,
                                                          tzminutes))
            tm = [int(x) for x in (years, months, days,
                                   hours, minutes, seconds, useconds)]
            t = tzinfo.localize(datetime(*tm))
            return tzinfo.normalize(t)
        except (ValueError, OverflowError):
            pass

    return None

def _libc_parse_date(text, tzinfo):
    for format in ('%x %X', '%x, %X', '%X %x', '%X, %x', '%x', '%c',
                   '%b %d, %Y'):
        try:
            tm = time.strptime(text, format)
            dt = tzinfo.localize(datetime(*tm[0:6]))
            return tzinfo.normalize(dt)
        except (ValueError, OverflowError):
            continue
    try:
        return _i18n_parse_date(text, tzinfo, None)
    except (ValueError, OverflowError):
        pass
    return

def parse_date(text, tzinfo=None, locale=None, hint='date'):
    tzinfo = tzinfo or localtz
    text = text.strip()

    dt = _parse_date_iso8601(text, tzinfo)
    if dt is None and locale != 'iso8601':
        if babel and locale:
            dt = _i18n_parse_date(text, tzinfo, locale)
        else:
            dt = _libc_parse_date(text, tzinfo)
    if dt is None:
        dt = _parse_relative_time(text, tzinfo)
    if dt is None:
        formatted_hint = {
            'datetime': get_datetime_format_hint,
            'date': get_date_format_hint,
            'relative': get_datetime_format_hint,
            'iso8601': lambda l: get_datetime_format_hint('iso8601'),
        }.get(hint, lambda(l): hint)(locale)
        if locale == 'iso8601' and hint in ('date', 'datetime') or \
                hint == 'iso8601':
            msg = _('"%(date)s" is an invalid date, or the date format '
                    'is not known. Try "%(hint)s" instead.',
                    date=text, hint=formatted_hint)
        else:
            isohint = get_date_format_hint('iso8601') \
                      if hint == 'date' \
                      else get_datetime_format_hint('iso8601')
            msg = _('"%(date)s" is an invalid date, or the date format is '
                    'not known. Try "%(hint)s" or "%(isohint)s" instead.',
                    date=text, hint=formatted_hint, isohint=isohint)
        raise TracError(msg, _('Invalid Date'))
    # Make sure we can convert it to a timestamp and back - fromtimestamp()
    # may raise ValueError if larger than platform C localtime() or gmtime()
    try:
        datetime.utcfromtimestamp(to_timestamp(dt))
    except (ValueError, OverflowError):
        raise TracError(_('The date "%(date)s" is outside valid range. '
                          'Try a date closer to present time.', date=text),
                          _('Invalid Date'))
    return dt

def _i18n_parse_date_pattern(locale):
    format_keys = {
        'y': ('y', 'Y'),
        'M': ('M',),
        'd': ('d',),
        'h': ('h', 'H'),
        'm': ('m',),
        's': ('s',),
    }

    if locale is None:
        formats = (_libc_get_datetime_format_hint(format=True),
                   _libc_get_date_format_hint(format=True))
    else:
        date_format = get_date_format('medium', locale=locale)
        time_format = get_time_format('medium', locale=locale)
        datetime_format = get_datetime_format('medium', locale=locale)
        formats = (datetime_format.replace('{0}', time_format.format) \
                                  .replace('{1}', date_format.format),
                   date_format.format)

    orders = []
    for format in formats:
        order = []
        for key, chars in format_keys.iteritems():
            for char in chars:
                idx = format.find('%(' + char)
                if idx != -1:
                    order.append((idx, key))
                    break
        order.sort()
        orders.append(dict((key, idx) for idx, (_, key) in enumerate(order)))

    # always allow using English names regardless of locale
    month_names = dict(zip(('jan', 'feb', 'mar', 'apr', 'may', 'jun',
                            'jul', 'aug', 'sep', 'oct', 'nov', 'dec',),
                           xrange(1, 13)))
    period_names = {'am': 'am', 'pm': 'pm'}

    if locale is None:
        for num in xrange(1, 13):
            t = datetime(1999, num, 1, tzinfo=utc)
            names = format_date(t, '%b\t%B', utc).split('\t')
            month_names.update((name.lower(), num) for name in names
                               if str(num) not in name)
        for num, period in ((11, 'am'), (23, 'pm')):
            t = datetime(1999, 1, 1, num, tzinfo=utc)
            name = format_datetime(t, '%p', utc)
            if name:
                period_names[name.lower()] = period
    else:
        if formats[0].find('%(MMM)s') != -1:
            for width in ('wide', 'abbreviated'):
                names = get_month_names(width, locale=locale)
                month_names.update((name.lower(), num)
                                   for num, name in names.iteritems())
        if formats[0].find('%(a)s') != -1:
            names = get_period_names(locale=locale)
            period_names.update((name.lower(), period)
                                for period, name in names.iteritems()
                                if period in ('am', 'pm'))

    regexp = ['[0-9]+']
    regexp.extend(re.escape(name) for name in month_names)
    regexp.extend(re.escape(name) for name in period_names)

    return {
        'orders': orders,
        'regexp': re.compile('(%s)' % '|'.join(regexp), re.IGNORECASE),
        'month_names': month_names,
        'period_names': period_names,
    }

_I18N_PARSE_DATE_PATTERNS = {}
_I18N_PARSE_DATE_PATTERNS_LIBC = {}

def _i18n_parse_date(text, tzinfo, locale):
    if locale is None:
        key = getlocale(LC_TIME)[0]
        patterns = _I18N_PARSE_DATE_PATTERNS_LIBC
    else:
        locale = Locale.parse(locale)
        key = str(locale)
        patterns = _I18N_PARSE_DATE_PATTERNS

    pattern = patterns.get(key)
    if pattern is None:
        pattern = _i18n_parse_date_pattern(locale)
        patterns[key] = pattern

    regexp = pattern['regexp']
    period_names = pattern['period_names']
    month_names = pattern['month_names']
    text = text.lower()
    for order in pattern['orders']:
        try:
            return _i18n_parse_date_0(text, order, regexp, period_names,
                                      month_names, tzinfo)
        except (ValueError, OverflowError):
            continue

    return None

def _i18n_parse_date_0(text, order, regexp, period_names, month_names, tzinfo):
    matches = regexp.findall(text)
    if not matches:
        return None

    # remove am/pm markers on ahead
    period = None
    for idx, match in enumerate(matches):
        period = period_names.get(match)
        if period is not None:
            del matches[idx]
            break

    # for date+time, use 0 seconds if seconds are missing
    if 's' in order and len(matches) == 5:
        matches.insert(order['s'], 0)

    values = {}
    for key, idx in order.iteritems():
        if idx < len(matches):
            value = matches[idx]
            if key == 'y':
                if len(value) == 2 and value.isdigit():
                    value = '20' + value
            values[key] = value

    if 'y' not in values or 'M' not in values or 'd' not in values:
        raise ValueError

    for key in ('y', 'M', 'd'):
        value = values[key]
        value = month_names.get(value)
        if value is not None:
            if key == 'M':
                values[key] = value
            else:
                values[key], values['M'] = values['M'], value
            break

    values = dict((key, int(value)) for key, value in values.iteritems())
    values.setdefault('h', 0)
    values.setdefault('m', 0)
    values.setdefault('s', 0)

    if period and values['h'] <= 12:
        if period == 'am':
            values['h'] %= 12
        elif period == 'pm':
            values['h'] = values['h'] % 12 + 12

    t = tzinfo.localize(datetime(*(values[k] for k in 'yMdhms')))
    return tzinfo.normalize(t)

_REL_FUTURE_RE = re.compile(
    r'(?:in|\+)\s*(\d+\.?\d*)\s*'
    r'(second|minute|hour|day|week|month|year|[hdwmy])s?$')
_REL_PAST_RE = re.compile(
    r'(?:-\s*)?(\d+\.?\d*)\s*'
    r'(second|minute|hour|day|week|month|year|[hdwmy])s?\s*(?:ago)?$')
_time_intervals = dict(
    second=lambda v: timedelta(seconds=v),
    minute=lambda v: timedelta(minutes=v),
    hour=lambda v: timedelta(hours=v),
    day=lambda v: timedelta(days=v),
    week=lambda v: timedelta(weeks=v),
    month=lambda v: timedelta(days=30 * v),
    year=lambda v: timedelta(days=365 * v),
    h=lambda v: timedelta(hours=v),
    d=lambda v: timedelta(days=v),
    w=lambda v: timedelta(weeks=v),
    m=lambda v: timedelta(days=30 * v),
    y=lambda v: timedelta(days=365 * v),
)
_TIME_START_RE = re.compile(r'(this|last|next)\s*'
                            r'(second|minute|hour|day|week|month|year)$')
_time_starts = dict(
    second=lambda now: datetime(now.year, now.month, now.day, now.hour,
                                now.minute, now.second),
    minute=lambda now: datetime(now.year, now.month, now.day, now.hour,
                                now.minute),
    hour=lambda now: datetime(now.year, now.month, now.day, now.hour),
    day=lambda now: datetime(now.year, now.month, now.day),
    week=lambda now: datetime(now.year, now.month, now.day) \
                     - timedelta(days=now.weekday()),
    month=lambda now: datetime(now.year, now.month, 1),
    year=lambda now: datetime(now.year, 1, 1),
)

def _parse_relative_time(text, tzinfo, now=None):
    if now is None:     # now argument for unit tests
        now = datetime_now(tzinfo)
    if text == 'now':
        return now

    dt = None
    if text == 'today':
        dt = _time_starts['day'](now)
    elif text == 'yesterday':
        dt = _time_starts['day'](now) - timedelta(days=1)
    elif text == 'tomorrow':
        dt = _time_starts['day'](now) + timedelta(days=1)
    if dt is None:
        match = _REL_FUTURE_RE.match(text)
        if match:
            (value, interval) = match.groups()
            dt = now + _time_intervals[interval](float(value))
    if dt is None:
        match = _REL_PAST_RE.match(text)
        if match:
            (value, interval) = match.groups()
            dt = now - _time_intervals[interval](float(value))
    if dt is None:
        match = _TIME_START_RE.match(text)
        if match:
            (which, start) = match.groups()
            dt = _time_starts[start](now)
            if which == 'last':
                if start == 'month':
                    if dt.month > 1:
                        dt = dt.replace(month=dt.month - 1)
                    else:
                        dt = dt.replace(year=dt.year - 1, month=12)
                elif start == 'year':
                    dt = dt.replace(year=dt.year - 1)
                else:
                    dt -= _time_intervals[start](1)
            elif which == 'next':
                if start == 'month':
                    if dt.month < 12:
                        dt = dt.replace(month=dt.month + 1)
                    else:
                        dt = dt.replace(year=dt.year + 1, month=1)
                elif start == 'year':
                    dt = dt.replace(year=dt.year + 1)
                else:
                    dt += _time_intervals[start](1)

    if dt is None:
        return None
    if not dt.tzinfo:
        dt = tzinfo.localize(dt)
    return tzinfo.normalize(dt)


# -- formatting/parsing helper functions

def user_time(req, func, *args, **kwargs):
    """A helper function which passes to `tzinfo` and `locale` keyword
    arguments of `func` using `req` parameter. It is expected to be used with
    `format_*` and `parse_date` methods in `trac.util.datefmt` package.

    :param req: a instance of `Request`
    :param func: a function which must accept `tzinfo` and `locale` keyword
                 arguments
    :param args: arguments which pass to `func` function
    :param kwargs: keyword arguments which pass to `func` function
    """
    if 'tzinfo' not in kwargs:
        kwargs['tzinfo'] = getattr(req, 'tz', None)
    if 'locale' not in kwargs:
        kwargs['locale'] = getattr(req, 'lc_time', None)
    return func(*args, **kwargs)

def format_date_or_datetime(format, *args, **kwargs):
    if format == 'date':
        return format_date(*args, **kwargs)
    else:
        return format_datetime(*args, **kwargs)

# -- timezone utilities

class FixedOffset(tzinfo):
    """Fixed offset in minutes east from UTC."""

    def __init__(self, offset, name):
        self._offset = timedelta(minutes=offset)
        self.zone = name

    def __str__(self):
        return self.zone

    def __repr__(self):
        return '<FixedOffset "%s" %s>' % (self.zone, self._offset)

    def utcoffset(self, dt):
        return self._offset

    def tzname(self, dt):
        return self.zone

    def dst(self, dt):
        return _zero

    def localize(self, dt, is_dst=False):
        if dt.tzinfo is not None:
            raise ValueError('Not naive datetime (tzinfo is already set)')
        return dt.replace(tzinfo=self)

    def normalize(self, dt, is_dst=False):
        if dt.tzinfo is None:
            raise ValueError('Naive time (no tzinfo set)')
        return dt


class LocalTimezone(tzinfo):
    """A 'local' time zone implementation"""

    _std_offset = None
    _dst_offset = None
    _dst_diff = None
    _std_tz = None
    _dst_tz = None

    @classmethod
    def _initialize(cls):
        cls._std_offset = timedelta(seconds=-time.timezone)
        cls._std_tz = cls(cls._std_offset)
        if time.daylight:
            cls._dst_offset = timedelta(seconds=-time.altzone)
            cls._dst_tz = cls(cls._dst_offset)
        else:
            cls._dst_offset = cls._std_offset
            cls._dst_tz = cls._std_tz
        cls._dst_diff = cls._dst_offset - cls._std_offset

    def __init__(self, offset=None):
        self._offset = offset

    def __str__(self):
        return self._tzname_offset(self.utcoffset(datetime_now()))

    def __repr__(self):
        if self._offset is None:
            return '<LocalTimezone "%s" %s "%s" %s>' % \
                   (time.tzname[False], self._std_offset,
                    time.tzname[True], self._dst_offset)
        return '<LocalTimezone "%s" %s>' % (self._tzname(), self._offset)

    def _tzname(self):
        if self is self._std_tz:
            return time.tzname[False]
        elif self is self._dst_tz:
            return time.tzname[True]
        elif self._offset is not None:
            return self._tzname_offset(self._offset)
        else:
            return '%s, %s' % time.tzname

    def _tzname_offset(self, offset):
        secs = offset.days * 3600 * 24 + offset.seconds
        hours, rem = divmod(abs(secs), 3600)
        return 'UTC%c%02d:%02d' % ('+-'[secs < 0], hours, rem / 60)

    def _tzinfo(self, dt, is_dst=False):
        tzinfo = dt.tzinfo
        if isinstance(tzinfo, LocalTimezone) and tzinfo._offset is not None:
            return tzinfo

        base_tt = (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second,
                   dt.weekday(), 0)
        local_tt = [None, None]
        for idx in (0, 1):
            try:
                local_tt[idx] = time.localtime(time.mktime(base_tt + (idx,)))
            except (ValueError, OverflowError):
                pass
        if local_tt[0] is local_tt[1] is None:
            return self._std_tz

        std_correct = local_tt[0] and local_tt[0].tm_isdst == 0
        dst_correct = local_tt[1] and local_tt[1].tm_isdst == 1
        if is_dst is None and std_correct is dst_correct:
            if std_correct:
                raise ValueError('Ambiguous time "%s"' % dt)
            if not std_correct:
                raise ValueError('Non existent time "%s"' % dt)
        tt = None
        if std_correct and dst_correct:
            tt = local_tt[bool(is_dst)]
        elif std_correct:
            tt = local_tt[0]
        elif dst_correct:
            tt = local_tt[1]
        if tt:
            utc_ts = to_timestamp(datetime(tzinfo=utc, *tt[:6]))
            tz_offset = timedelta(seconds=utc_ts - time.mktime(tt))
        else:
            dt = dt.replace(tzinfo=utc)
            utc_ts = to_timestamp(dt)
            dt -= timedelta(seconds=21600)
            tt = (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second,
                  dt.weekday(), 0, -1)
            try:
                tz_offset = timedelta(seconds=utc_ts - time.mktime(tt) - 21600)
            except (ValueError, OverflowError):
                return self._std_tz

        # if UTC offset doesn't match timezone offset, create a
        # LocalTimezone instance with the UTC offset (#11563)
        if tz_offset == self._std_offset:
            tz = self._std_tz
        elif tz_offset == self._dst_offset:
            tz = self._dst_tz
        else:
            tz = LocalTimezone(tz_offset)
        return tz

    def _is_dst(self, dt, is_dst=False):
        tz = self._tzinfo(dt, is_dst)
        if tz is self._dst_tz:
            return True
        return False

    def utcoffset(self, dt):
        offset = self._tzinfo(dt)._offset
        if offset.seconds % 60 != 0:
            # Avoid "ValueError: tzinfo.utcoffset() must return a whole
            # number of minutes" (#12617)
            seconds = offset.days * 86400 + offset.seconds
            offset = timedelta(seconds=int((seconds + 30) // 60) * 60)
        return offset

    def dst(self, dt):
        if self._is_dst(dt):
            return self._dst_diff
        else:
            return _zero

    def tzname(self, dt):
        return self._tzinfo(dt)._tzname()

    def localize(self, dt, is_dst=False):
        if dt.tzinfo is not None:
            raise ValueError('Not naive datetime (tzinfo is already set)')
        return dt.replace(tzinfo=self._tzinfo(dt, is_dst))

    def normalize(self, dt, is_dst=False):
        if dt.tzinfo is None:
            raise ValueError('Naive time (no tzinfo set)')
        if dt.tzinfo is localtz: # if not localized, returns without changes
            return dt
        return self.fromutc(dt.replace(tzinfo=self) - dt.utcoffset())

    def fromutc(self, dt):
        if dt.tzinfo is None or dt.tzinfo is not self:
            raise ValueError('fromutc: dt.tzinfo is not self')
        dt = dt.replace(tzinfo=utc)
        try:
            tt = time.localtime(to_timestamp(dt))
        except (ValueError, OverflowError):
            return dt.replace(tzinfo=self._std_tz) + self._std_offset
        # if UTC offset from localtime() doesn't match timezone offset,
        # create a LocalTimezone instance with the UTC offset (#11563)
        new_dt = datetime(*(tt[:6] + (dt.microsecond, utc)))
        tz_offset = new_dt - dt
        if tz_offset == self._std_offset:
            tz = self._std_tz
        elif tz_offset == self._dst_offset:
            tz = self._dst_tz
        else:
            tz = LocalTimezone(tz_offset)
        return new_dt.replace(tzinfo=tz)


utc = FixedOffset(0, 'UTC')
utcmin = datetime.min.replace(tzinfo=utc)
utcmax = datetime.max.replace(tzinfo=utc)
_epoc = datetime(1970, 1, 1, tzinfo=utc)
_zero = timedelta(0)
_min_ts = -(1 << 31)
_max_ts = (1 << 31) - 1

LocalTimezone._initialize()
localtz = LocalTimezone()

STDOFFSET = LocalTimezone._std_offset
DSTOFFSET = LocalTimezone._dst_offset
DSTDIFF = LocalTimezone._dst_diff


# Use a makeshift timezone implementation if pytz is not available.
# This implementation only supports fixed offset time zones.
#
_timezones = [
    FixedOffset(0, 'UTC'),
    FixedOffset(-720, 'GMT -12:00'), FixedOffset(-660, 'GMT -11:00'),
    FixedOffset(-600, 'GMT -10:00'), FixedOffset(-540, 'GMT -9:00'),
    FixedOffset(-480, 'GMT -8:00'),  FixedOffset(-420, 'GMT -7:00'),
    FixedOffset(-360, 'GMT -6:00'),  FixedOffset(-300, 'GMT -5:00'),
    FixedOffset(-240, 'GMT -4:00'),  FixedOffset(-180, 'GMT -3:00'),
    FixedOffset(-120, 'GMT -2:00'),  FixedOffset(-60, 'GMT -1:00'),
    FixedOffset(0, 'GMT'),           FixedOffset(60, 'GMT +1:00'),
    FixedOffset(120, 'GMT +2:00'),   FixedOffset(180, 'GMT +3:00'),
    FixedOffset(240, 'GMT +4:00'),   FixedOffset(300, 'GMT +5:00'),
    FixedOffset(360, 'GMT +6:00'),   FixedOffset(420, 'GMT +7:00'),
    FixedOffset(480, 'GMT +8:00'),   FixedOffset(540, 'GMT +9:00'),
    FixedOffset(600, 'GMT +10:00'),  FixedOffset(660, 'GMT +11:00'),
    FixedOffset(720, 'GMT +12:00'),  FixedOffset(780, 'GMT +13:00'),
    FixedOffset(840, 'GMT +14:00')]
_tzmap = dict([(z.zone, z) for z in _timezones])

all_timezones = [z.zone for z in _timezones]

try:
    import pytz

    _tzoffsetmap = dict([(tz.utcoffset(None), tz) for tz in _timezones
                         if tz.zone != 'UTC'])

    def timezone(tzname):
        """Fetch timezone instance by name or raise `KeyError`"""
        tz = get_timezone(tzname)
        if not tz:
            raise KeyError(tzname)
        return tz

    def get_timezone(tzname):
        """Fetch timezone instance by name or return `None`"""
        try:
            # if given unicode parameter, pytz.timezone fails with:
            # "type() argument 1 must be string, not unicode"
            tz = pytz.timezone(to_unicode(tzname).encode('ascii', 'replace'))
        except (KeyError, IOError):
            tz = _tzmap.get(tzname)
        if tz and tzname.startswith('Etc/'):
            tz = _tzoffsetmap.get(tz.utcoffset(None))
        return tz

    _pytz_zones = [tzname for tzname in pytz.common_timezones
                   if not tzname.startswith('Etc/') and
                      not tzname.startswith('GMT')]
    # insert just the GMT timezones into the pytz zones at the right location
    # the pytz zones already include UTC so skip it
    from bisect import bisect
    _gmt_index = bisect(_pytz_zones, 'GMT')
    all_timezones = _pytz_zones[:_gmt_index] + all_timezones[1:] + \
                    _pytz_zones[_gmt_index:]

except ImportError:
    pytz = None

    def timezone(tzname):
        """Fetch timezone instance by name or raise `KeyError`"""
        return _tzmap[tzname]

    def get_timezone(tzname):
        """Fetch timezone instance by name or return `None`"""
        return _tzmap.get(tzname)
