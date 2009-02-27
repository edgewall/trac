# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2009 Edgewall Software
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
# Copyright (C) 2006 Matthew Good <trac@matt-good.net>
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

def sql_escape_percent(sql):
    import re
    return re.sub("'((?:[^']|(?:''))*)'", lambda m: m.group(0).replace('%', '%%'), sql)


class IterableCursor(object):
    """Wrapper for DB-API cursor objects that makes the cursor iterable
    and escapes all "%"s used inside literal strings with parameterized
    queries.
    
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

    def execute(self, sql, args=None):
        # -- In case of SQL errors, uncomment the following 'print' statements
        # print 'execute', repr(sql)
        if args:
            # print repr(args)
            return self.cursor.execute(sql_escape_percent(sql), args)
        return self.cursor.execute(sql)

    def executemany(self, sql, args=None):
        # print 'executemany', repr(sql)
        if args:
            # print repr(args)
            return self.cursor.executemany(sql_escape_percent(sql), args)
        return self.cursor.executemany(sql)


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
