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

    def __del__(self):
        if self.cursor:
            try:
                self.cursor.close()
            except ReferenceError:
                pass

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

    def __del__(self):
        if self.cnx:
            try:
                self.cnx.close()
            except ReferenceError:
                pass

    def __getattr__(self, name):
        return getattr(self.cnx, name)

    def cursor(self):
        cursor = self.cnx.cursor()
        return IterableCursor(cursor)


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
