# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2005 Edgewall Software
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
#
# Trac is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version.
#
# Trac is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#
# Author: Christopher Lenz <cmlenz@gmx.de>

from __future__ import generators

from trac.util import TracError

import os
import os.path
from threading import Condition, Lock


class IterableCursor(object):
    """
    Wrapper for DB-API cursor objects that makes the cursor iterable. Iteration
    will generate the rows of a SELECT query one by one.
    """

    __slots__ = 'cursor'

    def __init__(self, cursor):
        self.cursor = cursor

    def __getattr__(self, name):
        return getattr(self.cursor, name)

    def __iter__(self):
        while 1:
            row = self.cursor.fetchone()
            if not row:
                return
            yield row


class ConnectionWrapper(object):
    """
    Generic wrapper around connection objects. This wrapper makes cursor
    produced by the connection iterable using IterableCursor.
    """

    __slots__ = ['cnx']

    def __init__(self, cnx):
        self.cnx = cnx

    def __getattr__(self, name):
        return getattr(self.cnx, name)

    def cursor(self):
        cursor = self.cnx.cursor()
        return IterableCursor(cursor)


class TimeoutError(Exception):
    pass


class PooledConnection(ConnectionWrapper):

    def __init__(self, pool, cnx, log=None):
        ConnectionWrapper.__init__(self, cnx)
        self.__pool = pool
        self.__log = log

    def close(self):
        try:
            self.cnx.rollback()
        except:
            pass
        self.__pool._return_cnx(self)

    def __del__(self):
        if self.__log:
            self.__log.warning("DB connection closed by garbage collection")
        try:
            self.close()
        except:
            pass


class ConnectionPool(object):

    def __init__(self, maxsize, db_module, *args, **kwargs):
        self.__cnxs = []
        self.__lock = Lock()
        self.__available = Condition(self.__lock)
        self.__maxsize = maxsize
        self.__cursize = 0

        threadlevel = getattr(db_module, "threadlevel", 0)
        threadsafety = getattr(db_module, "threadsafety", threadlevel)
        if not threadsafety >= 1:
            raise Exception, "Database module must have threadsafety >= 1"

        if callable(getattr(db_module, "connect", None)):
            self.__fconnect = db_module.connect
        else:
            raise Exception, "Database module has no 'connect' function"

        self.__args = args
        self.__kwargs = kwargs

    def get_cnx(self, timeout=None):
        start = time.time()
        self.__lock.acquire()
        try:
            while 1:
                if self.__cnxs:
                    cnx = self.__cnxs.pop(0)
                    break
                elif self.__maxsize and self.__cursize <= self.__maxsize:
                    cnx = PooledConnection(self,
                        self.__fconnect(*self.__args, **self.__kwargs))
                    self.__cursize += 1
                    break
                else:
                    if timeout:
                        self.__available.wait(timeout)
                        if (time.time() - start) >= timeout:
                            raise TimeoutError, "Unable to get connection " \
                                                "within %d seconds" % timeout
                    else:
                        self.__available.wait()
            return cnx
        finally:
            self.__lock.release()

    def _return_cnx(self, cnx):
        self.__lock.acquire()
        try:
            self.__cnxs.append(cnx)
            self.__cursize -= 1
            self.__available.notify()
        finally:
            self.__lock.release()


class SQLiteConnection(ConnectionWrapper):
    """
    Connection wrapper for SQLite.
    """

    __slots__ = ['cnx']

    def __init__(self, dbpath, timeout=10000):
        self.cnx = None
        if dbpath != ':memory:':
            if not os.access(dbpath, os.F_OK):
                raise TracError, 'Database "%s" not found.' % dbpath
            
            dbdir = os.path.dirname(dbpath)
            if not os.access(dbpath, os.R_OK + os.W_OK) or \
                   not os.access(dbdir, os.R_OK + os.W_OK):
                raise TracError, 'The web server user requires read _and_ ' \
                                 'write permission to the database %s and ' \
                                 'the directory this file is located in.' \
                                 % dbpath

        import sqlite
        cnx = sqlite.connect(dbpath, timeout=timeout)
        ConnectionWrapper.__init__(self, cnx)

    def get_last_id(self):
        return self.cnx.db.sqlite_last_insert_rowid()


def get_cnx(env):
    db_str = env.get_config('trac', 'database', 'sqlite:db/trac.db')
    scheme, rest = db_str.split(':', 1)

    if scheme == 'sqlite':
        if not rest.startswith('/'):
            rest = os.path.join(env.path, rest)
        return SQLiteConnection(rest)

    raise TracError, 'Unsupported database type "%s"' % scheme


__all__ = ['get_cnx']
