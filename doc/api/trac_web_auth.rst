:mod:`trac.web.auth` -- Trac Authentication
===========================================

.. module :: trac.web.auth

This module deals with web request authentication, and provides the
default implementation for the `~trac.web.api.IAuthenticator`
interface.


Component
---------

.. autoclass :: LoginModule
   :members:


Support Classes
---------------

A few classes are provided for directly computing the REMOTE_USER
information from the HTTP headers for Basic or Digest authentication.
This will be used by the
`~trac.web.standalone.AuthenticationMiddleware`.

.. autoclass :: BasicAuthentication
   :members:

.. autoclass :: DigestAuthentication
   :members:

