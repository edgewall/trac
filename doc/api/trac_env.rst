:mod:`trac.env` -- Trac Environment model and APIs
==================================================

.. module :: trac.env

Interfaces
----------

.. autoclass :: trac.env.IEnvironmentSetupParticipant
   :members:

   See also :extensionpoints:`trac.env.IEnvironmentSetupParticipant`

.. autoclass :: trac.env.ISystemInfoProvider
   :members:

   See also :extensionpoints:`trac.env.ISystemInfoProvider`


Components
----------

The `Environment` is special in the sense it is not only a
`Component`, but also a `trac.core.ComponentManager`.

.. autoclass :: trac.env.Environment
   :members:

.. autoclass :: EnvironmentSetup
   :members:

.. autoclass :: EnvironmentAdmin
   :members:


Functions
---------

.. autofunction :: trac.env.open_environment


Exceptions
----------

.. autoexception :: BackupError
   :members:
