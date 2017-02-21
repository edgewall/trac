:mod:`trac.perm` -- the Trac permission system
==============================================

.. automodule :: trac.perm
   :exclude-members: PermissionError, IPermissionRequestor, IPermissionStore,
		     IPermissionGroupProvider, IPermissionPolicy,
		     PermissionSystem


Interfaces
----------

.. autoclass :: IPermissionRequestor
   :members:

.. autoclass :: IPermissionStore
   :members:

.. autoclass :: IPermissionGroupProvider
   :members:

.. autoclass :: IPermissionPolicy
   :members:


Components
----------

.. autoclass :: PermissionSystem
   :members:

.. autoclass :: DefaultPermissionGroupProvider
   :members:

.. autoclass :: DefaultPermissionPolicy
   :members:

.. autoclass :: DefaultPermissionStore
   :members:

.. autoclass :: PermissionAdmin
   :members:


Exceptions
----------

.. autoexception :: PermissionError
   :members:

.. autoexception :: PermissionExistsError
   :members:


Miscellaneous
-------------

.. autoclass :: PermissionCache
   :members:

