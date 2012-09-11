:mod:`trac.db.api` -- Trac DB abstraction layer
===============================================

.. module :: trac.db.api


Interfaces
----------

.. autoclass :: IDatabaseConnector
   :members:

   See also :extensionpoints:`trac.db.api.IDatabaseConnector`.


Classes
-------

The following classes are not meant to be used directly, but rather
via the `~trac.env.Environment` methods
`~trac.env.Environment.db_transaction` and
`~trac.env.Environment.db_query`.

.. autoclass :: QueryContextManager
   :show-inheritance:
   :members:

.. autoclass :: TransactionContextManager
   :show-inheritance:
   :members:

The above are both subclasses of `DbContextManager`:

.. autoclass :: DbContextManager
   :members:


Components
----------

.. autoclass :: DatabaseManager
   :members:


Functions
---------

.. autofunction :: get_column_names

.. autofunction :: with_transaction


See also
--------

:teo:`wiki/TracDev/DatabaseApi`

