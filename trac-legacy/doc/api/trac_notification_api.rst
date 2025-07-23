:mod:`trac.notification.api` -- Trac notification system
========================================================

.. module :: trac.notification.api

Interfaces
----------

.. autoclass:: INotificationDistributor
   :members:

.. autoclass:: INotificationFormatter
   :members:

.. autoclass:: INotificationSubscriber
   :members:

.. autoclass:: IEmailAddressResolver
   :members:

.. autoclass:: IEmailDecorator
   :members:

.. autoclass:: IEmailSender
   :members:

Classes
-------

.. autoclass:: NotificationEvent
   :members:

Components
----------

.. autoclass:: NotificationSystem
   :members:

Functions
---------
.. autofunction:: parse_subscriber_config

.. autofunction:: get_target_id
