# -*- coding: utf-8 -*-
#
# Copyright (C) 2015 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

from trac.db.api import DatabaseManager
from trac.db_default import schema


def do_upgrade(env, version, cursor):
    """Change `text` type to `mediumtext` type in all columns
    only if MySQL database backend."""

    if DatabaseManager(env).connection_uri.startswith('mysql:'):
        with env.db_transaction as db:
            tabs = [tab.name for tab in schema]
            cursor.execute("""
                SELECT table_name, column_name FROM information_schema.columns
                WHERE table_schema=%%s AND table_name IN (%s)
                AND data_type='text' ORDER BY table_name, column_name
                """ % ','.join(('%s',) * len(tabs)),
                [db.schema] + tabs)
            text_columns = {}
            for tab, col in cursor:
                text_columns.setdefault(tab, []).append(col)

            # Execute directly "ALTER TABLE" statements because
            # `alter_column_types()` does not work in the case
            for tab, cols in text_columns.iteritems():
                mods = ', '.join('MODIFY %s mediumtext' % db.quote(col)
                                 for col in cols)
                cursor.execute('ALTER TABLE %s %s' % (db.quote(tab), mods))
