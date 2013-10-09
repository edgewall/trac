#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2013 Edgewall Software
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

# This script completely migrates a <= 0.8.x Trac environment to use the new
# default ticket model introduced in Trac 0.9.
#
# In particular, this means that the severity field is removed (or rather
# disabled by removing all possible values), and the priority values are
# changed to the more meaningful new defaults.
#
# Make sure to make a backup of the Trac environment before running this!

from __future__ import with_statement

import os
import sys

from trac.env import open_environment
from trac.ticket.model import Priority, Severity

priority_mapping = {
    'highest':  'blocker',
    'high':     'critical',
    'normal':   'major',
    'low':      'minor',
    'lowest':   'trivial'
}

def main():
    if len(sys.argv) < 2:
        print >> sys.stderr, 'usage: %s /path/to/projenv' \
                             % os.path.basename(sys.argv[0])
        sys.exit(2)

    env = open_environment(sys.argv[1])
    with env.db_transaction:
        for oldprio, newprio in priority_mapping.items():
            priority = Priority(env, oldprio)
            priority.name = newprio
            priority.update()

        for severity in list(Severity.select(env)):
            severity.delete()

if __name__ == '__main__':
    main()
