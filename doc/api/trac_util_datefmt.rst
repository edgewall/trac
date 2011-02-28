:mod:`trac.util.datefmt` -- Date and Time manipulation
======================================================
.. module :: trac.util.datefmt

Since version 0.10, Trac mainly uses `datetime.datetime` objects for
handling date and time values. This enables us to properly deal with
timezones so that time can be shown in the user's own local time.

Conversion
----------

From "anything" to a `datetime`:

.. autofunction :: to_datetime

A `datetime` can be converted to milliseconds and microseconds
timestamps.  The latter is the preferred representation for dates and
times values for storing them in the database, since Trac 0.12.

.. autofunction :: to_timestamp

.. autofunction :: to_utimestamp

Besides `to_datetime`, there's a specialized conversion from
microseconds timestamps to `datetime`:

.. autofunction :: from_utimestamp


Parsing
-------

.. autofunction :: parse_date


Formatting
----------

.. autofunction :: pretty_timedelta

.. autofunction :: format_datetime

Derivatives:

.. autofunction :: format_date

.. autofunction :: format_time

Propose suggestion for date/time input format:

.. autofunction :: get_date_format_hint

.. autofunction :: get_datetime_format_hint

.. autofunction :: http_date

Formatting and parsing according to user preferences:

.. autofunction	:: user_time


Timezone utilities
------------------

.. autoattribute :: trac.util.datefmt.localtz

.. attribute :: trac.util.datefmt.all_timezones

List of all available timezones. If pytz_ is installed, this
corresponds to a rich variety of "official" timezones, otherwise this
corresponds to `FixedOffset` instances, ranging from GMT -12:00 to GMT
+13:00.

.. autofunction :: get_timezone

.. autoclass :: FixedOffset

.. _pytz: http://pytz.sourceforge.net/

