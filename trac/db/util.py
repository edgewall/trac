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

from trac.util.concurrency import ThreadLocal


_transaction_local = ThreadLocal(db=None)

def with_transaction(env, db=None):
    """Transaction decorator for simple use-once transactions.
    
    >>> def api_method(p1, p2):
    >>>     result[0] = value1
    >>>     @with_transaction(env)
    >>>     def implementation_method(db):
    >>>         # implementation
    >>>         result[0] = value2
    >>>     return result[0]
    
    Nested transactions are supported, and a COMMIT will only be issued when
    the outermost transaction block in a thread exits.
    
    This decorator will be replaced by a context manager once python 2.4
    support is dropped.

    The optional `db` argument is intended for legacy code and should not
    be used in new code.
    """
    def transaction_wrapper(fn):
        ldb = _transaction_local.db
        if db is not None:
            if ldb is None:
                _transaction_local.db = db
                try:
                    fn(db)
                finally:
                    _transaction_local.db = None
            else:
                assert ldb is db, "Invalid transaction nesting"
                fn(db)
        elif ldb:
            fn(ldb)
        else:
            ldb = _transaction_local.db = env.get_db_cnx()
            try:
                fn(ldb)
                ldb.commit()
                _transaction_local.db = None
            except:
                _transaction_local.db = None
                ldb.rollback()
                ldb = None
                raise
    return transaction_wrapper


def get_read_db(env):
    """Get a database connection for reading only."""
    return _transaction_local.db or env.get_db_cnx()


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
