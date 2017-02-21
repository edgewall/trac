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

.. note ::

   The `IRequestHandler.process_request` method plays a major role
   during the compatibility period in which both the legacy Genshi
   templates and the new Jinja2 templates are supported by Trac.

   The return type of `(template_name, data, content_type)` tuple is
   still supported, and when it is used, it is interpreted as an
   indication that the template is actually a legacy Genshi template,
   and not a Jinja2 template.  For the same backward compatibility
   reasons, returning `(template, data, None)` is interpreted as
   specifying a `content_type` of `None` (i.e. ending up with the
   `"text/html"` default).

   This support for legacy Genshi templates will be removed in Trac
   1.5.1, where only the new API will be supported. At that point, if
   the third value in the returned tuple is `None`, this will have the
   same effect as returning only a `(template, data)` pair or
   `(template, data, {})` triple (i.e. an empty metadata dict).

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
.. autofunction :: is_valid_default_handler


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
