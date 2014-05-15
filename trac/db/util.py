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

import re

_sql_escape_percent_re = re.compile("""
    '(?:[^']+|'')*' |
    `(?:[^`]+|``)*` |
    "(?:[^"]+|"")*" """, re.VERBOSE)


def sql_escape_percent(sql):
    def repl(match):
        return match.group(0).replace('%', '%%')
    return _sql_escape_percent_re.sub(repl, sql)


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
            self.log.debug('SQL: %s', sql)
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
            except Exception as e:
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
            except Exception as e:
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

    :since 1.0: added a 'readonly' flag preventing the forwarding of
                `commit` and `rollback`
    """
    __slots__ = ('cnx', 'log', 'readonly')

    def __init__(self, cnx, log=None, readonly=False):
        self.cnx = cnx
        self.log = log
        self.readonly = readonly

    def __getattr__(self, name):
        if self.readonly and name in ('commit', 'rollback'):
            raise AttributeError
        return getattr(self.cnx, name)

    def execute(self, query, params=None):
        """Execute an SQL `query`

        The optional `params` is a tuple containing the parameter
        values expected by the query.

        If the query is a SELECT, return all the rows ("fetchall").
        When more control is needed, use `cursor()`.
        """
        dql = self.check_select(query)
        cursor = self.cnx.cursor()
        cursor.execute(query, params if params is not None else [])
        rows = cursor.fetchall() if dql else None
        cursor.close()
        return rows

    __call__ = execute

    def executemany(self, query, params=None):
        """Execute an SQL `query`, on a sequence of tuples ("executemany").

        The optional `params` is a sequence of tuples containing the
        parameter values expected by the query.

        If the query is a SELECT, return all the rows ("fetchall").
        When more control is needed, use `cursor()`.
        """
        dql = self.check_select(query)
        cursor = self.cnx.cursor()
        cursor.executemany(query, params)
        rows = cursor.fetchall() if dql else None
        cursor.close()
        return rows

    def check_select(self, query):
        """Verify if the query is compatible according to the readonly nature
        of the wrapped Connection.

        :return: `True` if this is a SELECT
        :raise: `ValueError` if this is not a SELECT and the wrapped
                Connection is read-only.
        """
        dql = query.lstrip().startswith('SELECT')
        if self.readonly and not dql:
            raise ValueError("a 'readonly' connection can only do a SELECT")
        return dql
