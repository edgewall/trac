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
import time
import urllib
from threading import Condition, Lock

__all__ = ['get_cnx_pool', 'init_db']


class IterableCursor(object):
    """
    Wrapper for DB-API cursor objects that makes the cursor iterable. Iteration
    will generate the rows of a SELECT query one by one.
    """
    __slots__ = ['cursor']

    def __init__(self, cursor):
        self.cursor = cursor

    def __getattr__(self, name):
        return getattr(self.cursor, name)

    def __iter__(self):
        while True:
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
        if hasattr(self, 'cnx'):
            return getattr(self.cnx, name)
        return object.__getattr__(self, name)

    def cursor(self):
        return IterableCursor(self.cnx.cursor())


class TimeoutError(Exception):
    pass


class PooledConnection(ConnectionWrapper):
    """A database connection that can be pooled. When closed, it gets returned
    to the pool.
    """

    def __init__(self, pool, cnx):
        ConnectionWrapper.__init__(self, cnx)
        self.__pool = pool

    def close(self):
        self.__pool._return_cnx(self.cnx)

    def __del__(self):
        self.close()


class ConnectionPool(object):
    """A very simple connection pool implementation."""

    def __init__(self, maxsize, cnx_class, **args):
        self._cnxs = []
        self._available = Condition(Lock())
        self._maxsize = maxsize
        self._cursize = 0
        self._cnx_class = cnx_class
        self._args = args

    def get_cnx(self, timeout=None):
        start = time.time()
        self._available.acquire()
        try:
            while True:
                if self._cnxs:
                    cnx = self._cnxs.pop()
                    break
                elif self._maxsize and self._cursize < self._maxsize:
                    cnx = self._cnx_class(**self._args)
                    self._cursize += 1
                    break
                else:
                    if timeout:
                        self._available.wait(timeout)
                        if (time.time() - start) >= timeout:
                            raise TimeoutError, "Unable to get connection " \
                                                "within %d seconds" % timeout
                    else:
                        self._available.wait()
            return PooledConnection(self, cnx)
        finally:
            self._available.release()

    def _return_cnx(self, cnx):
        self._available.acquire()
        try:
            if cnx not in self._cnxs:
                cnx.rollback()
                self._cnxs.append(cnx)
                self._available.notify()
        finally:
            self._available.release()

    def shutdown(self):
        self._available.acquire()
        try:
            for con in self._cnxs:
                con.cnx.close()
        finally:
            self._available.release()


try:
    import pysqlite2.dbapi2 as sqlite
    using_pysqlite2 = True

    class PyFormatCursor(sqlite.Cursor):
        def execute(self, sql, args=None):
            if args:
                sql = sql % tuple(['?'] * len(args))
            sqlite.Cursor.execute(self, sql, args or [])
        def executemany(self, sql, args=None):
            if args:
                sql = sql % tuple(['?'] * len(args[0]))
            sqlite.Cursor.executemany(self, sql, args or [])

except ImportError:
    using_pysqlite2 = False


class SQLiteConnection(ConnectionWrapper):
    """Connection wrapper for SQLite."""

    __slots__ = ['cnx']

    def __init__(self, path, params={}):
        global using_pysqlite2
        self.cnx = None
        if path != ':memory:':
            if not os.access(path, os.F_OK):
                raise TracError, 'Database "%s" not found.' % path

            dbdir = os.path.dirname(path)
            if not os.access(path, os.R_OK + os.W_OK) or \
                   not os.access(dbdir, os.R_OK + os.W_OK):
                raise TracError, 'The web server user requires read _and_ ' \
                                 'write permission to the database %s and ' \
                                 'the directory this file is located in.' \
                                 % path

        timeout = int(params.get('timeout', 10000))
        if using_pysqlite2:
            global sqlite

            # Convert unicode to UTF-8 bytestrings. This is case-sensitive, so
            # we need two converters
            sqlite.register_converter('text', str)
            sqlite.register_converter('TEXT', str)

            cnx = sqlite.connect(path, detect_types=sqlite.PARSE_DECLTYPES,
                                 timeout=timeout)
        else:
            import sqlite
            cnx = sqlite.connect(path, timeout=timeout)

        ConnectionWrapper.__init__(self, cnx)

    def cast(self, column, type):
        return column

    def cursor(self):
        global using_pysqlite2
        if using_pysqlite2:
            return self.cnx.cursor(PyFormatCursor)
        else:
            return self.cnx.cursor()

    def like(self):
        return 'LIKE'

    def get_last_id(self, cursor, table, column='id'):
        global using_pysqlite2
        if using_pysqlite2:
            return cursor.lastrowid
        else:
            return self.cnx.db.sqlite_last_insert_rowid()

    def init_db(cls, path, params={}):
        if path != ':memory:':
            # make the directory to hold the database
            if os.path.exists(path):
                raise TracError, 'Database already exists at %s' % path
            os.makedirs(os.path.split(path)[0])
        import sqlite
        cnx = sqlite.connect(path, timeout=int(params.get('timeout', 10000)))
        cursor = cnx.cursor()
        from trac.db_default import schema
        for table in schema:
            for stmt in cls.to_sql(table):
                cursor.execute(stmt)
        cnx.commit()
    init_db = classmethod(init_db)

    def to_sql(cls, table):
        sql = ["CREATE TABLE %s (" % table.name]
        coldefs = []
        for column in table.columns:
            ctype = column.type.lower()
            if column.auto_increment:
                ctype = "integer PRIMARY KEY"
            elif len(table.key) == 1 and column.name in table.key:
                ctype += " PRIMARY KEY"
            elif ctype == "int":
                ctype = "integer"
            coldefs.append("    %s %s" % (column.name, ctype))
        if len(table.key) > 1:
            coldefs.append("    UNIQUE (%s)" % ','.join(table.key))
        sql.append(',\n'.join(coldefs) + '\n);')
        yield '\n'.join(sql)
        for index in table.indexes:
            yield "CREATE INDEX %s_idx ON %s (%s);" % (table.name,
                  table.name, ','.join(index.columns))
    to_sql = classmethod(to_sql)


class PostgreSQLConnection(ConnectionWrapper):
    """Connection wrapper for PostgreSQL."""

    __slots__ = ['cnx']

    def __init__(self, path, user=None, password=None, host=None, port=None,
                 params={}):
        from pyPgSQL import libpq, PgSQL
        if path.startswith('/'):
            path = path[1:]
        cnx = PgSQL.connect('', user, password, host, path, port)
        ConnectionWrapper.__init__(self, cnx)

    def cast(self, column, type):
        # Temporary hack needed for the union of selects in the search module
        return 'CAST(%s AS %s)' % (column, type)

    def like(self):
        # Temporary hack needed for the case-insensitive string matching in the
        # search module
        return 'ILIKE'

    def get_last_id(self, cursor, table, column='id'):
        cursor.execute("SELECT CURRVAL('%s_%s_seq')" % (table, column))
        return cursor.fetchone()[0]

    def init_db(cls, **args):
        from pyPgSQL import libpq, PgSQL
        self = cls(**args)
        cursor = self.cursor()
        from trac.db_default import schema
        for table in schema:
            for stmt in cls.to_sql(table):
                cursor.execute(stmt)
        self.commit()
    init_db = classmethod(init_db)

    def to_sql(cls, table):
        sql = ["CREATE TABLE %s (" % table.name]
        coldefs = []
        for column in table.columns:
            ctype = column.type
            if column.auto_increment:
                ctype = "SERIAL"
            coldefs.append("    %s %s" % (column.name, ctype))
        if len(table.key) > 1:
            coldefs.append("    CONSTRAINT %s_pk PRIMARY KEY (%s)"
                           % (table.name, ','.join(table.key)))
        sql.append(',\n'.join(coldefs) + '\n);')
        yield '\n'.join(sql)
        for index in table.indexes:
            yield "CREATE INDEX %s_idx ON %s (%s);" % (table.name, table.name,
                  ','.join(index.columns))
    to_sql = classmethod(to_sql)


_cnx_map = {'postgres': PostgreSQLConnection, 'sqlite': SQLiteConnection}

def init_db(env_path, db_str):
    cls, args = _get_cnx_class(env_path, db_str)
    cls.init_db(**args)

def get_cnx_pool(env):
    cls, args = _get_cnx_class(env.path, env.config.get('trac', 'database'))
    return ConnectionPool(5, cls, **args)

def _get_cnx_class(env_path, db_str):
    scheme, args = _parse_db_str(db_str)
    if not scheme in _cnx_map:
        raise TracError, 'Unsupported database type "%s"' % scheme

    if scheme == 'sqlite':
        # Special case for SQLite to support a path relative to the
        # environment directory
        if args['path'] != ':memory:' and not args['path'].startswith('/'):
            args['path'] = os.path.join(env_path, args['path'].lstrip('/'))

    return _cnx_map[scheme], args

def _parse_db_str(db_str):
    scheme, rest = db_str.split(':', 1)

    if not rest.startswith('/'):
        if scheme == 'sqlite':
            # Support for relative and in-memory SQLite connection strings
            host = None
            path = rest
        else:
            raise TracError, 'Database connection string %s must start with ' \
                             'scheme:/' % db_str
    else:
        if rest.startswith('/') and not rest.startswith('//'):
            host = None
            rest = rest[1:]
        elif rest.startswith('///'):
            host = None
            rest = rest[3:]
        else:
            rest = rest[2:]
            if rest.find('/') == -1:
                host = rest
                rest = ''
            else:
                host, rest = rest.split('/', 1)
        path = None

    if host and host.find('@') != -1:
        user, host = host.split('@', 1)
        if user.find(':') != -1:
            user, password = user.split(':', 1)
        else:
            password = None
    else:
        user = password = None
    if host and host.find(':') != -1:
        host, port = host.split(':')
        port = int(port)
    else:
        port = None

    if not path:
        path = '/' + rest
    if os.name == 'nt':
        # Support local paths containing drive letters on Win32
        if len(rest) > 1 and rest[1] == '|':
            path = "%s:%s" % (rest[0], rest[2:])

    params = {}
    if path.find('?') != -1:
        path, qs = path.split('?', 1)
        qs = qs.split('&')
        for param in qs:
            name, value = param.split('=', 1)
            value = urllib.unquote(value)
            params[name] = value

    args = zip(('user', 'password', 'host', 'port', 'path', 'params'),
               (user, password, host, port, path, params))
    return scheme, dict(filter(lambda x: x[1], args))
