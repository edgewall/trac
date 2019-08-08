# -*- coding: utf-8 -*-
#
# Copyright (C) 2010-2019 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/.

import os

from trac.util.text import exception_to_unicode, printerr


def do_upgrade(env, ver, cursor):
    """
    1. Zero-pad Subversion revision numbers in the cache.
    2. Remove wiki-macros directory.
    """
    # Zero-pad Subversion revision numbers.
    cursor.execute("""
        SELECT id, value FROM repository WHERE name='repository_dir'
        """)
    for id in [id for id, dir in cursor if dir.startswith('svn:')]:
        cursor.execute("SELECT DISTINCT rev FROM revision WHERE repos=%s",
                       (id,))
        for rev in {row[0] for row in cursor}:
            cursor.execute("""
                UPDATE revision SET rev=%s WHERE repos=%s AND rev=%s
                """, ('%010d' % int(rev), id, rev))

        cursor.execute("SELECT DISTINCT rev FROM node_change WHERE repos=%s",
                       (id,))
        for rev in {row[0] for row in cursor}:
            cursor.execute("""
                UPDATE node_change SET rev=%s WHERE repos=%s AND rev=%s
                """, ('%010d' % int(rev), id, rev))

    # Remove wiki-macros if it is empty and warn if it isn't.
    wiki_macros = os.path.join(env.path, 'wiki-macros')
    try:
        entries = os.listdir(wiki_macros)
    except OSError:
        pass
    else:
        if entries:
            printerr("Warning: the wiki-macros directory in the environment "
                     "is non-empty, but Trac\ndoesn't load plugins from "
                     "there anymore. Please remove it by hand.")
        else:
            try:
                os.rmdir(wiki_macros)
            except OSError as e:
                printerr("Error while removing wiki-macros: %(err)s\nTrac "
                         "doesn't load plugins from wiki-macros anymore. "
                         "Please remove it by hand.",
                         err=exception_to_unicode(e))
