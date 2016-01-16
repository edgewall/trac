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
import sys

from trac.core import TracError
from trac.db.util import ConnectionWrapper
from trac.util.concurrency import threading
from trac.util.datefmt import time_now
from trac.util.text import exception_to_unicode
from trac.util.translation import _


class TimeoutError(TracError):
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
            cnx = self.cnx
            self.cnx = None
            self.log = None
            self._pool._return_cnx(cnx, self._key, self._tid)

    def __del__(self):
        self.close()



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
        start = time_now()
        tid = threading._get_ident()
        # Get a Connection, either directly or a deferred one
        with self._available:
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

        deferred = num == 1 and isinstance(cnx, tuple)
        exc_info = (None, None, None)
        if deferred:
            # Potentially lengthy operations must be done without lock held
            op, cnx = cnx
            try:
                if op == 'ping':
                    cnx.ping()
                elif op == 'close':
                    cnx.close()
                if op in ('close', 'create'):
                    cnx = connector.get_connection(**kwargs)
            except TracError:
                exc_info = sys.exc_info()
                cnx = None
            except Exception:
                exc_info = sys.exc_info()
                if log:
                    log.error('Exception caught on %s', op, exc_info=True)
                cnx = None

        if cnx and not isinstance(cnx, tuple):
            if deferred:
                # replace placeholder with real Connection
                with self._available:
                    self._active[(tid, key)] = (cnx, num)
            return PooledConnection(self, cnx, key, tid, log)

        if deferred:
            # cnx couldn't be reused, clear placeholder
            with self._available:
                del self._active[(tid, key)]
            if op == 'ping': # retry
                return self.get_cnx(connector, kwargs)

        # if we didn't get a cnx after wait(), something's fishy...
        if isinstance(exc_info[1], TracError):
            raise exc_info[0], exc_info[1], exc_info[2]
        timeout = time_now() - start
        errmsg = _("Unable to get database connection within %(time)d seconds.",
                   time=timeout)
        if exc_info[1]:
            errmsg += " (%s)" % exception_to_unicode(exc_info[1])
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
        with self._available:
            assert (tid, key) in self._active
            cnx, num = self._active[(tid, key)]
            if num == 1:
                del self._active[(tid, key)]
            else:
                self._active[(tid, key)] = (cnx, num - 1)
        if num == 1:
            # Reset connection outside of critical section
            try:
                cnx.rollback() # resets the connection
            except Exception:
                cnx.close()
                cnx = None
            # Connection available, from reuse or from creation of a new one
            with self._available:
                if cnx and cnx.poolable:
                    self._pool.append(cnx)
                    self._pool_key.append(key)
                    self._pool_time.append(time_now())
                self._available.notify()

    def shutdown(self, tid=None):
        """Close pooled connections not used in a while"""
        delay = 120
        if tid is None:
            delay = 0
        when = time_now() - delay
        with self._available:
            if tid is None: # global shutdown, also close active connections
                for db, num in self._active.values():
                    db.close()
                self._active = {}
            while self._pool_time and self._pool_time[0] <= when:
                db = self._pool.pop(0)
                db.close()
                self._pool_key.pop(0)
                self._pool_time.pop(0)


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
