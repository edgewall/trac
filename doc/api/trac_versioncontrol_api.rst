:mod:`trac.versioncontrol.api` -- Trac Version Control APIs
===========================================================

.. automodule :: trac.versioncontrol.api

This module implements an abstraction layer over different kind of
version control systems and the mechanism to access several
heterogeneous repositories under a single "virtual" hierarchy.

This abstraction was derived from the original model built around the
Subversion system (versioned tree, changesets). It gradually became
more general, now aiming at supporting distributed version control
systems (DVCS).


Interfaces
----------

.. autoclass :: IRepositoryConnector
   :members:

.. autoclass :: IRepositoryProvider
   :members:

.. autoclass :: IRepositoryChangeListener
   :members:

Components
----------

.. autoclass :: RepositoryManager
   :members:
 
Exceptions
----------

Subclasses of `ResourceNotFound`.

.. autoclass :: NoSuchChangeset
   :members:

.. autoclass :: NoSuchNode
   :members:

Abstract classes
----------------

.. autoclass :: Repository
   :members:

.. autoclass :: Node
   :members:

.. autoclass :: Changeset
   :members:
