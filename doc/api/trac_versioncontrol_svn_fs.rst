:mod:`trac.versioncontrol.svn_fs` -- Subversion backend for Trac
================================================================

This module can be considered to be private. However, it can serve as
an example implementation of a version control backend.

Speaking of Subversion, we use its ``svn.fs`` layer mainly, which
means we need direct (read) access to the repository content.

.. automodule :: trac.versioncontrol.svn_fs


Components
----------

.. autoclass :: SubversionConnector

Concrete classes
----------------

.. autoclass :: SubversionRepository
   :members:

.. autoclass :: SubversionNode
   :members:

.. autoclass :: SubversionChangeset
   :members:
