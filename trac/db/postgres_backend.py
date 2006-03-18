# -*- coding: iso-8859-1 -*-
#
# Copyright (C) 2005 Edgewall Software
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://projects.edgewall.com/trac/.
#
# Author: Christopher Lenz <cmlenz@gmx.de>

from trac.core import *
from trac.db.api import IDatabaseConnector
from trac.db.util import ConnectionWrapper

psycopg = None
PgSQL = None


class PostgreSQLConnector(Component):
    """PostgreSQL database support."""

    implements(IDatabaseConnector)

    def get_supported_schemes(self):
        return [('postgres', 1)]

    def get_connection(self, path, user=None, password=None, host=None,
                       port=None, params={}):
        return PostgreSQLConnection(path, user, password, host, port, params)

    def init_db(self, path, user=None, password=None, host=None, port=None,
                params={}):
        cnx = self.get_connection(path, user, password, host, port, params)
        cursor = cnx.cursor()
        from trac.db_default import schema
        for table in schema:
            for stmt in self.to_sql(table):
                cursor.execute(stmt)
        cnx.commit()

    def to_sql(self, table):
        sql = ["CREATE TABLE %s (" % table.name]
        coldefs = []
        for column in table.columns:
            ctype = column.type
            if column.auto_increment:
                ctype = "SERIAL"
            if len(table.key) == 1 and column.name in table.key:
                ctype += " PRIMARY KEY"
            coldefs.append("    %s %s" % (column.name, ctype))
        if len(table.key) > 1:
            coldefs.append("    CONSTRAINT %s_pk PRIMARY KEY (%s)"
                           % (table.name, ','.join(table.key)))
        sql.append(',\n'.join(coldefs) + '\n)')
        yield '\n'.join(sql)
        for index in table.indices:
            yield "CREATE INDEX %s_%s_idx ON %s (%s)" % (table.name, 
                   '_'.join(index.columns), table.name, ','.join(index.columns))


class PostgreSQLConnection(ConnectionWrapper):
    """Connection wrapper for PostgreSQL."""

    poolable = True

    def __init__(self, path, user=None, password=None, host=None, port=None,
                 params={}):
        if path.startswith('/'):
            path = path[1:]
        # We support both psycopg and PgSQL but prefer psycopg
        global psycopg
        global PgSQL
        global have_psycopg2
        
        if not psycopg and not PgSQL:
            try:
                try:
                    import psycopg2 as psycopg
                    import psycopg2.extensions
                    psycopg2.extensions.register_type(psycopg2.extensions.UNICODE)
                    have_psycopg2 = True
                except ImportError:
                    have_psycopg2 = False
                    import psycopg
            except ImportError:
                from pyPgSQL import PgSQL
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
            if have_psycopg2:
                cnx.set_client_encoding('UNICODE')
        else:
            cnx = PgSQL.connect('', user, password, host, path, port)
        ConnectionWrapper.__init__(self, cnx)

    def cast(self, column, type):
        # Temporary hack needed for the union of selects in the search module
        return 'CAST(%s AS %s)' % (column, type)

    def like(self):
        # Temporary hack needed for the case-insensitive string matching in the
        # search module
        return 'ILIKE'

    def get_last_id(self, cursor, table, column='id'):
        cursor.execute("SELECT CURRVAL('%s_%s_seq')" % (table, column))
        return cursor.fetchone()[0]
