# -*- coding: utf-8 -*-
#
# Copyright (C) 2003-2006 Edgewall Software
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
import sys
import time
from datetime import tzinfo, timedelta, datetime

# Date/time utilities

def pretty_timedelta(time1, time2=None, resolution=None):
    """Calculate time delta (inaccurately, only for decorative purposes ;-) for
    prettyprinting. If time1 is None, the current time is used."""
    if not time1: time1 = datetime.now(utc)
    if not time2: time2 = datetime.now(utc)
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
    if age_s < 60:
        return '%i second%s' % (age_s, age_s != 1 and 's' or '')
    for u, unit, unit_plural in units:
        r = float(age_s) / float(u)
        if r >= 0.9:
            r = int(round(r))
            return '%d %s' % (r, r == 1 and unit or unit_plural)
    return ''

def format_datetime(t=None, format='%x %X', tzinfo=None):
    if not tzinfo:
        tzinfo = localtz
    if t is None:
        t = datetime.now(utc)
    if isinstance(t, int):
        t = datetime.fromtimestamp(t, tzinfo)
    t = t.astimezone(tzinfo)
    text = t.strftime(format)
    encoding = locale.getpreferredencoding()
    if sys.platform != 'win32':
        encoding = locale.getlocale(locale.LC_TIME)[1] or encoding
        # the above is broken on win32, e.g. we'd get '437' instead of 'cp437'
    return unicode(text, encoding, 'replace')

def format_date(t=None, format='%x', tzinfo=None):
    return format_datetime(t, format, tzinfo=tzinfo)

def format_time(t=None, format='%X', tzinfo=None):
    return format_datetime(t, format, tzinfo=tzinfo)

def get_date_format_hint():
    t = datetime(1999, 10, 29, tzinfo=utc)
    tmpl = format_date(t, tzinfo=utc)
    return tmpl.replace('1999', 'YYYY', 1).replace('99', 'YY', 1) \
               .replace('10', 'MM', 1).replace('29', 'DD', 1)

def get_datetime_format_hint():
    t = datetime(1999, 10, 29, 23, 59, 58, tzinfo=utc)
    tmpl = format_datetime(t, tzinfo=utc)
    return tmpl.replace('1999', 'YYYY', 1).replace('99', 'YY', 1) \
               .replace('10', 'MM', 1).replace('29', 'DD', 1) \
               .replace('23', 'hh', 1).replace('11', 'hh', 1) \
               .replace('59', 'mm', 1).replace('58', 'ss', 1)

def http_date(t=None):
    """Format t as a rfc822 timestamp"""
    if t is None:
        t = datetime.now(utc)
    t = t.astimezone(utc)
    weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep',
              'Oct', 'Nov', 'Dec']
    return '%s, %02d %s %04d %02d:%02d:%02d GMT' % (
        weekdays[t.weekday()], t.day, months[t.month - 1], t.year,
        t.hour, t.minute, t.second)

def parse_date(text, tzinfo=None):
    tzinfo = tzinfo or localtz
    if text == 'now':
        return datetime.now(utc)
    tm = None
    text = text.strip()
    for format in ['%x %X', '%x, %X', '%X %x', '%X, %x', '%x', '%c',
                   '%b %d, %Y', '%Y-%m-%d']:
        try:
            tm = time.strptime(text, format)
            break
        except ValueError:
            continue
    if tm == None:
        raise ValueError('%s is invalid or not a known date format' % text)
    return datetime(*(tm[0:6] + (0, tzinfo)))

def to_timestamp(dt):
    """Return the corresponding POSIX timestamp"""
    if dt:
        diff = dt - _epoc
        return diff.days * 86400 + diff.seconds
    else:
        return 0


class FixedOffset(tzinfo):
    """Fixed offset in minutes east from UTC."""

    def __init__(self, offset, name):
        self._offset = timedelta(minutes=offset)
        self._name = name

    def utcoffset(self, dt):
        return self._offset

    def tzname(self, dt):
        return self._name

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
        stamp = time.mktime(tt)
        tt = time.localtime(stamp)
        return tt.tm_isdst > 0


utc = FixedOffset(0, 'UTC')
utcmin = datetime.min.replace(tzinfo=utc)
utcmax = datetime.max.replace(tzinfo=utc)
_epoc = datetime(1970, 1, 1, tzinfo=utc)
_zero = timedelta(0)

localtz = LocalTimezone()

try:
    from pytz import all_timezones, timezone
except ImportError:
    # Use a makeshift timezone implementation if pytz is not available.
    # This implementation only supports fixed offset time zones.
    #
    _timezones = [
        FixedOffset(840, 'Etc/GMT-14'), FixedOffset(780, 'Etc/GMT-13'),
        FixedOffset(720, 'Etc/GMT-12'), FixedOffset(660, 'Etc/GMT-11'),
        FixedOffset(600, 'Etc/GMT-10'), FixedOffset(540, 'Etc/GMT-9'),
        FixedOffset(480, 'Etc/GMT-8'),  FixedOffset(420, 'Etc/GMT-7'),
        FixedOffset(360, 'Etc/GMT-6'),  FixedOffset(300, 'Etc/GMT-5'),
        FixedOffset(240, 'Etc/GMT-4'),  FixedOffset(180, 'Etc/GMT-3'),
        FixedOffset(120, 'Etc/GMT-2'),  FixedOffset(60, 'Etc/GMT-1'),
        FixedOffset(0, 'Etc/GMT-0'),    FixedOffset(0, 'Etc/GMT'),
        FixedOffset(0, 'Etc/GMT+0'),    FixedOffset(-60, 'Etc/GMT+1'),
        FixedOffset(-120, 'Etc/GMT+2'), FixedOffset(-180, 'Etc/GMT+3'),
        FixedOffset(-240, 'Etc/GMT+4'), FixedOffset(-300, 'Etc/GMT+5'),
        FixedOffset(-360, 'Etc/GMT+6'), FixedOffset(-420, 'Etc/GMT+7'),
        FixedOffset(-480, 'Etc/GMT+8'), FixedOffset(-540, 'Etc/GMT+9'),
        FixedOffset(-600, 'Etc/GMT+10'), FixedOffset(-660, 'Etc/GMT+11'),
        FixedOffset(-720, 'Etc/GMT+12')]
    all_timezones = [z._name for z in _timezones]
    _tzmap = dict([(z._name, z) for z in _timezones])

    def timezone(zone):
        """Fetch timezone instance by name or raise `KeyError`"""
        return _tzmap[zone]
