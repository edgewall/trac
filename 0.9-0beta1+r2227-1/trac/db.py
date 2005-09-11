# -*- coding: iso8859-1 -*-
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

from __future__ import generators

import os
import time
import urllib
try:
    import threading
except ImportError:
    import dummy_threading as threading
    threading._get_ident = lambda: 0

from trac.core import TracError

__all__ = ['get_cnx_pool', 'init_db']


class Table(object):
    """Declare a table in a database schema."""

    def __init__(self, name, key=[]):
        self.name = name
        self.columns = []
        self.indexes = []
        self.key = key
        if isinstance(key, (str, unicode)):
            self.key = [key]

    def __getitem__(self, objs):
        self.columns = [o for o in objs if isinstance(o, Column)]
        self.indexes = [o for o in objs if isinstance(o, Index)]
        return self

class Column(object):
    """Declare a table column in a database schema."""

    def __init__(self, name, type='text', size=None, unique=False,
                 auto_increment=False):

        self.name = name
        self.type = type
        self.size = size
        self.auto_increment = auto_increment

class Index(object):
    """Declare an index for a database schema."""

    def __init__(self, columns):
        self.columns = columns


class IterableCursor(object):
    """Wrapper for DB-API cursor objects that makes the cursor iterable.
    
    Iteration will generate the rows of a SELECT query one by one.
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
    """Generic wrapper around connection objects.
    
    This wrapper makes cursors produced by the connection iterable using
    `IterableCursor`.
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

    def __init__(self, maxsize, cnx_class, **args):
        self._dormant = [] # inactive connections in pool
        self._active = {} # active connections by thread ID
        self._available = threading.Condition(threading.RLock())
        self._maxsize = maxsize # maximum pool size
        self._cursize = 0 # current pool size, includes active connections
        self._cnx_class = cnx_class
        self._args = args

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
                    cnx = self._cnx_class(**self._args)
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
                        self._dormant.append(cnx)
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


try:
    import pysqlite2.dbapi2 as sqlite
    have_pysqlite = 2

    class PyFormatCursor(sqlite.Cursor):
        def execute(self, sql, args=None):
            if args:
                sql = sql % tuple(['?'] * len(args))
            sqlite.Cursor.execute(self, sql, args or [])
        def executemany(self, sql, args=None):
            if args:
                sql = sql % tuple(['?'] * len(args[0]))
            sqlite.Cursor.executemany(self, sql, args or [])
        def _convert_row(self, row):
            return tuple([(isinstance(v, unicode) and [v.encode('utf-8')] or [v])[0]
                          for v in row])
        def fetchone(self):
            row = sqlite.Cursor.fetchone(self)
            return row and self._convert_row(row) or None
        def fetchmany(self, num):
            rows = sqlite.Cursor.fetchmany(self, num)
            return rows != None and [self._convert_row(row)
                                     for row in rows] or None
        def fetchall(self):
            rows = sqlite.Cursor.fetchall(self)
            return rows != None and [self._convert_row(row)
                                     for row in rows] or None
                
except ImportError:
    try:
        import sqlite
        have_pysqlite = 1
    except ImportError:
        have_pysqlite = 0


class SQLiteConnection(ConnectionWrapper):
    """Connection wrapper for SQLite."""

    __slots__ = ['cnx']

    def __init__(self, path, params={}):
        assert have_pysqlite > 0
        self.cnx = None
        if path != ':memory:':
            if not os.access(path, os.F_OK):
                raise TracError, 'Database "%s" not found.' % path

            dbdir = os.path.dirname(path)
            if not os.access(path, os.R_OK + os.W_OK) or \
                   not os.access(dbdir, os.R_OK + os.W_OK):
                from getpass import getuser
                raise TracError, 'The user %s requires read _and_ write ' \
                                 'permission to the database file %s and the ' \
                                 'directory it is located in.' \
                                 % (getuser(), path)

        timeout = int(params.get('timeout', 10000))
        if have_pysqlite == 2:
            # Convert unicode to UTF-8 bytestrings. This is case-sensitive, so
            # we need two converters
            sqlite.register_converter('text', str)
            sqlite.register_converter('TEXT', str)

            cnx = sqlite.connect(path, detect_types=sqlite.PARSE_DECLTYPES,
                                 check_same_thread=False, timeout=timeout)
        else:
            cnx = sqlite.connect(path, timeout=timeout)
        ConnectionWrapper.__init__(self, cnx)

    if have_pysqlite == 2:
        def cursor(self):
            return self.cnx.cursor(PyFormatCursor)
    else:
        def cursor(self):
            return self.cnx.cursor()

    def cast(self, column, type):
        return column

    def like(self):
        return 'LIKE'

    if have_pysqlite == 2:
        def get_last_id(self, cursor, table, column='id'):
            return cursor.lastrowid
    else:
        def get_last_id(self, cursor, table, column='id'):
            return self.cnx.db.sqlite_last_insert_rowid()

    def init_db(cls, path, params={}):
        if path != ':memory:':
            # make the directory to hold the database
            if os.path.exists(path):
                raise TracError, 'Database already exists at %s' % path
            os.makedirs(os.path.split(path)[0])
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


psycopg = None
PgSQL = None

class PostgreSQLConnection(ConnectionWrapper):
    """Connection wrapper for PostgreSQL."""

    __slots__ = ['cnx']

    def __init__(self, path, user=None, password=None, host=None, port=None,
                 params={}):
        if path.startswith('/'):
            path = path[1:]
        # We support both psycopg and PgSQL but prefer psycopg
        global psycopg
        global PgSQL
        if not psycopg and not PgSQL:
            try:
                try:
                    import psycopg2 as psycopg
                except ImportError:
                    import psycopg
            except ImportError:
                from pyPgSQL import PgSQL
        if psycopg:
            dsn = []
            if path:
                dsn.append('dbname=' + path)
            if user:
                dsn.append('user=' + user)
            if password:
                dsn.append('password=' + password)
            if host:
                dsn.append('host=' + host)
            cnx = psycopg.connect(' '.join(dsn))
        else:
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
    return scheme, dict([(key, value) for key, value in args if value])
