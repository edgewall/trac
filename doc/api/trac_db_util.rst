:mod:`trac.db.utils` -- Trac DB utilities
=========================================

.. module :: trac.db.util

Utilities for the Trac DB abstraction layer.

Classes
-------

The following classes are not meant to be used directly.
In particular, the `ConnectionWrapper` is what the 
`~trac.db.api.DbContextManager` context managers will return.

For example::

  >>> with env.db_query as db:
  ...     for name, value in db.execute("SELECT name, value FROM system"):
  ...         print "row: [{name}, {value}]".format(name=name, value=value)
  ...
  row: [database_version, 29]

Here ``db`` is a `ConnectionWrapper`.

.. autoclass :: ConnectionWrapper
   :members:


All the `ConnectionWrapper` subclasses (``SQLiteConnection``,
``PostgreSQLConnection`` and ``MySQLConnection``) have a reimplemented
``cursor()`` method which returns an `IterableCursor`.

.. autoclass :: IterableCursor
   :members:
