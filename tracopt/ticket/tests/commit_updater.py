# -*- coding: utf-8 -*-
#
# Copyright (C) 2013-2020 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.
import textwrap
import unittest
from datetime import datetime

from trac.test import EnvironmentStub, Mock
from trac.tests.contentgen import random_sentence
from trac.ticket.test import insert_ticket
from trac.util.datefmt import utc
from trac.versioncontrol.api import Repository, RepositoryManager
from trac.wiki.tests import formatter
from tracopt.ticket.commit_updater import CommitTicketUpdater


class CommitTicketUpdaterTestCase(unittest.TestCase):

    def setUp(self):
        self.env = EnvironmentStub(enable=['trac.*',
                                           'tracopt.ticket.commit_updater.*'])
        self.env.config.set('ticket', 'commit_ticket_update_check_perms', False)
        self.repos = Mock(Repository, 'repos1', {'name': 'repos1', 'id': 1},
                          self.env.log, normalize_rev=lambda rev: 1)
        self.updater = CommitTicketUpdater(self.env)

    def tearDown(self):
        self.env.reset_db()

    def _make_tickets(self, num):
        self.tickets = []
        for i in range(num):
            ticket = insert_ticket(self.env, reporter='someone',
                                   summary=random_sentence())
            self.tickets.append(ticket)

    def test_changeset_added(self):
        self._make_tickets(1)
        message = 'This is the first comment. Refs #1.'
        chgset = Mock(repos=self.repos, rev=1, message=message, author='joe',
                      date=datetime(2001, 1, 1, 1, 1, 1, 0, utc))
        self.updater.changeset_added(self.repos, chgset)
        changes = self.tickets[0].get_change(cnum=1)
        self.assertEqual(textwrap.dedent("""\
            In [changeset:"1/repos1" 1/repos1]:
            {{{#!CommitTicketReference repository="repos1" revision="1"
            This is the first comment. Refs #1.
            }}}"""), changes['fields']['comment']['new'])

    def test_changeset_added_multiline_comment(self):
        self._make_tickets(1)
        message = ("This is a multiline comment.\n\n"
                   "It is multiline.\n\n"
                   "Refs #1.")
        chgset = Mock(repos=self.repos, rev=1, message=message, author='joe',
                      date=datetime(2001, 1, 1, 1, 1, 1, 0, utc))
        self.updater.changeset_added(self.repos, chgset)
        changes = self.tickets[0].get_change(cnum=1)
        self.assertEqual(textwrap.dedent("""\
            In [changeset:"1/repos1" 1/repos1]:
            {{{#!CommitTicketReference repository="repos1" revision="1"
            This is a multiline comment.

            It is multiline.

            Refs #1.
            }}}"""), changes['fields']['comment']['new'])

    def test_changeset_modified(self):
        self._make_tickets(2)
        message = 'This is the first comment. Refs #1.'
        old_chgset = Mock(repos=self.repos, rev=1,
                          message=message, author='joe',
                          date=datetime(2001, 1, 1, 1, 1, 1, 0, utc))
        message = 'This is the first comment after an edit. Refs #1, #2.'
        new_chgset = Mock(repos=self.repos, rev=1,
                          message=message, author='joe',
                          date=datetime(2001, 1, 2, 1, 1, 1, 0, utc))
        self.updater.changeset_added(self.repos, old_chgset)
        self.updater.changeset_modified(self.repos, new_chgset, old_chgset)
        changes = self.tickets[0].get_change(cnum=1)
        self.assertEqual(textwrap.dedent("""\
            In [changeset:"1/repos1" 1/repos1]:
            {{{#!CommitTicketReference repository="repos1" revision="1"
            This is the first comment. Refs #1.
            }}}"""), changes['fields']['comment']['new'])
        changes = self.tickets[1].get_change(cnum=1)
        self.assertEqual(textwrap.dedent("""\
            In [changeset:"1/repos1" 1/repos1]:
            {{{#!CommitTicketReference repository="repos1" revision="1"
            This is the first comment after an edit. Refs #1, #2.
            }}}"""), changes['fields']['comment']['new'])

    def test_commands_refs(self):
        commands ={(1,): 'Refs #1', (2,): 'refs #2',
                   (3,): 'refs ticket:3#comment:1',
                   (4,5): 'refs ticket:4#comment:description and '
                          'ticket:5#comment:1'}
        self._make_tickets(5)
        rev = 0

        for tkts, cmd in commands.items():
            rev += 1
            message = "This is the first comment. %s." % cmd
            chgset = Mock(repos=self.repos, rev=rev,
                          message=message, author='joe',
                          date=datetime(2001, 1, 1, 1, 1, 1, 0, utc))

            self.updater.changeset_added(self.repos, chgset)
            comment = self.updater.make_ticket_comment(self.repos, chgset)

            for tkt in tkts:
                change = self.tickets[tkt-1].get_change(cnum=1)
                self.assertEqual(comment, change['fields']['comment']['new'])


def macro_setup(tc):
    tc.env = EnvironmentStub(enable=('trac.*',
                                     'tracopt.ticket.commit_updater.*',))
    insert_ticket(tc.env, summary='the summary', status='new')
    def _get_repository(reponame):
        return Mock(get_changeset=_get_changeset, resource=None)
    def _get_changeset(rev=None):
        return Mock(message="the message. refs #1.  ", rev=rev)
    setattr(RepositoryManager(tc.env), 'get_repository', _get_repository)


COMMIT_TICKET_REF_MACRO_TEST_CASES = """\
============================== No arguments
[[CommitTicketReference]]
------------------------------
<p>
</p><div class="message"><p>
the message. refs <a class="new ticket" href="/ticket/1" title="#1: the summary (new)">#1</a>.  <br />
</p>
</div><p>
</p>
------------------------------
"""


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(CommitTicketUpdaterTestCase))
    suite.addTest(formatter.test_suite(COMMIT_TICKET_REF_MACRO_TEST_CASES,
                                       macro_setup, __file__,
                                       context=('ticket', 1)))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
