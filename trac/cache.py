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

try:
    import threading
except ImportError:
    import dummy_threading as threading

from trac.core import Component
from trac.db.util import with_transaction
from trac.util.compat import partial

__all__ = ["CacheManager", "cached", "cached_value"]


class cached_value(object):
    """Method decorator creating a cached attribute from a data retrieval
    method.
    
    Accessing the cached attribute gives back the cached value. The data
    retrieval method will be called as needed by the CacheManager.
    Invalidating the cache for this value is done by `del`eting the attribute.
    
    The data retrieval method is called with a single argument `db` containing
    a reference to a database connection. All data retrieval should be done
    through this connection.
    
    Note that the cache validity is maintained using a table in the database.
    Most notably, a cache invalidation will trigger a commit, so don't do this
    while another database operation is in progress.
    
    If more control over the transaction is needed, see the `cached` decorator.
    
    This decorator can only be used within `Component` subclasses. See
    CacheProxy for caching attributes of other objects.
    """
    def __init__(self, retriever):
        self.retriever = retriever
        self.__doc__ = retriever.__doc__
        
    def __get__(self, instance, owner):
        if instance is None:
            return self
        id = owner.__module__ + '.' + owner.__name__ \
             + '.' + self.retriever.__name__
        return CacheManager(instance.env).get(id,
                partial(self.retriever, instance))
        
    def __delete__(self, instance):
        id = instance.__class__.__module__ \
             + '.' + instance.__class__.__name__ \
             + '.' + self.retriever.__name__
        CacheManager(instance.env).invalidate(id)


class cached(cached_value):
    """Method decorator creating a cached attribute from a data retrieval
    method.
    
    In contrast with cached attributes created by the `cached_value` decorator,
    accessing a cached attribute created with `cached` will not directly give 
    back the cached value. Instead, this will return a proxy object with `get`
    and `invalidate` methods, both accepting a `db` connection. After calling
    `invalidate(db)`, doing a `commit` is the responsibility of the caller.
    
    This decorator can only be used within `Component` subclasses. See
    CacheProxy for caching attributes of other objects.
    """
    def __get__(self, instance, owner):
        if instance is None:
            return self
        id = owner.__module__ + '.' + owner.__name__ \
             + '.' + self.retriever.__name__
        return CacheProxy(id, partial(self.retriever, instance),
                          instance.env)


class CacheProxy(object):
    """Cached attribute proxy.
    
    This is the class of the object returned when accessing an attribute
    cached with the `cached` decorator.
    
    It can also be instantiated explicitly to cache attributes of
    non-`Component` objects. In this case, the cache identifier `id` must be
    provided, and the data retrieval function is a normal callable (not an
    unbound method).
    """
    __slots__ = ["id", "retriever", "env"]
    
    def __init__(self, id, retriever, env):
        self.id = id
        self.retriever = retriever
        self.env = env
    
    def get(self, db=None):
        return CacheManager(self.env).get(self.id, self.retriever, db)
    
    __call__ = get
    
    def invalidate(self, db=None):
        CacheManager(self.env).invalidate(self.id, db)


class CacheManager(Component):
    """Cache manager."""
    
    def __init__(self):
        self._cache = {}
        self._local = threading.local()
        self._lock = threading.RLock()
    
    # Public interface
    
    def reset_metadata(self):
        """Reset per-request cache metadata."""
        try:
            del self._local.meta
            del self._local.cache
        except AttributeError:
            pass

    def get(self, id, retriever, db=None):
        """Get cached or fresh data for the given id."""
        # Get cache metadata
        try:
            local_meta = self._local.meta
            local_cache = self._local.cache
        except AttributeError:
            # First cache usage in this request, retrieve cache metadata
            # from the database and make a thread-local copy of the cache
            if db is None:
                db = self.env.get_db_cnx()
            cursor = db.cursor()
            cursor.execute("SELECT id,generation FROM cache")
            self._local.meta = local_meta = dict(cursor)
            self._local.cache = local_cache = self._cache.copy()
        
        db_generation = local_meta.get(id, -1)
        
        # Try the thread-local copy first
        try:
            (data, generation) = local_cache[id]
            if generation == db_generation:
                return data
        except KeyError:
            pass
        
        self._lock.acquire()
        try:
            # Get data from the process cache
            try:
                (data, generation) = local_cache[id] = self._cache[id]
                if generation == db_generation:
                    return data
            except KeyError:
                generation = None   # Force retrieval from the database
            
            # Check if the process cache has the newest version, as it may
            # have been updated after the metadata retrieval
            if db is None:
                db = self.env.get_db_cnx()
            cursor = db.cursor()
            cursor.execute("SELECT generation FROM cache WHERE id=%s", (id,))
            row = cursor.fetchone()
            db_generation = not row and -1 or row[0]
            if db_generation == generation:
                return data
            
            # Retrieve data from the database
            data = retriever(db)
            local_cache[id] = self._cache[id] = (data, db_generation)
            local_meta[id] = db_generation
            return data
        finally:
            self._lock.release()
        
    def invalidate(self, id, db=None):
        """Invalidate cached data for the given id."""
        self._lock.acquire()
        try:
            # Invalidate in other processes

            # The row corresponding to the cache may not exist in the table
            # yet.
            #  - If the row exists, the UPDATE increments the generation, the
            #    SELECT returns a row and we're done.
            #  - If the row doesn't exist, the UPDATE does nothing, but starts
            #    a transaction. The SELECT then returns nothing, and we can
            #    safely INSERT a new row.
            @with_transaction(self.env, db)
            def do_invalidate(db):
                cursor = db.cursor()
                cursor.execute("UPDATE cache SET generation=generation+1 "
                               "WHERE id=%s", (id,))
                cursor.execute("SELECT generation FROM cache WHERE id=%s",
                               (id,))
                if not cursor.fetchone():
                    cursor.execute("INSERT INTO cache VALUES (%s, %s)", (id, 0))
            
            # Invalidate in this process
            self._cache.pop(id, None)
            
            # Invalidate in this thread
            try:
                del self._local.cache[id]
            except (AttributeError, KeyError):
                pass
        finally:
            self._lock.release()
