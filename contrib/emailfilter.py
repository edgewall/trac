#!/usr/bin/python
"""
emailfilter.py -- Email tickets to Trac.

A simple MTA filter to create Trac tickets from inbound emails.

Copyright 2005, Daniel Lundin <daniel@edgewall.com>
Copyright 2005, Edgewall Software

The scripts reads emails from stdin and inserts directly into a Trac database.
MIME headers are mapped as follows:

    * From: => Reporter
    * Subject: => Summary
    * Body => Description

How to use
----------
 * Set TRAC_ENV_PATH to the path of your project's Trac environment
 * Configure script as a mail (pipe) filter with your MTA
    typically, this involves adding a line like this to /etc/aliases:
       somename: |/path/to/email2trac.py
    Check your MTA's documentation for specifics.

Todo
----
  * Configure target database through env variable?
  * Handle/discard HTML parts
  * Attachment support
"""

TRAC_ENV_PATH = '/var/trac/test'

import email
import sys

from trac.env import Environment
from trac.Ticket import Ticket


class TicketEmailParser(object):

    env = None

    def __init__(self, env):
        self.env = env
        self.config = env.config

    def parse(self, fp):
        msg = email.message_from_file(fp)
        db = self.env.get_db_cnx()
        tkt = Ticket()
        tkt['status'] = 'new'
        tkt['component'] = self.config.get('ticket', 'default_component')
        cursor = db.cursor()
        cursor.execute('SELECT owner FROM component '
                       'WHERE name=%s', tkt['component'])
        tkt['owner'] = cursor.fetchone()[0]
        tkt['milestone'] = self.config.get('ticket', 'default_milestone')
        tkt['priority'] = self.config.get('ticket', 'default_priority')
        tkt['severity'] = self.config.get('ticket', 'default_severity')
        tkt['version'] = self.config.get('ticket', 'default_version')
        tkt['reporter'] = msg['from']
        tkt['summary'] = msg['subject']
        for part in msg.walk():
            if part.get_content_type() == 'text/plain':
                tkt['description'] = part.get_payload(decode=1).strip()

        if tkt.get('description'):
            tkt.insert(db)

if __name__ == '__main__':
    env = Environment(TRAC_ENV_PATH, create=0)
    tktparser = TicketEmailParser(env)
    tktparser.parse(sys.stdin)
