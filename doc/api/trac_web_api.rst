:mod:`trac.web.api` -- Trac Web Request Handling
================================================

.. module :: trac.web.api

Primary interface for handling web requests.

Interfaces
----------

The following interfaces allow components to interact at various
stages of the web requests processing pipeline.

.. autoclass :: trac.web.chrome.IRequestHandler
   :members:

.. autoclass :: trac.web.api.IRequestFilter
   :members:

For how the main content itself can be generated, see `trac.web.chrome`.

.. autoclass :: trac.web.api.ITemplateStreamFilter
   :members:

.. autoclass :: trac.web.api.IAuthenticator
   :members:

Important classes
-----------------

.. autoclass :: trac.web.api.Request
   :members:

.. autoclass :: trac.web.api.RequestDone
   :members:

See also `trac.web.href.Href`.
