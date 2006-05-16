# -*- coding: iso8859-1 -*-
#
# Copyright (C) 2005-2006 Edgewall Software
# Copyright (C) 2005-2006 Christopher Lenz <cmlenz@gmx.de>
# Copyright (C) 2005 Jeff Weiss <trac@jeffweiss.org>
# Copyright (C) 2006 Andres Salomon <dilinger@athenacr.com>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://projects.edgewall.com/trac/.

from trac.core import *
from trac.db.api import IDatabaseConnector
from trac.db.util import ConnectionWrapper


class MySQLConnector(Component):
    """MySQL database support for version 4.1 and greater.
    
    Database urls should be of the form:
        mysql://user[:password]@host[:port]/database
    """

    implements(IDatabaseConnector)

    def get_supported_schemes(self):
        return [('mysql', 1)]

    def get_connection(self, path, user=None, password=None, host=None,
                       port=None, params={}):
        return MySQLConnection(path, user, password, host, port, params)

    def init_db(self, path, user=None, password=None, host=None, port=None,
                params={}):
        cnx = self.get_connection(path, user, password, host, port, params)
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
        limit = 500 / len(columns)
        if limit > 255:
            limit = 255
        for c in columns:
            name = '`%s`' % c
            table_col = filter((lambda x: x.name == c), table.columns)
            if len(table_col) == 1 and table_col[0].type.lower() == 'text':
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
            yield 'CREATE INDEX %s_%s_idx ON %s (%s);' % (table.name,
                  '_'.join(index.columns), table.name,
                  self._collist(table, index.columns))


class MySQLConnection(ConnectionWrapper):
    """Connection wrapper for MySQL."""

    poolable = True

    def __init__(self, path, user=None, password=None, host=None,
                 port=None, params={}):
        import MySQLdb

        if path.startswith('/'):
            path = path[1:]
        if password == None:
            password = ''
        if port == None:
            port = 3306

        cnx = MySQLdb.connect(db=path, user=user, passwd=password, host=host,
                              port=port, use_unicode=True, charset='utf8')
        ConnectionWrapper.__init__(self, cnx)

    def cast(self, column, type):
        return 'CAST(%s AS %s)' % (column, type)

    def like(self):
        return 'LIKE'

    def get_last_id(self, cursor, table, column='id'):
        return self.cnx.insert_id()
