# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2019 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

import unittest

import trac.ticket.admin
from trac.admin.api import get_console_locale
from trac.admin.console import TracAdmin
from trac.admin.test import TracAdminTestCaseBase
from trac.test import EnvironmentStub
from trac.ticket.test import insert_ticket
from trac.util.datefmt import get_datetime_format_hint


class TracAdminTestCase(TracAdminTestCaseBase):

    def setUp(self):
        self.env = EnvironmentStub(default_data=True, enable=('trac.*',),
                                   disable=('trac.tests.*',))
        self.admin = TracAdmin()
        self.admin.env_set('', self.env)
        self._test_date = '2004-01-11'  # Set test date to 11th Jan 2004

    def tearDown(self):
        self.env = None

    @property
    def datetime_format_hint(self):
        return get_datetime_format_hint(get_console_locale(self.env))

    def test_component_help(self):
        rv, output = self.execute('help component')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_component_list_ok(self):
        """
        Tests the 'component list' command in trac-admin.  Since this command
        has no command arguments, it is hard to call it incorrectly.  As
        a result, there is only this one test.
        """
        rv, output = self.execute('component list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_component_add_ok(self):
        """
        Tests the 'component add' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        self.execute('component add new_component')
        rv, output = self.execute('component list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_component_add_optional_owner_ok(self):
        """
        Tests the 'component add' command in trac-admin with the optional
        'owner' argument.  This particular test passes valid arguments and
        checks for success.
        """
        self.execute('component add new_component new_user')
        rv, output = self.execute('component list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_component_add_complete_optional_owner_restrict_owner_false(self):
        """Tests completion of the 'component add <component>' command with
        [ticket] restrict_owner = false.
        """
        self.execute('config set ticket restrict_owner false')
        self.execute('session add user1')
        self.execute('session add user3')
        self.execute('permission add user1 TICKET_MODIFY')
        self.execute('permission add user2 TICKET_VIEW')
        self.execute('permission add user3 TICKET_MODIFY')
        output = self.complete_command('component', 'add',
                                        'new_component', '')
        self.assertEqual([], output)

    def test_component_add_complete_optional_owner_restrict_owner_true(self):
        """Tests completion of the 'component add <component>' command with
        [ticket] restrict_owner = true.
        """
        self.execute('config set ticket restrict_owner true')
        self.execute('session add user1')
        self.execute('session add user3')
        self.execute('permission add user1 TICKET_MODIFY')
        self.execute('permission add user2 TICKET_VIEW')
        self.execute('permission add user3 TICKET_MODIFY')
        output = self.complete_command('component', 'add',
                                        'new_component', '')
        self.assertEqual(['user1', 'user3'], output)

    def test_component_add_error_already_exists(self):
        """
        Tests the 'component add' command in trac-admin.  This particular
        test passes a component name that already exists and checks for an
        error message.
        """
        rv, output = self.execute('component add component1 new_user')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_component_rename_ok(self):
        """
        Tests the 'component rename' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        self.execute('component rename component1 changed_name')
        rv, output = self.execute('component list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_component_rename_error_bad_component(self):
        """
        Tests the 'component rename' command in trac-admin.  This particular
        test tries to rename a component that does not exist.
        """
        rv, output = self.execute('component rename bad_component changed_name')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_component_rename_error_bad_new_name(self):
        """
        Tests the 'component rename' command in trac-admin.  This particular
        test tries to rename a component to a name that already exists.
        """
        rv, output = self.execute('component rename component1 component2')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_component_chown_ok(self):
        """
        Tests the 'component chown' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        self.execute('component chown component2 changed_owner')
        rv, output = self.execute('component list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_component_chown_complete_component(self):
        """Tests completion of the 'component chown' command.
        """
        output = self.complete_command('component', 'chown', '')
        self.assertEqual(['component1', 'component2'], output)

    def test_component_chown_complete_owner_restrict_owner_false(self):
        """Tests completion of the 'component chown <component>' command with
        [ticket] restrict_owner = false.
        """
        self.execute('config set ticket restrict_owner false')
        self.execute('session add user1')
        self.execute('session add user3')
        self.execute('permission add user1 TICKET_MODIFY')
        self.execute('permission add user2 TICKET_VIEW')
        self.execute('permission add user3 TICKET_MODIFY')
        output = self.complete_command('component', 'chown', 'component1', '')
        self.assertEqual([], output)

    def test_component_chown_complete_owner_restrict_owner_true(self):
        """Tests completion of the 'component chown <component>' command with
        [ticket] restrict_owner = true.
        """
        self.execute('config set ticket restrict_owner true')
        self.execute('session add user1')
        self.execute('session add user3')
        self.execute('permission add user1 TICKET_MODIFY')
        self.execute('permission add user2 TICKET_VIEW')
        self.execute('permission add user3 TICKET_MODIFY')
        output = self.complete_command('component', 'chown', 'component1', '')
        self.assertEqual(['user1', 'user3'], output)

    def test_component_chown_error_bad_component(self):
        """
        Tests the 'component chown' command in trac-admin.  This particular
        test tries to change the owner of a component that does not
        exist.
        """
        rv, output = self.execute('component chown bad_component changed_owner')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_component_remove_ok(self):
        """
        Tests the 'component remove' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """
        self.execute('component remove component1')
        rv, output = self.execute('component list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_component_remove_error_bad_component(self):
        """
        Tests the 'component remove' command in trac-admin.  This particular
        test tries to remove a component that does not exist.
        """
        rv, output = self.execute('component remove bad_component')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_ticket_help(self):
        rv, output = self.execute('help ticket')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_ticket_remove_ok(self):
        """Ticket is successfully deleted."""
        insert_ticket(self.env)
        rv, output = self.execute('ticket remove 1')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_ticket_remove_error_no_ticket_argument(self):
        """Error reported when ticket# argument is missing."""
        rv, output = self.execute('ticket remove')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_ticket_remove_error_ticket_id_not_an_int(self):
        """Error reported when ticket id is not an int."""
        insert_ticket(self.env)
        rv, output = self.execute('ticket remove a')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_ticket_remove_error_invalid_ticket_id(self):
        """ResourceNotFound error reported when ticket does not exist."""
        insert_ticket(self.env)
        rv, output = self.execute('ticket remove 2')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_ticket_comment_remove_ok(self):
        """Ticket comment is successfully deleted."""
        ticket = insert_ticket(self.env)
        ticket.save_changes('user1', 'the comment')
        rv, output = self.execute('ticket remove_comment 1 1')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_ticket_comment_remove_error_no_ticket_argument(self):
        """Error reported when ticket# argument is missing."""
        rv, output = self.execute('ticket remove_comment')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_ticket_comment_remove_error_no_comment_argument(self):
        """Error reported when comment# argument is missing."""
        ticket = insert_ticket(self.env)
        rv, output = self.execute('ticket remove_comment 1')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_ticket_comment_remove_error_ticket_id_not_an_int(self):
        """ResourceNotFound error reported when comment does not exist."""
        ticket = insert_ticket(self.env)
        ticket.save_changes('user1', 'the comment')
        rv, output = self.execute('ticket remove_comment a 1')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_ticket_comment_remove_error_comment_id_not_an_int(self):
        """ResourceNotFound error reported when comment does not exist."""
        ticket = insert_ticket(self.env)
        ticket.save_changes('user1', 'the comment')
        rv, output = self.execute('ticket remove_comment 1 a')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_ticket_comment_remove_error_invalid_ticket_id(self):
        """ResourceNotFound error reported when ticket does not exist."""
        ticket = insert_ticket(self.env)
        ticket.save_changes('user1', 'the comment')
        rv, output = self.execute('ticket remove_comment 2 1')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_ticket_comment_remove_error_invalid_comment_id(self):
        """ResourceNotFound error reported when comment does not exist."""
        ticket = insert_ticket(self.env)
        ticket.save_changes('user1', 'the comment')
        rv, output = self.execute('ticket remove_comment 1 2')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_ticket_type_list_ok(self):
        """
        Tests the 'ticket_type list' command in trac-admin.  Since this command
        has no command arguments, it is hard to call it incorrectly.  As
        a result, there is only this one test.
        """
        rv, output = self.execute('ticket_type list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_ticket_type_add_ok(self):
        """
        Tests the 'ticket_type add' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """
        self.execute('ticket_type add new_type')
        rv, output = self.execute('ticket_type list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_ticket_type_add_error_already_exists(self):
        """
        Tests the 'ticket_type add' command in trac-admin.  This particular
        test passes a ticket type that already exists and checks for an error
        message.
        """
        rv, output = self.execute('ticket_type add defect')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_ticket_type_change_ok(self):
        """
        Tests the 'ticket_type change' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        self.execute('ticket_type change defect bug')
        rv, output = self.execute('ticket_type list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_ticket_type_change_error_bad_type(self):
        """
        Tests the 'ticket_type change' command in trac-admin.  This particular
        test tries to change a priority that does not exist.
        """
        rv, output = self.execute('ticket_type change bad_type changed_type')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_ticket_type_change_error_bad_new_name(self):
        """
        Tests the 'ticket_type change' command in trac-admin.  This particular
        test tries to change a ticket type to another type that already exists.
        """
        rv, output = self.execute('ticket_type change defect task')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_ticket_type_remove_ok(self):
        """
        Tests the 'ticket_type remove' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """
        self.execute('ticket_type remove task')
        rv, output = self.execute('ticket_type list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_ticket_type_remove_error_bad_type(self):
        """
        Tests the 'ticket_type remove' command in trac-admin.  This particular
        test tries to remove a ticket type that does not exist.
        """
        rv, output = self.execute('ticket_type remove bad_type')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_ticket_type_order_down_ok(self):
        """
        Tests the 'ticket_type order' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """
        self.execute('ticket_type order defect down')
        rv, output = self.execute('ticket_type list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_ticket_type_order_up_ok(self):
        """
        Tests the 'ticket_type order' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """
        self.execute('ticket_type order enhancement up')
        rv, output = self.execute('ticket_type list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_ticket_type_order_error_bad_type(self):
        """
        Tests the 'priority order' command in trac-admin.  This particular
        test tries to reorder a priority that does not exist.
        """
        rv, output = self.execute('ticket_type order bad_type up')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_priority_help(self):
        rv, output = self.execute('help priority')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_priority_list_ok(self):
        """
        Tests the 'priority list' command in trac-admin.  Since this command
        has no command arguments, it is hard to call it incorrectly.  As
        a result, there is only this one test.
        """
        rv, output = self.execute('priority list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_priority_add_ok(self):
        """
        Tests the 'priority add' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """
        self.execute('priority add new_priority')
        rv, output = self.execute('priority list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_priority_add_many_ok(self):
        """
        Tests adding more than 10 priority values.  This makes sure that
        ordering is preserved when adding more than 10 values.
        """
        for i in xrange(11):
            self.execute('priority add p%s' % i)
        rv, output = self.execute('priority list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_priority_add_error_already_exists(self):
        """
        Tests the 'priority add' command in trac-admin.  This particular
        test passes a priority name that already exists and checks for an
        error message.
        """
        rv, output = self.execute('priority add blocker')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_priority_change_ok(self):
        """
        Tests the 'priority change' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        self.execute('priority change major normal')
        rv, output = self.execute('priority list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_priority_change_error_bad_priority(self):
        """
        Tests the 'priority change' command in trac-admin.  This particular
        test tries to change a priority that does not exist.
        """
        rv, output = self.execute('priority change bad_priority changed_name')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_priority_change_error_bad_new_name(self):
        """
        Tests the 'priority change' command in trac-admin.  This particular
        test tries to change a priority to a name that already exists.
        """
        rv, output = self.execute('priority change major minor')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_priority_remove_ok(self):
        """
        Tests the 'priority remove' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """
        self.execute('priority remove major')
        rv, output = self.execute('priority list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_priority_remove_error_bad_priority(self):
        """
        Tests the 'priority remove' command in trac-admin.  This particular
        test tries to remove a priority that does not exist.
        """
        rv, output = self.execute('priority remove bad_priority')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_priority_order_down_ok(self):
        """
        Tests the 'priority order' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """
        self.execute('priority order blocker down')
        rv, output = self.execute('priority list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_priority_order_up_ok(self):
        """
        Tests the 'priority order' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """
        self.execute('priority order critical up')
        rv, output = self.execute('priority list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_priority_order_error_bad_priority(self):
        """
        Tests the 'priority order' command in trac-admin.  This particular
        test tries to reorder a priority that does not exist.
        """
        rv, output = self.execute('priority remove bad_priority')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_severity_help(self):
        rv, output = self.execute('help severity')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_severity_list_ok(self):
        """
        Tests the 'severity list' command in trac-admin.  Since this command
        has no command arguments, it is hard to call it incorrectly.  As
        a result, there is only this one test.
        """
        rv, output = self.execute('severity list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_severity_add_ok(self):
        """
        Tests the 'severity add' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """
        self.execute('severity add new_severity')
        rv, output = self.execute('severity list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_severity_add_error_already_exists(self):
        """
        Tests the 'severity add' command in trac-admin.  This particular
        test passes a severity name that already exists and checks for an
        error message.
        """
        self.execute('severity add blocker')
        rv, output = self.execute('severity add blocker')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_severity_change_ok(self):
        """
        Tests the 'severity add' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        self.execute('severity add critical')
        self.execute('severity change critical "end-of-the-world"')
        rv, output = self.execute('severity list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_severity_change_error_bad_severity(self):
        """
        Tests the 'severity change' command in trac-admin.  This particular
        test tries to change a severity that does not exist.
        """
        rv, output = self.execute(
            'severity change bad_severity changed_name')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_severity_change_error_bad_new_name(self):
        """
        Tests the 'severity change' command in trac-admin.  This particular
        test tries to change a severity to a name that already exists.
        """
        self.execute('severity add major')
        self.execute('severity add critical')
        rv, output = self.execute('severity change critical major')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_severity_remove_ok(self):
        """
        Tests the 'severity add' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """
        self.execute('severity remove trivial')
        rv, output = self.execute('severity list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_severity_remove_error_bad_severity(self):
        """
        Tests the 'severity remove' command in trac-admin.  This particular
        test tries to remove a severity that does not exist.
        """
        rv, output = self.execute('severity remove bad_severity')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_severity_order_down_ok(self):
        """
        Tests the 'severity order' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """
        self.execute('severity add foo')
        self.execute('severity add bar')
        self.execute('severity order foo down')
        rv, output = self.execute('severity list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_severity_order_up_ok(self):
        """
        Tests the 'severity order' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """
        self.execute('severity add foo')
        self.execute('severity add bar')
        self.execute('severity order bar up')
        rv, output = self.execute('severity list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_severity_order_error_bad_severity(self):
        """
        Tests the 'severity order' command in trac-admin.  This particular
        test tries to reorder a priority that does not exist.
        """
        rv, output = self.execute('severity remove bad_severity')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_help_version_time(self):
        doc = self.get_command_help('version', 'time')
        self.assertIn(self.datetime_format_hint, doc)
        self.assertIn(u'"YYYY-MM-DDThh:mm:ss±hh:mm"', doc)

    def test_version_help(self):
        rv, output = self.execute('help version')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_version_list_ok(self):
        """
        Tests the 'version list' command in trac-admin.  Since this command
        has no command arguments, it is hard to call it incorrectly.  As
        a result, there is only this one test.
        """
        rv, output = self.execute('version list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_version_add_ok(self):
        """
        Tests the 'version add' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        self.execute('version add 9.9 "%s"' % self._test_date)
        rv, output = self.execute('version list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_version_add_too_many_arguments(self):
        rv, output = self.execute('version add 7.7 8.8 9.9')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_version_add_error_already_exists(self):
        """
        Tests the 'version add' command in trac-admin.  This particular
        test passes a version name that already exists and checks for an
        error message.
        """
        rv, output = self.execute(
            'version add 1.0 "%s"' % self._test_date)
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_version_rename_ok(self):
        """
        Tests the 'version rename' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        self.execute('version rename 1.0 9.9')
        rv, output = self.execute('version list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_version_rename_error_bad_version(self):
        """
        Tests the 'version rename' command in trac-admin.  This particular
        test tries to rename a version that does not exist.
        """
        rv, output = self.execute(
            'version rename bad_version changed_name')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_version_rename_error_bad_new_name(self):
        """
        Tests the 'version rename' command in trac-admin.  This particular
        test tries to rename a version to a name that already exists.
        """
        rv, output = self.execute('version rename 1.0 2.0')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_version_time_ok(self):
        """
        Tests the 'version time' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        self.execute('version time 2.0 "%s"' % self._test_date)
        rv, output = self.execute('version list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_version_time_unset_ok(self):
        """
        Tests the 'version time' command in trac-admin.  This particular
        test passes valid arguments for unsetting the date.
        """
        self.execute('version time 2.0 "%s"' % self._test_date)
        self.execute('version time 2.0 ""')
        rv, output = self.execute('version list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_version_time_error_bad_version(self):
        """
        Tests the 'version time' command in trac-admin.  This particular
        test tries to change the time on a version that does not exist.
        """
        rv, output = self.execute('version time bad_version "%s"'
                                  % self._test_date)
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_version_remove_ok(self):
        """
        Tests the 'version remove' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """
        self.execute('version remove 1.0')
        rv, output = self.execute('version list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_version_remove_error_bad_version(self):
        """
        Tests the 'version remove' command in trac-admin.  This particular
        test tries to remove a version that does not exist.
        """
        rv, output = self.execute('version remove bad_version')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_backslash_use_ok(self):
        if self.admin.interactive:
            self.execute('version add \\')
        else:
            self.execute(r"version add '\'")
        rv, output = self.execute('version list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_milestone_help(self):
        rv, output = self.execute('help milestone')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_help_milestone_due(self):
        doc = self.get_command_help('milestone', 'due')
        self.assertIn(self.datetime_format_hint, doc)
        self.assertIn(u'"YYYY-MM-DDThh:mm:ss±hh:mm"', doc)

    def test_help_milestone_completed(self):
        doc = self.get_command_help('milestone', 'completed')
        self.assertIn(self.datetime_format_hint, doc)
        self.assertIn(u'"YYYY-MM-DDThh:mm:ss±hh:mm"', doc)

    def test_milestone_list_ok(self):
        """
        Tests the 'milestone list' command in trac-admin.  Since this command
        has no command arguments, it is hard to call it incorrectly.  As
        a result, there is only this one test.
        """
        rv, output = self.execute('milestone list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_milestone_add_ok(self):
        """
        Tests the 'milestone add' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        self.execute('milestone add new_milestone "%s"' % self._test_date)
        rv, output = self.execute('milestone list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_milestone_add_utf8_ok(self):
        """
        Tests the 'milestone add' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        self.execute(u'milestone add \xa9tat_final "%s"'  # \xc2\xa9
                     % self._test_date)
        rv, output = self.execute('milestone list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_milestone_add_error_already_exists(self):
        """
        Tests the 'milestone add' command in trac-admin.  This particular
        test passes a milestone name that already exists and checks for an
        error message.
        """
        rv, output = self.execute('milestone add milestone1 "%s"'
                                  % self._test_date)
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_milestone_add_invalid_date(self):
        rv, output = self.execute('milestone add new_milestone <add>')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output, {
            'hint': self.datetime_format_hint,
            'isohint': get_datetime_format_hint('iso8601')
        })

    def test_milestone_rename_ok(self):
        """
        Tests the 'milestone rename' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        self.execute('milestone rename milestone1 changed_milestone')
        rv, output = self.execute('milestone list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_milestone_rename_error_bad_milestone(self):
        """
        Tests the 'milestone rename' command in trac-admin.  This particular
        test tries to rename a milestone that does not exist.
        """
        rv, output = self.execute(
            'milestone rename bad_milestone changed_name')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_milestone_due_ok(self):
        """
        Tests the 'milestone due' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        self.execute('milestone due milestone2 "%s"' % self._test_date)
        rv, output = self.execute('milestone list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_milestone_due_unset_ok(self):
        """
        Tests the 'milestone due' command in trac-admin.  This particular
        test passes valid arguments for unsetting the due date.
        """
        self.execute('milestone due milestone2 "%s"' % self._test_date)
        self.execute('milestone due milestone2 ""')
        rv, output = self.execute('milestone list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_milestone_due_error_bad_milestone(self):
        """
        Tests the 'milestone due' command in trac-admin.  This particular
        test tries to change the due date on a milestone that does not exist.
        """
        rv, output = self.execute('milestone due bad_milestone "%s"'
                                  % self._test_date)
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_milestone_due_invalid_date(self):
        rv, output = self.execute('milestone due milestone1 <due>')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output, {
            'hint': self.datetime_format_hint,
            'isohint': get_datetime_format_hint('iso8601')
        })

    def test_milestone_completed_ok(self):
        """
        Tests the 'milestone completed' command in trac-admin.  This particular
        test passes valid arguments and checks for success.
        """
        self.execute(
            'milestone completed milestone2 "%s"' % self._test_date)
        rv, output = self.execute('milestone list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_milestone_completed_error_bad_milestone(self):
        """
        Tests the 'milestone completed' command in trac-admin.  This particular
        test tries to change the completed date on a milestone that does not
        exist.
        """
        rv, output = self.execute('milestone completed bad_milestone "%s"'
                                  % self._test_date)
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)

    def test_milestone_completed_invalid_date(self):
        rv, output = self.execute('milestone completed milestone1 <com>')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output, {
            'hint': self.datetime_format_hint,
            'isohint': get_datetime_format_hint('iso8601')
        })

    def test_milestone_remove_ok(self):
        """
        Tests the 'milestone remove' command in trac-admin.  This particular
        test passes a valid argument and checks for success.
        """
        self.execute('milestone remove milestone3')
        rv, output = self.execute('milestone list')
        self.assertEqual(0, rv, output)
        self.assertExpectedResult(output)

    def test_milestone_remove_error_bad_milestone(self):
        """
        Tests the 'milestone remove' command in trac-admin.  This particular
        test tries to remove a milestone that does not exist.
        """
        rv, output = self.execute('milestone remove bad_milestone')
        self.assertEqual(2, rv, output)
        self.assertExpectedResult(output)


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TracAdminTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
