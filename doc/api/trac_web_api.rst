:mod:`trac.web.api` -- Trac Web Request Handling
================================================

.. module :: trac.web.api

Primary interface for handling web requests.

Interfaces
----------

The following interfaces allow components to interact at various
stages of the web requests processing pipeline.

.. autoclass :: IRequestHandler
   :members:

.. autoclass :: IRequestFilter
   :members:

For how the main content itself can be generated, see `trac.web.chrome`.

.. autoclass :: ITemplateStreamFilter
   :members:

.. autoclass :: IAuthenticator
   :members:

Important classes
-----------------

.. autoclass :: Request
   :members:

   .. attribute :: Request.authname

      The name associated with the user after authentification or
      `'anonymous'` if no authentification took place.


.. autoclass :: trac.web.api.RequestDone
   :members:

See also `trac.web.href.Href`.
