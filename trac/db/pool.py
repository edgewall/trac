# -*- coding: utf-8 -*-
#
# Copyright (C)2005-2009 Edgewall Software
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.
#
# Author: Christopher Lenz <cmlenz@gmx.de>

import os
import time

from trac.db.util import ConnectionWrapper
from trac.util.concurrency import threading
from trac.util.text import exception_to_unicode
from trac.util.translation import _


class TimeoutError(Exception):
    """Exception raised by the connection pool when no connection has become
    available after a given timeout."""


class PooledConnection(ConnectionWrapper):
    """A database connection that can be pooled. When closed, it gets returned
    to the pool.
    """

    def __init__(self, pool, cnx, key, tid, log=None):
        ConnectionWrapper.__init__(self, cnx, log)
        self._pool = pool
        self._key = key
        self._tid = tid

    def close(self):
        if self.cnx:
            self._pool._return_cnx(self.cnx, self._key, self._tid)
            self.cnx = None
            self.log = None

    def __del__(self):
        self.close()


def try_rollback(cnx):
    """Resets the Connection in a safe way, returning True when it succeeds.
    
    The rollback we do for safety on a Connection can fail at
    critical times because of a timeout on the Connection.
    """
    try:
        cnx.rollback() # resets the connection
        return True
    except Exception:
        cnx.close()
        return False


class ConnectionPoolBackend(object):
    """A process-wide LRU-based connection pool.
    """
    def __init__(self, maxsize):
        self._available = threading.Condition(threading.RLock())
        self._maxsize = maxsize
        self._active = {}
        self._pool = []
        self._pool_key = []
        self._pool_time = []
        self._waiters = 0

    def get_cnx(self, connector, kwargs, timeout=None):
        cnx = None
        log = kwargs.get('log')
        key = unicode(kwargs)
        start = time.time()
        tid = threading._get_ident()
        # Get a Connection, either directly or a deferred one
        self._available.acquire()
        try:
            # First choice: Return the same cnx already used by the thread
            if (tid, key) in self._active:
                cnx, num = self._active[(tid, key)]
                num += 1
            else:
                if self._waiters == 0:
                    cnx = self._take_cnx(connector, kwargs, key, tid)
                if not cnx:
                    self._waiters += 1
                    self._available.wait()
                    self._waiters -= 1
                    cnx = self._take_cnx(connector, kwargs, key, tid)
                num = 1
            if cnx:
                self._active[(tid, key)] = (cnx, num)
        finally:
            self._available.release()

        deferred = num == 1 and isinstance(cnx, tuple)
        err = None
        if deferred:
            # Potentially lenghty operations must be done without lock held
            op, cnx = cnx
            try:
                if op == 'ping':
                    cnx.ping()
                elif op == 'close':
                    cnx.close()
                if op in ('close', 'create'):
                    cnx = connector.get_connection(**kwargs)
            except Exception, e:
                err = e
                cnx = None
        
        if cnx:
            if deferred:
                # replace placeholder with real Connection
                self._available.acquire()
                try:
                    self._active[(tid, key)] = (cnx, num)
                finally:
                    self._available.release()
            return PooledConnection(self, cnx, key, tid, log)

        if deferred:
            # cnx couldn't be reused, clear placeholder
            self._available.acquire()
            try:
                del self._active[(tid, key)]
            finally:
                self._available.release()
            if op == 'ping': # retry
                return self.get_cnx(connector, kwargs)

        # if we didn't get a cnx after wait(), something's fishy...
        timeout = time.time() - start
        errmsg = _("Unable to get database connection within %(time)d seconds.",
                   time=timeout)
        if err:
            errmsg += " (%s)" % exception_to_unicode(err)
        raise TimeoutError(errmsg)

    def _take_cnx(self, connector, kwargs, key, tid):
        """Note: _available lock must be held when calling this method."""
        # Second best option: Reuse a live pooled connection
        if key in self._pool_key:
            idx = self._pool_key.index(key)
            self._pool_key.pop(idx)
            self._pool_time.pop(idx)
            cnx = self._pool.pop(idx)
            # If possible, verify that the pooled connection is
            # still available and working.
            if hasattr(cnx, 'ping'):
                return ('ping', cnx)
            return cnx
        # Third best option: Create a new connection
        elif len(self._active) + len(self._pool) < self._maxsize:
            return ('create', None)
        # Forth best option: Replace a pooled connection with a new one
        elif len(self._active) < self._maxsize:
            # Remove the LRU connection in the pool
            cnx = self._pool.pop(0)
            self._pool_key.pop(0)
            self._pool_time.pop(0)
            return ('close', cnx)

    def _return_cnx(self, cnx, key, tid):
        # Decrement active refcount, clear slot if 1
        self._available.acquire()
        try:
            assert (tid, key) in self._active
            cnx, num = self._active[(tid, key)]
            if num == 1:
                del self._active[(tid, key)]
            else:
                self._active[(tid, key)] = (cnx, num - 1)
        finally:
            self._available.release()
        if num == 1:
            # Reset connection outside of critical section
            if not try_rollback(cnx): # TODO inline this in 0.13
                cnx = None
            # Connection available, from reuse or from creation of a new one
            self._available.acquire()
            try:
                if cnx and cnx.poolable:
                    self._pool.append(cnx)
                    self._pool_key.append(key)
                    self._pool_time.append(time.time())
                self._available.notify() 
            finally:
                self._available.release()

    def shutdown(self, tid=None):
        """Close pooled connections not used in a while"""
        delay = 120
        if tid is None:
            delay = 0
        when = time.time() - delay
        self._available.acquire()
        try:
            while self._pool_time and self._pool_time[0] <= when:
                self._pool.pop(0)
                self._pool_key.pop(0)
                self._pool_time.pop(0)
        finally:
            self._available.release()


_pool_size = int(os.environ.get('TRAC_DB_POOL_SIZE', 10))
_backend = ConnectionPoolBackend(_pool_size)


class ConnectionPool(object):
    def __init__(self, maxsize, connector, **kwargs):
        # maxsize not used right now but kept for api compatibility
        self._connector = connector
        self._kwargs = kwargs

    def get_cnx(self, timeout=None):
        return _backend.get_cnx(self._connector, self._kwargs, timeout)

    def shutdown(self, tid=None):
        _backend.shutdown(tid)

