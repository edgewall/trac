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

from ctypes.util import find_library
import ctypes
import os
import re

from genshi import Markup

from trac.api import ISystemInfoProvider
from trac.core import *
from trac.config import Option
from trac.db.api import ConnectionBase, IDatabaseConnector, \
                        parse_connection_uri
from trac.db.util import ConnectionWrapper, IterableCursor
from trac.util import get_pkginfo, lazy
from trac.util.compat import close_fds
from trac.util.text import empty, exception_to_unicode, to_unicode
from trac.util.translation import _

try:
    import psycopg2 as psycopg
    import psycopg2.extensions
    from psycopg2 import DataError, ProgrammingError
    from psycopg2.extensions import register_type, UNICODE, \
                                    register_adapter, AsIs, QuotedString
except ImportError:
    has_psycopg = False
    psycopg = None
    psycopg2_version = None
else:
    has_psycopg = True
    register_type(UNICODE)
    register_adapter(Markup, lambda markup: QuotedString(unicode(markup)))
    register_adapter(type(empty), lambda empty: AsIs("''"))
    psycopg2_version = get_pkginfo(psycopg).get('version',
                                                psycopg.__version__)

if hasattr(psycopg, 'libpq_version'):
    _libpq_pathname = None
else:
    try:
        _libpq_pathname = find_library('pq' if os.name != 'nt' else 'libpq')
    except Exception:
        _libpq_pathname = None

_like_escape_re = re.compile(r'([/_%])')

# Mapping from "abstract" SQL types to DB-specific types
_type_map = {
    'int64': 'bigint',
}

min_postgresql_version = (9, 1, 0)


def assemble_pg_dsn(path, user=None, password=None, host=None, port=None):
    """Quote the parameters and assemble the DSN."""
    def quote(value):
        if not isinstance(value, basestring):
            value = unicode(value)
        return "'%s'" % value.replace('\\', r'\\').replace("'", r"\'")

    dsn = {'dbname': path, 'user': user, 'password': password, 'host': host,
           'port': port}
    return ' '.join("%s=%s" % (name, quote(value))
                    for name, value in dsn.iteritems() if value)


def _quote(identifier):
    return '"%s"' % identifier.replace('"', '""')


def _version_tuple(ver):

    if ver:
        # Extract 9.1.23 from 90123.
        def get_digit(version, n):
            return version / 10 ** (2 * n) % 100
        return get_digit(ver, 2), get_digit(ver, 1), get_digit(ver, 0)


def _version_string(ver):
    if ver and not isinstance(ver, tuple):
        ver = _version_tuple(ver)
    if ver:
        return '.'.join(map(str, ver))
    else:
        return '(unknown)'



class PostgreSQLConnector(Component):
    """Database connector for PostgreSQL.

    Database URLs should be of the form:
    {{{
    postgres://user[:password]@host[:port]/database[?schema=my_schema]
    }}}
    """
    implements(IDatabaseConnector)

    required = False

    pg_dump_path = Option('trac', 'pg_dump_path', 'pg_dump',
        """Location of pg_dump for Postgres database backups""")

    def __init__(self):
        if has_psycopg:
            self._postgresql_version = \
                'server: (not-connected), client: %s' % \
                _version_string(self._client_version)
        else:
            self._postgresql_version = None
        self.error = None

    # IDatabaseConnector methods

    def get_supported_schemes(self):
        if not has_psycopg:
            self.error = _("Cannot load Python bindings for PostgreSQL")
        yield 'postgres', -1 if self.error else 1

    def get_connection(self, path, log=None, user=None, password=None,
                       host=None, port=None, params={}):
        cnx = PostgreSQLConnection(path, log, user, password, host, port,
                                   params)
        if not self.required:
            if cnx.server_version < min_postgresql_version:
                error = _(
                    "PostgreSQL version is %(version)s. Minimum required "
                    "version is %(min_version)s.",
                    version='%d.%d.%d' % cnx.server_version,
                    min_version='%d.%d.%d' % min_postgresql_version)
                raise TracError(error)
            self._postgresql_version = \
                'server: %s, client: %s' \
                % (_version_string(cnx.server_version),
                   _version_string(self._client_version))
            self.required = True
        return cnx

    def get_exceptions(self):
        return psycopg

    def init_db(self, path, schema=None, log=None, user=None, password=None,
                host=None, port=None, params={}):
        cnx = self.get_connection(path, log, user, password, host, port,
                                  params)
        cursor = cnx.cursor()
        if cnx.schema:
            cursor.execute('CREATE SCHEMA ' + _quote(cnx.schema))
            cursor.execute('SET search_path TO %s', (cnx.schema,))
        if schema is None:
            from trac.db_default import schema
        for table in schema:
            for stmt in self.to_sql(table):
                cursor.execute(stmt)
        cnx.commit()

    def destroy_db(self, path, log=None, user=None, password=None, host=None,
                   port=None, params={}):
        cnx = self.get_connection(path, log, user, password, host, port,
                                  params)
        cnx.execute('DROP SCHEMA %s CASCADE' % _quote(cnx.schema))
        cnx.commit()

    def db_exists(self, path, log=None, user=None, password=None, host=None,
                  port=None, params={}):
        cnx = self.get_connection(path, log, user, password, host, port,
                                  params)
        cursor = cnx.cursor()
        cursor.execute("""
            SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname=%s);
            """, (cnx.schema,))
        return cursor.fetchone()[0]

    def to_sql(self, table):
        sql = ['CREATE TABLE %s (' % _quote(table.name)]
        coldefs = []
        for column in table.columns:
            ctype = column.type
            ctype = _type_map.get(ctype, ctype)
            if column.auto_increment:
                ctype = 'SERIAL'
            if len(table.key) == 1 and column.name in table.key:
                ctype += ' PRIMARY KEY'
            coldefs.append('    %s %s' % (_quote(column.name), ctype))
        if len(table.key) > 1:
            coldefs.append('    CONSTRAINT %s PRIMARY KEY (%s)' %
                           (_quote(table.name + '_pk'),
                            ','.join(_quote(col) for col in table.key)))
        sql.append(',\n'.join(coldefs) + '\n)')
        yield '\n'.join(sql)
        for index in table.indices:
            unique = 'UNIQUE' if index.unique else ''
            yield 'CREATE %s INDEX %s ON %s (%s)' % \
                  (unique,
                   _quote('%s_%s_idx' % (table.name, '_'.join(index.columns))),
                   _quote(table.name),
                   ','.join(_quote(col) for col in index.columns))

    def alter_column_types(self, table, columns):
        """Yield SQL statements altering the type of one or more columns of
        a table.

        Type changes are specified as a `columns` dict mapping column names
        to `(from, to)` SQL type tuples.
        """
        alterations = []
        for name, (from_, to) in sorted(columns.iteritems()):
            to = _type_map.get(to, to)
            if to != _type_map.get(from_, from_):
                alterations.append((name, to))
        if alterations:
            yield 'ALTER TABLE %s %s' % \
                  (_quote(table),
                   ', '.join('ALTER COLUMN %s TYPE %s' % (_quote(name), type_)
                             for name, type_ in alterations))

    def backup(self, dest_file):
        from subprocess import Popen, PIPE
        db_url = self.env.config.get('trac', 'database')
        scheme, db_prop = parse_connection_uri(db_url)
        db_params = db_prop.setdefault('params', {})
        db_name = os.path.basename(db_prop['path'])

        args = [self.pg_dump_path, '-C', '--inserts', '-x', '-Z', '8']
        if 'user' in db_prop:
            args.extend(['-U', db_prop['user']])
        host = db_params.get('host', db_prop.get('host'))
        if host:
            args.extend(['-h', host])
            if '/' not in host:
                args.extend(['-p', str(db_prop.get('port', '5432'))])

        if 'schema' in db_params:
            # Need quote for -n (--schema) option
            args.extend(['-n', '"%s"' % db_params['schema']])

        dest_file += ".gz"
        args.extend(['-f', dest_file, db_name])

        environ = os.environ.copy()
        if 'password' in db_prop:
            environ['PGPASSWORD'] = str(db_prop['password'])
        try:
            p = Popen(args, env=environ, stderr=PIPE, close_fds=close_fds)
        except OSError as e:
            raise TracError(_("Unable to run %(path)s: %(msg)s",
                              path=self.pg_dump_path,
                              msg=exception_to_unicode(e)))
        errmsg = p.communicate()[1]
        if p.returncode != 0:
            raise TracError(_("pg_dump failed: %(msg)s",
                              msg=to_unicode(errmsg.strip())))
        if not os.path.exists(dest_file):
            raise TracError(_("No destination file created"))
        return dest_file

    def get_system_info(self):
        if has_psycopg:
            yield 'PostgreSQL', self._postgresql_version
            yield 'psycopg2', psycopg2_version

    @lazy
    def _client_version(self):
        version = None
        if hasattr(psycopg, 'libpq_version'):
            version = psycopg.libpq_version()
        elif _libpq_pathname:
            try:
                lib = ctypes.CDLL(_libpq_pathname)
                version = lib.PQlibVersion()
            except Exception as e:
                self.log.warning("Exception caught while retrieving libpq's "
                                 "version%s",
                                 exception_to_unicode(e, traceback=True))
        return _version_tuple(version)

    def _pgdump_version(self):
        from subprocess import Popen, PIPE
        try:
            p = Popen([self.pg_dump_path, '--version'], stdout=PIPE,
                      close_fds=close_fds)
        except OSError as e:
            raise TracError(_("Unable to run %(path)s: %(msg)s",
                              path=self.pg_dump_path,
                              msg=exception_to_unicode(e)))
        return p.communicate()[0]


class PostgreSQLConnection(ConnectionBase, ConnectionWrapper):
    """Connection wrapper for PostgreSQL."""

    poolable = True

    def __init__(self, path, log=None, user=None, password=None, host=None,
                 port=None, params={}):
        if path.startswith('/'):
            path = path[1:]
        if 'host' in params:
            host = params['host']

        cnx = psycopg.connect(assemble_pg_dsn(path, user, password, host,
                                              port))

        cnx.set_client_encoding('UNICODE')
        self.schema = None
        if 'schema' in params:
            self.schema = params['schema']
            try:
                cnx.cursor().execute('SET search_path TO %s', (self.schema,))
                cnx.commit()
            except (DataError, ProgrammingError):
                cnx.rollback()
        ConnectionWrapper.__init__(self, cnx, log)

    def cursor(self):
        return IterableCursor(self.cnx.cursor(), self.log)

    def cast(self, column, type):
        # Temporary hack needed for the union of selects in the search module
        return 'CAST(%s AS %s)' % (column, _type_map.get(type, type))

    def concat(self, *args):
        return '||'.join(args)

    def drop_column(self, table, column):
        self.execute("""
            ALTER TABLE %s DROP COLUMN IF EXISTS %s
            """ % (self.quote(table), self.quote(column)))

    def drop_table(self, table):
        self.execute("DROP TABLE IF EXISTS " + self.quote(table))

    def get_column_names(self, table):
        rows = self.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema=%s AND table_name=%s
            ORDER BY ordinal_position
            """, (self.schema, table))
        return [row[0] for row in rows]

    def get_last_id(self, cursor, table, column='id'):
        cursor.execute("SELECT CURRVAL(%s)",
                       (self.quote(self._sequence_name(table, column)),))
        return cursor.fetchone()[0]

    def get_table_names(self):
        rows = self.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema=%s""", (self.schema,))
        return [row[0] for row in rows]

    def like(self):
        return "ILIKE %s ESCAPE '/'"

    def like_escape(self, text):
        return _like_escape_re.sub(r'/\1', text)

    def ping(self):
        cursor = self.cnx.cursor()
        cursor.execute('SELECT 1')

    def prefix_match(self):
        return "LIKE %s ESCAPE '/'"

    def prefix_match_value(self, prefix):
        return self.like_escape(prefix) + '%'

    def quote(self, identifier):
        return _quote(identifier)

    def reset_tables(self):
        if not self.schema:
            return []
        # reset sequences
        cursor = self.cursor()
        cursor.execute("""
            SELECT sequence_name FROM information_schema.sequences
            WHERE sequence_schema=%s
            """, (self.schema,))
        for seq, in cursor.fetchall():
            cursor.execute("ALTER SEQUENCE %s RESTART WITH 1" % seq)
        # clear tables
        table_names = self.get_table_names()
        for name in table_names:
            cursor.execute("DELETE FROM " + self.quote(name))
        # PostgreSQL supports TRUNCATE TABLE as well
        # (see https://www.postgresql.org/docs/9.1/static/sql-truncate.html)
        # but on the small tables used here, DELETE is actually much faster
        return table_names

    def update_sequence(self, cursor, table, column='id'):
        cursor.execute("SELECT SETVAL(%%s, (SELECT MAX(%s) FROM %s))"
                       % (self.quote(column), self.quote(table)),
                       (self.quote(self._sequence_name(table, column)),))

    def _sequence_name(self, table, column):
        return '%s_%s_seq' % (table, column)

    @lazy
    def server_version(self):
        return _version_tuple(self.cnx.server_version)
