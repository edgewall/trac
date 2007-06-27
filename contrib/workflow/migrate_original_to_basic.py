#!/usr/bin/python
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
    db = trac_env.get_db_cnx()
    cursor = db.cursor()
    cursor.execute("UPDATE ticket SET status = 'accepted' "
                   "WHERE status = 'assigned'")
    db.commit()

if __name__ == '__main__':
    main()
