#!/usr/bin/env python

# trac-post-commit-hook
# ----------------------------------------------------------------------------
# Copyright (c) 2004 Stephen Hansen 
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to
# deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
#   The above copyright notice and this permission notice shall be included in
#   all copies or substantial portions of the Software. 
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.
# ----------------------------------------------------------------------------

# This Subversion post-commit hook script is meant to interface to the
# Trac (http://www.edgewall.com/products/trac/) issue tracking/wiki/etc 
# system.
# 
# It should be called from the 'post-commit' script in Subversion, such as
# via:
#
# REPOS="$1"
# REV="$2"
# LOG=`/usr/bin/svnlook log -r $REV $REPOS`
# AUTHOR=`/usr/bin/svnlook author -r $REV $REPOS`
# TRAC_ENV='/somewhere/trac/project/'
# TRAC_URL='http://trac.mysite.com/project/'
#
# /usr/bin/python /usr/local/src/trac/contrib/trac-post-commit-hook \
#  -p "$TRAC_ENV"  \
#  -r "$REV"       \
#  -u "$AUTHOR"    \
#  -m "$LOG"       \
#  -s "$TRAC_URL"
#
# It searches commit messages for text in the form of:
#   command #1
#   command #1, #2
#   command #1 & #2 
#   command #1 and #2
#
# You can have more then one command in a message. The following commands
# are supported. There is more then one spelling for each command, to make
# this as user-friendly as possible.
#
#   closes, fixes
#     The specified issue numbers are closed with the contents of this
#     commit message being added to it. 
#   references, refs, addresses, re 
#     The specified issue numbers are left in their current status, but 
#     the contents of this commit message are added to their notes. 
#
# A fairly complicated example of what you can do is with a commit message
# of:
#
#    Changed blah and foo to do this or that. Fixes #10 and #12, and refs #12.
#
# This will close #10 and #12, and add a note to #12.

import re
import os
import sys
import time 

from trac.env import open_environment
from trac.ticket.notification import TicketNotifyEmail
from trac.ticket import Ticket
from trac.ticket.web_ui import TicketModule
# TODO: move grouped_changelog_entries to model.py
from trac.util.text import to_unicode
from trac.web.href import Href

try:
    from optparse import OptionParser
except ImportError:
    try:
        from optik import OptionParser
    except ImportError:
        raise ImportError, 'Requires Python 2.3 or the Optik option parsing library.'

parser = OptionParser()
depr = '(not used anymore)'
parser.add_option('-e', '--require-envelope', dest='env', default='',
                  help="""
Require commands to be enclosed in an envelope.
If -e[], then commands must be in the form of [closes #4].
Must be two characters.""")
parser.add_option('-p', '--project', dest='project',
                  help='Path to the Trac project.')
parser.add_option('-r', '--revision', dest='rev',
                  help='Repository revision number.')
parser.add_option('-u', '--user', dest='user',
                  help='The user who is responsible for this action '+depr)
parser.add_option('-m', '--msg', dest='msg',
                  help='The log message to search '+depr)
parser.add_option('-c', '--encoding', dest='encoding',
                  help='The encoding used by the log message '+depr)
parser.add_option('-s', '--siteurl', dest='url',
                  help='The base URL to the project\'s trac website (to which '
                       '/ticket/## is appended).  If this is not specified, '
                       'the project URL from trac.ini will be used.')

(options, args) = parser.parse_args(sys.argv[1:])

if options.env:
    leftEnv = '\\' + options.env[0]
    rghtEnv = '\\' + options.env[1]
else:
    leftEnv = ''
    rghtEnv = ''

commandPattern = re.compile(leftEnv + r'(?P<action>[A-Za-z]*).?(?P<ticket>#[0-9]+(?:(?:[, &]*|[ ]?and[ ]?)#[0-9]+)*)' + rghtEnv)
ticketPattern = re.compile(r'#([0-9]*)')

class CommitHook:
    _supported_cmds = {'close':      '_cmdClose',
                       'closed':     '_cmdClose',
                       'closes':     '_cmdClose',
                       'fix':        '_cmdClose',
                       'fixed':      '_cmdClose',
                       'fixes':      '_cmdClose',
                       'addresses':  '_cmdRefs',
                       're':         '_cmdRefs',
                       'references': '_cmdRefs',
                       'refs':       '_cmdRefs',
                       'see':        '_cmdRefs'}

    def __init__(self, project=options.project, author=options.user,
                 rev=options.rev, url=options.url):
        self.env = open_environment(project)
        repos = self.env.get_repository()
        repos.sync()
        
        # Instead of bothering with the encoding, we'll use unicode data
        # as provided by the Trac versioncontrol API (#1310).
        chgset = repos.get_changeset(rev)
        self.author = chgset.author
        self.rev = rev
        self.msg = "(In [%s]) %s" % (rev, chgset.message)
        self.now = int(time.time()) 
        if url is None:
            url = self.env.config.get('trac', 'base_url')
        self.env.href = Href(url)
        self.env.abs_href = Href(url)

        cmdGroups = commandPattern.findall(self.msg)

        tickets = {}
        for cmd, tkts in cmdGroups:
            funcname = CommitHook._supported_cmds.get(cmd.lower(), '')
            if funcname:
                for tkt_id in ticketPattern.findall(tkts):
                    func = getattr(self, funcname)
                    tickets.setdefault(tkt_id, []).append(func)

        for tkt_id, cmds in tickets.iteritems():
            try:
                db = self.env.get_db_cnx()
                
                ticket = Ticket(self.env, int(tkt_id), db)
                for cmd in cmds:
                    cmd(ticket)

                # determine sequence number... 
                cnum = 0
                tm = TicketModule(self.env)
                for change in tm.grouped_changelog_entries(ticket, db):
                    if change['permanent']:
                        cnum += 1
                
                ticket.save_changes(self.author, self.msg, self.now, db, cnum+1)
                db.commit()
                
                tn = TicketNotifyEmail(self.env)
                tn.notify(ticket, newticket=0, modtime=self.now)
            except Exception, e:
                # import traceback
                # traceback.print_exc(file=sys.stderr)
                print>>sys.stderr, 'Unexpected error while processing ticket ' \
                                   'ID %s: %s' % (tkt_id, e)
            

    def _cmdClose(self, ticket):
        ticket['status'] = 'closed'
        ticket['resolution'] = 'fixed'

    def _cmdRefs(self, ticket):
        pass


if __name__ == "__main__":
    if len(sys.argv) < 5:
        print "For usage: %s --help" % (sys.argv[0])
        print
        print "Note that the deprecated options will be removed in Trac 0.12."
    else:
        CommitHook()
