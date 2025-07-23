:mod:`trac.admin.api` -- Trac Administration panels
===================================================

.. module :: trac.admin.api

Primary interface for managing administration panels.


Interfaces
----------

.. autoclass :: IAdminPanelProvider
   :members:

   See also :extensionpoints:`trac.admin.api.IAdminPanelProvider`

.. autoclass :: IAdminCommandProvider

   See also :extensionpoints:`trac.admin.api.IAdminCommandProvider`

Exceptions
----------

.. autoclass :: AdminCommandError
   :members:

Components
----------

.. autoclass :: AdminCommandManager
   :members:

Classes
-------

.. autoclass :: PathList
   :members:

.. autoclass :: PrefixList
   :members:

Helper Functions
----------------

.. autofunction :: get_console_locale
.. autofunction :: get_dir_list
