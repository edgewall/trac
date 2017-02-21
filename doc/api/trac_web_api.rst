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

   See also :extensionpoints:`trac.web.api.IRequestHandler`

.. autoclass :: IRequestFilter
   :members:

   See also :extensionpoints:`trac.web.api.IRequestFilter`

For how the main content itself can be generated, see `trac.web.chrome`.

.. autoclass :: ITemplateStreamFilter
   :members:

   See also :extensionpoints:`trac.web.api.ITemplateStreamFilter`

.. autoclass :: IAuthenticator
   :members:

   See also :extensionpoints:`trac.web.api.IAuthenticator`


Classes
-------

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


Helper Functions
----------------

.. autofunction :: arg_list_to_args
.. autofunction :: parse_arg_list


Exceptions
----------

.. autoexception :: TracNotImplementedError

.. autoexception :: HTTPBadGateway
.. autoexception :: HTTPBadRequest
.. autoexception :: HTTPConflict
.. autoexception :: HTTPExpectationFailed
.. autoexception :: HTTPForbidden
.. autoexception :: HTTPGatewayTimeout
.. autoexception :: HTTPGone
.. autoexception :: HTTPInternalError
.. autoexception :: HTTPLengthRequired
.. autoexception :: HTTPMethodNotAllowed
.. autoexception :: HTTPNotAcceptable
.. autoexception :: HTTPNotFound
.. autoexception :: HTTPNotImplemented
.. autoexception :: HTTPPaymentRequired
.. autoexception :: HTTPPreconditionFailed
.. autoexception :: HTTPProxyAuthenticationRequired
.. autoexception :: HTTPRequestEntityTooLarge
.. autoexception :: HTTPRequestTimeout
.. autoexception :: HTTPRequestUriTooLong
.. autoexception :: HTTPRequestedRangeNotSatisfiable
.. autoexception :: HTTPServiceUnavailable
.. autoexception :: HTTPUnauthorized
.. autoexception :: HTTPUnsupportedMediaType
.. autoexception :: HTTPVersionNotSupported
