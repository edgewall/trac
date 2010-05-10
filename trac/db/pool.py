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

    def get_cnx(self, connector, kwargs, timeout=None):
        num = 1
        cnx = None
        log = kwargs.get('log')
        key = unicode(kwargs)
        start = time.time()
        tid = threading._get_ident()
        self._available.acquire()
        try:
            while True:
                # First choice: Return the same cnx already used by the thread
                if (tid, key) in self._active:
                    cnx, num = self._active[(tid, key)]
                    num += 1
                # Second best option: Reuse a live pooled connection
                elif key in self._pool_key:
                    idx = self._pool_key.index(key)
                    self._pool_key.pop(idx)
                    self._pool_time.pop(idx)
                    cnx = self._pool.pop(idx)
                    # If possible, verify that the pooled connection is
                    # still available and working.
                    if hasattr(cnx, 'ping'):
                        try:
                            cnx.ping()
                        except:
                            continue
                # Third best option: Create a new connection
                elif len(self._active) + len(self._pool) < self._maxsize:
                    cnx = connector.get_connection(**kwargs)
                # Forth best option: Replace a pooled connection with a new one
                elif len(self._active)  < self._maxsize:
                    # Remove the LRU connection in the pool
                    self._pool.pop(0).close()
                    self._pool_key.pop(0)
                    self._pool_time.pop(0)
                    cnx = connector.get_connection(**kwargs)
                if cnx:
                    self._active[(tid, key)] = (cnx, num)
                    return PooledConnection(self, cnx, key, tid, log)
                # Worst option: wait until a connection pool slot is available
                if timeout and (time.time() - start) > timeout:
                    raise TimeoutError(_('Unable to get database '
                                         'connection within %(time)d '
                                         'seconds', time=timeout))
                elif timeout:
                    self._available.wait(timeout)
                else:
                    self._available.wait()
        finally:
            self._available.release()

    def _return_cnx(self, cnx, key, tid):
        self._available.acquire()
        try:
            assert (tid, key) in self._active
            cnx, num = self._active[(tid, key)]
            if num == 1:
                del self._active[(tid, key)]
                self._available.notify() 
                if cnx.poolable and try_rollback(cnx):
                    self._pool.append(cnx)
                    self._pool_key.append(key)
                    self._pool_time.append(time.time())
            else:
                self._active[(tid, key)] = (cnx, num - 1)
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

