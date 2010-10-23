:mod:`trac.env` -- Trac Environment model and APIs
==================================================

.. module :: trac.env

Interfaces
----------

.. autoclass :: trac.env.IEnvironmentSetupParticipant
   :members:

.. autoclass :: trac.env.ISystemInfoProvider
   :members:

Components
----------

The :class:`Environment` is special in the sense it is not only a
:class:`Component`, but also a :class:`ComponentManager`.

.. autoclass :: trac.env.Environment
   :members:
 
Functions
---------

.. autofunction :: trac.env.open_environment



