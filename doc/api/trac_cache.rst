:mod:`trac.cache` -- Control of cached data coherency
=====================================================

Trac is a server application which may involve multiple concurrent
processes. The coherency of the data presented to the clients is
ensured by the underlying database and its transaction
handling. However, a server process will not systematically retrieve
data from the database, as various in-memory caches are used for
performance reasons. We could ensure the integrity of those caches in
a single process in presence of multiple threads by the appropriate
use of locking and by updating the caches as needed, but we also need
a mechanism for invalidating the caches in the *other* processes.

The purpose of this module is to provide a `cached` decorator_ which
can annotate a data *retriever* method of a class for turning it into
an attribute working like a cache. This means that an access to this
attribute will only call the underlying retriever method once on first
access, or only once after the cache has been invalidated, even if
this invalidation happened in another process.

.. _decorator: http://docs.python.org/glossary.html#term-decorator

.. module :: trac.cache

Public API
----------

.. autofunction :: cached

Internal API
------------

.. autoclass :: CacheManager
   :members:

The following classes are the descriptors_ created by the `cached`
decorator:

.. _descriptors: http://docs.python.org/glossary.html#term-descriptor

.. autoclass :: CachedSingletonProperty
   :members:

.. autoclass :: CachedProperty
   :members:

Both classes inherit from a common base:

.. autoclass :: CachedPropertyBase
   :members:

.. function :: key_to_id
