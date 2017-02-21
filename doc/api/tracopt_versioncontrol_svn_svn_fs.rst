:mod:`tracopt.versioncontrol.svn.svn_fs` -- Subversion backend for Trac
=======================================================================

This module can be considered to be private. However, it can serve as
an example implementation of a version control backend.

Speaking of Subversion, we use its ``svn.fs`` layer mainly, which
means we need direct (read) access to the repository content.

Though there's no documentation for the Python API per se, the doxygen
documentation for the `C libraries`_ are usually enough.  Another
possible source of inspiration are the `examples`_ and the helper
classes in the `bindings`_ themselves.

.. _C libraries: http://svn.collab.net/svn-doxygen/files.html
.. _examples: http://svn.apache.org/viewvc/subversion/trunk/tools/examples/
.. _bindings: http://svn.apache.org/viewvc/subversion/trunk/subversion/bindings/swig/python/svn/

.. automodule :: tracopt.versioncontrol.svn.svn_fs


Components
----------

.. autoclass :: SubversionConnector
   :members:

Concrete classes
----------------

.. autoclass :: SubversionRepository
   :members:

.. autoclass :: SubversionNode
   :members:

.. autoclass :: SubversionChangeset
   :members:

Miscellaneous
-------------

.. autoclass :: Pool
   :members:

.. autoclass :: SvnCachedRepository
   :members:
