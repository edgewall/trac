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

   All of the following methods but `execute`, `executemany` and
   `check_select` need to be implemented by the backend-specific
   subclass.

   In addition, the standard methods from :pep:`0249` *Connection
   Objects* are also available.

   .. method :: cast(self, column, type)

      Local SQL dialect for type casting.

      :param column: name of the column
      :param type: generic type (``int``, ``int64``, ``text``)

   .. method :: concat(self, *args):

      Local SQL dialect for string concatenation.

      :param args: values to be concatenated specified as multiple
                   parameters.

   .. method :: like(self):

      Local SQL dialect for a case-insensitive LIKE clause.

   .. method :: like_escape(self, text):

      Local SQL dialect for searching for litteral text in a LIKE
      clause.

   .. method :: quote(self, identifier):

      Local SQL dialect for quoting an identifier.

   .. method :: get_last_id(self, cursor, table, column='id'):

      Local SQL dialect for retrieving the last value of an
      auto-increment column, immediately following an INSERT clause.

      :param cursor: the cursor in which the INSERT was executed
      :param table: the name of the table in which the insertion happened
      :param column: the name of the auto-increment column

      Some backends, like PostgreSQL, support that feature natively
      indirectly via sequences.

   .. method :: update_sequence(self, cursor, table, column='id'):

      Local SQL dialect for resetting a sequence.

      Same parameters as for `get_last_id`.

      This can be used whenever rows were created *with an explicit
      value for the auto-increment column*, as it could happen during
      a database upgrade and the recreation of a table.  See
      :teo:`#8575` for details.


Also, all the `ConnectionWrapper` subclasses (``SQLiteConnection``,
``PostgreSQLConnection`` and ``MySQLConnection``) have a reimplemented
``cursor()`` method which returns an `IterableCursor`.

.. autoclass :: IterableCursor
   :members:
