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
    return re.sub("'((?:[^']|(?:''))*)'",
                  lambda m: m.group(0).replace('%', '%%'), sql)


class IterableCursor(object):
    """Wrapper for DB-API cursor objects that makes the cursor iterable
    and escapes all "%"s used inside literal strings with parameterized
    queries.
    
    Iteration will generate the rows of a SELECT query one by one.
    """
    __slots__ = ['cursor', 'log']

    def __init__(self, cursor, log=None):
        self.cursor = cursor
        self.log = log

    def __getattr__(self, name):
        return getattr(self.cursor, name)

    def __iter__(self):
        while True:
            row = self.cursor.fetchone()
            if not row:
                return
            yield row

    def execute(self, sql, args=None):
        if self.log:
            self.log.debug('SQL: %r', sql)
            try:
                if args:
                    self.log.debug('args: %r', args)
                    r = self.cursor.execute(sql_escape_percent(sql), args)
                else:
                    r = self.cursor.execute(sql)
                rows = getattr(self.cursor, 'rows', None)
                if rows is not None:
                    self.log.debug("prefetch: %d rows", len(rows))
                return r
            except Exception, e:
                self.log.debug('execute exception: %r', e)
                raise
        if args:
            return self.cursor.execute(sql_escape_percent(sql), args)
        return self.cursor.execute(sql)

    def executemany(self, sql, args):
        if self.log:
            self.log.debug('SQL: %r', sql)
            self.log.debug('args: %r', args)
            if not args:
                return
            try:
                if args[0]:
                    return self.cursor.executemany(sql_escape_percent(sql),
                                                   args)
                return self.cursor.executemany(sql, args)
            except Exception, e:
                self.log.debug('executemany exception: %r', e)
                raise
        if not args:
            return
        if args[0]:
            return self.cursor.executemany(sql_escape_percent(sql), args)
        return self.cursor.executemany(sql, args)


class ConnectionWrapper(object):
    """Generic wrapper around connection objects.
    
    :since 0.12: This wrapper no longer makes cursors produced by the
    connection iterable using `IterableCursor`.
    """
    __slots__ = ('cnx', 'log')

    def __init__(self, cnx, log=None):
        self.cnx = cnx
        self.log = log

    def __getattr__(self, name):
        return getattr(self.cnx, name)
