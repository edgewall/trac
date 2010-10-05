# -*- coding: utf-8 -*-
#
# Copyright (C) 2009 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

from __future__ import with_statement

from .core import Component
from .util import arity
from .util.concurrency import ThreadLocal, threading

__all__ = ["CacheManager", "cached"]


class CachedProperty(object):
    """Cached property descriptor"""
    
    def __init__(self, retriever, id_attr=None):
        self.retriever = retriever
        self.id_attr = id_attr
        self.__doc__ = retriever.__doc__
        
    def __get__(self, instance, owner):
        if instance is None:
            return self
        if self.id_attr is not None:
            id = getattr(instance, self.id_attr)
        else:
            id = "%s.%s.%s" % (owner.__module__,
                               owner.__name__,
                               self.retriever.__name__)
        return CacheManager(instance.env).get(id, self.retriever, instance)
        
    def __delete__(self, instance):
        if self.id_attr is not None:
            id = getattr(instance, self.id_attr)
        else:
            id = '%s.%s.%s' % (instance.__class__.__module__,
                               instance.__class__.__name__,
                               self.retriever.__name__)
        CacheManager(instance.env).invalidate(id)


def cached(fn_or_id=None):
    """Method decorator creating a cached attribute from a data retrieval
    method.
    
    Accessing the cached attribute gives back the cached value. The data
    retrieval method is called as needed by the CacheManager. Invalidating
    the cache for this value is done by `del`eting the attribute.
    
    Note that the cache validity is maintained using a table in the database.
    Cache invalidation is performed within a transaction block, and can be
    nested within another transaction block.
    
    The id used to identify the attribute in the database is constructed from
    the names of the containing module, class and retriever method. If the
    decorator is used in non-signleton (typically non-`Component`) objects,
    an optional string specifying the name of the attribute containing the id
    must be passed to the decorator call as follows:
    {{{
    def __init__(self, env, name):
        self.env = env
        self._metadata_id = 'custom_id.' + name
    
    @cached('_metadata_id')
    def metadata(db):
        ...
    }}}
    
    This decorator requires that the object on which it is used has an `env`
    attribute containing the application `Environment`.

    :since 0.13:
    The data retrieval method used to be called with a single argument `db`
    containing a reference to a database connection.
    This is the same connection that can be retrieved via the normal
    `Environment.db_query` or `Environment.db_transaction`, so this is no
    longer needed, though methods supporting that argument are still supported
    (will be removed in version 0.14). 
    """
    if not hasattr(fn_or_id, '__call__'):
        def decorator(fn):
            return CachedProperty(fn, fn_or_id)
        return decorator
    else:
        return CachedProperty(fn_or_id)


class CacheManager(Component):
    """Cache manager."""

    required = True
    
    def __init__(self):
        self._cache = {}
        self._local = ThreadLocal(meta=None, cache=None)
        self._lock = threading.RLock()
    
    # Public interface
    
    def reset_metadata(self):
        """Reset per-request cache metadata."""
        self._local.meta = self._local.cache = None

    def get(self, id, retriever, instance):
        """Get cached or fresh data for the given id."""
        # Get cache metadata
        local_meta = self._local.meta
        local_cache = self._local.cache
        if local_meta is None:
            # First cache usage in this request, retrieve cache metadata
            # from the database and make a thread-local copy of the cache
            meta = self.env.db_query("SELECT id, generation FROM cache")
            self._local.meta = local_meta = dict(meta)
            self._local.cache = local_cache = self._cache.copy()
        
        db_generation = local_meta.get(id, -1)
        
        # Try the thread-local copy first
        try:
            (data, generation) = local_cache[id]
            if generation == db_generation:
                return data
        except KeyError:
            pass
        
        with self.env.db_transaction as db:
            with self._lock:
                # Get data from the process cache
                try:
                    (data, generation) = local_cache[id] = self._cache[id]
                    if generation == db_generation:
                        return data
                except KeyError:
                    generation = None   # Force retrieval from the database
                
                # Check if the process cache has the newest version, as it may
                # have been updated after the metadata retrieval
                for db_generation, in db(
                        "SELECT generation FROM cache WHERE id=%s", (id,)):
                    break
                else:
                    db_generation = -1
                if db_generation == generation:
                    return data
                
                # Retrieve data from the database
                if arity(retriever) == 2:
                    data = retriever(instance, db)
                else:
                    data = retriever(instance)
                local_cache[id] = self._cache[id] = (data, db_generation)
                local_meta[id] = db_generation
                return data
        
    def invalidate(self, id):
        """Invalidate cached data for the given id."""
        with self.env.db_transaction as db:
            with self._lock:
                # Invalidate in other processes

                # The row corresponding to the cache may not exist in the table
                # yet.
                #  - If the row exists, the UPDATE increments the generation,
                #    the SELECT returns a row and we're done.
                #  - If the row doesn't exist, the UPDATE does nothing, but 
                #    starts a transaction. The SELECT then returns nothing, 
                #    and we can safely INSERT a new row.
                db("UPDATE cache SET generation=generation+1 WHERE id=%s",
                   (id,))
                if not db("SELECT generation FROM cache WHERE id=%s", (id,)):
                    db("INSERT INTO cache VALUES (%s, %s)", (id, 0))
            
            # Invalidate in this process
            self._cache.pop(id, None)
            
            # Invalidate in this thread
            try:
                del self._local.cache[id]
            except (KeyError, TypeError):
                pass
