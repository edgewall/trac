# -*- coding: utf-8 -*-
#
# Copyright (C) 2005 Edgewall Software
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://projects.edgewall.com/trac/.
#
# Author: Christopher Lenz <cmlenz@gmx.de>

try:
    import threading
except ImportError:
    import dummy_threading as threading
    threading._get_ident = lambda: 0
import time

from trac.db.util import ConnectionWrapper


class TimeoutError(Exception):
    """Exception raised by the connection pool when no connection has become
    available after a given timeout."""


class PooledConnection(ConnectionWrapper):
    """A database connection that can be pooled. When closed, it gets returned
    to the pool.
    """

    def __init__(self, pool, cnx):
        ConnectionWrapper.__init__(self, cnx)
        self._pool = pool

    def close(self):
        if self.cnx:
            self._pool._return_cnx(self.cnx)
            self.cnx = None

    def __del__(self):
        self.close()


class ConnectionPool(object):
    """A very simple connection pool implementation."""

    def __init__(self, maxsize, connector, **kwargs):
        self._dormant = [] # inactive connections in pool
        self._active = {} # active connections by thread ID
        self._available = threading.Condition(threading.Lock())
        self._maxsize = maxsize # maximum pool size
        self._cursize = 0 # current pool size, includes active connections
        self._connector = connector
        self._kwargs = kwargs

    def get_cnx(self, timeout=None):
        start = time.time()
        self._available.acquire()
        try:
            tid = threading._get_ident()
            if tid in self._active:
                self._active[tid][0] += 1
                return PooledConnection(self, self._active[tid][1])
            while True:
                if self._dormant:
                    cnx = self._dormant.pop()
                    break
                elif self._maxsize and self._cursize < self._maxsize:
                    cnx = self._connector.get_connection(**self._kwargs)
                    self._cursize += 1
                    break
                else:
                    if timeout:
                        self._available.wait(timeout)
                        if (time.time() - start) >= timeout:
                            raise TimeoutError, 'Unable to get database ' \
                                                'connection within %d seconds' \
                                                % timeout
                    else:
                        self._available.wait()
            self._active[tid] = [1, cnx]
            return PooledConnection(self, cnx)
        finally:
            self._available.release()

    def _return_cnx(self, cnx):
        self._available.acquire()
        try:
            tid = threading._get_ident()
            if tid in self._active:
                num, cnx_ = self._active.get(tid)
                assert cnx is cnx_
                if num > 1:
                    self._active[tid][0] = num - 1
                else:
                    del self._active[tid]
                    if cnx not in self._dormant:
                        cnx.rollback()
                        if cnx.poolable:
                            self._dormant.append(cnx)
                        else:
                            self._cursize -= 1
                        self._available.notify()
        finally:
            self._available.release()

    def shutdown(self):
        self._available.acquire()
        try:
            for cnx in self._dormant:
                cnx.cnx.close()
        finally:
            self._available.release()
