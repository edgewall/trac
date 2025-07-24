:mod:`trac.web.main` -- Trac Web Entry Point
============================================

.. module :: trac.web.main

Entry point for dispatching web requests.


`trac.web.dispatch_request`
---------------------------

The WSGI compliant callable.  It adapts the ``environ`` information
passed from the WSGI gateway and retrieve the appropriate
`~trac.env.Environment` from it, creates a `~trac.web.api.Request`
instance and let the `RequestDispatcher` component forward it to the
component implementing a matching `~trac.web.api.IRequestHandler`.

.. autofunction :: dispatch_request


Components
----------

.. autoclass :: RequestDispatcher
   :members:


Classes
-------

.. autoclass :: RequestWithSession


Helper Functions
----------------

.. autofunction :: get_environments
.. autofunction :: get_tracignore_patterns


Miscellaneous
-------------

.. autodata :: default_tracker
