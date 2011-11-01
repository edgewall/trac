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

import re, os

from genshi import Markup

from trac.core import *
from trac.config import Option
from trac.db.api import IDatabaseConnector, _parse_db_str
from trac.db.util import ConnectionWrapper, IterableCursor
from trac.util import get_pkginfo
from trac.util.compat import close_fds
from trac.util.text import empty, exception_to_unicode, to_unicode
from trac.util.translation import _

has_psycopg = False
try:
    import psycopg2 as psycopg
    import psycopg2.extensions
    from psycopg2 import DataError, ProgrammingError
    from psycopg2.extensions import register_type, UNICODE, \
                                    register_adapter, AsIs, QuotedString

    register_type(UNICODE)
    register_adapter(Markup, lambda markup: QuotedString(unicode(markup)))
    register_adapter(type(empty), lambda empty: AsIs("''"))

    has_psycopg = True
except ImportError:
    pass

_like_escape_re = re.compile(r'([/_%])')

# Mapping from "abstract" SQL types to DB-specific types
_type_map = {
    'int64': 'bigint',
}


def assemble_pg_dsn(path, user=None, password=None, host=None, port=None):
    """Quote the parameters and assemble the DSN."""

    dsn = {'dbname': path, 'user': user, 'password': password, 'host': host,
           'port': port}
    return ' '.join(["%s='%s'" % (k,v) for k,v in dsn.iteritems() if v])


class PostgreSQLConnector(Component):
    """Database connector for PostgreSQL.
    
    Database URLs should be of the form:
    {{{
    postgres://user[:password]@host[:port]/database[?schema=my_schema]
    }}}
    """
    implements(IDatabaseConnector)

    pg_dump_path = Option('trac', 'pg_dump_path', 'pg_dump',
        """Location of pg_dump for Postgres database backups""")

    def __init__(self):
        self._version = None
        self.error = None

    def get_supported_schemes(self):
        if not has_psycopg:
            self.error = _("Cannot load Python bindings for PostgreSQL")
        yield ('postgres', self.error and -1 or 1)

    def get_connection(self, path, log=None, user=None, password=None,
                       host=None, port=None, params={}):
        cnx = PostgreSQLConnection(path, log, user, password, host, port,
                                   params)
        if not self._version:
            self._version = get_pkginfo(psycopg).get('version',
                                                     psycopg.__version__)
            self.env.systeminfo.append(('psycopg2', self._version))
            self.required = True
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
            ctype = _type_map.get(ctype, ctype)
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
            yield "ALTER TABLE %s %s" % (table,
                ', '.join("ALTER COLUMN %s TYPE %s" % each
                          for each in alterations))

    def backup(self, dest_file):
        from subprocess import Popen, PIPE
        db_url = self.env.config.get('trac', 'database')
        scheme, db_prop = _parse_db_str(db_url)
        db_params = db_prop.setdefault('params', {})
        db_name = os.path.basename(db_prop['path'])

        args = [self.pg_dump_path, '-C', '--inserts', '-x', '-Z', '8']
        if 'user' in db_prop:
            args.extend(['-U', db_prop['user']])
        if 'host' in db_params:
            host = db_params['host']
        else:
            host = db_prop.get('host')
        if host:
            args.extend(['-h', host])
            if '/' not in host:
                args.extend(['-p', str(db_prop.get('port', '5432'))])

        if 'schema' in db_params:
            try:
                p = Popen([self.pg_dump_path, '--version'], stdout=PIPE,
                          close_fds=close_fds)
            except OSError, e:
                raise TracError(_("Unable to run %(path)s: %(msg)s",
                                  path=self.pg_dump_path,
                                  msg=exception_to_unicode(e)))
            # Need quote for -n (--schema) option in PostgreSQL 8.2+
            version = p.communicate()[0]
            if re.search(r' 8\.[01]\.', version):
                args.extend(['-n', db_params['schema']])
            else:
                args.extend(['-n', '"%s"' % db_params['schema']])

        dest_file += ".gz"
        args.extend(['-f', dest_file, db_name])

        environ = os.environ.copy()
        if 'password' in db_prop:
            environ['PGPASSWORD'] = str(db_prop['password'])
        try:
            p = Popen(args, env=environ, stderr=PIPE, close_fds=close_fds)
        except OSError, e:
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


class PostgreSQLConnection(ConnectionWrapper):
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
        try:
            self.schema = None
            if 'schema' in params:
                self.schema = params['schema']
                cnx.cursor().execute('SET search_path TO %s', (self.schema,))
                cnx.commit()
        except (DataError, ProgrammingError):
            cnx.rollback()
        ConnectionWrapper.__init__(self, cnx, log)

    def cast(self, column, type):
        # Temporary hack needed for the union of selects in the search module
        return 'CAST(%s AS %s)' % (column, _type_map.get(type, type))

    def concat(self, *args):
        return '||'.join(args)

    def like(self):
        """Return a case-insensitive LIKE clause."""
        return "ILIKE %s ESCAPE '/'"

    def like_escape(self, text):
        return _like_escape_re.sub(r'/\1', text)

    def quote(self, identifier):
        """Return the quoted identifier."""
        return '"%s"' % identifier.replace('"', '""')

    def get_last_id(self, cursor, table, column='id'):
        cursor.execute("""SELECT CURRVAL('"%s_%s_seq"')""" % (table, column))
        return cursor.fetchone()[0]

    def update_sequence(self, cursor, table, column='id'):
        cursor.execute("""
            SELECT setval('"%s_%s_seq"', (SELECT MAX(id) FROM %s))
            """ % (table, column, table))

    def cursor(self):
        return IterableCursor(self.cnx.cursor(), self.log)

