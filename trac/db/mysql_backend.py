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

import re, sys, os, time
from subprocess import Popen, PIPE

from trac.core import *
from trac.config import Option
from trac.db.api import IDatabaseConnector, _parse_db_str
from trac.db.util import ConnectionWrapper
from trac.util import get_pkginfo
from trac.util.compat import close_fds
from trac.util.text import to_unicode

_like_escape_re = re.compile(r'([/_%])')

try:
    import MySQLdb
    import MySQLdb.cursors
    has_mysqldb = True
    
    class MySQLUnicodeCursor(MySQLdb.cursors.Cursor):
        def _convert_row(self, row):
            return tuple([(isinstance(v, str) and [v.decode('utf-8')] or [v])[0]
                          for v in row])
        def fetchone(self):
            row = super(MySQLUnicodeCursor, self).fetchone()
            return row and self._convert_row(row) or None
        def fetchmany(self, num):
            rows = super(MySQLUnicodeCursor, self).fetchmany(num)
            return rows != None and [self._convert_row(row)
                                     for row in rows] or []
        def fetchall(self):
            rows = super(MySQLUnicodeCursor, self).fetchall()
            return rows != None and [self._convert_row(row)
                                     for row in rows] or []
except ImportError:
    has_mysqldb = False


class MySQLConnector(Component):
    """MySQL database support for version 4.1 and greater.
    
    Database urls should be of the form:
        mysql://user[:password]@host[:port]/database
    """

    implements(IDatabaseConnector)

    mysqldump_path = Option('trac', 'mysqldump_path', 'mysqldump',
        """Location of mysqldump for MySQL database backups""")

    def __init__(self):
        self._version = None

    def get_supported_schemes(self):
        global has_mysqldb
        if has_mysqldb:
            return [('mysql', 1)]
        else:
            return []

    def get_connection(self, path, user=None, password=None, host=None,
                       port=None, params={}, log=None):
        cnx = MySQLConnection(path, user, password, host, port, params, log)
        if not self._version:
            self._version = get_pkginfo(MySQLdb).get('version',
                                                     MySQLdb.__version__)
            mysql_info = 'server: "%s", client: "%s", thread-safe: %s' % \
                         (cnx.cnx.get_server_info(),
                          MySQLdb.get_client_info(),
                          MySQLdb.thread_safe())
            self.env.systeminfo.extend([('MySQL', mysql_info),
                                        ('MySQLdb', self._version)])
        return cnx
    
    def init_db(self, path, user=None, password=None, host=None, port=None,
                params={}, log=None):
        cnx = self.get_connection(path, user, password, host, port, params,
                                  log)
        cursor = cnx.cursor()
        from trac.db_default import schema
        for table in schema:
            for stmt in self.to_sql(table):
                self.env.log.debug(stmt)
                cursor.execute(stmt)
        cnx.commit()

    def _collist(self, table, columns):
        """Take a list of columns and impose limits on each so that indexing
        works properly.
        
        Some Versions of MySQL limit each index prefix to 500 bytes total, with
        a max of 255 bytes per column.
        """
        cols = []
        limit = 333 / len(columns)
        if limit > 255:
            limit = 255
        for c in columns:
            name = '`%s`' % c
            table_col = filter((lambda x: x.name == c), table.columns)
            if len(table_col) == 1 and table_col[0].type.lower() == 'text':
                if name == '`rev`':
                    name += '(20)'
                elif name == '`path`':
                    name += '(255)'
                elif name == '`change_type`':
                    name += '(2)'
                else:
                    name += '(%s)' % limit
            # For non-text columns, we simply throw away the extra bytes.
            # That could certainly be optimized better, but for now let's KISS.
            cols.append(name)
        return ','.join(cols)

    def to_sql(self, table):
        sql = ['CREATE TABLE %s (' % table.name]
        coldefs = []
        for column in table.columns:
            ctype = column.type
            if column.auto_increment:
                ctype = 'INT UNSIGNED NOT NULL AUTO_INCREMENT'
                # Override the column type, as a text field cannot
                # use auto_increment.
                column.type = 'int'
            coldefs.append('    `%s` %s' % (column.name, ctype))
        if len(table.key) > 0:
            coldefs.append('    PRIMARY KEY (%s)' %
                           self._collist(table, table.key))
        sql.append(',\n'.join(coldefs) + '\n)')
        yield '\n'.join(sql)

        for index in table.indices:
            unique = index.unique and 'UNIQUE' or ''
            yield 'CREATE %s INDEX %s_%s_idx ON %s (%s);' % (unique, table.name,
                  '_'.join(index.columns), table.name,
                  self._collist(table, index.columns))

    def backup(self, dest_file):
        db_url = self.env.config.get('trac', 'database')
        scheme, db_prop = _parse_db_str(db_url)
        db_name = os.path.basename(db_prop['path'])

        args = [self.mysqldump_path, '-u', db_prop['user'],
                '-h', db_prop['host']]
        if 'port' in db_prop:
            args.extend(['-P', str(db_prop['port'])])
        args.extend(['-r', dest_file, db_name])
        
        environ = os.environ.copy()
        environ['MYSQL_PWD'] = str(db_prop['password'])
        p = Popen(args, env=environ, stderr=PIPE, close_fds=close_fds)
        errmsg = p.communicate()[1]
        if p.returncode != 0:
            raise TracError("Backup attempt failed (%s)" % to_unicode(errmsg))
        if not os.path.exists(dest_file):
            raise TracError("Backup attempt failed")
        return dest_file


class MySQLConnection(ConnectionWrapper):
    """Connection wrapper for MySQL."""

    poolable = True

    def __init__(self, path, user=None, password=None, host=None,
                 port=None, params={}, log=None):
        if path.startswith('/'):
            path = path[1:]
        if password == None:
            password = ''
        if port == None:
            port = 3306
        cnx = MySQLdb.connect(db=path, user=user, passwd=password,
                              host=host, port=port, charset='utf8')
        ConnectionWrapper.__init__(self, cnx, log)
        self._is_closed = False

    def cast(self, column, type):
        if type == 'int':
            type = 'signed'
        elif type == 'text':
            type = 'char'
        return 'CAST(%s AS %s)' % (column, type)

    def concat(self, *args):
        return 'concat(%s)' % ', '.join(args)

    def like(self):
        return "LIKE %s ESCAPE '/'"

    def like_escape(self, text):
        return _like_escape_re.sub(r'/\1', text)

    def get_last_id(self, cursor, table, column='id'):
        return self.cnx.insert_id()

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

    def cursor(self):
        return MySQLUnicodeCursor(self.cnx)
