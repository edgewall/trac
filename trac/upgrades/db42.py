# -*- coding: utf-8 -*-
#
# Copyright (C) 2016-2019 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/.


def do_upgrade(env, version, cursor):
    """Drop ipnr column from attachment and wiki tables."""

    with env.db_transaction as db:
        db.drop_column('attachment', 'ipnr')
        db.drop_column('wiki', 'ipnr')
