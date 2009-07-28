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

import re, sys, os, time

from trac.core import *
from trac.config import Option
from trac.db.api import IDatabaseConnector, _parse_db_str
from trac.db.util import ConnectionWrapper
from trac.util import get_pkginfo
from trac.util.compat import close_fds
from trac.util.text import to_unicode

psycopg = None
PgSQL = None
PGSchemaError = None

_like_escape_re = re.compile(r'([/_%])')


class PostgreSQLConnector(Component):
    """PostgreSQL database support."""

    implements(IDatabaseConnector)

    pg_dump_path = Option('trac', 'pg_dump_path', 'pg_dump',
        """Location of pg_dump for Postgres database backups""")

    def __init__(self):
        self._version = None

    def get_supported_schemes(self):
        return [('postgres', 1)]

    def get_connection(self, path, log=None, user=None, password=None,
                       host=None, port=None, params={}):
        global psycopg
        global PgSQL
        cnx = PostgreSQLConnection(path, log, user, password, host, port,
                                   params)
        if not self._version:
            if psycopg:
                self._version = get_pkginfo(psycopg).get('version',
                                                         psycopg.__version__)
                name = 'psycopg2'
            elif PgSQL:
                import pyPgSQL
                self._version = get_pkginfo(pyPgSQL).get('version',
                                                         pyPgSQL.__version__)
                name = 'pyPgSQL'
            else:
                name = 'unknown postgreSQL driver'
                self._version = '?'
            self.env.systeminfo.append((name, self._version))
        return cnx

    def init_db(self, path, log=None, user=None, password=None, host=None,
                port=None, params={}):
        cnx = self.get_connection(path, log, user, password, host, port,
                                  params)
        cursor = cnx.cursor()
        if cnx.schema:
            cursor.execute('CREATE SCHEMA "%s"' % cnx.schema)
            cursor.execute('SET search_path TO %s', (cnx.schema,))
        from trac.db_default import schema
        for table in schema:
            for stmt in self.to_sql(table):
                cursor.execute(stmt)
        cnx.commit()

    def to_sql(self, table):
        sql = ['CREATE TABLE "%s" (' % table.name]
        coldefs = []
        for column in table.columns:
            ctype = column.type
            if column.auto_increment:
                ctype = 'SERIAL'
            if len(table.key) == 1 and column.name in table.key:
                ctype += ' PRIMARY KEY'
            coldefs.append('    "%s" %s' % (column.name, ctype))
        if len(table.key) > 1:
            coldefs.append('    CONSTRAINT "%s_pk" PRIMARY KEY ("%s")'
                           % (table.name, '","'.join(table.key)))
        sql.append(',\n'.join(coldefs) + '\n)')
        yield '\n'.join(sql)
        for index in table.indices:
            unique = index.unique and 'UNIQUE' or ''
            yield 'CREATE %s INDEX "%s_%s_idx" ON "%s" ("%s")' % \
                    (unique, table.name, 
                     '_'.join(index.columns), table.name,
                     '","'.join(index.columns))

    def backup(self, dest_file):
        try:
            from subprocess import Popen, PIPE
        except ImportError:
            raise TracError('Python >= 2.4 or the subprocess module '
                            'is required for pre-upgrade backup support')
        db_url = self.env.config.get('trac', 'database')
        scheme, db_prop = _parse_db_str(db_url)
        db_prop.setdefault('params', {})
        db_name = os.path.basename(db_prop['path'])

        args = [self.pg_dump_path, '-C', '-d', '-x', '-Z', '8']
        if 'user' in db_prop:
            args.extend(['-U', db_prop['user']])
        if 'host' in db_prop['params']:
            host = db_prop['params']['host']
        else:
            host = db_prop.get('host', 'localhost')
        args.extend(['-h', host])
        if '/' not in host:
            args.extend(['-p', str(db_prop.get('port', '5432'))])

        if 'schema' in db_prop['params']:
            args.extend(['-n', '"%s"' % db_prop['params']['schema']])

        dest_file += ".gz"
        args.extend(['-f', dest_file, db_name])

        environ = os.environ.copy()
        if 'password' in db_prop:
            environ['PGPASSWORD'] = str(db_prop['password'])
        p = Popen(args, env=environ, stderr=PIPE, close_fds=close_fds)
        errmsg = p.communicate()[1]
        if p.returncode != 0:
            raise TracError("Backup attempt failed (%s)" % to_unicode(errmsg))
        if not os.path.exists(dest_file):
            raise TracError("Backup attempt failed")
        return dest_file


class PostgreSQLConnection(ConnectionWrapper):
    """Connection wrapper for PostgreSQL."""

    poolable = True

    def __init__(self, path, log=None, user=None, password=None, host=None,
                 port=None, params={}):
        if path.startswith('/'):
            path = path[1:]
        # We support both psycopg and PgSQL but prefer psycopg
        global psycopg
        global PgSQL
        global PGSchemaError
        
        if not psycopg and not PgSQL:
            try:
                import psycopg2 as psycopg
                import psycopg2.extensions
                from psycopg2 import ProgrammingError as PGSchemaError
                psycopg2.extensions.register_type(psycopg2.extensions.UNICODE)
            except ImportError:
                from pyPgSQL import PgSQL
                from pyPgSQL.libpq import OperationalError as PGSchemaError
        if 'host' in params:
            host = params['host']
        if psycopg:
            dsn = []
            if path:
                dsn.append('dbname=' + path)
            if user:
                dsn.append('user=' + user)
            if password:
                dsn.append('password=' + password)
            if host:
                dsn.append('host=' + host)
            if port:
                dsn.append('port=' + str(port))
            cnx = psycopg.connect(' '.join(dsn))
            cnx.set_client_encoding('UNICODE')
        else:
            # Don't use chatty, inefficient server-side cursors.
            # http://pypgsql.sourceforge.net/pypgsql-faq.html#id2787367
            PgSQL.fetchReturnsList = 1
            PgSQL.noPostgresCursor = 1
            cnx = PgSQL.connect('', user, password, host, path, port, 
                                client_encoding='utf-8', unicode_results=True)
        try:
            self.schema = None
            if 'schema' in params:
                self.schema = params['schema']
                cnx.cursor().execute('SET search_path TO %s', (self.schema,))
                cnx.commit()
        except PGSchemaError:
            cnx.rollback()
        ConnectionWrapper.__init__(self, cnx, log)

    def cast(self, column, type):
        # Temporary hack needed for the union of selects in the search module
        return 'CAST(%s AS %s)' % (column, type)

    def concat(self, *args):
        return '||'.join(args)

    def like(self):
        # Temporary hack needed for the case-insensitive string matching in the
        # search module
        return "ILIKE %s ESCAPE '/'"

    def like_escape(self, text):
        return _like_escape_re.sub(r'/\1', text)

    def get_last_id(self, cursor, table, column='id'):
        cursor.execute("SELECT CURRVAL('%s_%s_seq')" % (table, column))
        return cursor.fetchone()[0]
