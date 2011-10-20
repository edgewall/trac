# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2009 Edgewall Software
# Copyright (C) 2003-2006 Jonas Borgström <jonas@edgewall.com>
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

import locale
import math
import re
import sys
import time
from datetime import tzinfo, timedelta, datetime, date

from trac.core import TracError
from trac.util.text import to_unicode
from trac.util.translation import _, ngettext

# Date/time utilities

# -- conversion

def to_datetime(t, tzinfo=None):
    """Convert `t` into a `datetime` object, using the following rules:
    
     - If `t` is already a `datetime` object, it is simply returned.
     - If `t` is None, the current time will be used.
     - If `t` is a number, it is interpreted as a timestamp.
     
    If no `tzinfo` is given, the local timezone will be used.

    Any other input will trigger a `TypeError`.
    """
    if t is None:
        return datetime.now(tzinfo or localtz)
    elif isinstance(t, datetime):
        return t
    elif isinstance(t, date):
        return (tzinfo or localtz).localize(datetime(t.year, t.month, t.day))
    elif isinstance(t, (int, long, float)):
        if not (_min_ts <= t <= _max_ts):
            # Handle microsecond timestamps for 0.11 compatibility
            t *= 0.000001
        if t < 0 and isinstance(t, float):
            # Work around negative fractional times bug in Python 2.4
            # http://bugs.python.org/issue1646728
            frac, integer = math.modf(t)
            return datetime.fromtimestamp(integer - 1, tzinfo or localtz) \
                   + timedelta(seconds=frac + 1)
        return datetime.fromtimestamp(t, tzinfo or localtz)
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

    
def format_datetime(t=None, format='%x %X', tzinfo=None):
    """Format the `datetime` object `t` into an `unicode` string

    If `t` is None, the current time will be used.
    
    The formatting will be done using the given `format`, which consist
    of conventional `strftime` keys. In addition the format can be 'iso8601'
    to specify the international date format (compliant with RFC 3339).

    `tzinfo` will default to the local timezone if left to `None`.
    """
    tz = tzinfo or localtz
    t = to_datetime(t, tzinfo).astimezone(tz)
    normalize_Z = False
    if format.lower().startswith('iso8601'):
        if 'date' in format:
            format = '%Y-%m-%d'
        elif 'time' in format:
            format = '%H:%M:%S%z'
            normalize_Z = True
        else:
            format = '%Y-%m-%dT%H:%M:%S%z'
            normalize_Z = True
    text = t.strftime(str(format))
    if normalize_Z:
        text = text.replace('+0000', 'Z')
        if not text.endswith('Z'):
            text = text[:-2] + ":" + text[-2:]
    encoding = locale.getpreferredencoding() or sys.getdefaultencoding()
    if sys.platform != 'win32' or sys.version_info[:2] > (2, 3):
        encoding = locale.getlocale(locale.LC_TIME)[1] or encoding
        # Python 2.3 on windows doesn't know about 'XYZ' alias for 'cpXYZ'
    return unicode(text, encoding, 'replace')

def format_date(t=None, format='%x', tzinfo=None):
    """Convenience method for formatting the date part of a `datetime` object.
    See `format_datetime` for more details.
    """
    if format == 'iso8601':
        format = 'iso8601date'
    return format_datetime(t, format, tzinfo=tzinfo)

def format_time(t=None, format='%X', tzinfo=None):
    """Convenience method for formatting the time part of a `datetime` object.
    See `format_datetime` for more details.
    """
    if format == 'iso8601':
        format = 'iso8601time'
    return format_datetime(t, format, tzinfo=tzinfo)

def get_date_format_hint():
    """Present the default format used by `format_date` in a human readable
    form.
    This is a format that will be recognized by `parse_date` when reading a
    date.
    """
    t = datetime(1999, 10, 29, tzinfo=utc)
    tmpl = format_date(t, tzinfo=utc)
    return tmpl.replace('1999', 'YYYY', 1).replace('99', 'YY', 1) \
               .replace('10', 'MM', 1).replace('29', 'DD', 1)

def get_datetime_format_hint():
    """Present the default format used by `format_datetime` in a human readable
    form.
    This is a format that will be recognized by `parse_date` when reading a
    date.
    """
    t = datetime(1999, 10, 29, 23, 59, 58, tzinfo=utc)
    tmpl = format_datetime(t, tzinfo=utc)
    return tmpl.replace('1999', 'YYYY', 1).replace('99', 'YY', 1) \
               .replace('10', 'MM', 1).replace('29', 'DD', 1) \
               .replace('23', 'hh', 1).replace('11', 'hh', 1) \
               .replace('59', 'mm', 1).replace('58', 'ss', 1)

def http_date(t=None):
    """Format `datetime` object `t` as a rfc822 timestamp"""
    t = to_datetime(t).astimezone(utc)
    weekdays = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')
    months = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep',
              'Oct', 'Nov', 'Dec')
    return '%s, %02d %s %04d %02d:%02d:%02d GMT' % (
        weekdays[t.weekday()], t.day, months[t.month - 1], t.year,
        t.hour, t.minute, t.second)


# -- parsing

_ISO_8601_RE = re.compile(r'''
    (\d\d\d\d)(?:-?(\d\d)(?:-?(\d\d))?)?    # date
    (?:T(\d\d)(?::?(\d\d)(?::?(\d\d))?)?)?  # time
    (Z?(?:([-+])?(\d\d):?(\d\d)?)?)?$       # timezone
    ''', re.VERBOSE)

def parse_date(text, tzinfo=None, hint='date'):
    tzinfo = tzinfo or localtz
    dt = None
    text = text.strip()
    # normalize ISO time
    match = _ISO_8601_RE.match(text)
    if match:
        try:
            g = match.groups()
            years = g[0]
            months = g[1] or '01'
            days = g[2] or '01'
            hours, minutes, seconds = [x or '00' for x in g[3:6]]
            z, tzsign, tzhours, tzminutes = g[6:10]
            if z:
                tz = timedelta(hours=int(tzhours or '0'),
                               minutes=int(tzminutes or '0')).seconds / 60
                if tz == 0:
                    tzinfo = utc
                else:
                    tzinfo = FixedOffset(tzsign == '-' and -tz or tz,
                                         '%s%s:%s' %
                                         (tzsign, tzhours, tzminutes))
            tm = time.strptime('%s ' * 6 % (years, months, days,
                                            hours, minutes, seconds),
                               '%Y %m %d %H %M %S ')
            dt = tzinfo.localize(datetime(*tm[0:6]))
        except ValueError:
            pass
    if dt is None:
        for format in ['%x %X', '%x, %X', '%X %x', '%X, %x', '%x', '%c',
                       '%b %d, %Y']:
            try:
                tm = time.strptime(text, format)
                dt = tzinfo.localize(datetime(*tm[0:6]))
                break
            except ValueError:
                continue
    if dt is None:
        dt = _parse_relative_time(text, tzinfo)
    if dt is None:
        hint = {'datetime': get_datetime_format_hint,
                'date': get_date_format_hint}.get(hint, lambda: hint)()
        raise TracError(_('"%(date)s" is an invalid date, or the date format '
                          'is not known. Try "%(hint)s" instead.', 
                          date=text, hint=hint), _('Invalid Date'))
    # Make sure we can convert it to a timestamp and back - fromtimestamp()
    # may raise ValueError if larger than platform C localtime() or gmtime()
    try:
        to_datetime(to_timestamp(dt), tzinfo)
    except ValueError:
        raise TracError(_('The date "%(date)s" is outside valid range. '
                          'Try a date closer to present time.', date=text),
                          _('Invalid Date'))
    return dt


_REL_TIME_RE = re.compile(
    r'(\d+\.?\d*)\s*'
    r'(second|minute|hour|day|week|month|year|[hdwmy])s?\s*'
    r'(?:ago)?$')
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
_TIME_START_RE = re.compile(r'(this|last)\s*'
                            r'(second|minute|hour|day|week|month|year)$')
_time_starts = dict(
    second=lambda now: now.replace(microsecond=0),
    minute=lambda now: now.replace(microsecond=0, second=0),
    hour=lambda now: now.replace(microsecond=0, second=0, minute=0),
    day=lambda now: now.replace(microsecond=0, second=0, minute=0, hour=0),
    week=lambda now: now.replace(microsecond=0, second=0, minute=0, hour=0) \
                     - timedelta(days=now.weekday()),
    month=lambda now: now.replace(microsecond=0, second=0, minute=0, hour=0,
                                  day=1),
    year=lambda now: now.replace(microsecond=0, second=0, minute=0, hour=0,
                                  day=1, month=1),
)

def _parse_relative_time(text, tzinfo):
    now = tzinfo.localize(datetime.now())
    if text == 'now':
        return now
    if text == 'today':
        return now.replace(microsecond=0, second=0, minute=0, hour=0)
    if text == 'yesterday':
        return now.replace(microsecond=0, second=0, minute=0, hour=0) \
               - timedelta(days=1)
    match = _REL_TIME_RE.match(text)
    if match:
        (value, interval) = match.groups()
        return now - _time_intervals[interval](float(value))
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
            else:
                dt -= _time_intervals[start](1)
        return dt
    return None


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


STDOFFSET = timedelta(seconds=-time.timezone)
if time.daylight:
    DSTOFFSET = timedelta(seconds=-time.altzone)
else:
    DSTOFFSET = STDOFFSET

DSTDIFF = DSTOFFSET - STDOFFSET


class LocalTimezone(tzinfo):
    """A 'local' time zone implementation"""
    
    def __str__(self):
        return self.tzname(datetime.now())
    
    def __repr__(self):
        return '<LocalTimezone "%s" %s "%s" %s>' % (
            time.tzname[False], STDOFFSET,
            time.tzname[True], DSTOFFSET)

    def utcoffset(self, dt):
        if self._isdst(dt):
            return DSTOFFSET
        else:
            return STDOFFSET

    def dst(self, dt):
        if self._isdst(dt):
            return DSTDIFF
        else:
            return _zero

    def tzname(self, dt):
        return time.tzname[self._isdst(dt)]

    def _isdst(self, dt):
        tt = (dt.year, dt.month, dt.day,
              dt.hour, dt.minute, dt.second,
              dt.weekday(), 0, -1)
        try:
            stamp = time.mktime(tt)
            tt = time.localtime(stamp)
            return tt.tm_isdst > 0
        except OverflowError:
            return False

    def localize(self, dt, is_dst=False):
        if dt.tzinfo is not None:
            raise ValueError('Not naive datetime (tzinfo is already set)')
        return dt.replace(tzinfo=self)

    def normalize(self, dt, is_dst=False):
        if dt.tzinfo is None:
            raise ValueError('Naive time (no tzinfo set)')
        return dt


utc = FixedOffset(0, 'UTC')
utcmin = datetime.min.replace(tzinfo=utc)
utcmax = datetime.max.replace(tzinfo=utc)
_epoc = datetime(1970, 1, 1, tzinfo=utc)
_zero = timedelta(0)
_min_ts = -(1 << 31)
_max_ts = (1 << 31) - 1

localtz = LocalTimezone()

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
    FixedOffset(720, 'GMT +12:00'),  FixedOffset(780, 'GMT +13:00')]
_tzmap = dict([(z.zone, z) for z in _timezones])

all_timezones = [z.zone for z in _timezones]

try:
    import pytz

    _tzoffsetmap = dict([(tz.utcoffset(None), tz) for tz in _timezones
                         if tz.zone != 'UTC'])

    def timezone(tzname):
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

