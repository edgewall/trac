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
import re
import sys
import time
from datetime import tzinfo, timedelta, datetime, date

from trac.core import TracError
from trac.util.text import to_unicode

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
        return datetime(t.year, t.month, t.day, tzinfo=tzinfo or localtz)
    elif isinstance(t, (int,long,float)):
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


# -- formatting

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
    units = ((3600 * 24 * 365, 'year',   'years'),
             (3600 * 24 * 30,  'month',  'months'),
             (3600 * 24 * 7,   'week',   'weeks'),
             (3600 * 24,       'day',    'days'),
             (3600,            'hour',   'hours'),
             (60,              'minute', 'minutes'))
    diff = time2 - time1
    age_s = int(diff.days * 86400 + diff.seconds)
    if resolution and age_s < resolution:
        return ''
    if age_s <= 60 * 1.9:
        return '%i second%s' % (age_s, age_s != 1 and 's' or '')
    for u, unit, unit_plural in units:
        r = float(age_s) / float(u)
        if r >= 1.9:
            r = int(round(r))
            return '%d %s' % (r, r == 1 and unit or unit_plural)
    return ''
    
def format_datetime(t=None, format='%x %X', tzinfo=None):
    """Format the `datetime` object `t` into an `unicode` string

    If `t` is None, the current time will be used.
    
    The formatting will be done using the given `format`, which consist
    of conventional `strftime` keys. In addition the format can be 'iso8601'
    to specify the international date format.

    `tzinfo` will default to the local timezone if left to `None`.
    """
    tz = tzinfo or localtz
    t = to_datetime(t, tzinfo).astimezone(tz)
    normalize_Z = False
    if format.lower().startswith('iso8601'):
        date_only = time_only = False
        if 'date' in format:
            date_only = True
        elif 'time' in format:
            time_only = True
        if date_only:
            format = '%Y-%m-%d'
        elif time_only:
            format = '%H:%M:%S'
        else:
            format = '%Y-%m-%dT%H:%M:%S'
        if not date_only:
            format += '%z'
            normalize_Z = True
    text = t.strftime(format)
    if normalize_Z:
        text = text.replace('+0000', 'Z')
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

_ISO_8601_RE = re.compile(r'(\d\d\d\d)(?:-?(\d\d)(?:-?(\d\d))?)?'   # date
                          r'(?:T(\d\d)(?::?(\d\d)(?::?(\d\d))?)?)?' # time
                          r'(Z?(?:([-+])?(\d\d):?(\d\d)?)?)?$'      # timezone
                          )

def parse_date(text, tzinfo=None):
    tzinfo = tzinfo or localtz
    if text == 'now': # TODO: today, yesterday, etc.
        return datetime.now(utc)
    tm = None
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
        except ValueError:
            pass
    else:
        for format in ['%x %X', '%x, %X', '%X %x', '%X, %x', '%x', '%c',
                       '%b %d, %Y']:
            try:
                tm = time.strptime(text, format)
                break
            except ValueError:
                continue
    if tm == None:
        hint = get_date_format_hint()        
        raise TracError('"%s" is an invalid date, or the date format '
                        'is not known. Try "%s" instead.' % (text, hint),
                        'Invalid Date')
    dt = datetime(*(tm[0:6] + (0, tzinfo)))
    # Make sure we can convert it to a timestamp and back - fromtimestamp()
    # may raise ValueError if larger than platform C localtime() or gmtime()
    try:
        to_datetime(to_timestamp(dt), tzinfo)
    except ValueError:
        raise TracError('The date "%s" is outside valid range. '
                        'Try a date closer to present time.' % (text,),
                        'Invalid Date')
    return dt


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


STDOFFSET = timedelta(seconds=-time.timezone)
if time.daylight:
    DSTOFFSET = timedelta(seconds=-time.altzone)
else:
    DSTOFFSET = STDOFFSET

DSTDIFF = DSTOFFSET - STDOFFSET


class LocalTimezone(tzinfo):
    """A 'local' time zone implementation"""

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


utc = FixedOffset(0, 'UTC')
utcmin = datetime.min.replace(tzinfo=utc)
utcmax = datetime.max.replace(tzinfo=utc)
_epoc = datetime(1970, 1, 1, tzinfo=utc)
_zero = timedelta(0)

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

    def timezone(tzname):
        """Fetch timezone instance by name or raise `KeyError`"""
        return _tzmap[tzname]

    def get_timezone(tzname):
        """Fetch timezone instance by name or return `None`"""
        return _tzmap.get(tzname)

