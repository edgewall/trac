#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2008-2020 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

import datetime
import re
import unittest

from trac.admin.tests.functional import AuthorizationTestCaseSetup
from trac.test import locale_en
from trac.tests.contentgen import random_unique_camel
from trac.tests.functional import FunctionalTestCaseSetup, b, \
                                  internal_error, tc
from trac.util.datefmt import datetime_now, format_date, format_datetime, \
                              localtz, utc


class AdminEnumDefaultTestCaseSetup(FunctionalTestCaseSetup):
    def test_default(self, enum, name):
        url = self._tester.url + '/admin/ticket/%s' % enum
        self._tester.go_to_url(url)
        tc.find(name)
        tc.formvalue('enumtable', 'default', name)
        tc.submit('apply')
        tc.url(url)
        tc.find('radio.*checked="checked" value="%s"' % name)
        # Test the "Clear default" button
        self._tester.go_to_url(url)
        tc.submit('clear', formname='enumtable')
        tc.url(url, regexp=False)
        tc.notfind(internal_error)
        tc.find('<input type="radio" name="default" value="%s"/>' % name)
        tc.notfind('type="radio" name="default" checked="checked" value=".+"')


class TestAdminComponent(FunctionalTestCaseSetup):
    def runTest(self):
        """Admin create component"""
        self._tester.create_component()


class TestAdminComponentAuthorization(AuthorizationTestCaseSetup):
    def runTest(self):
        """Check permissions required to access the Ticket Components
        panel."""
        self.test_authorization('/admin/ticket/components', 'TICKET_ADMIN',
                                "Manage Components")


class TestAdminComponentDuplicates(FunctionalTestCaseSetup):
    def runTest(self):
        """Admin create duplicate component"""
        name = self._testenv.add_component()
        self._tester.go_to_url('/admin/ticket/components')
        tc.formvalue('addcomponent', 'name', name)
        tc.submit()
        tc.notfind(internal_error)
        tc.find('Component .* already exists')


class TestAdminComponentRemoval(FunctionalTestCaseSetup):
    def runTest(self):
        """Admin remove component"""
        name = self._testenv.add_component()
        self._tester.go_to_url('/admin/ticket/components')
        tc.formvalue('component_table', 'sel', name)
        tc.submit('remove')
        tc.notfind(name)


class TestAdminComponentNonRemoval(FunctionalTestCaseSetup):
    @tc.javascript_disabled
    def runTest(self):
        """Admin remove no selected component"""
        self._tester.go_to_url('/admin/ticket/components')
        tc.submit('remove', formname='component_table')
        tc.find('No component selected')


class TestAdminComponentDefault(FunctionalTestCaseSetup):
    def runTest(self):
        """Admin set default component"""
        name = self._testenv.add_component()
        self._tester.go_to_url('/admin/ticket/components')
        tc.formvalue('component_table', 'default', name)
        tc.submit('apply')
        tc.find('type="radio" name="default" checked="checked" value="%s"' %
                name)
        self._tester.go_to_url('/newticket')
        tc.find('<option selected="selected" value="%s">%s</option>'
                % (name, name))
        # Test the "Clear default" button
        self._testenv.set_config('ticket', 'allowed_empty_fields', 'component')
        self._tester.go_to_url('/admin/ticket/components')
        tc.submit('clear', formname='component_table')
        tc.notfind('type="radio" name="default" checked="checked" value=".+"')
        self._tester.create_ticket()
        tc.find(r'<th class="missing" id="h_component">\s*Component:\s*</th>'
                r'\s*<td headers="h_component">\s*</td>')
        self._testenv.remove_config('ticket', 'allowed_empty_fields')


class TestAdminComponentDetail(FunctionalTestCaseSetup):
    def runTest(self):
        """Admin component detail"""
        name = self._testenv.add_component()
        self._tester.go_to_url('/admin/ticket/components')
        tc.follow(name)
        desc = 'Some component description'
        tc.formvalue('edit', 'description', desc)
        tc.submit('cancel')
        tc.url(self._tester.url + '/admin/ticket/components', regexp=False)
        tc.follow(name)
        tc.notfind(desc)


class TestAdminComponentNoneDefined(FunctionalTestCaseSetup):
    def runTest(self):
        """The table should be hidden and help text shown when there are no
        components defined (#11103)."""
        from trac.ticket import model
        env = self._testenv.get_trac_environment()
        components = list(model.Component.select(env))
        self._tester.go_to_admin()
        tc.follow(r"\bComponents\b")

        try:
            for comp in components:
                tc.formvalue('component_table', 'sel', comp.name)
            tc.submit('remove')
            tc.notfind('<table class="listing" id="complist">')
            tc.find("As long as you don't add any items to the list, this "
                    "field[ \t\n]*will remain completely hidden from the "
                    "user interface.")
        finally:
            for comp in components:
                name = self._testenv.add_component(comp.name, comp.owner)


class TestAdminMilestone(FunctionalTestCaseSetup):
    def runTest(self):
        """Admin create milestone"""
        name = self._tester.create_milestone()

        # Make sure it's on the roadmap.
        tc.follow(r"\bRoadmap\b")
        tc.url(self._tester.url + '/roadmap', regexp=False)
        tc.find("Milestone:.*%s" % name)
        tc.follow(r"\b%s\b" % name)
        tc.url(self._tester.url + '/milestone/' + name, regexp=False)
        tc.find('No date set')


class TestAdminMilestoneAuthorization(AuthorizationTestCaseSetup):
    def runTest(self):
        """Check permissions required to access the Ticket Milestone
        panel."""
        self.test_authorization('/admin/ticket/milestones', 'TICKET_ADMIN',
                                "Manage Milestones")

        # Test for regression of https://trac.edgewall.org/ticket/11618
        name = self._testenv.add_milestone()
        try:
            self._testenv.grant_perm('user', 'TICKET_ADMIN')
            self._tester.go_to_front()
            self._tester.logout()
            self._tester.login('user')
            self._tester.go_to_url('/admin/ticket/milestones/' + name)
            tc.notfind('No administration panels available')
            tc.find(' readonly="readonly"')
            tc.notfind(' readonly="True"')
        finally:
            self._testenv.revoke_perm('user', 'TICKET_ADMIN')
            self._tester.go_to_front()
            self._tester.logout()
            self._tester.login('admin')


class TestAdminMilestoneSpace(FunctionalTestCaseSetup):
    def runTest(self):
        """Admin create milestone with a space"""
        self._tester.create_milestone('Milestone 1')


class TestAdminMilestoneDuplicates(FunctionalTestCaseSetup):
    def runTest(self):
        """Admin create duplicate milestone"""
        name = self._testenv.add_milestone()
        self._tester.go_to_url(self._tester.url + "/admin/ticket/milestones")
        tc.formvalue('addmilestone', 'name', name)
        tc.submit()
        tc.notfind(internal_error)
        tc.find('Milestone "%s" already exists, please choose '
                'another name.' % name)
        tc.notfind('%s')


class TestAdminMilestoneListing(FunctionalTestCaseSetup):
    def runTest(self):
        """Admin milestone listing."""
        name1 = self._testenv.add_milestone()
        self._tester.create_ticket(info={'milestone': name1})
        name2 = self._testenv.add_milestone()

        milestone_url = self._tester.url + '/admin/ticket/milestones'
        self._tester.go_to_url(milestone_url)
        tc.find(r'<a href="/admin/ticket/milestones/%(name)s">%(name)s</a>'
                % {'name': name1})
        m1_query_link = r'<a href="/query\?group=status&amp;' \
                        r'milestone=%(name)s">1</a>' % {'name': name1}
        tc.find(m1_query_link)
        tc.find(r'<a href="/admin/ticket/milestones/%(name)s">%(name)s</a>'
                % {'name': name2})
        tc.notfind(r'<a href="/query\?group=status&amp;milestone=%(name)s">'
                   r'0</a>' % {'name': name2})

        apply_submit = '<input type="submit" name="apply" ' \
                       'value="Apply changes" />'
        clear_submit = '<input type="submit"[ \t\n]+title="Clear default ' \
                       'ticket milestone and default retargeting milestone"' \
                       '[ \t\n]+name="clear" value="Clear defaults" />'
        tc.find(apply_submit)
        tc.find(clear_submit)
        tc.find('<input type="radio" name="ticket_default" value="%(name)s"/>'
                % {'name': name1})
        tc.find('<input type="radio" name="retarget_default" value="%(name)s"/>'
                % {'name': name1})

        # TICKET_ADMIN is required to change the ticket default and retarget
        # default configuration options. TICKET_VIEW is required for the
        # milestone tickets query link to be present.
        try:
            self._testenv.grant_perm('user', 'MILESTONE_ADMIN')
            self._testenv.revoke_perm('anonymous', 'TICKET_VIEW')
            self._tester.go_to_front()
            self._tester.logout()
            self._tester.login('user')
            self._tester.go_to_url(milestone_url)
            tc.notfind(apply_submit)
            tc.notfind(clear_submit)
            tc.find('<input type="radio" name="ticket_default" '
                    'disabled="disabled" value="%(name)s"/>' % {'name': name1})
            tc.find('<input type="radio" name="retarget_default" '
                    'disabled="disabled" value="%(name)s"/>' % {'name': name1})
            tc.notfind(m1_query_link)
        finally:
            self._testenv.revoke_perm('user', 'MILESTONE_ADMIN')
            self._testenv.grant_perm('anonymous', 'TICKET_VIEW')
            self._tester.logout()
            self._tester.login('admin')


class TestAdminMilestoneDetail(FunctionalTestCaseSetup):
    def runTest(self):
        """Admin modify milestone details"""
        name = self._testenv.add_milestone()

        milestone_url = self._tester.url + '/admin/ticket/milestones'
        def go_to_milestone_detail():
            self._tester.go_to_url(milestone_url)
            tc.follow(name)
            tc.url(milestone_url + '/' + name, regexp=False)

        # Modify the details of the milestone
        go_to_milestone_detail()
        tc.formvalue('edit', 'due', True)
        tc.formvalue('edit', 'description', 'Some description.')
        tc.submit('save')
        tc.url(milestone_url, regexp=False)

        # Milestone is not closed
        self._tester.go_to_roadmap()
        tc.find(name)

        # Cancel more modifications and modification are not saved
        go_to_milestone_detail()
        tc.formvalue('edit', 'description', '~~Some other description.~~')
        tc.submit('cancel')
        tc.url(milestone_url, regexp=False)
        self._tester.go_to_roadmap()
        tc.find('Some description.')
        tc.follow(name)
        tc.find('Some description.')

        # Milestone is readonly when user doesn't have MILESTONE_MODIFY
        self._tester.logout()
        self._testenv.grant_perm('user', 'TICKET_ADMIN')
        self._tester.login('user')
        go_to_milestone_detail()
        try:
            tc.find(r'<input[^>]+id="name"[^>]+readonly="readonly"')
            tc.find(r'<input[^>]+id="due"[^>]+disabled="disabled"')
            tc.find(r'<input[^>]+id="duedate"[^>]+readonly="readonly"')
            tc.find(r'<input[^>]+id="completed"[^>]+disabled="disabled"')
            tc.find(r'<input[^>]+id="completeddate"[^>]+readonly="readonly"')
            tc.find(r'<textarea[^>]+id="description"[^>]+readonly="readonly"')
            tc.find(r'<input[^>]+name="save"[^>]+disabled="disabled"')
            tc.submit('cancel', 'edit')
            tc.url(milestone_url, regexp=False)
        finally:
            self._tester.logout()
            self._testenv.revoke_perm('user', 'TICKET_ADMIN')
            self._tester.login('admin')


class TestAdminMilestoneDue(FunctionalTestCaseSetup):
    def runTest(self):
        """Admin milestone duedate"""
        duedate = datetime_now(tz=utc)
        duedate_string = format_datetime(duedate, tzinfo=utc,
                                         locale=locale_en)
        self._tester.create_milestone(due=duedate_string)
        tc.find(duedate_string)


class TestAdminMilestoneDetailDue(FunctionalTestCaseSetup):
    def runTest(self):
        """Admin modify milestone duedate on detail page"""
        name = self._testenv.add_milestone()

        # Modify the details of the milestone
        milestone_url = self._tester.url + "/admin/ticket/milestones"
        self._tester.go_to_url(milestone_url)
        tc.follow(name)
        tc.url(milestone_url + '/' + name, regexp=False)
        duedate = datetime_now(tz=utc)
        duedate_string = format_datetime(duedate, tzinfo=utc,
                                         locale=locale_en)
        tc.formvalue('edit', 'due', True)
        tc.formvalue('edit', 'duedate', duedate_string)
        tc.submit('save')
        tc.url(milestone_url, regexp=False)
        tc.find(name + '(<[^>]*>|\\s)*'+ duedate_string, 's')


class TestAdminMilestoneDetailRename(FunctionalTestCaseSetup):
    def runTest(self):
        """Admin rename milestone"""
        name1 = self._testenv.add_milestone()
        name2 = random_unique_camel()
        tid = self._tester.create_ticket(info={'milestone': name1})
        milestone_url = self._tester.url + '/admin/ticket/milestones'

        self._tester.go_to_url(milestone_url)
        tc.follow(name1)
        tc.url(milestone_url + '/' + name1, regexp=False)
        tc.formvalue('edit', 'name', name2)
        tc.submit('save')

        tc.find(r"Your changes have been saved\.")
        tc.find(r"\b%s\b" % name2)
        tc.notfind(r"\b%s\b" % name1)
        self._tester.go_to_ticket(tid)
        tc.find('<a class="milestone" href="/milestone/%(name)s" '
                'title="No date set">%(name)s</a>' % {'name': name2})
        tc.find('<th class="trac-field-milestone">Milestone:</th>[ \t\n]+'
                '<td>[ \t\n]+<span class="trac-field-old">%s</span>'
                '[ \t\n]+→[ \t\n]+'
                '<span class="trac-field-new">%s</span>[ \t\n]+</td>'
                % (name1, name2))
        tc.find("Milestone renamed")


class TestAdminMilestoneCompleted(FunctionalTestCaseSetup):
    def runTest(self):
        """Admin milestone completed"""
        name = self._testenv.add_milestone()
        milestone_url = self._tester.url + "/admin/ticket/milestones"
        self._tester.go_to_url(milestone_url)
        tc.follow(name)
        tc.url(milestone_url + '/' + name, regexp=False)
        tc.formvalue('edit', 'completed', True)
        tc.submit('save')
        tc.url(milestone_url, regexp=False)


class TestAdminMilestoneCompletedFuture(FunctionalTestCaseSetup):
    def runTest(self):
        """Admin milestone completed in the future"""
        name = self._testenv.add_milestone()
        milestone_url = self._tester.url + "/admin/ticket/milestones"
        self._tester.go_to_url(milestone_url)
        tc.follow(name)
        tc.url(milestone_url + '/' + name, regexp=False)
        tc.formvalue('edit', 'completed', True)
        cdate = datetime_now(tz=utc) + datetime.timedelta(days=2)
        cdate_string = format_date(cdate, tzinfo=localtz, locale=locale_en)
        tc.formvalue('edit', 'completeddate', cdate_string)
        tc.submit('save')
        tc.find('Completion date may not be in the future')
        # And make sure it wasn't marked as completed.
        self._tester.go_to_roadmap()
        tc.find(name)


class TestAdminMilestoneCompletedRetarget(FunctionalTestCaseSetup):
    """Admin milestone completed and verify that tickets are retargeted
    to the selected milestone"""
    def runTest(self):
        name = self._testenv.add_milestone()
        tid1 = self._tester.create_ticket(info={'milestone': name})
        tc.click('#propertyform .collapsed .foldable a')
        tc.formvalue('propertyform', 'action', 'resolve')
        tc.formvalue('propertyform',
                     'action_resolve_resolve_resolution', 'fixed')
        tc.submit('submit')

        # Check that hint is shown when there are no open tickets to retarget
        milestone_url = self._tester.url + "/admin/ticket/milestones/" + name
        self._tester.go_to_url(milestone_url)
        tc.find("There are no open tickets associated with this milestone.")

        retarget_to = self._testenv.add_milestone()

        # Check that open tickets retargeted, closed not retargeted
        tid2 = self._tester.create_ticket(info={'milestone': name})
        self._tester.go_to_url(milestone_url)
        completed = format_datetime(
            datetime_now(tz=utc) - datetime.timedelta(hours=1),
            tzinfo=localtz, locale=locale_en)
        tc.formvalue('edit', 'completed', True)
        tc.formvalue('edit', 'completeddate', completed)
        tc.formvalue('edit', 'target', retarget_to)
        tc.submit('save')

        tc.url(self._tester.url + '/admin/ticket/milestones')
        tc.find('The open tickets associated with milestone "%s" '
                'have been retargeted to milestone "%s".'
                % (name, retarget_to))
        tc.find("Completed")

        # Closed ticket will not be retargeted.
        self._tester.go_to_ticket(tid1)
        tc.find('<a class="closed milestone" href="/milestone/%(name)s" '
                'title="Completed .+ ago (.+)">%(name)s</a>'
                % {'name': name})
        tc.notfind('changed from <em>%s</em> to <em>%s</em>'
                   % (name, retarget_to))
        tc.notfind("Ticket retargeted after milestone closed")
        # Open ticket will be retargeted.
        self._tester.go_to_ticket(tid2)
        tc.find('<a class="milestone" href="/milestone/%(name)s" '
                'title="No date set">%(name)s</a>' % {'name': retarget_to})
        tc.find('<span class="trac-field-old">%s</span>'
                '[ \n]+→[ \n]+'
                '<span class="trac-field-new">%s</span>'
                % (name, retarget_to))
        tc.find("Ticket retargeted after milestone closed")


class TestAdminMilestoneRemove(FunctionalTestCaseSetup):
    def runTest(self):
        """Admin remove milestone"""
        name = self._testenv.add_milestone()
        tid = self._tester.create_ticket(info={'milestone': name})
        milestone_url = self._tester.url + '/admin/ticket/milestones'

        self._tester.go_to_url(milestone_url)
        tc.formvalue('milestone_table', 'sel', name)
        tc.submit('remove')

        tc.url(milestone_url, regexp=False)
        tc.notfind(name)
        self._tester.go_to_ticket(tid)
        tc.find('<th class="missing" id="h_milestone">'
                '[ \t\n]*Milestone:[ \t\n]*</th>')
        tc.find('<th class="trac-field-milestone">Milestone:</th>[ \t\n]+'
                '<td>[ \t\n]+'
                '<span class="trac-field-deleted">%s</span>'
                '[ \t\n]+</td>' % name)
        tc.find("Milestone deleted")


class TestAdminMilestoneRemoveMulti(FunctionalTestCaseSetup):
    def runTest(self):
        """Admin remove multiple milestones"""
        name = []
        count = 3
        for i in range(count):
            name.append(self._testenv.add_milestone())
        milestone_url = self._tester.url + '/admin/ticket/milestones'
        self._tester.go_to_url(milestone_url)
        for i in range(count):
            tc.find(name[i])
        for i in range(count):
            tc.formvalue('milestone_table', 'sel', name[i])
        tc.submit('remove')
        tc.url(milestone_url, regexp=False)
        for i in range(count):
            tc.notfind(name[i])


class TestAdminMilestoneNonRemoval(FunctionalTestCaseSetup):
    @tc.javascript_disabled
    def runTest(self):
        """Admin remove no selected milestone"""
        self._tester.go_to_url('/admin/ticket/milestones')
        tc.submit('remove', formname='milestone_table')
        tc.find('No milestone selected')


class TestAdminMilestoneDefaults(FunctionalTestCaseSetup):
    def runTest(self):
        """Admin set default ticket milestone, default retarget milestone
        and clear defaults."""
        def clear_defaults():
            # Test the "Clear default" button
            self._tester.go_to_url(milestone_url)
            tc.submit('clear', formname='milestone_table')
            tc.notfind('type="radio" name="ticket_default" '
                       'checked="checked" value=".+"')
            tc.notfind('type="radio" name="retarget_default" '
                       'checked="checked value=".+""')
            self._tester.go_to_ticket(tid)
            tc.find('<th class="missing" id="h_milestone">[ \t\n]+'
                    'Milestone:[ \t\n]+</th>[ \t\n]+'
                    '(?!<td headers="h_milestone">)')
            self._tester.go_to_milestone(mid2)
            tc.submit(formname='deletemilestone')
            tc.notfind('<option selected="selected" value="%s">%s</option>'
                       % (mid1, mid1))

        milestone_url = self._tester.url + "/admin/ticket/milestones"
        tid = self._tester.create_ticket()
        mid1 = self._testenv.add_milestone()
        mid2 = self._testenv.add_milestone()
        self._tester.create_ticket(info={'milestone': mid2})

        # Set default ticket milestone
        self._tester.go_to_url(milestone_url)
        tc.formvalue('milestone_table', 'ticket_default', mid1)
        tc.submit('apply')
        tc.find('type="radio" name="ticket_default"'
                ' checked="checked" value="%s"' % mid1)
        tc.notfind('type="radio" name="retarget_default"'
                   ' checked="checked" value=".+"')
        # verify it is the default on the newticket page.
        self._tester.go_to_url('/newticket')
        tc.find('<option selected="selected" value="%s">%s</option>'
                % (mid1, mid1))
        clear_defaults()

        # Set default retarget to milestone
        self._tester.go_to_url(milestone_url)
        tc.formvalue('milestone_table', 'retarget_default', mid1)
        tc.submit('apply')
        tc.find('type="radio" name="retarget_default"'
                ' checked="checked" value="%s"' % mid1)
        tc.notfind('type="radio" name="ticket_default"'
                   ' checked="checked" value=".+"')
        # verify it is the default on the confirm delete page.
        self._tester.go_to_milestone(mid2)
        tc.submit(formname='deletemilestone')
        tc.find('<option selected="selected" value="%s">%s</option>'
                % (mid1, mid1))
        clear_defaults()

        # Set both
        self._tester.go_to_url(milestone_url)
        tc.formvalue('milestone_table', 'ticket_default', mid1)
        tc.formvalue('milestone_table', 'retarget_default', mid1)
        tc.submit('apply')
        tc.find('type="radio" name="ticket_default"'
                ' checked="checked" value="%s"' % mid1)
        tc.find('type="radio" name="retarget_default"'
                ' checked="checked" value="%s"' % mid1)
        # verify it is the default on the newticket page.
        self._tester.go_to_url('/newticket')
        tc.find('<option selected="selected" value="%s">%s</option>'
                % (mid1, mid1))
        # verify it is the default on the confirm delete page.
        self._tester.go_to_milestone(mid2)
        tc.submit(formname='deletemilestone')
        tc.find('<option selected="selected" value="%s">%s</option>'
                % (mid1, mid1))
        clear_defaults()

        #Set neither
        self._tester.go_to_url(milestone_url)
        tc.submit('apply', formname='milestone_table')
        tc.notfind('type="radio" name="retarget_default"'
                   ' checked="checked" value=".+"')
        tc.notfind('type="radio" name="ticket_default"'
                   ' checked="checked" value=".+"')
        # verify no default on the newticket page.
        self._tester.go_to_url('/newticket')
        tc.find('<th class="missing" id="h_milestone">[ \t\n]+'
                'Milestone:[ \t\n]+</th>[ \t\n]+'
                '(?!<td headers="h_milestone">)')
        # verify none selected on the confirm delete page.
        self._tester.go_to_milestone(mid2)
        tc.submit(formname='deletemilestone')
        tc.notfind('<option selected="selected" value="%s">%s</option>'
                   % (mid1, mid1))


class TestAdminPriority(FunctionalTestCaseSetup):
    def runTest(self):
        """Admin create priority"""
        self._tester.create_priority()


class TestAdminPriorityAuthorization(AuthorizationTestCaseSetup):
    def runTest(self):
        """Check permissions required to access the Ticket Priority
        panel."""
        self.test_authorization('/admin/ticket/priority', 'TICKET_ADMIN',
                                "Manage Priorities")


class TestAdminPriorityDuplicates(FunctionalTestCaseSetup):
    def runTest(self):
        """Admin create duplicate priority"""
        name = self._testenv.add_priority()
        self._tester.go_to_url('/admin/ticket/priority')
        self._tester.create_priority(name)
        tc.find('Priority %s already exists' % name)


class TestAdminPriorityModify(FunctionalTestCaseSetup):
    def runTest(self):
        """Admin modify priority"""
        name = self._testenv.add_priority()
        self._tester.go_to_url('/admin/ticket/priority')
        tc.find(name)
        tc.follow(name)
        tc.formvalue('edit', 'name', name * 2)
        tc.submit('save')
        priority_url = self._tester.url + '/admin/ticket/priority'
        tc.url(priority_url, regexp=False)
        tc.find(name * 2)


class TestAdminPriorityRemove(FunctionalTestCaseSetup):
    def runTest(self):
        """Admin remove priority"""
        name = self._testenv.add_priority()
        self._tester.go_to_url('/admin/ticket/priority')
        tc.find(name)
        tc.formvalue('enumtable', 'sel', name)
        tc.submit('remove')
        priority_url = self._tester.url + '/admin/ticket/priority'
        tc.url(priority_url, regexp=False)
        tc.notfind(name)


class TestAdminPriorityRemoveMulti(FunctionalTestCaseSetup):
    def runTest(self):
        """Admin remove multiple priorities"""
        name = []
        count = 3
        for i in range(count):
            name.append(self._testenv.add_priority())
        self._tester.go_to_url('/admin/ticket/priority')
        for i in range(count):
            tc.find(name[i])
        for i in range(count):
            tc.formvalue('enumtable', 'sel', name[i])
        tc.submit('remove')
        priority_url = self._tester.url + '/admin/ticket/priority'
        tc.url(priority_url, regexp=False)
        for i in range(count):
            tc.notfind(name[i])


class TestAdminPriorityNonRemoval(FunctionalTestCaseSetup):
    @tc.javascript_disabled
    def runTest(self):
        """Admin remove no selected priority"""
        name = self._testenv.add_priority()
        self._tester.go_to_url('/admin/ticket/priority')
        tc.submit('remove', formname='enumtable')
        tc.find('No priority selected')


class TestAdminPriorityDefault(AdminEnumDefaultTestCaseSetup):
    def runTest(self):
        """Admin default priority"""
        name = self._testenv.add_priority()
        self.test_default('priority', name)


class TestAdminPriorityDetail(FunctionalTestCaseSetup):
    def runTest(self):
        """Admin modify priority details"""
        name1 = self._testenv.add_priority()
        self._tester.go_to_url('/admin/ticket/priority')

        # Modify the details of the priority
        tc.follow(name1)
        priority_url = self._tester.url + "/admin/ticket/priority"
        tc.url(priority_url + '/' + name1, regexp=False)
        name2 = random_unique_camel()
        tc.formvalue('edit', 'name', name2)
        tc.submit('save')
        tc.url(priority_url, regexp=False)

        # Cancel more modifications
        self._tester.go_to_url(priority_url)
        tc.follow(name2)
        name3 = random_unique_camel()
        tc.formvalue('edit', 'name', name3)
        tc.submit('cancel')
        tc.url(priority_url, regexp=False)

        # Verify that only the correct modifications show up
        tc.notfind(name1)
        tc.find(name2)
        tc.notfind(name3)


class TestAdminPriorityRenumber(FunctionalTestCaseSetup):
    def runTest(self):
        """Admin renumber priorities"""
        valuesRE = re.compile(b'<select name="value_([0-9]+)">', re.M)
        html = b.get_html()
        max_priority = max([int(x) for x in valuesRE.findall(html)])

        name = "RenumberPriority"
        self._testenv.add_priority(name + '1')
        self._testenv.add_priority(name + '2')
        self._tester.go_to_url('/admin/ticket/priority')
        tc.find(name + '1')
        tc.find(name + '2')
        tc.formvalue('enumtable',
                     'value_%s' % (max_priority + 1), str(max_priority + 2))
        tc.formvalue('enumtable',
                     'value_%s' % (max_priority + 2), str(max_priority + 1))
        tc.submit('apply')
        priority_url = self._tester.url + '/admin/ticket/priority'
        tc.url(priority_url, regexp=False)
        # Verify that their order has changed.
        tc.find(name + '2.*' + name + '1', 's')


class TestAdminPriorityRenumberDup(FunctionalTestCaseSetup):
    @tc.javascript_disabled
    def runTest(self):
        """Admin badly renumber priorities"""
        # Make the first priority the 2nd priority, and leave the 2nd priority
        # as the 2nd priority.
        priority_url = self._tester.url + '/admin/ticket/priority'
        self._tester.go_to_url(priority_url)
        tc.formvalue('enumtable', 'value_1', '2')
        tc.submit('apply')
        tc.url(priority_url + '#', regexp=False)
        tc.find('Order numbers must be unique')


class TestAdminResolution(FunctionalTestCaseSetup):
    def runTest(self):
        """Admin create resolution"""
        self._tester.create_resolution()


class TestAdminResolutionAuthorization(AuthorizationTestCaseSetup):
    def runTest(self):
        """Check permissions required to access the Ticket Resolutions
        panel."""
        self.test_authorization('/admin/ticket/resolution', 'TICKET_ADMIN',
                                "Manage Resolutions")


class TestAdminResolutionDuplicates(FunctionalTestCaseSetup):
    def runTest(self):
        """Admin create duplicate resolution"""
        name = self._testenv.add_resolution()
        self._tester.create_resolution(name)
        tc.find(re.escape('Resolution value &#34;%s&#34; already exists' %
                          name))


class TestAdminResolutionDefault(AdminEnumDefaultTestCaseSetup):
    def runTest(self):
        """Admin default resolution"""
        name = self._testenv.add_resolution()
        self.test_default('resolution', name)


class TestAdminSeverity(FunctionalTestCaseSetup):
    def runTest(self):
        """Admin create severity"""
        self._tester.create_severity()


class TestAdminSeverityAuthorization(AuthorizationTestCaseSetup):
    def runTest(self):
        """Check permissions required to access the Ticket Severities
        panel."""
        self.test_authorization('/admin/ticket/severity', 'TICKET_ADMIN',
                                "Manage Severities")


class TestAdminSeverityDuplicates(FunctionalTestCaseSetup):
    def runTest(self):
        """Admin create duplicate severity"""
        name = self._testenv.add_severity()
        self._tester.create_severity(name)
        tc.find(re.escape('Severity value &#34;%s&#34; already exists' % name))


class TestAdminSeverityDefault(AdminEnumDefaultTestCaseSetup):
    def runTest(self):
        """Admin default severity"""
        name = self._testenv.add_severity()
        self.test_default('severity', name)


class TestAdminType(FunctionalTestCaseSetup):
    def runTest(self):
        """Admin create type"""
        self._tester.create_type()


class TestAdminTypeAuthorization(AuthorizationTestCaseSetup):
    def runTest(self):
        """Check permissions required to access the Ticket Types
        panel."""
        self.test_authorization('/admin/ticket/type', 'TICKET_ADMIN',
                                "Manage Ticket Types")


class TestAdminTypeDuplicates(FunctionalTestCaseSetup):
    def runTest(self):
        """Admin create duplicate type"""
        name = self._testenv.add_ticket_type()
        self._tester.create_type(name)
        tc.find(re.escape('Type value &#34;%s&#34; already exists' % name))


class TestAdminTypeDefault(AdminEnumDefaultTestCaseSetup):
    def runTest(self):
        """Admin default type"""
        name = self._testenv.add_ticket_type()
        self.test_default('type', name)


class TestAdminVersion(FunctionalTestCaseSetup):
    def runTest(self):
        """Admin create version"""
        self._tester.create_version()
        self._tester.create_version(releasetime='')


class TestAdminVersionAuthorization(AuthorizationTestCaseSetup):
    def runTest(self):
        """Check permissions required to access the Versions panel."""
        self.test_authorization('/admin/ticket/versions', 'TICKET_ADMIN',
                                "Manage Versions")


class TestAdminVersionDuplicates(FunctionalTestCaseSetup):
    def runTest(self):
        """Admin create duplicate version"""
        name = self._testenv.add_version()
        self._tester.go_to_url('/admin/ticket/versions')
        tc.formvalue('addversion', 'name', name)
        tc.submit()
        tc.notfind(internal_error)
        tc.find(re.escape('Version &#34;%s&#34; already exists.' % name))


class TestAdminVersionDetail(FunctionalTestCaseSetup):
    # This is somewhat pointless... the only place to find the version
    # description is on the version details page.
    def runTest(self):
        """Admin version details"""
        name = self._testenv.add_version()
        self._tester.go_to_url('/admin/ticket/versions')
        tc.follow(name)

        desc = 'Some version description.'
        tc.formvalue('edit', 'description', desc)
        tc.submit('save')
        tc.url(self._tester.url + "/admin/ticket/versions", regexp=False)
        tc.follow(name)
        tc.find(desc)


class TestAdminVersionDetailTime(FunctionalTestCaseSetup):
    def runTest(self):
        """Admin version detail set time"""
        name = self._testenv.add_version()
        self._tester.go_to_url('/admin/ticket/versions')
        tc.follow(name)

        # Clear value and send ENTER to close the datepicker.
        tc.formvalue('edit', 'time', '')
        tc.send_keys(tc.keys.ESCAPE)  # close datepicker
        tc.wait_for('invisibility_of_element', id='ui-datepicker-div')
        tc.submit('save')
        version_admin = self._tester.url + "/admin/ticket/versions"
        tc.url(version_admin, regexp=False)
        tc.find(name + '(<[^>]*>|\\s)*<[^>]* name="default" value="%s"'
                % name, 's')

        # Empty time value is not automatically populated.
        tc.follow(name)
        tc.find('<input type="text" id="releaseddate"[^>]*value=""')
        tc.submit('save', formname="edit")
        tc.url(version_admin, regexp=False)
        tc.find(name + '(<[^>]*>|\\s)*<[^>]* name="default" value="%s"'
                % name, 's')


class TestAdminVersionDetailCancel(FunctionalTestCaseSetup):
    def runTest(self):
        """Admin version details"""
        name = self._testenv.add_version()
        self._tester.go_to_url('/admin/ticket/versions')
        tc.follow(name)

        desc = 'Some other version description.'
        tc.formvalue('edit', 'description', desc)
        tc.submit('cancel')
        tc.url(self._tester.url + "/admin/ticket/versions", regexp=False)
        tc.follow(name)
        tc.notfind(desc)


class TestAdminVersionRemove(FunctionalTestCaseSetup):
    def runTest(self):
        """Admin remove version"""
        name = self._testenv.add_version()
        self._tester.go_to_url('/admin/ticket/versions')

        tc.find(name)
        tc.formvalue('version_table', 'sel', name)
        tc.submit('remove')
        tc.url(self._tester.url + "/admin/ticket/versions", regexp=False)
        tc.notfind(name)


class TestAdminVersionRemoveMulti(FunctionalTestCaseSetup):
    def runTest(self):
        """Admin remove multiple versions"""
        name = []
        count = 3
        for i in range(count):
            name.append(self._testenv.add_version())
        self._tester.go_to_url('/admin/ticket/versions')
        for i in range(count):
            tc.find(name[i])
        for i in range(count):
            tc.formvalue('version_table', 'sel', name[i])
        tc.submit('remove')
        tc.url(self._tester.url + '/admin/ticket/versions', regexp=False)
        for i in range(count):
            tc.notfind(name[i])


class TestAdminVersionNonRemoval(FunctionalTestCaseSetup):
    @tc.javascript_disabled
    def runTest(self):
        """Admin remove no selected version"""
        self._tester.go_to_url('/admin/ticket/versions')
        tc.submit('remove', formname='version_table')
        tc.find('No version selected')


class TestAdminVersionDefault(FunctionalTestCaseSetup):
    def runTest(self):
        """Admin set default version"""
        name = self._tester.create_version()
        tc.formvalue('version_table', 'default', name)
        tc.submit('apply')
        tc.find('type="radio" name="default" checked="checked" value="%s"' %
                name)
        # verify it is the default on the newticket page.
        self._tester.go_to_url('/newticket')
        tc.find('<option selected="selected" value="%s">%s</option>'
                % (name, name))
        # Test the "Clear default" button
        self._tester.go_to_url('/admin/ticket/versions')
        tc.submit('clear', formname='version_table')
        tc.notfind('type="radio" name="default" checked="checked" value=".+"')
        self._tester.create_ticket()
        tc.find('<th class="missing" id="h_version">[ \t\n]+'
                'Version:[ \t\n]+</th>[ \t\n]+'
                '(?!<td headers="h_version">)')


class TestTicketDefaultValues(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/10772"""
        def find_prop(field, value=None):
            if value and field == 'type':
                tc.find(r'<span class="trac-type">\s*'
                        r'<a href="/query\?status=!closed&amp;'
                        r'type=%(value)s">\s*%(value)s\s*</a>\s*</span>'
                        % {'value': value})
            elif value and field == 'milestone':
                tc.find(r'<td headers="h_milestone">\s*'
                        r'<a class="milestone" href="/milestone/%(value)s" '
                        r'title=".+">\s*%(value)s\s*</a>\s*</td>'
                        % {'value': value})
            elif value:
                if field in ('component', 'priority'):
                    tc.find(r'<td headers="h_%(field)s">\s*'
                            r'<a href="/query\?%(field)s=%(value)s&amp;'
                            r'status=!closed">\s*%(value)s\s*</a>\s*</td>'
                            % {'field': field, 'value': value})
                elif field == 'version':
                    tc.find(r'<td headers="h_%(field)s">\s*'
                            r'<a href="/query\?status=!closed&amp;'
                            r'%(field)s=%(value)s">\s*%(value)s\s*</a>\s*</td>'
                            % {'field': field, 'value': value})
                else:
                    raise AssertionError('Invalid field: %r' % field)
            else:
                tc.find(r'<td headers="h_%(field)s">\s*</td>'
                        % {'field': field})

        self._testenv.set_config('ticket', 'allowed_empty_fields',
                                 'component, milestone, priority, version')

        try:
            self._tester.go_to_admin("Components")
            tc.submit('clear', formname='component_table')
            self._tester.go_to_admin("Milestones")
            tc.submit('clear', formname='milestone_table')
            self._tester.go_to_admin("Versions")
            tc.submit('clear', formname='version_table')
            self._tester.go_to_admin("Priorities")
            tc.formvalue('enumtable', 'default', 'major')
            tc.submit('apply')

            self._tester.create_ticket('ticket summary')

            find_prop('component')
            find_prop('milestone')
            find_prop('priority', 'major')
            find_prop('version')

            self._testenv.set_config('ticket', 'allowed_empty_fields', '')
            self._tester.go_to_admin("Components")
            tc.formvalue('component_table', 'default', 'component2')
            tc.submit('apply')
            self._tester.go_to_admin("Milestones")
            tc.formvalue('milestone_table', 'ticket_default', 'milestone2')
            tc.submit('apply')
            self._tester.go_to_admin("Priorities")
            tc.formvalue('enumtable', 'default', 'minor')
            tc.submit('apply')
            self._tester.go_to_admin("Versions")
            tc.formvalue('version_table', 'default', '2.0')
            tc.submit('apply')
            self._tester.go_to_admin("Ticket Types")
            tc.formvalue('enumtable', 'default', 'task')
            tc.submit('apply')

            self._tester.create_ticket('ticket summary')

            find_prop('component', 'component2')
            find_prop('milestone', 'milestone2')
            find_prop('priority', 'minor')
            find_prop('version', '2.0')
            find_prop('type', 'task')
        finally:
            self._testenv.remove_config('ticket', 'allowed_empty_fields')


def functionalSuite(suite=None):
    if not suite:
        import trac.tests.functional
        suite = trac.tests.functional.functionalSuite()
    suite.addTest(TestAdminComponentNonRemoval())
    suite.addTest(TestAdminComponent())
    suite.addTest(TestAdminComponentAuthorization())
    suite.addTest(TestAdminComponentDuplicates())
    suite.addTest(TestAdminComponentRemoval())
    suite.addTest(TestAdminComponentNonRemoval())
    suite.addTest(TestAdminComponentDefault())
    suite.addTest(TestAdminComponentDetail())
    suite.addTest(TestAdminComponentNoneDefined())
    suite.addTest(TestAdminMilestone())
    suite.addTest(TestAdminMilestoneAuthorization())
    suite.addTest(TestAdminMilestoneSpace())
    suite.addTest(TestAdminMilestoneDuplicates())
    suite.addTest(TestAdminMilestoneListing())
    suite.addTest(TestAdminMilestoneDetail())
    suite.addTest(TestAdminMilestoneDue())
    suite.addTest(TestAdminMilestoneDetailDue())
    suite.addTest(TestAdminMilestoneDetailRename())
    suite.addTest(TestAdminMilestoneCompleted())
    suite.addTest(TestAdminMilestoneCompletedFuture())
    suite.addTest(TestAdminMilestoneCompletedRetarget())
    suite.addTest(TestAdminMilestoneRemove())
    suite.addTest(TestAdminMilestoneRemoveMulti())
    suite.addTest(TestAdminMilestoneNonRemoval())
    suite.addTest(TestAdminMilestoneDefaults())
    suite.addTest(TestAdminPriority())
    suite.addTest(TestAdminPriorityAuthorization())
    suite.addTest(TestAdminPriorityModify())
    suite.addTest(TestAdminPriorityRemove())
    suite.addTest(TestAdminPriorityRemoveMulti())
    suite.addTest(TestAdminPriorityNonRemoval())
    suite.addTest(TestAdminPriorityDefault())
    suite.addTest(TestAdminPriorityDetail())
    suite.addTest(TestAdminPriorityRenumber())
    suite.addTest(TestAdminPriorityRenumberDup())
    suite.addTest(TestAdminResolution())
    suite.addTest(TestAdminResolutionAuthorization())
    suite.addTest(TestAdminResolutionDuplicates())
    suite.addTest(TestAdminResolutionDefault())
    suite.addTest(TestAdminSeverity())
    suite.addTest(TestAdminSeverityAuthorization())
    suite.addTest(TestAdminSeverityDuplicates())
    suite.addTest(TestAdminSeverityDefault())
    suite.addTest(TestAdminType())
    suite.addTest(TestAdminTypeAuthorization())
    suite.addTest(TestAdminTypeDuplicates())
    suite.addTest(TestAdminTypeDefault())
    suite.addTest(TestAdminVersion())
    suite.addTest(TestAdminVersionAuthorization())
    suite.addTest(TestAdminVersionDuplicates())
    suite.addTest(TestAdminVersionDetail())
    suite.addTest(TestAdminVersionDetailTime())
    suite.addTest(TestAdminVersionDetailCancel())
    suite.addTest(TestAdminVersionRemove())
    suite.addTest(TestAdminVersionRemoveMulti())
    suite.addTest(TestAdminVersionNonRemoval())
    suite.addTest(TestAdminVersionDefault())
    suite.addTest(TestTicketDefaultValues())

    return suite


test_suite = functionalSuite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
