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

from trac.core import Component
from trac.util.concurrency import ThreadLocal, threading

__all__ = ["CacheManager", "cached"]


class CachedProperty(object):
    """Cached property descriptor"""
    
    def __init__(self, retriever, id_attr=None):
        self.retriever = retriever
        self.__doc__ = retriever.__doc__
        self.id_attr = id_attr
        self.id = None
        
    def __get__(self, instance, owner):
        if instance is None:
            return self
        if self.id_attr is not None:
            id = getattr(instance, self.id_attr)
        else:
            id = self.id
            if id is None:
                id = self.id = self.make_id(owner)
        return CacheManager(instance.env).get(id, self.retriever, instance)
        
    def __delete__(self, instance):
        if self.id_attr is not None:
            id = getattr(instance, self.id_attr)
        else:
            id = self.id
            if id is None:
                id = self.id = self.make_id(instance.__class__)
        CacheManager(instance.env).invalidate(id)

    def make_id(self, cls):
        attr = self.retriever.__name__
        for base in cls.mro():
            if base.__dict__.get(attr) is self:
                cls = base
                break
        return '%s.%s.%s' % (cls.__module__, cls.__name__, attr)


def cached(fn_or_id=None):
    """Method decorator creating a cached attribute from a data retrieval
    method.
    
    Accessing the cached attribute gives back the cached value. The data
    retrieval method is called as needed by the CacheManager. Invalidating
    the cache for this value is done by `del`eting the attribute.
    
    The data retrieval method is called with a single argument `db` containing
    a reference to a database connection. All data retrieval should be done
    through this connection.
    
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
            db = self.env.get_read_db()
            cursor = db.cursor()
            cursor.execute("SELECT id,generation FROM cache")
            self._local.meta = local_meta = dict(cursor)
            self._local.cache = local_cache = self._cache.copy()
        else:
            db = None
        
        db_generation = local_meta.get(id, -1)
        
        # Try the thread-local copy first
        try:
            (data, generation) = local_cache[id]
            if generation == db_generation:
                return data
        except KeyError:
            pass
        
        if db is None:
            db = self.env.get_read_db()
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
            cursor = db.cursor()
            cursor.execute("SELECT generation FROM cache WHERE id=%s", (id,))
            row = cursor.fetchone()
            db_generation = not row and -1 or row[0]
            if db_generation == generation:
                return data
            
            # Retrieve data from the database
            data = retriever(instance, db)
            local_cache[id] = self._cache[id] = (data, db_generation)
            local_meta[id] = db_generation
            return data
        finally:
            self._lock.release()
        
    def invalidate(self, id):
        """Invalidate cached data for the given id."""
        db = self.env.get_read_db() # prevent deadlock
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
            @self.env.with_transaction()
            def do_invalidate(db):
                cursor = db.cursor()
                cursor.execute("""
                    UPDATE cache SET generation=generation+1 WHERE id=%s
                    """, (id,))
                cursor.execute("SELECT generation FROM cache WHERE id=%s",
                               (id,))
                if not cursor.fetchone():
                    cursor.execute("INSERT INTO cache VALUES (%s, %s)",
                                   (id, 0))
            
            # Invalidate in this process
            self._cache.pop(id, None)
            
            # Invalidate in this thread
            try:
                del self._local.cache[id]
            except (KeyError, TypeError):
                pass
        finally:
            self._lock.release()
