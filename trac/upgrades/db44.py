# -*- coding: utf-8 -*-
#
# Copyright (C) 2016-2020 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/.

import re

from trac.db.api import DatabaseManager
from trac.db.schema import Column, Table
from trac.resource import ResourceNotFound
from trac.ticket.model import Report
from trac.util.text import printout
from trac.util.translation import _

url = 'https://trac.edgewall.org/wiki/1.3/TracUpgrade#enum-description-field'


def do_upgrade(env, version, cursor):
    """Add `description` column to `enum` table."""
    new_schema = [
        Table('enum', key=('type', 'name'))[
            Column('type'),
            Column('name'),
            Column('value'),
            Column('description'),
        ]
    ]

    with env.db_transaction:
        DatabaseManager(env).upgrade_tables(new_schema)
        failures = []
        for id_ in [1, 2, 3, 4, 5, 7, 8]:
            try:
                r = Report(env, id_)
            except ResourceNotFound:
                pass
            else:
                query = replace_sql_fragment(r.query)
                if query:
                    r.query = query
                    r.update()
                else:
                    failures.append(str(id_))

    if failures:
        failures = ', '.join(failures)
        # TRANSLATOR: Wrap message to 80 columns
        printout(_("""\
Report(s) %(ids)s could not be upgraded and may need to be manually
edited to avoid an "ambiguous column name" error. See %(url)s for more
information.
""", ids=failures, url=url))


pattern = r'(?<!\.)(description AS _description)((?=_)|\b)'
def replace_sql_fragment(query):
    """Replace SQL fragment, but try to confirm that the default reports
    haven't been modified. The default reports have at most one
    'description AS ...' fragment.
    """
    if len(re.findall(pattern, query)) == 1:
        return re.sub(pattern, r't.\1', query)
