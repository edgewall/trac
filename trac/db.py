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

    def __init__(self, pool, cnx):
        ConnectionWrapper.__init__(self, cnx)
        self.__pool = pool

    def close(self):
        try:
            self.cnx.rollback()
        except:
            pass
        self.__pool._return_cnx(self)

    def __del__(self):
        try:
            self.close()
        except:
            pass


class ConnectionPool(object):

    def __init__(self, maxsize, cnx_class, **args):
        self.__cnxs = []
        self.__lock = Lock()
        self.__available = Condition(self.__lock)
        self.__maxsize = maxsize
        self.__cursize = 0
        self.__cnx_class = cnx_class
        self.__args = args

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
                        self.__cnx_class(**self.__args))
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
    """Connection wrapper for SQLite."""

    __slots__ = ['cnx']

    def __init__(self, path, params={}):
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

        import sqlite
        cnx = sqlite.connect(path, timeout=int(params.get('timeout', 10000)))
        ConnectionWrapper.__init__(self, cnx)

    def cast(self, column, type):
        return column

    def like(self):
        return 'LIKE'

    def get_last_id(self, table, column='id'):
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
        cursor.execute(cls._get_init_sql())
        cnx.commit()
    init_db = classmethod(init_db)

    def _get_init_sql(cls):
        sql = []
        from trac.db_default import schema, Table, Index
        for table in [t for t in schema if isinstance(t, Table)]:
            sql.append("CREATE TABLE %s (" % table.name)
            coldefs = []
            for column in table.columns:
                ctype = column.type.upper()
                if column.auto_increment:
                    ctype = "INTEGER PRIMARY KEY"
                elif len(table.key) == 1 and column.name in table.key:
                    ctype += " PRIMARY KEY"
                elif ctype == "INT":
                    ctype = "INTEGER"
                coldefs.append("    %s %s" % (column.name, ctype))
            if len(table.key) > 1:
                coldefs.append("    UNIQUE (%s)" % ','.join(table.key))
            sql.append(',\n'.join(coldefs) + '\n);')
        for index in [i for i in schema if isinstance(i, Index)]:
            sql.append("CREATE INDEX %s ON %s (%s);"
                       % (index.name, index.table, ','.join(index.columns)))
        return '\n'.join(sql)
    _get_init_sql = classmethod(_get_init_sql)


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

    def get_last_id(self, table, column='id'):
        cursor = self.cursor()
        cursor.execute("SELECT %s FROM %s WHERE %s=CURRVAL('%s_%s_seq')"
                       % (column, table, column, table, column))
        return cursor.fetchone()[0]

    def init_db(cls, **args):
        from pyPgSQL import libpq, PgSQL

        sql = []
        from trac.db_default import schema, Table, Index
        for table in [t for t in schema if isinstance(t, Table)]:
            sql.append("CREATE TABLE %s (" % table.name)
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
        for index in [i for i in schema if isinstance(i, Index)]:
            sql.append("CREATE INDEX %s ON %s (%s);"
                       % (index.name, index.table, ','.join(index.columns)))

        self = cls(**args)
        cursor = self.cursor()
        cursor.execute('\n'.join(sql))
        self.commit()
        return self

    init_db = classmethod(init_db)


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
