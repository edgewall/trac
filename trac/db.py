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
import urllib


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

    def get_last_id(self, table, column='id'):
        return self.cnx.db.sqlite_last_insert_rowid()


_cnx_map = {'sqlite': SQLiteConnection}

def get_cnx(env):
    db_str = env.config.get('trac', 'database')
    scheme, args = _parse_db_str(db_str)
    if not scheme in _cnx_map:
        raise TracError, 'Unsupported database type "%s"' % scheme

    if scheme == 'sqlite':
        # Special case for SQLite to support a path relative to the
        # environment directory
        if args['path'] != ':memory:' and not args['path'].startswith('/'):
            args['path'] = os.path.join(env.path, args['path'].lstrip('/'))

    return _cnx_map[scheme](**args)

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


__all__ = ['get_cnx']
