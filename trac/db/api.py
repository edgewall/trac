# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2019 Edgewall Software
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.
#
# Author: Christopher Lenz <cmlenz@gmx.de>

import importlib
import os
import time
import urllib
from abc import ABCMeta, abstractmethod

from trac import db_default
from trac.api import IEnvironmentSetupParticipant, ISystemInfoProvider
from trac.config import BoolOption, ConfigurationError, IntOption, Option
from trac.core import *
from trac.db.pool import ConnectionPool
from trac.db.schema import Table
from trac.db.util import ConnectionWrapper
from trac.util.concurrency import ThreadLocal
from trac.util.html import tag
from trac.util.text import unicode_passwd
from trac.util.translation import _, tag_


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
        db = self.dbmgr._transaction_local.wdb  # outermost writable db
        if not db:
            db = self.dbmgr._transaction_local.rdb  # reuse wrapped connection
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
        db = self.dbmgr._transaction_local.rdb  # outermost readonly db
        if not db:
            db = self.dbmgr._transaction_local.wdb  # reuse wrapped connection
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


class ConnectionBase(object):
    """Abstract base class for database connection classes."""

    __metaclass__ = ABCMeta

    @abstractmethod
    def cast(self, column, type):
        """Returns a clause casting `column` as `type`."""
        pass

    @abstractmethod
    def concat(self, *args):
        """Returns a clause concatenating the sequence `args`."""
        pass

    @abstractmethod
    def drop_column(self, table, column):
        """Drops the `column` from `table`."""
        pass

    @abstractmethod
    def drop_table(self, table):
        """Drops the `table`."""
        pass

    @abstractmethod
    def get_column_names(self, table):
        """Returns the list of the column names in `table`."""
        pass

    @abstractmethod
    def get_last_id(self, cursor, table, column='id'):
        """Returns the current value of the primary key sequence for `table`.
        The `column` of the primary key may be specified, which defaults
        to `id`."""
        pass

    @abstractmethod
    def get_sequence_names(self):
        """Returns a list of the sequence names."""
        pass

    @abstractmethod
    def get_table_names(self):
        """Returns a list of the table names."""
        pass

    @abstractmethod
    def has_table(self, table):
        """Returns whether the table exists."""
        pass

    @abstractmethod
    def like(self):
        """Returns a case-insensitive `LIKE` clause."""
        pass

    @abstractmethod
    def like_escape(self, text):
        """Returns `text` escaped for use in a `LIKE` clause."""
        pass

    @abstractmethod
    def prefix_match(self):
        """Return a case sensitive prefix-matching operator."""
        pass

    @abstractmethod
    def prefix_match_value(self, prefix):
        """Return a value for case sensitive prefix-matching operator."""
        pass

    @abstractmethod
    def quote(self, identifier):
        """Returns the quoted `identifier`."""
        pass

    @abstractmethod
    def reset_tables(self):
        """Deletes all data from the tables and resets autoincrement indexes.

        :return: list of names of the tables that were reset.
        """
        pass

    @abstractmethod
    def update_sequence(self, cursor, table, column='id'):
        """Updates the current value of the primary key sequence for `table`.
        The `column` of the primary key may be specified, which defaults
        to `id`."""
        pass


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

    def destroy_db(self, path, log=None, **kwargs):
        """Destroy the database."""

    def db_exists(self, path, log=None, **kwargs):
        """Return `True` if the database exists."""

    def to_sql(table):
        """Return the DDL statements necessary to create the specified
        table, including indices."""

    def backup(dest):
        """Backup the database to a location defined by
        trac.backup_dir"""

    def get_system_info():
        """Yield a sequence of `(name, version)` tuples describing the
        name and version information of external packages used by the
        connector.
        """


class DatabaseManager(Component):
    """Component used to manage the `IDatabaseConnector` implementations."""

    implements(IEnvironmentSetupParticipant, ISystemInfoProvider)

    connectors = ExtensionPoint(IDatabaseConnector)

    connection_uri = Option('trac', 'database', 'sqlite:db/trac.db',
        """Database connection
        [wiki:TracEnvironment#DatabaseConnectionStrings string] for this
        project""")

    backup_dir = Option('trac', 'backup_dir', 'db',
        """Database backup location""")

    timeout = IntOption('trac', 'timeout', '20',
        """Timeout value for database connection, in seconds.
        Use '0' to specify ''no timeout''.""")

    debug_sql = BoolOption('trac', 'debug_sql', False,
        """Show the SQL queries in the Trac log, at DEBUG level.
        """)

    def __init__(self):
        self._cnx_pool = None
        self._transaction_local = ThreadLocal(wdb=None, rdb=None)

    def init_db(self):
        connector, args = self.get_connector()
        args['schema'] = db_default.schema
        connector.init_db(**args)

    def destroy_db(self):
        connector, args = self.get_connector()
        # Connections to on-disk db must be closed before deleting it.
        self.shutdown()
        connector.destroy_db(**args)

    def db_exists(self):
        connector, args = self.get_connector()
        return connector.db_exists(**args)

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

    def drop_columns(self, table, columns):
        """Drops the specified columns from table.

        :since: version 1.2
        """
        table_name = table.name if isinstance(table, Table) else table
        with self.env.db_transaction as db:
            if not db.has_table(table_name):
                raise self.env.db_exc.OperationalError('Table %s not found' %
                                                       db.quote(table_name))
            for col in columns:
                db.drop_column(table_name, col)

    def drop_tables(self, schema):
        """Drop the specified tables.

        :param schema: an iterable of `Table` objects or table names.

        :since: version 1.0.2
        """
        with self.env.db_transaction as db:
            for table in schema:
                table_name = table.name if isinstance(table, Table) else table
                db.drop_table(table_name)

    def insert_into_tables(self, data_or_callable):
        """Insert data into existing tables.

        :param data_or_callable: Nested tuples of table names, column names
                                 and row data::

                                   (table1,
                                    (column1, column2),
                                    ((row1col1, row1col2),
                                     (row2col1, row2col2)),
                                    table2, ...)

                                 or a callable that takes a single parameter
                                 `db` and returns the aforementioned nested
                                 tuple.
        :since: version 1.1.3
        """
        with self.env.db_transaction as db:
            data = data_or_callable(db) if callable(data_or_callable) \
                                        else data_or_callable
            for table, cols, vals in data:
                db.executemany("INSERT INTO %s (%s) VALUES (%s)"
                               % (db.quote(table), ','.join(cols),
                                  ','.join(['%s'] * len(cols))), vals)

    def reset_tables(self):
        """Deletes all data from the tables and resets autoincrement indexes.

        :return: list of names of the tables that were reset.

        :since: version 1.1.3
        """
        with self.env.db_transaction as db:
            return db.reset_tables()

    def upgrade_tables(self, new_schema):
        """Upgrade table schema to `new_schema`, preserving data in
        columns that exist in the current schema and `new_schema`.

        :param new_schema: tuple or list of `Table` objects

        :since: version 1.2
        """
        with self.env.db_transaction as db:
            cursor = db.cursor()
            for new_table in new_schema:
                temp_table_name = new_table.name + '_old'
                has_table = self.has_table(new_table)
                if has_table:
                    old_column_names = set(self.get_column_names(new_table))
                    new_column_names = {col.name for col in new_table.columns}
                    column_names = old_column_names & new_column_names
                    if column_names:
                        cols_to_copy = ','.join(db.quote(name)
                                                for name in column_names)
                        cursor.execute("""
                            CREATE TEMPORARY TABLE %s AS SELECT * FROM %s
                            """ % (db.quote(temp_table_name),
                                   db.quote(new_table.name)))
                    self.drop_tables((new_table,))
                self.create_tables((new_table,))
                if has_table and column_names:
                    cursor.execute("""
                        INSERT INTO %s (%s) SELECT %s FROM %s
                        """ % (db.quote(new_table.name), cols_to_copy,
                               cols_to_copy, db.quote(temp_table_name)))
                    for col in new_table.columns:
                        if col.auto_increment:
                            db.update_sequence(cursor, new_table.name,
                                               col.name)
                    self.drop_tables((temp_table_name,))

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

    def get_database_version(self, name='database_version'):
        """Returns the database version from the SYSTEM table as an int,
        or `False` if the entry is not found.

        :param name: The name of the entry that contains the database version
                     in the SYSTEM table. Defaults to `database_version`,
                     which contains the database version for Trac.
        """
        with self.env.db_query as db:
            for value, in db("""
                    SELECT value FROM {0} WHERE name=%s
                    """.format(db.quote('system')), (name,)):
                return int(value)
            else:
                return False

    def get_exceptions(self):
        return self.get_connector()[0].get_exceptions()

    def get_sequence_names(self):
        """Returns a list of the sequence names.

        :since: 1.3.2
        """
        with self.env.db_query as db:
            return db.get_sequence_names()

    def get_table_names(self):
        """Returns a list of the table names.

        :since: 1.1.6
        """
        with self.env.db_query as db:
            return db.get_table_names()

    def get_column_names(self, table):
        """Returns a list of the column names for `table`.

        :param table: a `Table` object or table name.

        :since: 1.2
        """
        table_name = table.name if isinstance(table, Table) else table
        with self.env.db_query as db:
            if not db.has_table(table_name):
                raise self.env.db_exc.OperationalError('Table %s not found' %
                                                       db.quote(table_name))
            return db.get_column_names(table_name)

    def has_table(self, table):
        """Returns whether the table exists."""
        table_name = table.name if isinstance(table, Table) else table
        with self.env.db_query as db:
            return db.has_table(table_name)

    def set_database_version(self, version, name='database_version'):
        """Sets the database version in the SYSTEM table.

        :param version: an integer database version.
        :param name: The name of the entry that contains the database version
                     in the SYSTEM table. Defaults to `database_version`,
                     which contains the database version for Trac.
        """
        current_database_version = self.get_database_version(name)
        if current_database_version is False:
            with self.env.db_transaction as db:
                db("""
                    INSERT INTO {0} (name, value) VALUES (%s, %s)
                    """.format(db.quote('system')), (name, version))
        else:
            with self.env.db_transaction as db:
                db("""
                    UPDATE {0} SET value=%s WHERE name=%s
                    """.format(db.quote('system')), (version, name))
            self.log.info("Upgraded %s from %d to %d",
                          name, current_database_version, version)

    def needs_upgrade(self, version, name='database_version'):
        """Checks the database version to determine if an upgrade is needed.

        :param version: the expected integer database version.
        :param name: the name of the entry in the SYSTEM table that contains
                     the database version. Defaults to `database_version`,
                     which contains the database version for Trac.

        :return: `True` if the stored version is less than the expected
                  version, `False` if it is equal to the expected version.
        :raises TracError: if the stored version is greater than the expected
                           version.
        """
        dbver = self.get_database_version(name)
        if dbver == version:
            return False
        elif dbver > version:
            raise TracError(_("Need to downgrade %(name)s.", name=name))
        self.log.info("Need to upgrade %s from %d to %d",
                      name, dbver, version)
        return True

    def upgrade(self, version, name='database_version', pkg='trac.upgrades'):
        """Invokes `do_upgrade(env, version, cursor)` in module
        `"%s/db%i.py" % (pkg, version)`, for each required version upgrade.

        :param version: the expected integer database version.
        :param name: the name of the entry in the SYSTEM table that contains
                     the database version. Defaults to `database_version`,
                     which contains the database version for Trac.
        :param pkg: the package containing the upgrade modules.

        :raises TracError: if the package or module doesn't exist.
        """
        dbver = self.get_database_version(name)
        for i in xrange(dbver + 1, version + 1):
            module = '%s.db%i' % (pkg, i)
            try:
                upgrader = importlib.import_module(module)
            except ImportError:
                raise TracError(_("No upgrade module %(module)s.py",
                                  module=module))
            with self.env.db_transaction as db:
                cursor = db.cursor()
                upgrader.do_upgrade(self.env, i, cursor)
                self.set_database_version(i, name)

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
        scheme, args = parse_connection_uri(self.connection_uri)
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

    # IEnvironmentSetupParticipant methods

    def environment_created(self):
        """Insert default data into the database."""
        self.insert_into_tables(db_default.get_data)

    def environment_needs_upgrade(self):
        return self.needs_upgrade(db_default.db_version)

    def upgrade_environment(self):
        self.upgrade(db_default.db_version)

    # ISystemInfoProvider methods

    def get_system_info(self):
        connector = self.get_connector()[0]
        for info in connector.get_system_info():
            yield info


def get_column_names(cursor):
    """Retrieve column names from a cursor, if possible."""
    return [unicode(d[0], 'utf-8') if isinstance(d[0], str) else d[0]
            for d in cursor.description] if cursor.description else []


def parse_connection_uri(db_str):
    """Parse the database connection string.

    The database connection string for an environment is specified through
    the `database` option in the `[trac]` section of trac.ini.

    :return: a tuple containing the scheme and a dictionary of attributes:
             `user`, `password`, `host`, `port`, `path`, `params`.
    :since: 1.1.3
    """
    if not db_str:
        section = tag.a("[trac]",
                        title=_("TracIni documentation"),
                        class_='trac-target-new',
                        href='https://trac.edgewall.org/wiki/TracIni'
                             '#trac-section')
        raise ConfigurationError(
            tag_("Database connection string is empty. Set the %(option)s "
                 "configuration option in the %(section)s section of "
                 "trac.ini. Please refer to the %(doc)s for help.",
                 option=tag.code("database"), section=section,
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
    return scheme, {key: value for key, value in args if value}


def _invalid_db_str(db_str):
    return ConfigurationError(
        tag_("Invalid format %(db_str)s for the database connection string. "
             "Please refer to the %(doc)s for help.",
             db_str=tag.code(db_str), doc=_doc_db_str()))


def _doc_db_str():
    return tag.a(_("documentation"),
                 title=_("Database Connection Strings documentation"),
                 class_='trac-target-new',
                 href='https://trac.edgewall.org/wiki/'
                      'TracIni#DatabaseConnectionStrings')
