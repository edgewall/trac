# -*- coding: utf-8 -*-
#
# Copyright (C)2005-2014 Edgewall Software
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
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

from __future__ import with_statement

import os
import time
import urllib

from genshi.builder import tag
from trac.config import BoolOption, ConfigurationError, IntOption, Option
from trac.core import *
from trac.db.schema import Table
from trac.util.concurrency import ThreadLocal
from trac.util.text import unicode_passwd
from trac.util.translation import _, tag_

from .pool import ConnectionPool
from .util import ConnectionWrapper


def with_transaction(env, db=None):
    """Function decorator to emulate a context manager for database
    transactions.

    >>> def api_method(p1, p2):
    >>>     result[0] = value1
    >>>     @with_transaction(env)
    >>>     def implementation(db):
    >>>         # implementation
    >>>         result[0] = value2
    >>>     return result[0]

    In this example, the `implementation()` function is called
    automatically right after its definition, with a database
    connection as an argument. If the function completes, a COMMIT is
    issued on the connection. If the function raises an exception, a
    ROLLBACK is issued and the exception is re-raised. Nested
    transactions are supported, and a COMMIT will only be issued when
    the outermost transaction block in a thread exits.

    This mechanism is intended to replace the former practice of
    getting a database connection with `env.get_db_cnx()` and issuing
    an explicit commit or rollback, for mutating database
    accesses. Its automatic handling of commit, rollback and nesting
    makes it much more robust.

    The optional `db` argument is intended for legacy code and should
    not be used in new code.

    :deprecated: This decorator is in turn deprecated in favor of
                 context managers now that python 2.4 support has been
                 dropped. It will be removed in Trac 1.3.1. Use instead
                 the new context managers, `QueryContextManager` and
                 `TransactionContextManager`, which make for much
                 simpler to write code:

    >>> def api_method(p1, p2):
    >>>     result = value1
    >>>     with env.db_transaction as db:
    >>>         # implementation
    >>>         result = value2
    >>>     return result

    """
    dbm = DatabaseManager(env)
    _transaction_local = dbm._transaction_local

    def transaction_wrapper(fn):
        ldb = _transaction_local.wdb
        if db is not None:
            if ldb is None:
                _transaction_local.wdb = db
                try:
                    fn(db)
                finally:
                    _transaction_local.wdb = None
            else:
                assert ldb is db, "Invalid transaction nesting"
                fn(db)
        elif ldb:
            fn(ldb)
        else:
            ldb = _transaction_local.wdb = dbm.get_connection()
            try:
                fn(ldb)
                ldb.commit()
                _transaction_local.wdb = None
            except:
                _transaction_local.wdb = None
                ldb.rollback()
                ldb = None
                raise
    return transaction_wrapper


class DbContextManager(object):
    """Database Context Manager

    The outermost `DbContextManager` will close the connection.
    """

    db = None

    def __init__(self, env):
        self.dbmgr = DatabaseManager(env)

    def execute(self, query, params=None):
        """Shortcut for directly executing a query."""
        with self as db:
            return db.execute(query, params)

    __call__ = execute

    def executemany(self, query, params=None):
        """Shortcut for directly calling "executemany" on a query."""
        with self as db:
            return db.executemany(query, params)


class TransactionContextManager(DbContextManager):
    """Transactioned Database Context Manager for retrieving a
    `~trac.db.util.ConnectionWrapper`.

    The outermost such context manager will perform a commit upon
    normal exit or a rollback after an exception.
    """

    def __enter__(self):
        db = self.dbmgr._transaction_local.wdb # outermost writable db
        if not db:
            db = self.dbmgr._transaction_local.rdb # reuse wrapped connection
            if db:
                db = ConnectionWrapper(db.cnx, db.log)
            else:
                db = self.dbmgr.get_connection()
            self.dbmgr._transaction_local.wdb = self.db = db
        return db

    def __exit__(self, et, ev, tb):
        if self.db:
            self.dbmgr._transaction_local.wdb = None
            if et is None:
                self.db.commit()
            else:
                self.db.rollback()
            if not self.dbmgr._transaction_local.rdb:
                self.db.close()


class QueryContextManager(DbContextManager):
    """Database Context Manager for retrieving a read-only
    `~trac.db.util.ConnectionWrapper`.
    """

    def __enter__(self):
        db = self.dbmgr._transaction_local.rdb # outermost readonly db
        if not db:
            db = self.dbmgr._transaction_local.wdb # reuse wrapped connection
            if db:
                db = ConnectionWrapper(db.cnx, db.log, readonly=True)
            else:
                db = self.dbmgr.get_connection(readonly=True)
            self.dbmgr._transaction_local.rdb = self.db = db
        return db

    def __exit__(self, et, ev, tb):
        if self.db:
            self.dbmgr._transaction_local.rdb = None
            if not self.dbmgr._transaction_local.wdb:
                self.db.close()


class IDatabaseConnector(Interface):
    """Extension point interface for components that support the
    connection to relational databases.
    """

    def get_supported_schemes():
        """Return the connection URL schemes supported by the
        connector, and their relative priorities as an iterable of
        `(scheme, priority)` tuples.

        If `priority` is a negative number, this is indicative of an
        error condition with the connector. An error message should be
        attached to the `error` attribute of the connector.
        """

    def get_connection(path, log=None, **kwargs):
        """Create a new connection to the database."""

    def get_exceptions():
        """Return an object (typically a module) containing all the
        backend-specific exception types as attributes, named
        according to the Python Database API
        (http://www.python.org/dev/peps/pep-0249/).
        """

    def init_db(path, schema=None, log=None, **kwargs):
        """Initialize the database."""

    def to_sql(table):
        """Return the DDL statements necessary to create the specified
        table, including indices."""

    def backup(dest):
        """Backup the database to a location defined by
        trac.backup_dir"""


class DatabaseManager(Component):
    """Component used to manage the `IDatabaseConnector` implementations."""

    connectors = ExtensionPoint(IDatabaseConnector)

    connection_uri = Option('trac', 'database', 'sqlite:db/trac.db',
        """Database connection
        [wiki:TracEnvironment#DatabaseConnectionStrings string] for this
        project""")

    backup_dir = Option('trac', 'backup_dir', 'db',
        """Database backup location""")

    timeout = IntOption('trac', 'timeout', '20',
        """Timeout value for database connection, in seconds.
        Use '0' to specify ''no timeout''. ''(Since 0.11)''""")

    debug_sql = BoolOption('trac', 'debug_sql', False,
        """Show the SQL queries in the Trac log, at DEBUG level.
        ''(Since 0.11.5)''""")

    def __init__(self):
        self._cnx_pool = None
        self._transaction_local = ThreadLocal(wdb=None, rdb=None)

    def init_db(self):
        connector, args = self.get_connector()
        from trac.db_default import schema
        args['schema'] = schema
        connector.init_db(**args)

    def create_tables(self, schema):
        """Create the specified tables.

        :param schema: an iterable of table objects.

        :since: version 1.0.2
        """
        connector = self.get_connector()[0]
        with self.env.db_transaction as db:
            for table in schema:
                for sql in connector.to_sql(table):
                    db(sql)

    def drop_tables(self, schema):
        """Drop the specified tables.

        :param schema: an iterable of `Table` objects or table names.

        :since: version 1.0.2
        """
        with self.env.db_transaction as db:
            for table in schema:
                table_name = table.name if isinstance(table, Table) else table
                db.drop_table(table_name)

    def get_connection(self, readonly=False):
        """Get a database connection from the pool.

        If `readonly` is `True`, the returned connection will purposely
        lack the `rollback` and `commit` methods.
        """
        if not self._cnx_pool:
            connector, args = self.get_connector()
            self._cnx_pool = ConnectionPool(5, connector, **args)
        db = self._cnx_pool.get_cnx(self.timeout or None)
        if readonly:
            db = ConnectionWrapper(db, readonly=True)
        return db

    def get_exceptions(self):
        return self.get_connector()[0].get_exceptions()

    def shutdown(self, tid=None):
        if self._cnx_pool:
            self._cnx_pool.shutdown(tid)
            if not tid:
                self._cnx_pool = None

    def backup(self, dest=None):
        """Save a backup of the database.

        :param dest: base filename to write to.

        Returns the file actually written.
        """
        connector, args = self.get_connector()
        if not dest:
            backup_dir = self.backup_dir
            if not os.path.isabs(backup_dir):
                backup_dir = os.path.join(self.env.path, backup_dir)
            db_str = self.config.get('trac', 'database')
            db_name, db_path = db_str.split(":", 1)
            dest_name = '%s.%i.%d.bak' % (db_name, self.env.database_version,
                                          int(time.time()))
            dest = os.path.join(backup_dir, dest_name)
        else:
            backup_dir = os.path.dirname(dest)
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
        return connector.backup(dest)

    def get_connector(self):
        scheme, args = _parse_db_str(self.connection_uri)
        candidates = [
            (priority, connector)
            for connector in self.connectors
            for scheme_, priority in connector.get_supported_schemes()
            if scheme_ == scheme
        ]
        if not candidates:
            raise TracError(_('Unsupported database type "%(scheme)s"',
                              scheme=scheme))
        priority, connector = max(candidates)
        if priority < 0:
            raise TracError(connector.error)

        if scheme == 'sqlite':
            if args['path'] == ':memory:':
                # Special case for SQLite in-memory database, always get
                # the /same/ connection over
                pass
            elif not os.path.isabs(args['path']):
                # Special case for SQLite to support a path relative to the
                # environment directory
                args['path'] = os.path.join(self.env.path,
                                            args['path'].lstrip('/'))

        if self.debug_sql:
            args['log'] = self.log
        return connector, args

    _get_connector = get_connector  # For 0.11 compatibility


def get_column_names(cursor):
    """Retrieve column names from a cursor, if possible."""
    return [unicode(d[0], 'utf-8') if isinstance(d[0], str) else d[0]
            for d in cursor.description] if cursor.description else []


def _parse_db_str(db_str):
    if not db_str:
        section = tag.a("[trac]",
                        title=_("TracIni documentation"),
                        class_='trac-target-new',
                        href='http://trac.edgewall.org/wiki/TracIni'
                             '#trac-section')
        raise ConfigurationError(
            tag_("Database connection string is empty. Set the %(option)s "
                 "configuration option in the %(section)s section of "
                 "trac.ini. Please refer to the %(doc)s for help.",
                 option=tag.tt("database"), section=section,
                 doc=_doc_db_str()))

    try:
        scheme, rest = db_str.split(':', 1)
    except ValueError:
        raise _invalid_db_str(db_str)

    if not rest.startswith('/'):
        if scheme == 'sqlite' and rest:
            # Support for relative and in-memory SQLite connection strings
            host = None
            path = rest
        else:
            raise _invalid_db_str(db_str)
    else:
        if not rest.startswith('//'):
            host = None
            rest = rest[1:]
        elif rest.startswith('///'):
            host = None
            rest = rest[3:]
        else:
            rest = rest[2:]
            if '/' in rest:
                host, rest = rest.split('/', 1)
            else:
                host = rest
                rest = ''
        path = None

    if host and '@' in host:
        user, host = host.split('@', 1)
        if ':' in user:
            user, password = user.split(':', 1)
        else:
            password = None
        if user:
            user = urllib.unquote(user)
        if password:
            password = unicode_passwd(urllib.unquote(password))
    else:
        user = password = None

    if host and ':' in host:
        host, port = host.split(':', 1)
        try:
            port = int(port)
        except ValueError:
            raise _invalid_db_str(db_str)
    else:
        port = None

    if not path:
        path = '/' + rest
    if os.name == 'nt':
        # Support local paths containing drive letters on Win32
        if len(rest) > 1 and rest[1] == '|':
            path = "%s:%s" % (rest[0], rest[2:])

    params = {}
    if '?' in path:
        path, qs = path.split('?', 1)
        qs = qs.split('&')
        for param in qs:
            try:
                name, value = param.split('=', 1)
            except ValueError:
                raise _invalid_db_str(db_str)
            value = urllib.unquote(value)
            params[name] = value

    args = zip(('user', 'password', 'host', 'port', 'path', 'params'),
               (user, password, host, port, path, params))
    return scheme, dict([(key, value) for key, value in args if value])


def _invalid_db_str(db_str):
    return ConfigurationError(
        tag_("Invalid format %(db_str)s for the database connection string. "
             "Please refer to the %(doc)s for help.",
             db_str=tag.tt(db_str), doc=_doc_db_str()))


def _doc_db_str():
    return tag.a(_("documentation"),
                 title=_("Database Connection Strings documentation"),
                 class_='trac-target-new',
                 href='http://trac.edgewall.org/wiki/'
                      'TracIni#DatabaseConnectionStrings')
