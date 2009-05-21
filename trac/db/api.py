# -*- coding: utf-8 -*-
#
# Copyright (C)2005-2009 Edgewall Software
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

import os
import urllib
import time

from trac.config import BoolOption, IntOption, Option
from trac.core import *
from trac.db.pool import ConnectionPool
from trac.util.text import unicode_passwd


def get_column_names(cursor):
    return cursor.description and \
           [(isinstance(d[0], str) and [unicode(d[0], 'utf-8')] or [d[0]])[0]
            for d in cursor.description] or []


class IDatabaseConnector(Interface):
    """Extension point interface for components that support the connection to
    relational databases."""

    def get_supported_schemes():
        """Return the connection URL schemes supported by the connector, and
        their relative priorities as an iterable of `(scheme, priority)` tuples.
        """

    def get_connection(**kwargs):
        """Create a new connection to the database."""
        
    def init_db(**kwargs):
        """Initialize the database."""

    def to_sql(table):
        """Return the DDL statements necessary to create the specified table,
        including indices."""
        
    def backup(dest):
        """Backup the database to a location defined by trac.backup_dir"""


class DatabaseManager(Component):

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

    def init_db(self):
        connector, args = self._get_connector()
        connector.init_db(**args)

    def get_connection(self):
        if not self._cnx_pool:
            connector, args = self._get_connector()
            self._cnx_pool = ConnectionPool(5, connector, **args)
        return self._cnx_pool.get_cnx(self.timeout or None)

    def shutdown(self, tid=None):
        if self._cnx_pool:
            self._cnx_pool.shutdown(tid)
            if not tid:
                self._cnx_pool = None
                
    def backup(self, dest=None):
        """Save a backup of the database.

        @param dest: base filename to write to.
        Returns the file actually written.
        """
        connector, args = self._get_connector()
        if not dest:
            backup_dir = self.backup_dir
            if backup_dir[0] != "/":
                backup_dir = os.path.join(self.env.path, backup_dir)
            db_str = self.config.get('trac', 'database')
            db_name, db_path = db_str.split(":",1)
            dest_name = '%s.%i.%d.bak' % (db_name, self.env.get_version(),
                                          int(time.time()))
            dest = os.path.join(backup_dir, dest_name)
        else:
            backup_dir = os.path.dirname(dest)
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
        return connector.backup(dest)

    def _get_connector(self): ### FIXME: Make it public?
        scheme, args = _parse_db_str(self.connection_uri)
        candidates = {}
        for connector in self.connectors:
            for scheme_, priority in connector.get_supported_schemes():
                if scheme_ != scheme:
                    continue
                highest = candidates.get(scheme_, (None, 0))[1]
                if priority > highest:
                    candidates[scheme] = (connector, priority)

        connector = candidates.get(scheme, [None])[0]
        if not connector:
            raise TracError('Unsupported database type "%s"' % scheme)

        if scheme == 'sqlite':
            # Special case for SQLite to support a path relative to the
            # environment directory
            if args['path'] != ':memory:' and \
                   not args['path'].startswith('/'):
                args['path'] = os.path.join(self.env.path,
                                            args['path'].lstrip('/'))

        if self.debug_sql:
            args['log'] = self.log
        return connector, args


def _parse_db_str(db_str):
    scheme, rest = db_str.split(':', 1)

    if not rest.startswith('/'):
        if scheme == 'sqlite':
            # Support for relative and in-memory SQLite connection strings
            host = None
            path = rest
        else:
            raise TracError('Database connection string must start with '
                            'scheme:/')
    else:
        if not rest.startswith('//'):
            host = None
            rest = rest[1:]
        elif rest.startswith('///'):
            host = None
            rest = rest[3:]
        else:
            rest = rest[2:]
            if '/' not in rest:
                host = rest
                rest = ''
            else:
                host, rest = rest.split('/', 1)
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
    if '?' in path:
        path, qs = path.split('?', 1)
        qs = qs.split('&')
        for param in qs:
            name, value = param.split('=', 1)
            value = urllib.unquote(value)
            params[name] = value

    args = zip(('user', 'password', 'host', 'port', 'path', 'params'),
               (user, password, host, port, path, params))
    return scheme, dict([(key, value) for key, value in args if value])
