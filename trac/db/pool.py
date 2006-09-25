# -*- coding: utf-8 -*-
#
# Copyright (C) 2005 Edgewall Software
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

    def __init__(self, pool, cnx, tid):
        ConnectionWrapper.__init__(self, cnx)
        self._pool = pool
        self._tid = tid

    def close(self):
        if self.cnx:
            self._pool._return_cnx(self.cnx, self._tid)
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
                num, cnx = self._active.get(tid)
                if num == 0: # was pushed back (see _cleanup)
                    cnx.rollback()
                self._active[tid][0] = num + 1
                return PooledConnection(self, cnx, tid)
            while True:
                if self._dormant:
                    cnx = self._dormant.pop()
                    try:
                        cnx.cursor() # check whether the connection is stale
                        break
                    except Exception:
                        cnx.close()
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
            return PooledConnection(self, cnx, tid)
        finally:
            self._available.release()

    def _return_cnx(self, cnx, tid):
        self._available.acquire()
        try:
            if tid in self._active:
                num, cnx_ = self._active.get(tid)
                assert cnx is cnx_
                if num > 1:
                    self._active[tid][0] = num - 1
                else:
                    self._cleanup(tid)
        finally:
            self._available.release()

    def _cleanup(self, tid):
        # Note: self._available *must* be acquired
        if tid in self._active:
            cnx = self._active.pop(tid)[1]
            if cnx not in self._dormant: # hm, how could that happen?
                if cnx.poolable: # i.e. we can manipulate it from other threads
                    cnx.rollback()
                    self._dormant.append(cnx)
                elif tid == threading._get_ident():
                    cnx.rollback() # non-poolable but same thread: close
                    cnx.close()
                    self._cursize -= 1
                else: # non-poolable, different thread: push it back
                    self._active[tid] = [0, cnx]
                self._available.notify()

    def shutdown(self, tid=None):
        self._available.acquire()
        try:
            if tid:
                cleanup_list = [tid]
            else:
                cleanup_list = self._active.keys()
            for tid in cleanup_list:
                self._cleanup(tid)
            if not tid:
                for cnx in self._dormant:
                    cnx.close()
        finally:
            self._available.release()
