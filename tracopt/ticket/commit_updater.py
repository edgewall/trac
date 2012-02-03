# -*- coding: utf-8 -*-
#
# Copyright (C) 2009 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

# This plugin was based on the contrib/trac-post-commit-hook script, which
# had the following copyright notice:
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

from datetime import datetime
import re

from genshi.builder import tag

from trac.config import BoolOption, Option
from trac.core import Component, implements
from trac.perm import PermissionCache
from trac.resource import Resource
from trac.ticket import Ticket
from trac.ticket.notification import TicketNotifyEmail
from trac.util.compat import any
from trac.util.datefmt import utc
from trac.util.text import exception_to_unicode
from trac.versioncontrol import IRepositoryChangeListener, RepositoryManager
from trac.versioncontrol.web_ui.changeset import ChangesetModule
from trac.wiki.formatter import format_to_html
from trac.wiki.macros import WikiMacroBase


class CommitTicketUpdater(Component):
    """Update tickets based on commit messages.
    
    This component hooks into changeset notifications and searches commit
    messages for text in the form of:
    {{{
    command #1
    command #1, #2
    command #1 & #2 
    command #1 and #2
    }}}
    
    Instead of the short-hand syntax "#1", "ticket:1" can be used as well,
    e.g.:
    {{{
    command ticket:1
    command ticket:1, ticket:2
    command ticket:1 & ticket:2 
    command ticket:1 and ticket:2
    }}}
    
    In addition, the ':' character can be omitted and issue or bug can be used
    instead of ticket.
    
    You can have more than one command in a message. The following commands
    are supported. There is more than one spelling for each command, to make
    this as user-friendly as possible.
    
      close, closed, closes, fix, fixed, fixes::
        The specified tickets are closed, and the commit message is added to
        them as a comment.
    
      references, refs, addresses, re, see::
        The specified tickets are left in their current status, and the commit
        message is added to them as a comment. 
    
    A fairly complicated example of what you can do is with a commit message
    of:
    
        Changed blah and foo to do this or that. Fixes #10 and #12,
        and refs #12.
    
    This will close #10 and #12, and add a note to #12.
    """
    
    implements(IRepositoryChangeListener)
    
    envelope = Option('ticket', 'commit_ticket_update_envelope', '',
        """Require commands to be enclosed in an envelope.
        
        Must be empty or contain two characters. For example, if set to "[]",
        then commands must be in the form of [closes #4].""")
    
    commands_close = Option('ticket', 'commit_ticket_update_commands.close',
        'close closed closes fix fixed fixes',
        """Commands that close tickets, as a space-separated list.""")
    
    commands_refs = Option('ticket', 'commit_ticket_update_commands.refs',
        'addresses re references refs see',
        """Commands that add a reference, as a space-separated list.
        
        If set to the special value <ALL>, all tickets referenced by the
        message will get a reference to the changeset.""")
    
    check_perms = BoolOption('ticket', 'commit_ticket_update_check_perms',
        'true',
        """Check that the committer has permission to perform the requested
        operations on the referenced tickets.
        
        This requires that the user names be the same for Trac and repository
        operations.""")

    notify = BoolOption('ticket', 'commit_ticket_update_notify', 'true',
        """Send ticket change notification when updating a ticket.""")
    
    ticket_prefix = '(?:#|(?:ticket|issue|bug)[: ]?)'
    ticket_reference = ticket_prefix + '[0-9]+'
    ticket_command = (r'(?P<action>[A-Za-z]*)\s*.?\s*'
                      r'(?P<ticket>%s(?:(?:[, &]*|[ ]?and[ ]?)%s)*)' %
                      (ticket_reference, ticket_reference))
    
    @property
    def command_re(self):
        (begin, end) = (re.escape(self.envelope[0:1]),
                        re.escape(self.envelope[1:2]))
        return re.compile(begin + self.ticket_command + end)
    
    ticket_re = re.compile(ticket_prefix + '([0-9]+)')
    
    _last_cset_id = None
    
    # IRepositoryChangeListener methods
    
    def changeset_added(self, repos, changeset):
        if self._is_duplicate(changeset):
            return
        tickets = self._parse_message(changeset.message)
        comment = self.make_ticket_comment(repos, changeset)
        self._update_tickets(tickets, changeset, comment,
                             datetime.now(utc))
    
    def changeset_modified(self, repos, changeset, old_changeset):
        if self._is_duplicate(changeset):
            return
        tickets = self._parse_message(changeset.message)
        old_tickets = {}
        if old_changeset is not None:
            old_tickets = self._parse_message(old_changeset.message)
        tickets = dict(each for each in tickets.iteritems()
                       if each[0] not in old_tickets)
        comment = self.make_ticket_comment(repos, changeset)
        self._update_tickets(tickets, changeset, comment,
                             datetime.now(utc))
    
    def _is_duplicate(self, changeset):
        # Avoid duplicate changes with multiple scoped repositories
        cset_id = (changeset.rev, changeset.message, changeset.author,
                   changeset.date)
        if cset_id != self._last_cset_id:
            self._last_cset_id = cset_id
            return False
        return True
        
    def _parse_message(self, message):
        """Parse the commit message and return the ticket references."""
        cmd_groups = self.command_re.findall(message)
        functions = self._get_functions()
        tickets = {}
        for cmd, tkts in cmd_groups:
            func = functions.get(cmd.lower())
            if not func and self.commands_refs.strip() == '<ALL>':
                func = self.cmd_refs
            if func:
                for tkt_id in self.ticket_re.findall(tkts):
                    tickets.setdefault(int(tkt_id), []).append(func)
        return tickets
    
    def make_ticket_comment(self, repos, changeset):
        """Create the ticket comment from the changeset data."""
        revstring = str(changeset.rev)
        if repos.reponame:
            revstring += '/' + repos.reponame
        return """\
In [changeset:%s]:
{{{
#!CommitTicketReference repository="%s" revision="%s"
%s
}}}""" % (revstring, repos.reponame, changeset.rev, changeset.message.strip())
        
    def _update_tickets(self, tickets, changeset, comment, date):
        """Update the tickets with the given comment."""
        perm = PermissionCache(self.env, changeset.author)
        for tkt_id, cmds in tickets.iteritems():
            try:
                self.log.debug("Updating ticket #%d", tkt_id)
                ticket = [None]
                @self.env.with_transaction()
                def do_update(db):
                    ticket[0] = Ticket(self.env, tkt_id, db)
                    for cmd in cmds:
                        cmd(ticket[0], changeset, perm(ticket[0].resource))
                    ticket[0].save_changes(changeset.author, comment, date, db)
                self._notify(ticket[0], date)
            except Exception, e:
                self.log.error("Unexpected error while processing ticket "
                               "#%s: %s", tkt_id, exception_to_unicode(e))
    
    def _notify(self, ticket, date):
        """Send a ticket update notification."""
        if not self.notify:
            return
        try:
            tn = TicketNotifyEmail(self.env)
            tn.notify(ticket, newticket=False, modtime=date)
        except Exception, e:
            self.log.error("Failure sending notification on change to "
                           "ticket #%s: %s", ticket.id,
                           exception_to_unicode(e))
    
    def _get_functions(self):
        """Create a mapping from commands to command functions."""
        functions = {}
        for each in dir(self):
            if not each.startswith('cmd_'):
                continue
            func = getattr(self, each)
            for cmd in getattr(self, 'commands_' + each[4:], '').split():
                functions[cmd] = func
        return functions
    
    def cmd_close(self, ticket, changeset, perm):
        if not self.check_perms or 'TICKET_MODIFY' in perm:
            ticket['status'] = 'closed'
            ticket['resolution'] = 'fixed'
            if not ticket['owner']:
                ticket['owner'] = changeset.author

    def cmd_refs(self, ticket, changeset, perm):
        pass


class CommitTicketReferenceMacro(WikiMacroBase):
    """Insert a changeset message into the output.
    
    This macro must be called using wiki processor syntax as follows:
    {{{
    {{{
    #!CommitTicketReference repository="reponame" revision="rev"
    }}}
    }}}
    where the arguments are the following:
     - `repository`: the repository containing the changeset
     - `revision`: the revision of the desired changeset
    """
    
    def expand_macro(self, formatter, name, content, args={}):
        reponame = args.get('repository') or ''
        rev = args.get('revision')
        repos = RepositoryManager(self.env).get_repository(reponame)
        try:
            changeset = repos.get_changeset(rev)
            message = changeset.message
            rev = changeset.rev
            resource = repos.resource
        except Exception:
            message = content
            resource = Resource('repository', reponame)
        if formatter.context.resource.realm == 'ticket':
            ticket_re = CommitTicketUpdater.ticket_re
            if not any(int(tkt_id) == int(formatter.context.resource.id)
                       for tkt_id in ticket_re.findall(message)):
                return tag.p("(The changeset message doesn't reference this "
                             "ticket)", class_='hint')
        if ChangesetModule(self.env).wiki_format_messages:
            return tag.div(format_to_html(self.env,
                formatter.context('changeset', rev, parent=resource),
                message, escape_newlines=True), class_='message')
        else:
            return tag.pre(message, class_='message')
