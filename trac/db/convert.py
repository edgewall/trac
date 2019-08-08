# -*- coding: utf-8 -*-
#
# Copyright (C) 2017-2019 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

import re
import sys

from trac.db.api import DatabaseManager, get_column_names
from trac.db import sqlite_backend
from trac.util.text import printfout


def copy_tables(src_env, dst_env, src_db, dst_db, src_dburi, dst_dburi):
    printfout("Copying tables:")

    if src_dburi.startswith('sqlite:'):
        src_db.cnx._eager = False  # avoid uses of eagar cursor
    src_cursor = src_db.cursor()
    if src_dburi.startswith('sqlite:'):
        if type(src_cursor.cursor) is not sqlite_backend.PyFormatCursor:
            raise AssertionError('src_cursor.cursor is %r' %
                                 src_cursor.cursor)
    src_tables = set(DatabaseManager(src_env).get_table_names())
    cursor = dst_db.cursor()
    dst_dbm = DatabaseManager(dst_env)
    tables = set(dst_dbm.get_table_names()) & src_tables
    sequences = set(dst_dbm.get_sequence_names())
    progress = sys.stdout.isatty() and sys.stderr.isatty()
    replace_cast = get_replace_cast(src_db, dst_db, src_dburi, dst_dburi)

    # speed-up copying data with SQLite database
    if dst_dburi.startswith('sqlite:'):
        sqlite_backend.set_synchronous(cursor, 'OFF')
        multirows_insert = sqlite_backend.sqlite_version >= (3, 7, 11)
        max_parameters = 999
    else:
        multirows_insert = True
        max_parameters = None

    def copy_table(db, cursor, table):
        src_cursor.execute('SELECT * FROM ' + src_db.quote(table))
        columns = get_column_names(src_cursor)
        n_rows = 100
        if multirows_insert and max_parameters:
            n_rows = min(n_rows, int(max_parameters // len(columns)))
        quoted_table = db.quote(table)
        holders = '(%s)' % ','.join(['%s'] * len(columns))
        count = 0

        cursor.execute('DELETE FROM ' + quoted_table)
        while True:
            rows = src_cursor.fetchmany(n_rows)
            if not rows:
                break
            count += len(rows)
            if progress:
                printfout("%d records\r  %s table... ", count, table,
                          newline=False)
            if replace_cast is not None and table == 'report':
                rows = replace_report_query(rows, columns, replace_cast)
            query = 'INSERT INTO %s (%s) VALUES ' % \
                    (quoted_table, ','.join(map(db.quote, columns)))
            if multirows_insert:
                cursor.execute(query + ','.join([holders] * len(rows)),
                               sum(rows, ()))
            else:
                cursor.executemany(query + holders, rows)

        return count

    try:
        cursor = dst_db.cursor()
        for table in sorted(tables):
            printfout("  %s table... ", table, newline=False)
            count = copy_table(dst_db, cursor, table)
            printfout("%d records.", count)
        for table in tables & sequences:
            dst_db.update_sequence(cursor, table)
        dst_db.commit()
    except:
        dst_db.rollback()
        raise


def get_replace_cast(src_db, dst_db, src_dburi, dst_dburi):
    if src_dburi.split(':', 1) == dst_dburi.split(':', 1):
        return None

    type_re = re.compile(r' AS ([^)]+)')
    def cast_type(db, type):
        match = type_re.search(db.cast('name', type))
        return match.group(1)

    type_maps = dict(filter(lambda src_dst: src_dst[0] != src_dst[1].lower(),
                            ((cast_type(src_db, t).lower(),
                              cast_type(dst_db, t))
                             for t in ('text', 'int', 'int64'))))
    if not type_maps:
        return None

    cast_re = re.compile(r'\bCAST\(\s*([^\s)]+)\s+AS\s+(%s)\s*\)' %
                         '|'.join(type_maps), re.IGNORECASE)
    def replace_cast(text):
        def replace(match):
            name, type = match.groups()
            return 'CAST(%s AS %s)' \
                   % (name, type_maps.get(type.lower(), type))
        return cast_re.sub(replace, text)

    return replace_cast


def replace_report_query(rows, columns, replace_cast):
    idx = columns.index('query')
    def replace(row):
        row = list(row)
        row[idx] = replace_cast(row[idx])
        return tuple(row)
    return [replace(row) for row in rows]
