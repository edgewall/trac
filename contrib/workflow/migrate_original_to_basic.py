#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2007-2013 Edgewall Software
# Copyright (C) 2007 Eli Carter <retracile@gmail.com>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.com/license.html.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/.

import sys

import trac.env
from trac.ticket.default_workflow import load_workflow_config_snippet


def main():
    """Rewrite the ticket-workflow section of the config; and change all
    'assigned' tickets to 'accepted'.
    """
    if len(sys.argv) != 2:
        print "Usage: %s path_to_trac_environment" % sys.argv[0]
        sys.exit(1)
    tracdir = sys.argv[1]
    trac_env = trac.env.open_environment(tracdir)

    # Update the config...
    old_workflow = trac_env.config.options('ticket-workflow')
    for name, value in old_workflow:
        trac_env.config.remove('ticket-workflow', name)
    load_workflow_config_snippet(trac_env.config, 'basic-workflow.ini')
    trac_env.config.save()

    # Update the ticket statuses...
    trac_env.db_transaction("""
        UPDATE ticket SET status = 'accepted' WHERE status = 'assigned'
        """)

if __name__ == '__main__':
    main()
