#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2008-2014 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import trac.tests.compat
from trac.tests.functional import *


class SetOwnerOperation(FunctionalTwillTestCaseSetup):

    def setUp(self):
        super(SetOwnerOperation, self).setUp()
        self.env = self._testenv.get_trac_environment()
        self.reassign_operations = self.env.config.get('ticket-workflow',
                                                       'reassign.operations')
        self.env.config.set('ticket-workflow', 'reassign.operations',
                       'set_owner')
        self.restrict_owner = self.env.config.get('ticket', 'restrict_owner')
        self.env.config.set('ticket', 'restrict_owner', False)
        self.env.config.save()

    def tearDown(self):
        super(SetOwnerOperation, self).tearDown()
        self.env.config.set('ticket-workflow', 'reassign.operations',
                       self.reassign_operations)
        self.env.config.set('ticket', 'restrict_owner', self.restrict_owner)
        self.env.config.save()

    def test_default(self):
        """When using the workflow operation `set_owner`, the assign-to field
        will default to the currently requesting username.
        """
        ticket_id = self._tester.create_ticket(self.__class__.__name__,
                                               info={'owner': 'lammy'})
        self._tester.go_to_ticket(ticket_id)
        tc.find("The owner will be changed from lammy")
        tc.find('<input type="text" name="action_reassign_reassign_owner" '
                'value="admin" id="action_reassign_reassign_owner" />')

    def test_restrict_owner_not_known_user(self):
        """When using the workflow operation `set_owner` with
        restrict_owner=true, the assign-to dropdown menu will not contain the
        requesting user, if the requesting user is not a known user.
        """
        try:
            ticket_id = self._tester.create_ticket(self.__class__.__name__,
                                                   info={'owner': 'lammy'})
            self.env.config.set('ticket', 'restrict_owner', True)
            self.env.config.save()
            self._tester.logout()
            self._testenv.grant_perm('anonymous', 'TICKET_ADMIN')

            self._tester.go_to_ticket(ticket_id)
            tc.find("The owner will be changed from lammy")
            tc.notfind('<option value="anonymous" selected="selected">'
                       'anonymous</option>')

        finally:
            self._testenv.revoke_perm('anonymous', 'TICKET_ADMIN')
            self._tester.login('admin')


class MaySetOwnerOperationRestrictOwnerFalse(FunctionalTestCaseSetup):
    """Test cases for may_set_owner operation with
    `[ticket] restrict_owner = False`
    http://trac.edgewall.org/ticket/10018
    """
    def setUp(self):
        super(MaySetOwnerOperationRestrictOwnerFalse, self).setUp()
        self.env = self._testenv.get_trac_environment()
        self.reassign_operations = self.env.config.get('ticket-workflow',
                                                       'reassign.operations')
        self.env.config.set('ticket-workflow', 'reassign.operations',
                            'may_set_owner')
        self.restrict_owner = self.env.config.get('ticket', 'restrict_owner')
        self.env.config.set('ticket', 'restrict_owner', False)
        self.env.config.save()

    def tearDown(self):
        super(MaySetOwnerOperationRestrictOwnerFalse, self).tearDown()
        self.env.config.set('ticket-workflow', 'reassign.operations',
                            self.reassign_operations)
        self.env.config.set('ticket', 'restrict_owner', self.restrict_owner)
        self.env.config.save()

    def test_default(self):
        """The assign-to field will default to the ticket's current owner.
        """
        ticket_id = self._tester.create_ticket(self.__class__.__name__,
                                               info={'owner': 'lammy'})
        self._tester.go_to_ticket(ticket_id)
        tc.find("The owner will be changed from lammy")
        tc.find('<input type="text" name="action_reassign_reassign_owner"'
                ' value="lammy" id="action_reassign_reassign_owner" />')

    def test_default_no_owner(self):
        """The assign-to field will default to a blank field if the ticket
        currently has no owner.
        """
        ticket_id = self._tester.create_ticket(self.__class__.__name__,
                                               info={'owner': ''})
        self._tester.go_to_ticket(ticket_id)
        tc.find("The ticket will remain with no owner.")
        tc.find("The owner will be changed from \(none\)")
        tc.find('<input type="text" name="action_reassign_reassign_owner"'
                ' id="action_reassign_reassign_owner" />')

    def test_default_restrict_owner(self):
        """The assign-to field will default to the ticket's current owner
        even if the current owner is not otherwise known to the Trac
        environment."""
        ticket_id = self._tester.create_ticket(self.__class__.__name__,
                                               info={'owner': 'lammy'})
        self.env.config.set('ticket', 'restrict_owner', True)
        self.env.config.save()
        self._tester.go_to_ticket(ticket_id)
        tc.find("The owner will be changed from lammy")
        tc.find('<option selected="selected" value="lammy">'
                'lammy</option>')

        known_usernames = [u[0] for u in self.env.get_known_users()]
        self.assertNotIn('lammy', known_usernames)



class MaySetOwnerOperationDefaultRestrictOwnerNone(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """When using the workflow operation `may_set_owner` with
        restrict_owner=true, the assign-to field will default to an empty
        option labeled (none) if the ticket currently has no owner.
        """
        env = self._testenv.get_trac_environment()
        reassign_operations = env.config.get('ticket-workflow',
                                             'reassign.operations')
        env.config.set('ticket-workflow', 'reassign.operations',
                       'may_set_owner')
        env.config.save()

        try:
            ticket_id = self._tester.create_ticket(self.__class__.__name__,
                                                   info={'owner': ''})
            restrict_owner = env.config.get('ticket', 'restrict_owner')
            env.config.set('ticket', 'restrict_owner', True)
            env.config.save()

            self._tester.go_to_ticket(ticket_id)
            tc.find("The ticket will remain with no owner.")
            tc.find("The owner will be changed from \(none\)")
            tc.find('<option selected="selected" value="">\(none\)</option>')
        finally:
            env.config.set('ticket-workflow', 'reassign.operations',
                           reassign_operations)
            env.config.set('ticket', 'restrict_owner', restrict_owner)
            env.config.save()


class MaySetOwnerOperationDefaultRestrictOwnerAnonymous(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """When using the workflow operation `may_set_owner` with
        restrict_owner=true, the assign-to dropdown menu will contain a
        selected option "anonymous" if the ticket is owned by "anonymous".
        """
        env = self._testenv.get_trac_environment()
        reassign_operations = env.config.get('ticket-workflow',
                                             'reassign.operations')
        env.config.set('ticket-workflow', 'reassign.operations',
                       'may_set_owner')
        restrict_owner = env.config.get('ticket', 'restrict_owner')
        env.config.set('ticket', 'restrict_owner', False)
        env.config.save()

        try:
            ticket_id = \
                self._tester.create_ticket(self.__class__.__name__,
                                           info={'owner': 'anonymous'})
            env.config.set('ticket', 'restrict_owner', True)
            env.config.save()
            self._tester.logout()
            self._testenv.grant_perm('anonymous', 'TICKET_ADMIN')

            self._tester.go_to_ticket(ticket_id)
            tc.find("The owner will be changed from anonymous")
            tc.find('<option selected="selected" value="anonymous">'
                    'anonymous</option>')

        finally:
            self._testenv.revoke_perm('anonymous', 'TICKET_ADMIN')
            self._tester.login('admin')
            env.config.set('ticket-workflow', 'reassign.operations',
                           reassign_operations)
            env.config.set('ticket', 'restrict_owner', restrict_owner)
            env.config.save()


def functionalSuite(suite=None):
    if not suite:
        import trac.tests.functional
        suite = trac.tests.functional.functionalSuite()

    suite.addTests(unittest.makeSuite(SetOwnerOperation))
    suite.addTests(unittest.makeSuite(MaySetOwnerOperationRestrictOwnerFalse))
    suite.addTest(MaySetOwnerOperationDefaultRestrictOwnerNone())
    suite.addTest(MaySetOwnerOperationDefaultRestrictOwnerAnonymous())

    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='functionalSuite')
