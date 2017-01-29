# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2009 Edgewall Software
# Copyright (C) 2005-2006 Christopher Lenz <cmlenz@gmx.de>
# Copyright (C) 2005 Jeff Weiss <trac@jeffweiss.org>
# Copyright (C) 2006 Andres Salomon <dilinger@athenacr.com>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import os
import re
import sys
import types

from genshi.core import Markup

from trac.core import *
from trac.config import Option
from trac.db.api import DatabaseManager, IDatabaseConnector, _parse_db_str, \
                        get_column_names
from trac.db.util import ConnectionWrapper, IterableCursor
from trac.env import IEnvironmentSetupParticipant
from trac.util import as_int, get_pkginfo
from trac.util.compat import close_fds
from trac.util.text import exception_to_unicode, to_unicode
from trac.util.translation import _

_like_escape_re = re.compile(r'([/_%])')

try:
    import MySQLdb
    import MySQLdb.cursors
except ImportError:
    has_mysqldb = False
else:
    has_mysqldb = True

    class MySQLUnicodeCursor(MySQLdb.cursors.Cursor):
        def _convert_row(self, row):
            return tuple(v.decode('utf-8') if isinstance(v, str) else v
                         for v in row)
        def fetchone(self):
            row = super(MySQLUnicodeCursor, self).fetchone()
            return self._convert_row(row) if row else None
        def fetchmany(self, num):
            rows = super(MySQLUnicodeCursor, self).fetchmany(num)
            return [self._convert_row(row) for row in rows] \
                   if rows is not None else []
        def fetchall(self):
            rows = super(MySQLUnicodeCursor, self).fetchall()
            return [self._convert_row(row) for row in rows] \
                   if rows is not None else []

# Mapping from "abstract" SQL types to DB-specific types
_type_map = {
    'int64': 'bigint',
}


class MySQLConnector(Component):
    """Database connector for MySQL version 4.1 and greater.

    Database URLs should be of the form::

      {{{
      mysql://user[:password]@host[:port]/database[?param1=value&param2=value]
      }}}

    The following parameters are supported:
     * `compress`: Enable compression (0 or 1)
     * `init_command`: Command to run once the connection is created
     * `named_pipe`: Use a named pipe to connect on Windows (0 or 1)
     * `read_default_file`: Read default client values from the given file
     * `read_default_group`: Configuration group to use from the default file
     * `unix_socket`: Use a Unix socket at the given path to connect
    """
    implements(IDatabaseConnector, IEnvironmentSetupParticipant)

    mysqldump_path = Option('trac', 'mysqldump_path', 'mysqldump',
        """Location of mysqldump for MySQL database backups""")

    def __init__(self):
        self._version = None
        self.error = None

    def get_supported_schemes(self):
        if not has_mysqldb:
            self.error = _("Cannot load Python bindings for MySQL")
        yield ('mysql', -1 if self.error else 1)

    def get_connection(self, path, log=None, user=None, password=None,
                       host=None, port=None, params={}):
        cnx = MySQLConnection(path, log, user, password, host, port, params)
        if not self._version:
            self._version = get_pkginfo(MySQLdb).get('version',
                                                     MySQLdb.__version__)
            mysql_info = 'server: "%s", client: "%s", thread-safe: %s' % \
                         (cnx.cnx.get_server_info(),
                          MySQLdb.get_client_info(),
                          MySQLdb.thread_safe())
            self.env.systeminfo.extend([('MySQL', mysql_info),
                                        ('MySQLdb', self._version)])
            self.required = True
        return cnx

    def get_exceptions(self):
        return MySQLdb

    def init_db(self, path, schema=None, log=None, user=None, password=None,
                host=None, port=None, params={}):
        cnx = self.get_connection(path, log, user, password, host, port,
                                  params)
        self._verify_variables(cnx)
        utf8_size = self._utf8_size(cnx)
        cursor = cnx.cursor()
        if schema is None:
            from trac.db_default import schema
        for table in schema:
            for stmt in self.to_sql(table, utf8_size=utf8_size):
                self.log.debug(stmt)
                cursor.execute(stmt)
        self._verify_table_status(cnx)
        cnx.commit()

    def _utf8_size(self, cnx):
        if cnx is None:
            connector, args = DatabaseManager(self.env).get_connector()
            cnx = connector.get_connection(**args)
            charset = cnx.charset
            cnx.close()
        else:
            charset = cnx.charset
        return 4 if charset == 'utf8mb4' else 3

    def _collist(self, table, columns, utf8_size):
        """Take a list of columns and impose limits on each so that indexing
        works properly.

        Some Versions of MySQL limit each index prefix to 1000 bytes total,
        with a max of 767 bytes per column.
        """
        cols = []
        limit_col = 767 / utf8_size
        limit = min(1000 / (utf8_size * len(columns)), limit_col)
        for c in columns:
            name = '`%s`' % c
            table_col = filter((lambda x: x.name == c), table.columns)
            if len(table_col) == 1 and table_col[0].type.lower() == 'text':
                if table_col[0].key_size is not None:
                    name += '(%d)' % min(table_col[0].key_size, limit_col)
                elif name == '`rev`':
                    name += '(20)'
                elif name == '`path`':
                    name += '(%d)' % limit_col
                elif name == '`change_type`':
                    name += '(2)'
                else:
                    name += '(%s)' % limit
            # For non-text columns, we simply throw away the extra bytes.
            # That could certainly be optimized better, but for now let's KISS.
            cols.append(name)
        return ','.join(cols)

    def to_sql(self, table, utf8_size=None):
        if utf8_size is None:
            utf8_size = self._utf8_size(None)
        sql = ['CREATE TABLE %s (' % table.name]
        coldefs = []
        for column in table.columns:
            ctype = column.type
            ctype = _type_map.get(ctype, ctype)
            if column.auto_increment:
                ctype = 'INT UNSIGNED NOT NULL AUTO_INCREMENT'
                # Override the column type, as a text field cannot
                # use auto_increment.
                column.type = 'int'
            coldefs.append('    `%s` %s' % (column.name, ctype))
        if len(table.key) > 0:
            coldefs.append('    PRIMARY KEY (%s)' %
                           self._collist(table, table.key,
                                         utf8_size=utf8_size))
        sql.append(',\n'.join(coldefs) + '\n)')
        yield '\n'.join(sql)

        for index in table.indices:
            unique = 'UNIQUE' if index.unique else ''
            yield 'CREATE %s INDEX %s_%s_idx ON %s (%s);' % (unique, table.name,
                  '_'.join(index.columns), table.name,
                  self._collist(table, index.columns, utf8_size=utf8_size))

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
                ', '.join("MODIFY %s %s" % each
                          for each in alterations))

    def backup(self, dest_file):
        from subprocess import Popen, PIPE
        db_url = self.env.config.get('trac', 'database')
        scheme, db_prop = _parse_db_str(db_url)
        db_params = db_prop.setdefault('params', {})
        db_name = os.path.basename(db_prop['path'])

        args = [self.mysqldump_path]
        if 'host' in db_prop:
            args.extend(['-h', db_prop['host']])
        if 'port' in db_prop:
            args.extend(['-P', str(db_prop['port'])])
        if 'user' in db_prop:
            args.extend(['-u', db_prop['user']])
        for name, value in db_params.iteritems():
            if name == 'compress' and as_int(value, 0):
                args.append('--compress')
            elif name == 'named_pipe' and as_int(value, 0):
                args.append('--protocol=pipe')
            elif name == 'read_default_file': # Must be first
                args.insert(1, '--defaults-file=' + value)
            elif name == 'unix_socket':
                args.extend(['--protocol=socket', '--socket=' + value])
            elif name not in ('init_command', 'read_default_group'):
                self.log.warning("Invalid connection string parameter '%s'",
                                 name)
        args.extend(['-r', dest_file, db_name])

        environ = os.environ.copy()
        if 'password' in db_prop:
            environ['MYSQL_PWD'] = str(db_prop['password'])
        try:
            p = Popen(args, env=environ, stderr=PIPE, close_fds=close_fds)
        except OSError, e:
            raise TracError(_("Unable to run %(path)s: %(msg)s",
                              path=self.mysqldump_path,
                              msg=exception_to_unicode(e)))
        errmsg = p.communicate()[1]
        if p.returncode != 0:
            raise TracError(_("mysqldump failed: %(msg)s",
                              msg=to_unicode(errmsg.strip())))
        if not os.path.exists(dest_file):
            raise TracError(_("No destination file created"))
        return dest_file

    # IEnvironmentSetupParticipant methods

    def environment_created(self):
        pass

    def environment_needs_upgrade(self, db):
        if getattr(self, 'required', False):
            self._verify_table_status(db)
            self._verify_variables(db)
        return False

    def upgrade_environment(self, db):
        pass

    UNSUPPORTED_ENGINES = ('MyISAM', 'EXAMPLE', 'ARCHIVE', 'CSV', 'ISAM')

    def _verify_table_status(self, db):
        from trac.db_default import schema
        tables = [t.name for t in schema]
        cursor = db.cursor()
        cursor.execute("SHOW TABLE STATUS WHERE name IN (%s)" %
                       ','.join(('%s',) * len(tables)),
                       tables)
        cols = get_column_names(cursor)
        rows = [dict(zip(cols, row)) for row in cursor]

        engines = [row['Name'] for row in rows
                               if row['Engine'] in self.UNSUPPORTED_ENGINES]
        if engines:
            raise TracError(_(
                "All tables must be created as InnoDB or NDB storage engine "
                "to support transactions. The following tables have been "
                "created as storage engine which doesn't support "
                "transactions: %(tables)s", tables=', '.join(engines)))

        non_utf8bin = [row['Name'] for row in rows
                       if row['Collation'] not in ('utf8_bin', 'utf8mb4_bin',
                                                   None)]
        if non_utf8bin:
            raise TracError(_("All tables must be created with utf8_bin or "
                              "utf8mb4_bin as collation. The following tables "
                              "don't have the collations: %(tables)s",
                              tables=', '.join(non_utf8bin)))

    SUPPORTED_COLLATIONS = (('utf8', 'utf8_bin'), ('utf8mb4', 'utf8mb4_bin'))

    def _verify_variables(self, db):
        cursor = db.cursor()
        cursor.execute("SHOW VARIABLES WHERE variable_name IN ("
                       "'default_storage_engine','storage_engine',"
                       "'default_tmp_storage_engine',"
                       "'character_set_database','collation_database')")
        vars = dict((row[0].lower(), row[1]) for row in cursor)

        engine = vars.get('default_storage_engine') or \
                 vars.get('storage_engine')
        if engine in self.UNSUPPORTED_ENGINES:
            raise TracError(_("The current storage engine is %(engine)s. "
                              "It must be InnoDB or NDB storage engine to "
                              "support transactions.", engine=engine))

        tmp_engine = vars.get('default_tmp_storage_engine')
        if tmp_engine in self.UNSUPPORTED_ENGINES:
            raise TracError(_("The current storage engine for TEMPORARY "
                              "tables is %(engine)s. It must be InnoDB or NDB "
                              "storage engine to support transactions.",
                              engine=tmp_engine))

        charset = vars['character_set_database']
        collation = vars['collation_database']
        if (charset, collation) not in self.SUPPORTED_COLLATIONS:
            raise TracError(_(
                "The charset and collation of database are '%(charset)s' and "
                "'%(collation)s'. The database must be created with one of "
                "%(supported)s.", charset=charset, collation=collation,
                supported=repr(self.SUPPORTED_COLLATIONS)))


class MySQLConnection(ConnectionWrapper):
    """Connection wrapper for MySQL."""

    poolable = True

    def __init__(self, path, log, user=None, password=None, host=None,
                 port=None, params={}):
        if path.startswith('/'):
            path = path[1:]
        if password == None:
            password = ''
        if port == None:
            port = 3306
        opts = {}
        for name, value in params.iteritems():
            key = name.encode('utf-8')
            if name == 'read_default_group':
                opts[key] = value
            elif name == 'init_command':
                opts[key] = value.encode('utf-8')
            elif name in ('read_default_file', 'unix_socket'):
                opts[key] = value.encode(sys.getfilesystemencoding())
            elif name in ('compress', 'named_pipe'):
                opts[key] = as_int(value, 0)
            else:
                self.log.warning("Invalid connection string parameter '%s'",
                                 name)
        cnx = MySQLdb.connect(db=path, user=user, passwd=password, host=host,
                              port=port, charset='utf8', **opts)
        self.schema = path
        if hasattr(cnx, 'encoders'):
            # 'encoders' undocumented but present since 1.2.1 (r422)
            cnx.encoders[Markup] = cnx.encoders[types.UnicodeType]
        cursor = cnx.cursor()
        cursor.execute("SHOW VARIABLES WHERE "
                       " variable_name='character_set_database'")
        self.charset = cursor.fetchone()[1]
        if self.charset != 'utf8':
            cnx.query("SET NAMES %s" % self.charset)
            cnx.store_result()
        ConnectionWrapper.__init__(self, cnx, log)
        self._is_closed = False

    def cursor(self):
        return IterableCursor(MySQLUnicodeCursor(self.cnx), self.log)

    def rollback(self):
        self.cnx.ping()
        try:
            self.cnx.rollback()
        except MySQLdb.ProgrammingError:
            self._is_closed = True

    def close(self):
        if not self._is_closed:
            try:
                self.cnx.close()
            except MySQLdb.ProgrammingError:
                pass # this error would mean it's already closed.  So, ignore
            self._is_closed = True

    def cast(self, column, type):
        if type == 'int' or type == 'int64':
            type = 'signed'
        elif type == 'text':
            type = 'char'
        return 'CAST(%s AS %s)' % (column, type)

    def concat(self, *args):
        return 'concat(%s)' % ', '.join(args)

    def drop_table(self, table):
        cursor = MySQLdb.cursors.Cursor(self.cnx)
        cursor._defer_warnings = True  # ignore "Warning: Unknown table ..."
        cursor.execute("DROP TABLE IF EXISTS " + self.quote(table))

    def get_column_names(self, table):
        rows = self.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema=%s AND table_name=%s
            """, (self.schema, table))
        return [row[0] for row in rows]

    def get_last_id(self, cursor, table, column='id'):
        return cursor.lastrowid

    def get_table_names(self):
        rows = self.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema=%s""", (self.schema,))
        return [row[0] for row in rows]

    def like(self):
        """Return a case-insensitive LIKE clause."""
        return "LIKE %%s COLLATE %s_general_ci ESCAPE '/'" % self.charset

    def like_escape(self, text):
        return _like_escape_re.sub(r'/\1', text)

    def prefix_match(self):
        """Return a case sensitive prefix-matching operator."""
        return "LIKE %s ESCAPE '/'"

    def prefix_match_value(self, prefix):
        """Return a value for case sensitive prefix-matching operator."""
        return self.like_escape(prefix) + '%'

    def quote(self, identifier):
        """Return the quoted identifier."""
        return "`%s`" % identifier.replace('`', '``')

    def update_sequence(self, cursor, table, column='id'):
        # MySQL handles sequence updates automagically
        pass
