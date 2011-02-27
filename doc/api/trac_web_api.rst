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

      This corresponds to the `~Request.remote_user` when the request
      is targeted to an area requiring authentication, otherwise the
      authname is retrieved from the ``trac_auth`` cookie.

   .. attribute :: Request.href

      An `~trac.web.href.Href` instance for generating *relative* URLs
      pointing to resources within the current Trac environment.

   .. attribute :: Request.abs_href

      An `~trac.web.href.Href` instance for generating *absolute* URLs
      pointing to resources within the current Trac environment.


.. autoclass :: trac.web.api.RequestDone
   :members:

