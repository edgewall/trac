#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2008-2015 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import re
import unittest

from datetime import timedelta

from trac.admin.tests.functional import AuthorizationTestCaseSetup
from trac.test import locale_en
from trac.tests.contentgen import random_unique_camel
from trac.tests.functional import FunctionalTwillTestCaseSetup, b, \
                                  internal_error, tc
from trac.util.datefmt import datetime_now, format_date, format_datetime, \
                              localtz, utc


class AdminEnumDefaultTestCaseSetup(FunctionalTwillTestCaseSetup):
    def test_default(self, enum, name):
        url = self._tester.url + '/admin/ticket/%s' % enum
        tc.go(url)
        tc.url(url + '$')
        tc.find(name)
        tc.formvalue('enumtable', 'default', name)
        tc.submit('apply')
        tc.url(url + '$')
        tc.find('radio.*"%s"\\schecked="checked"' % name)
        # Test the "Clear default" button
        tc.go(url)
        tc.submit('clear', formname='enumtable')
        tc.url(url + '$')
        tc.notfind(internal_error)
        tc.find('<input type="radio" name="default" value="[^>]+" />')
        tc.notfind('type="radio" name="default" value=".+" checked="checked"')


class TestAdminComponent(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin create component"""
        self._tester.create_component()


class TestAdminComponentAuthorization(AuthorizationTestCaseSetup):
    def runTest(self):
        """Check permissions required to access the Ticket Components
        panel."""
        self.test_authorization('/admin/ticket/components', 'TICKET_ADMIN',
                                "Manage Components")


class TestAdminComponentDuplicates(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin create duplicate component"""
        name = "DuplicateComponent"
        self._tester.create_component(name)
        component_url = self._tester.url + "/admin/ticket/components"
        tc.go(component_url)
        tc.formvalue('addcomponent', 'name', name)
        tc.submit()
        tc.notfind(internal_error)
        tc.find('Component .* already exists')


class TestAdminComponentRemoval(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin remove component"""
        name = "RemovalComponent"
        self._tester.create_component(name)
        component_url = self._tester.url + "/admin/ticket/components"
        tc.go(component_url)
        tc.formvalue('component_table', 'sel', name)
        tc.submit('remove')
        tc.notfind(name)


class TestAdminComponentNonRemoval(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin remove no selected component"""
        component_url = self._tester.url + "/admin/ticket/components"
        tc.go(component_url)
        tc.submit('remove', formname='component_table')
        tc.find('No component selected')


class TestAdminComponentDefault(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin set default component"""
        name = "DefaultComponent"
        self._tester.create_component(name)
        component_url = self._tester.url + "/admin/ticket/components"
        tc.go(component_url)
        tc.formvalue('component_table', 'default', name)
        tc.submit('apply')
        tc.find('type="radio" name="default" value="%s" checked="checked"' % \
                name)
        tc.go(self._tester.url + '/newticket')
        tc.find('<option selected="selected" value="%s">%s</option>'
                % (name, name))
        # Test the "Clear default" button
        self._testenv.set_config('ticket', 'allowed_empty_fields', 'component')
        tc.go(component_url)
        tc.submit('clear', formname='component_table')
        tc.notfind('type="radio" name="default" value=".+" checked="checked"')
        self._tester.create_ticket()
        tc.find('<th id="h_component" class="missing">\s*Component:\s*</th>'
                '\s*<td headers="h_component">\s*</td>')
        self._testenv.remove_config('ticket', 'allowed_empty_fields')


class TestAdminComponentDetail(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin component detail"""
        name = "DetailComponent"
        self._tester.create_component(name)
        component_url = self._tester.url + "/admin/ticket/components"
        tc.go(component_url)
        tc.follow(name)
        desc = 'Some component description'
        tc.formvalue('edit', 'description', desc)
        tc.submit('cancel')
        tc.url(component_url + '$')
        tc.follow(name)
        tc.notfind(desc)


class TestAdminComponentNoneDefined(FunctionalTwillTestCaseSetup):
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
                self._tester.create_component(comp.name, comp.owner,
                                              comp.description)


class TestAdminMilestone(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin create milestone"""
        self._tester.create_milestone()


class TestAdminMilestoneAuthorization(AuthorizationTestCaseSetup):
    def runTest(self):
        """Check permissions required to access the Ticket Milestone
        panel."""
        self.test_authorization('/admin/ticket/milestones', 'TICKET_ADMIN',
                                "Manage Milestones")


class TestAdminMilestoneSpace(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin create milestone with a space"""
        self._tester.create_milestone('Milestone 1')


class TestAdminMilestoneDuplicates(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin create duplicate milestone"""
        name = "DuplicateMilestone"
        self._tester.create_milestone(name)
        milestone_url = self._tester.url + "/admin/ticket/milestones"
        tc.go(milestone_url)
        tc.url(milestone_url)
        tc.formvalue('addmilestone', 'name', name)
        tc.submit()
        tc.notfind(internal_error)
        tc.find('Milestone "%s" already exists, please choose '
                'another name.' % name)
        tc.notfind('%s')


class TestAdminMilestoneListing(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin milestone listing."""
        name1 = self._tester.create_milestone()
        self._tester.create_ticket(info={'milestone': name1})
        name2 = self._tester.create_milestone()

        milestone_url = self._tester.url + '/admin/ticket/milestones'
        tc.go(milestone_url)
        tc.url(milestone_url)
        tc.find(r'<a href="/admin/ticket/milestones/%(name)s">%(name)s</a>'
                % {'name': name1})
        tc.find(r'<a href="/query\?group=status&amp;milestone=%(name)s">'
                r'1</a>' % {'name': name1})
        tc.find(r'<a href="/admin/ticket/milestones/%(name)s">%(name)s</a>'
                % {'name': name2})
        tc.notfind(r'<a href="/query\?group=status&amp;milestone=%(name)s">'
                   r'0</a>' % {'name': name2})


class TestAdminMilestoneDetail(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin modify milestone details"""
        name = self._tester.create_milestone()

        milestone_url = self._tester.url + '/admin/ticket/milestones'
        def go_to_milestone_detail():
            tc.go(milestone_url)
            tc.url(milestone_url)
            tc.follow(name)
            tc.url(milestone_url + '/' + name)

        # Modify the details of the milestone
        go_to_milestone_detail()
        tc.formvalue('edit', 'due', True)
        tc.formvalue('edit', 'description', 'Some description.')
        tc.submit('save')
        tc.url(milestone_url)

        # Milestone is not closed
        self._tester.go_to_roadmap()
        tc.find(name)

        # Cancel more modifications and modification are not saved
        go_to_milestone_detail()
        tc.formvalue('edit', 'description', '~~Some other description.~~')
        tc.submit('cancel')
        tc.url(milestone_url)
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
            tc.url(milestone_url)
        finally:
            self._tester.logout()
            self._testenv.revoke_perm('user', 'TICKET_ADMIN')
            self._tester.login('admin')


class TestAdminMilestoneDue(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin milestone duedate"""
        name = "DueMilestone"
        duedate = datetime_now(tz=utc)
        duedate_string = format_datetime(duedate, tzinfo=utc,
                                         locale=locale_en)
        self._tester.create_milestone(name, due=duedate_string)
        tc.find(duedate_string)


class TestAdminMilestoneDetailDue(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin modify milestone duedate on detail page"""
        name = "DetailDueMilestone"
        # Create a milestone
        self._tester.create_milestone(name)

        # Modify the details of the milestone
        milestone_url = self._tester.url + "/admin/ticket/milestones"
        tc.go(milestone_url)
        tc.url(milestone_url)
        tc.follow(name)
        tc.url(milestone_url + '/' + name)
        duedate = datetime_now(tz=utc)
        duedate_string = format_datetime(duedate, tzinfo=utc,
                                         locale=locale_en)
        tc.formvalue('edit', 'due', True)
        tc.formvalue('edit', 'duedate', duedate_string)
        tc.submit('save')
        tc.url(milestone_url + '$')
        tc.find(name + '(<[^>]*>|\\s)*'+ duedate_string, 's')


class TestAdminMilestoneDetailRename(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin rename milestone"""
        name1 = self._tester.create_milestone()
        name2 = random_unique_camel()
        tid = self._tester.create_ticket(info={'milestone': name1})
        milestone_url = self._tester.url + '/admin/ticket/milestones'

        self._tester.go_to_url(milestone_url)
        tc.follow(name1)
        tc.url(milestone_url + '/' + name1)
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


class TestAdminMilestoneCompleted(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin milestone completed"""
        name = "CompletedMilestone"
        self._tester.create_milestone(name)
        milestone_url = self._tester.url + "/admin/ticket/milestones"
        tc.go(milestone_url)
        tc.url(milestone_url)
        tc.follow(name)
        tc.url(milestone_url + '/' + name)
        tc.formvalue('edit', 'completed', True)
        tc.submit('save')
        tc.url(milestone_url + "$")


class TestAdminMilestoneCompletedFuture(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin milestone completed in the future"""
        name = "CompletedFutureMilestone"
        self._tester.create_milestone(name)
        milestone_url = self._tester.url + "/admin/ticket/milestones"
        tc.go(milestone_url)
        tc.url(milestone_url)
        tc.follow(name)
        tc.url(milestone_url + '/' + name)
        tc.formvalue('edit', 'completed', True)
        cdate = datetime_now(tz=utc) + timedelta(days=2)
        cdate_string = format_date(cdate, tzinfo=localtz, locale=locale_en)
        tc.formvalue('edit', 'completeddate', cdate_string)
        tc.submit('save')
        tc.find('Completion date may not be in the future')
        # And make sure it wasn't marked as completed.
        self._tester.go_to_roadmap()
        tc.find(name)


class TestAdminMilestoneRemove(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin remove milestone"""
        name = "MilestoneRemove"
        self._tester.create_milestone(name)
        tid = self._tester.create_ticket(info={'milestone': name})
        milestone_url = self._tester.url + '/admin/ticket/milestones'

        tc.go(milestone_url)
        tc.formvalue('milestone_table', 'sel', name)
        tc.submit('remove')

        tc.url(milestone_url + '$')
        tc.notfind(name)
        self._tester.go_to_ticket(tid)
        tc.find('<th id="h_milestone" class="missing">'
                '[ \t\n]*Milestone:[ \t\n]*</th>')
        tc.find('<th class="trac-field-milestone">Milestone:</th>[ \t\n]+'
                '<td>[ \t\n]+'
                '<span class="trac-field-deleted">%s</span>'
                '[ \t\n]+</td>' % name)
        tc.find("Milestone deleted")


class TestAdminMilestoneRemoveMulti(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin remove multiple milestones"""
        name = "MultiRemoveMilestone"
        count = 3
        for i in range(count):
            self._tester.create_milestone("%s%s" % (name, i))
        milestone_url = self._tester.url + '/admin/ticket/milestones'
        tc.go(milestone_url)
        tc.url(milestone_url + '$')
        for i in range(count):
            tc.find("%s%s" % (name, i))
        for i in range(count):
            tc.formvalue('milestone_table', 'sel', "%s%s" % (name, i))
        tc.submit('remove')
        tc.url(milestone_url + '$')
        for i in range(count):
            tc.notfind("%s%s" % (name, i))


class TestAdminMilestoneNonRemoval(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin remove no selected milestone"""
        milestone_url = self._tester.url + "/admin/ticket/milestones"
        tc.go(milestone_url)
        tc.submit('remove', formname='milestone_table')
        tc.find('No milestone selected')


class TestAdminMilestoneDefaults(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin set default ticket milestone, default retarget milestone
        and clear defaults."""
        def clear_defaults():
            # Test the "Clear default" button
            tc.go(milestone_url)
            tc.submit('clear', formname='milestone_table')
            tc.notfind('type="radio" name="ticket_default" '
                       'value=".+" checked="checked"')
            tc.notfind('type="radio" name="retarget_default" '
                       'value=".+" checked="checked"')
            self._tester.go_to_ticket(tid)
            tc.find('<th id="h_milestone" class="missing">[ \t\n]+'
                    'Milestone:[ \t\n]+</th>[ \t\n]+'
                    '(?!<td headers="h_milestone">)')
            self._tester.go_to_milestone(mid2)
            tc.submit(formname='deletemilestone')
            tc.notfind('<option selected="selected" value="%s">%s</option>'
                       % (mid1, mid1))

        milestone_url = self._tester.url + "/admin/ticket/milestones"
        tid = self._tester.create_ticket()
        mid1 = self._tester.create_milestone()
        mid2 = self._tester.create_milestone()
        self._tester.create_ticket(info={'milestone': mid2})

        # Set default ticket milestone
        tc.go(milestone_url)
        tc.formvalue('milestone_table', 'ticket_default', mid1)
        tc.submit('apply')
        tc.find('type="radio" name="ticket_default" value="%s" '
                'checked="checked"' % mid1)
        tc.notfind('type="radio" name="retarget_default" value=".+" '
                   'checked="checked"')
        # verify it is the default on the newticket page.
        tc.go(self._tester.url + '/newticket')
        tc.find('<option selected="selected" value="%s">%s</option>'
                % (mid1, mid1))
        clear_defaults()

        # Set default retarget to milestone
        tc.go(milestone_url)
        tc.formvalue('milestone_table', 'retarget_default', mid1)
        tc.submit('apply')
        tc.find('type="radio" name="retarget_default" value="%s" '
                'checked="checked"' % mid1)
        tc.notfind('type="radio" name="ticket_default" value=".+" '
                   'checked="checked"')
        # verify it is the default on the confirm delete page.
        self._tester.go_to_milestone(mid2)
        tc.submit(formname='deletemilestone')
        tc.find('<option selected="selected" value="%s">%s</option>'
                % (mid1, mid1))
        clear_defaults()

        # Set both
        tc.go(milestone_url)
        tc.formvalue('milestone_table', 'ticket_default', mid1)
        tc.formvalue('milestone_table', 'retarget_default', mid1)
        tc.submit('apply')
        tc.find('type="radio" name="ticket_default" value="%s" '
                'checked="checked"' % mid1)
        tc.find('type="radio" name="retarget_default" value="%s" '
                'checked="checked"' % mid1)
        # verify it is the default on the newticket page.
        tc.go(self._tester.url + '/newticket')
        tc.find('<option selected="selected" value="%s">%s</option>'
                % (mid1, mid1))
        # verify it is the default on the confirm delete page.
        self._tester.go_to_milestone(mid2)
        tc.submit(formname='deletemilestone')
        tc.find('<option selected="selected" value="%s">%s</option>'
                % (mid1, mid1))
        clear_defaults()

        #Set neither
        tc.go(milestone_url)
        tc.submit('apply', formname='milestone_table')
        tc.notfind('type="radio" name="retarget_default" value=".+" '
                   'checked="checked"')
        tc.notfind('type="radio" name="ticket_default" value=".+" '
                   'checked="checked"')
        # verify no default on the newticket page.
        tc.go(self._tester.url + '/newticket')
        tc.find('<th id="h_milestone" class="missing">[ \t\n]+'
                'Milestone:[ \t\n]+</th>[ \t\n]+'
                '(?!<td headers="h_milestone">)')
        # verify none selected on the confirm delete page.
        self._tester.go_to_milestone(mid2)
        tc.submit(formname='deletemilestone')
        tc.notfind('<option selected="selected" value="%s">%s</option>'
                   % (mid1, mid1))


class TestAdminPriority(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin create priority"""
        self._tester.create_priority()


class TestAdminPriorityAuthorization(AuthorizationTestCaseSetup):
    def runTest(self):
        """Check permissions required to access the Ticket Priority
        panel."""
        self.test_authorization('/admin/ticket/priority', 'TICKET_ADMIN',
                                "Manage Priorities")


class TestAdminPriorityDuplicates(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin create duplicate priority"""
        name = "DuplicatePriority"
        self._tester.create_priority(name)
        self._tester.create_priority(name)
        tc.find('Priority %s already exists' % name)


class TestAdminPriorityModify(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin modify priority"""
        name = "ModifyPriority"
        self._tester.create_priority(name)
        priority_url = self._tester.url + '/admin/ticket/priority'
        tc.go(priority_url)
        tc.url(priority_url + '$')
        tc.find(name)
        tc.follow(name)
        tc.formvalue('edit', 'name', name * 2)
        tc.submit('save')
        tc.url(priority_url + '$')
        tc.find(name * 2)


class TestAdminPriorityRemove(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin remove priority"""
        name = "RemovePriority"
        self._tester.create_priority(name)
        priority_url = self._tester.url + '/admin/ticket/priority'
        tc.go(priority_url)
        tc.url(priority_url + '$')
        tc.find(name)
        tc.formvalue('enumtable', 'sel', name)
        tc.submit('remove')
        tc.url(priority_url + '$')
        tc.notfind(name)


class TestAdminPriorityRemoveMulti(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin remove multiple priorities"""
        name = "MultiRemovePriority"
        count = 3
        for i in range(count):
            self._tester.create_priority("%s%s" % (name, i))
        priority_url = self._tester.url + '/admin/ticket/priority'
        tc.go(priority_url)
        tc.url(priority_url + '$')
        for i in range(count):
            tc.find("%s%s" % (name, i))
        for i in range(count):
            tc.formvalue('enumtable', 'sel', "%s%s" % (name, i))
        tc.submit('remove')
        tc.url(priority_url + '$')
        for i in range(count):
            tc.notfind("%s%s" % (name, i))


class TestAdminPriorityNonRemoval(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin remove no selected priority"""
        priority_url = self._tester.url + "/admin/ticket/priority"
        tc.go(priority_url)
        tc.submit('remove', formname='enumtable')
        tc.find('No priority selected')


class TestAdminPriorityDefault(AdminEnumDefaultTestCaseSetup):
    def runTest(self):
        """Admin default priority"""
        name = self._tester.create_priority()
        self.test_default('priority', name)


class TestAdminPriorityDetail(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin modify priority details"""
        name = "DetailPriority"
        # Create a priority
        self._tester.create_priority(name + '1')

        # Modify the details of the priority
        priority_url = self._tester.url + "/admin/ticket/priority"
        tc.go(priority_url)
        tc.url(priority_url + '$')
        tc.follow(name + '1')
        tc.url(priority_url + '/' + name + '1')
        tc.formvalue('edit', 'name', name + '2')
        tc.submit('save')
        tc.url(priority_url + '$')

        # Cancel more modifications
        tc.go(priority_url)
        tc.follow(name)
        tc.formvalue('edit', 'name', name + '3')
        tc.submit('cancel')
        tc.url(priority_url + '$')

        # Verify that only the correct modifications show up
        tc.notfind(name + '1')
        tc.find(name + '2')
        tc.notfind(name + '3')


class TestAdminPriorityRenumber(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin renumber priorities"""
        valuesRE = re.compile('<select name="value_([0-9]+)">', re.M)
        html = b.get_html()
        max_priority = max([int(x) for x in valuesRE.findall(html)])

        name = "RenumberPriority"
        self._tester.create_priority(name + '1')
        self._tester.create_priority(name + '2')
        priority_url = self._tester.url + '/admin/ticket/priority'
        tc.go(priority_url)
        tc.url(priority_url + '$')
        tc.find(name + '1')
        tc.find(name + '2')
        tc.formvalue('enumtable',
                     'value_%s' % (max_priority + 1), str(max_priority + 2))
        tc.formvalue('enumtable',
                     'value_%s' % (max_priority + 2), str(max_priority + 1))
        tc.submit('apply')
        tc.url(priority_url + '$')
        # Verify that their order has changed.
        tc.find(name + '2.*' + name + '1', 's')


class TestAdminPriorityRenumberDup(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin badly renumber priorities"""
        # Make the first priority the 2nd priority, and leave the 2nd priority
        # as the 2nd priority.
        priority_url = self._tester.url + '/admin/ticket/priority'
        tc.go(priority_url)
        tc.url(priority_url + '$')
        tc.formvalue('enumtable', 'value_1', '2')
        tc.submit('apply')
        tc.url(priority_url + '$')
        tc.find('Order numbers must be unique')


class TestAdminResolution(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin create resolution"""
        self._tester.create_resolution()


class TestAdminResolutionAuthorization(AuthorizationTestCaseSetup):
    def runTest(self):
        """Check permissions required to access the Ticket Resolutions
        panel."""
        self.test_authorization('/admin/ticket/resolution', 'TICKET_ADMIN',
                                "Manage Resolutions")


class TestAdminResolutionDuplicates(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin create duplicate resolution"""
        name = "DuplicateResolution"
        self._tester.create_resolution(name)
        self._tester.create_resolution(name)
        tc.find('Resolution value "%s" already exists' % name)


class TestAdminResolutionDefault(AdminEnumDefaultTestCaseSetup):
    def runTest(self):
        """Admin default resolution"""
        name = self._tester.create_resolution()
        self.test_default('resolution', name)


class TestAdminSeverity(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin create severity"""
        self._tester.create_severity()


class TestAdminSeverityAuthorization(AuthorizationTestCaseSetup):
    def runTest(self):
        """Check permissions required to access the Ticket Severities
        panel."""
        self.test_authorization('/admin/ticket/severity', 'TICKET_ADMIN',
                                "Manage Severities")


class TestAdminSeverityDuplicates(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin create duplicate severity"""
        name = "DuplicateSeverity"
        self._tester.create_severity(name)
        self._tester.create_severity(name)
        tc.find('Severity value "%s" already exists' % name)


class TestAdminSeverityDefault(AdminEnumDefaultTestCaseSetup):
    def runTest(self):
        """Admin default severity"""
        name = self._tester.create_severity()
        self.test_default('severity', name)


class TestAdminType(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin create type"""
        self._tester.create_type()


class TestAdminTypeAuthorization(AuthorizationTestCaseSetup):
    def runTest(self):
        """Check permissions required to access the Ticket Types
        panel."""
        self.test_authorization('/admin/ticket/type', 'TICKET_ADMIN',
                                "Manage Ticket Types")


class TestAdminTypeDuplicates(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin create duplicate type"""
        name = "DuplicateType"
        self._tester.create_type(name)
        self._tester.create_type(name)
        tc.find('Type value "%s" already exists' % name)


class TestAdminTypeDefault(AdminEnumDefaultTestCaseSetup):
    def runTest(self):
        """Admin default type"""
        name = self._tester.create_type()
        self.test_default('type', name)


class TestAdminVersion(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin create version"""
        self._tester.create_version()


class TestAdminVersionAuthorization(AuthorizationTestCaseSetup):
    def runTest(self):
        """Check permissions required to access the Versions panel."""
        self.test_authorization('/admin/ticket/versions', 'TICKET_ADMIN',
                                "Manage Versions")


class TestAdminVersionDuplicates(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin create duplicate version"""
        name = "DuplicateVersion"
        self._tester.create_version(name)
        version_admin = self._tester.url + "/admin/ticket/versions"
        tc.go(version_admin)
        tc.url(version_admin)
        tc.formvalue('addversion', 'name', name)
        tc.submit()
        tc.notfind(internal_error)
        tc.find('Version "%s" already exists.' % name)


class TestAdminVersionDetail(FunctionalTwillTestCaseSetup):
    # This is somewhat pointless... the only place to find the version
    # description is on the version details page.
    def runTest(self):
        """Admin version details"""
        name = "DetailVersion"
        self._tester.create_version(name)
        version_admin = self._tester.url + "/admin/ticket/versions"
        tc.go(version_admin)
        tc.url(version_admin)
        tc.follow(name)

        desc = 'Some version description.'
        tc.formvalue('edit', 'description', desc)
        tc.submit('save')
        tc.url(version_admin)
        tc.follow(name)
        tc.find(desc)


class TestAdminVersionDetailTime(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin version detail set time"""
        name = "DetailTimeVersion"
        self._tester.create_version(name)
        version_admin = self._tester.url + "/admin/ticket/versions"
        tc.go(version_admin)
        tc.url(version_admin)
        tc.follow(name)

        tc.formvalue('edit', 'time', '')
        tc.submit('save')
        tc.url(version_admin + '$')
        tc.find(name + '(<[^>]*>|\\s)*<[^>]* name="default" value="%s"'
                % name, 's')


class TestAdminVersionDetailCancel(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin version details"""
        name = "DetailVersion"
        self._tester.create_version(name)
        version_admin = self._tester.url + "/admin/ticket/versions"
        tc.go(version_admin)
        tc.url(version_admin)
        tc.follow(name)

        desc = 'Some other version description.'
        tc.formvalue('edit', 'description', desc)
        tc.submit('cancel')
        tc.url(version_admin)
        tc.follow(name)
        tc.notfind(desc)


class TestAdminVersionRemove(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin remove version"""
        name = "VersionRemove"
        self._tester.create_version(name)
        version_url = self._tester.url + "/admin/ticket/versions"
        tc.go(version_url)
        tc.formvalue('version_table', 'sel', name)
        tc.submit('remove')
        tc.url(version_url + '$')
        tc.notfind(name)


class TestAdminVersionRemoveMulti(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin remove multiple versions"""
        name = "MultiRemoveVersion"
        count = 3
        for i in range(count):
            self._tester.create_version("%s%s" % (name, i))
        version_url = self._tester.url + '/admin/ticket/versions'
        tc.go(version_url)
        tc.url(version_url + '$')
        for i in range(count):
            tc.find("%s%s" % (name, i))
        for i in range(count):
            tc.formvalue('version_table', 'sel', "%s%s" % (name, i))
        tc.submit('remove')
        tc.url(version_url + '$')
        for i in range(count):
            tc.notfind("%s%s" % (name, i))


class TestAdminVersionNonRemoval(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin remove no selected version"""
        version_url = self._tester.url + "/admin/ticket/versions"
        tc.go(version_url)
        tc.submit('remove', formname='version_table')
        tc.find('No version selected')


class TestAdminVersionDefault(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin set default version"""
        name = "DefaultVersion"
        self._tester.create_version(name)
        version_url = self._tester.url + "/admin/ticket/versions"
        tc.go(version_url)
        tc.formvalue('version_table', 'default', name)
        tc.submit('apply')
        tc.find('type="radio" name="default" value="%s" checked="checked"' % \
                name)
        # verify it is the default on the newticket page.
        tc.go(self._tester.url + '/newticket')
        tc.find('<option selected="selected" value="%s">%s</option>'
                % (name, name))
        # Test the "Clear default" button
        tc.go(version_url)
        tc.submit('clear', formname='version_table')
        tc.notfind('type="radio" name="default" value=".+" checked="checked"')
        self._tester.create_ticket()
        tc.find('<th id="h_version" class="missing">[ \t\n]+'
                'Version:[ \t\n]+</th>[ \t\n]+'
                '(?!<td headers="h_version">)')


class RegressionTestRev5665(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin create version without release time (r5665)"""
        self._tester.create_version(releasetime='')


class RegressionTestTicket10772(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/10772"""
        def find_prop(field, value=None):
            if value and field == 'type':
                tc.find(r'<span class="trac-%(field)s">\s*'
                        r'<a href="/query\?status=!closed&amp;'
                        r'%(field)s=%(value)s">\s*%(value)s\s*</a>\s*</span>'
                        % {'field': field, 'value': value})
            elif value and field == 'milestone':
                tc.find(r'<td headers="h_%(field)s">\s*'
                        r'<a class="%(field)s" href="/%(field)s/%(value)s" '
                        r'title=".+">\s*%(value)s\s*</a>\s*</td>'
                        % {'field': field, 'value': value})
            elif value:
                tc.find(r'<td headers="h_%(field)s">\s*'
                        r'<a href="/query\?status=!closed&amp;'
                        r'%(field)s=%(value)s">\s*%(value)s\s*</a>\s*</td>'
                        % {'field': field, 'value': value})
            else:
                tc.find(r'<td headers="h_%(field)s">\s*</td>'
                        % {'field': field})

        self._testenv.set_config('ticket', 'allowed_empty_fields',
                                 'component, milestone, priority, version')

        try:
            # TODO: use the //Clear default// buttons to clear these values
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


class RegressionTestTicket11618(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/11618
        fix for malformed `readonly="True"` attribute in milestone admin page
        """
        name = "11618Milestone"
        self._tester.create_milestone(name)
        try:
            self._testenv.grant_perm('user', 'TICKET_ADMIN')
            self._tester.go_to_front()
            self._tester.logout()
            self._tester.login('user')
            tc.go(self._tester.url + "/admin/ticket/milestones/" + name)
            tc.notfind('No administration panels available')
            tc.find(' readonly="readonly"')
            tc.notfind(' readonly="True"')
        finally:
            self._testenv.revoke_perm('user', 'TICKET_ADMIN')
            self._tester.go_to_front()
            self._tester.logout()
            self._tester.login('admin')


def functionalSuite(suite=None):
    if not suite:
        import trac.tests.functional
        suite = trac.tests.functional.functionalSuite()
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
    suite.addTest(RegressionTestRev5665())
    suite.addTest(RegressionTestTicket10772())
    suite.addTest(RegressionTestTicket11618())

    return suite


test_suite = functionalSuite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
