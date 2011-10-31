#!/usr/bin/python
import os
import re

from datetime import datetime, timedelta

from trac.tests.functional import *
from trac.util.datefmt import utc, localtz, format_date


class TestTickets(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Create a ticket, comment on it, and attach a file"""
        # TODO: this should be split into multiple tests
        summary = random_sentence(5)
        ticketid = self._tester.create_ticket(summary)
        self._tester.create_ticket()
        self._tester.add_comment(ticketid)
        self._tester.attach_file_to_ticket(ticketid)


class TestTicketPreview(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Preview ticket creation"""
        self._tester.go_to_front()
        tc.follow('New Ticket')
        summary = random_sentence(5)
        desc = random_sentence(5)
        tc.formvalue('propertyform', 'field-summary', summary)
        tc.formvalue('propertyform', 'field-description', desc)
        tc.submit('preview')
        tc.url(self._tester.url + '/newticket$')
        tc.find('ticket not yet created')
        tc.find(summary)
        tc.find(desc)


class TestTicketNoSummary(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Creating a ticket without summary should fail"""
        self._tester.go_to_front()
        tc.follow('New Ticket')
        desc = random_sentence(5)
        tc.formvalue('propertyform', 'field-description', desc)
        tc.submit('submit')
        tc.find(desc)
        tc.find('Tickets must contain a summary.')
        tc.find('Create New Ticket')
        tc.find('ticket not yet created')


class TestTicketAltFormats(FunctionalTestCaseSetup):
    def runTest(self):
        """Download ticket in alternative formats"""
        summary = random_sentence(5)
        ticketid = self._tester.create_ticket(summary)
        self._tester.go_to_ticket(ticketid)
        for format in ['Comma-delimited Text', 'Tab-delimited Text',
                       'RSS Feed']:
            tc.follow(format)
            content = b.get_html()
            if content.find(summary) < 0:
                raise AssertionError('Summary missing from %s format' % format)
            tc.back()


class TestTicketCSVFormat(FunctionalTestCaseSetup):
    def runTest(self):
        """Download ticket in CSV format"""
        summary = random_sentence(5)
        ticketid = self._tester.create_ticket(summary)
        self._tester.go_to_ticket(ticketid)
        tc.follow('Comma-delimited Text')
        csv = b.get_html()
        if not csv.startswith('id,summary,'):
            raise AssertionError('Bad CSV format')


class TestTicketTabFormat(FunctionalTestCaseSetup):
    def runTest(self):
        """Download ticket in Tab-delimitted format"""
        summary = random_sentence(5)
        ticketid = self._tester.create_ticket(summary)
        self._tester.go_to_ticket(ticketid)
        tc.follow('Tab-delimited Text')
        tab = b.get_html()
        if not tab.startswith('id\tsummary\t'):
            raise AssertionError('Bad tab delimitted format')


class TestTicketRSSFormat(FunctionalTestCaseSetup):
    def runTest(self):
        """Download ticket in RSS format"""
        summary = random_sentence(5)
        ticketid = self._tester.create_ticket(summary)
        self._tester.go_to_ticket(ticketid)
        # Make a number of changes to exercise all of the RSS feed code
        self._tester.go_to_ticket(ticketid)
        tc.formvalue('propertyform', 'comment', random_sentence(3))
        tc.formvalue('propertyform', 'field-type', 'task')
        tc.formvalue('propertyform', 'description', summary + '\n\n' +
                                                    random_sentence(8))
        tc.formvalue('propertyform', 'field-keywords', 'key')
        tc.submit('submit')
        time.sleep(1) # Have to wait a second
        tc.formvalue('propertyform', 'field-keywords', '')
        tc.submit('submit')

        tc.find('RSS Feed')
        tc.follow('RSS Feed')
        rss = b.get_html()
        if not rss.startswith('<?xml version="1.0"?>'):
            raise AssertionError('RSS Feed not valid feed')


class TestTicketSearch(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test ticket search"""
        summary = random_sentence(4)
        ticketid = self._tester.create_ticket(summary)
        self._tester.go_to_front()
        tc.follow('Search')
        tc.formvalue('fullsearch', 'ticket', True)
        tc.formvalue('fullsearch', 'q', summary)
        tc.submit('Search')
        tc.find('class="searchable">.*' + summary)
        tc.notfind('No matches found')


class TestNonTicketSearch(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test non-ticket search"""
        # Create a summary containing only unique words
        summary = ' '.join([random_word() + '_TestNonTicketSearch'
                            for i in range(5)])
        ticketid = self._tester.create_ticket(summary)
        self._tester.go_to_front()
        tc.follow('Search')
        tc.formvalue('fullsearch', 'ticket', False)
        tc.formvalue('fullsearch', 'q', summary)
        tc.submit('Search')
        tc.notfind('class="searchable">' + summary)
        tc.find('No matches found')


class TestTicketHistory(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test ticket history"""
        summary = random_sentence(5)
        ticketid = self._tester.create_ticket(summary)
        comment = random_sentence(5)
        self._tester.add_comment(ticketid, comment=comment)
        self._tester.go_to_ticket(ticketid)
        url = b.get_url()
        tc.go(url + '?version=0')
        tc.find('at <[^>]*>*Initial Version')
        tc.find(summary)
        tc.notfind(comment)
        tc.go(url + '?version=1')
        tc.find('at <[^>]*>*Version 1')
        tc.find(summary)
        tc.find(comment)


class TestTicketHistoryDiff(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test ticket history (diff)"""
        name = 'TestTicketHistoryDiff'
        ticketid = self._tester.create_ticket(name)
        self._tester.go_to_ticket(ticketid)
        tc.formvalue('propertyform', 'description', random_sentence(6))
        tc.submit('submit')
        tc.find('Description<[^>]*>\\s*modified \\(<[^>]*>diff', 's')
        tc.follow('diff')
        tc.find('Changes\\s*between\\s*<[^>]*>Initial Version<[^>]*>\\s*and' \
                '\\s*<[^>]*>Version 1<[^>]*>\\s*of\\s*<[^>]*>Ticket #' , 's')


class TestTicketQueryLinks(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test ticket query links"""
        count = 3
        ticket_ids = [self._tester.create_ticket(
                        summary='TestTicketQueryLinks%s' % i)
                      for i in range(count)]
        self._tester.go_to_query()
        # We don't have the luxury of javascript, so this is a multi-step
        # process
        tc.formvalue('query', 'add_filter_0', 'summary')
        tc.submit('add_0')
        tc.formvalue('query', '0_owner', 'nothing')
        tc.submit('rm_filter_0_owner_0')
        tc.formvalue('query', '0_summary', 'TestTicketQueryLinks')
        tc.submit('update')
        query_url = b.get_url()
        for i in range(count):
            tc.find('TestTicketQueryLinks%s' % i)

        tc.follow('TestTicketQueryLinks0')
        tc.find('class="missing">&larr; Previous Ticket')
        tc.find('title="Ticket #%s">Next Ticket' % ticket_ids[1])
        tc.follow('Back to Query')
        tc.url(re.escape(query_url))

        tc.follow('TestTicketQueryLinks1')
        tc.find('title="Ticket #%s">Previous Ticket' % ticket_ids[0])
        tc.find('title="Ticket #%s">Next Ticket' % ticket_ids[2])
        tc.follow('Next Ticket')

        tc.find('title="Ticket #%s">Previous Ticket' % ticket_ids[1])
        tc.find('class="missing">Next Ticket &rarr;')


class TestTicketQueryOrClause(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test ticket query with an or clauses"""
        count = 3
        ticket_ids = [self._tester.create_ticket(
                        summary='TestTicketQueryOrClause%s' % i,
                        info={'keywords': str(i)})
                      for i in range(count)]
        self._tester.go_to_query()
        tc.formvalue('query', '0_owner', '')
        tc.submit('rm_filter_0_owner_0')
        tc.formvalue('query', 'add_filter_0', 'summary')
        tc.submit('add_0')
        tc.formvalue('query', '0_summary', 'TestTicketQueryOrClause1')
        tc.formvalue('query', 'add_clause_1', 'keywords')
        tc.submit('add_1')
        tc.formvalue('query', '1_keywords', '2')
        tc.submit('update')
        tc.notfind('TestTicketQueryOrClause0')
        for i in [1, 2]:
            tc.find('TestTicketQueryOrClause%s' % i)


class TestTimelineTicketDetails(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test ticket details on timeline"""
        env = self._testenv.get_trac_environment()
        env.config.set('timeline', 'ticket_show_details', 'yes')
        env.config.save()
        summary = random_sentence(5)
        ticketid = self._tester.create_ticket(summary)
        self._tester.go_to_ticket(ticketid)
        self._tester.add_comment(ticketid)
        self._tester.go_to_timeline()
        tc.formvalue('prefs', 'ticket_details', True)
        tc.submit()
        htmltags = '(<[^>]*>)*'
        tc.find('Ticket ' + htmltags + '#' + str(ticketid) + htmltags + ' \\(' +
                summary + '\\) updated\\s+by\\s+' + htmltags + 'admin', 's')


class TestAdminComponent(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin create component"""
        self._tester.create_component()


class TestAdminComponentDuplicates(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin create duplicate component"""
        name = "DuplicateMilestone"
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
        tc.formvalue('component_table', 'remove', 'Remove selected items')
        tc.submit('remove')
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


class TestAdminComponentDetail(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin component detail"""
        name = "DetailComponent"
        self._tester.create_component(name)
        component_url = self._tester.url + "/admin/ticket/components"
        tc.go(component_url)
        tc.follow(name)
        desc = 'Some component description'
        tc.formvalue('modcomp', 'description', desc)
        tc.submit('cancel')
        tc.url(component_url + '$')
        tc.follow(name)
        tc.notfind(desc)


class TestAdminMilestone(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin create milestone"""
        self._tester.create_milestone()


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
        tc.find('Milestone %s already exists' % name)
        tc.notfind('%s')


class TestAdminMilestoneDetail(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin modify milestone details"""
        name = "DetailMilestone"
        # Create a milestone
        self._tester.create_milestone(name)

        # Modify the details of the milestone
        milestone_url = self._tester.url + "/admin/ticket/milestones"
        tc.go(milestone_url)
        tc.url(milestone_url)
        tc.follow(name)
        tc.url(milestone_url + '/' + name)
        tc.formvalue('modifymilestone', 'description', 'Some description.')
        tc.submit('save')
        tc.url(milestone_url)

        # Make sure the milestone isn't closed
        self._tester.go_to_roadmap()
        tc.find(name)

        # Cancel more modifications
        tc.go(milestone_url)
        tc.url(milestone_url)
        tc.follow(name)
        tc.formvalue('modifymilestone', 'description',
                     '~~Some other description.~~')
        tc.submit('cancel')
        tc.url(milestone_url)

        # Verify the correct modifications show up
        self._tester.go_to_roadmap()
        tc.find('Some description.')
        tc.follow(name)
        tc.find('Some description.')


class TestAdminMilestoneDue(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin milestone duedate"""
        name = "DueMilestone"
        duedate = datetime.now(tz=utc)
        duedate_string = format_date(duedate, tzinfo=utc)
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
        duedate = datetime.now(tz=utc)
        duedate_string = format_date(duedate, tzinfo=utc)
        tc.formvalue('modifymilestone', 'due', duedate_string)
        tc.submit('save')
        tc.url(milestone_url + '$')
        tc.find(name + '(<[^>]*>|\\s)*'+ duedate_string, 's')


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
        tc.formvalue('modifymilestone', 'completed', True)
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
        tc.formvalue('modifymilestone', 'completed', True)
        cdate = datetime.now(tz=utc) + timedelta(days=1)
        cdate_string = format_date(cdate, tzinfo=localtz)
        tc.formvalue('modifymilestone', 'completeddate', cdate_string)
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
        milestone_url = self._tester.url + "/admin/ticket/milestones"
        tc.go(milestone_url)
        tc.formvalue('milestone_table', 'sel', name)
        tc.submit('remove')
        tc.url(milestone_url + '$')
        tc.notfind(name)


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
        tc.formvalue('milestone_table', 'remove', 'Remove selected items')
        tc.submit('remove')
        tc.find('No milestone selected')


class TestAdminMilestoneDefault(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin set default milestone"""
        name = "DefaultMilestone"
        self._tester.create_milestone(name)
        milestone_url = self._tester.url + "/admin/ticket/milestones"
        tc.go(milestone_url)
        tc.formvalue('milestone_table', 'default', name)
        tc.submit('apply')
        tc.find('type="radio" name="default" value="%s" checked="checked"' % \
                name)
        # verify it is the default on the newticket page.
        tc.go(self._tester.url + '/newticket')
        tc.find('<option selected="selected" value="%s">%s</option>'
                % (name, name))


class TestAdminPriority(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin create priority"""
        self._tester.create_priority()


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
        tc.formvalue('modenum', 'name', name * 2)
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
        tc.formvalue('enumtable', 'remove', 'Remove selected items')
        tc.submit('remove')
        tc.find('No priority selected')


class TestAdminPriorityDefault(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin default priority"""
        name = "DefaultPriority"
        self._tester.create_priority(name)
        priority_url = self._tester.url + '/admin/ticket/priority'
        tc.go(priority_url)
        tc.url(priority_url + '$')
        tc.find(name)
        tc.formvalue('enumtable', 'default', name)
        tc.submit('apply')
        tc.url(priority_url + '$')
        tc.find('radio.*"%s"\\schecked="checked"' % name)


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
        tc.formvalue('modenum', 'name', name + '2')
        tc.submit('save')
        tc.url(priority_url + '$')

        # Cancel more modifications
        tc.go(priority_url)
        tc.follow(name)
        tc.formvalue('modenum', 'name', name + '3')
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
        tc.formvalue('enumtable', 'value_%s' % (max_priority + 1), str(max_priority + 2))
        tc.formvalue('enumtable', 'value_%s' % (max_priority + 2), str(max_priority + 1))
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


class TestAdminResolutionDuplicates(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin create duplicate resolution"""
        name = "DuplicateResolution"
        self._tester.create_resolution(name)
        self._tester.create_resolution(name)
        tc.find('Resolution value "%s" already exists' % name)


class TestAdminSeverity(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin create severity"""
        self._tester.create_severity()


class TestAdminSeverityDuplicates(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin create duplicate severity"""
        name = "DuplicateSeverity"
        self._tester.create_severity(name)
        self._tester.create_severity(name)
        tc.find('Severity value "%s" already exists' % name)


class TestAdminType(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin create type"""
        self._tester.create_type()


class TestAdminTypeDuplicates(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin create duplicate type"""
        name = "DuplicateType"
        self._tester.create_type(name)
        self._tester.create_type(name)
        tc.find('Type value "%s" already exists' % name)


class TestAdminVersion(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin create version"""
        self._tester.create_version()


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
        tc.find("Version %s already exists." % name)


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
        tc.formvalue('modifyversion', 'description', desc)
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

        tc.formvalue('modifyversion', 'time', '')
        tc.submit('save')
        tc.url(version_admin + '$')
        tc.find(name + '(<[^>]*>|\\s)*<[^>]* name="default" value="%s"' % name, 's')


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
        tc.formvalue('modifyversion', 'description', desc)
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
        tc.formvalue('version_table', 'remove', 'Remove selected items')
        tc.submit('remove')
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


class TestNewReport(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Create a new report"""
        self._tester.create_report(
            'Closed tickets, modified in the past 7 days by owner.',
            'SELECT DISTINCT p.value AS __color__,'
            '   id AS ticket,'
            '   summary, component, milestone, t.type AS type,'
            '   reporter, time AS created,'
            '   changetime AS modified, description AS _description,'
            '   priority,'
            '   round(julianday(\'now\') - '
            '         julianday(changetime, \'unixepoch\')) as days,'
            '   resolution,'
            '   owner as __group__'
            '  FROM ticket t'
            '  LEFT JOIN enum p ON p.name = t.priority AND '
            '                      p.type = \'priority\''
            '  WHERE ((julianday(\'now\') -'
            '          julianday(changetime, \'unixepoch\')) < 7)'
            '   AND status = \'closed\''
            '  ORDER BY __group__, changetime, p.value',
            'List of all tickets that are closed, and have been modified in'
            ' the past 7 days, grouped by owner.\n\n(So they have probably'
            ' been closed this week.)')


class TestReportRealmDecoration(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Realm/id decoration in report"""
        self._tester.create_report(
            'Realm/id decoration',
            """\
SELECT NULL AS _realm, NULL AS id, NULL AS _parent_realm, NULL AS _parent_id
UNION ALL SELECT 'ticket', '42', NULL, NULL
UNION ALL SELECT 'report', '42', NULL, NULL
UNION ALL SELECT 'milestone', '42', NULL, NULL
UNION ALL SELECT 'wiki', 'WikiStart', NULL, NULL
UNION ALL SELECT 'changeset', '42/trunk', NULL, NULL
UNION ALL SELECT 'changeset', '42/trunk', 'repository', 'repo'
UNION ALL SELECT 'changeset', '43/tags', 'repository', ''
UNION ALL SELECT 'attachment', 'file.ext', 'ticket', '42'
UNION ALL SELECT 'attachment', 'file.ext', 'milestone', '42'
UNION ALL SELECT 'attachment', 'file.ext', 'wiki', 'WikiStart'
""", '')
        tc.find('<a title="View ticket" href="[^"]*?/ticket/42">#42</a>')
        tc.find('<a title="View report" href="[^"]*?/report/42">report:42</a>')
        tc.find('<a title="View milestone" href="[^"]*?/milestone/42">42</a>')
        tc.find('<a title="View wiki" href="[^"]*?/wiki/WikiStart">'
                'WikiStart</a>')
        tc.find('<a title="View changeset" href="[^"]*?/changeset/42/trunk">'
                'Changeset 42/trunk</a>')
        tc.find('<a title="View changeset" '
                'href="[^"]*?/changeset/42/trunk/repo">'
                'Changeset 42/trunk in repo</a>')
        tc.find('<a title="View changeset" href="[^"]*?/changeset/43/tags">'
                'Changeset 43/tags</a>')
        tc.find('<a title="View attachment" '
                'href="[^"]*?/attachment/ticket/42/file[.]ext">'
                'file[.]ext [(]Ticket #42[)]</a>')
        tc.find('<a title="View attachment" '
                'href="[^"]*?/attachment/milestone/42/file[.]ext">'
                'file[.]ext [(]Milestone 42[)]</a>')
        tc.find('<a title="View attachment" '
                'href="[^"]*?/attachment/wiki/WikiStart/file[.]ext">'
                'file[.]ext [(]WikiStart[)]</a>')


class RegressionTestRev5665(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Admin create version without release time (r5665)"""
        self._tester.create_version(releasetime='')


class RegressionTestRev5994(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of the column label fix in r5994"""
        env = self._testenv.get_trac_environment()
        env.config.set('ticket-custom', 'custfield', 'text')
        env.config.set('ticket-custom', 'custfield.label', 'Custom Field')
        env.config.save()
        try:
            self._testenv.restart()
            self._tester.go_to_query()
            tc.find('<label>( |\\n)*<input[^<]*value="custfield"'
                    '[^<]*/>( |\\n)*Custom Field( |\\n)*</label>', 's')
        finally:
            pass
            #env.config.set('ticket', 'restrict_owner', 'no')
            #env.config.save()
            #self._testenv.restart()


class RegressionTestTicket4447(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/4447"""
        ticketid = self._tester.create_ticket(summary="Hello World")
        
        env = self._testenv.get_trac_environment()
        env.config.set('ticket-custom', 'newfield', 'text')
        env.config.set('ticket-custom', 'newfield.label',
                       'Another Custom Field')
        env.config.save()
        try:
            self._testenv.restart()
            self._tester.go_to_ticket(ticketid)
            self._tester.add_comment(ticketid)
            tc.notfind('deleted')
            tc.notfind('set to')
        finally:
            pass


class RegressionTestTicket4630a(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/4630 a"""
        env = self._testenv.get_trac_environment()
        env.config.set('ticket', 'restrict_owner', 'yes')
        env.config.save()
        try:
            self._testenv.restart()
            # Make sure 'user' has logged in.
            self._tester.go_to_front()
            self._tester.logout()
            self._tester.login('user')
            self._tester.logout()
            self._tester.login('admin')
            ticket_id = self._tester.create_ticket()
            self._tester.go_to_ticket(ticket_id)
            tc.formvalue('propertyform', 'action', 'reassign')
            tc.find('reassign_reassign_owner')
            tc.formvalue('propertyform', 'action_reassign_reassign_owner', 'user')
            tc.submit('submit')
        finally:
            # Undo the config change for now since this (failing)
            # regression test causes problems for later tests.
            env.config.set('ticket', 'restrict_owner', 'no')
            env.config.save()
            self._testenv.restart()


class RegressionTestTicket4630b(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/4630 b"""
        # NOTE: this must be run after RegressionTestTicket4630 (user must
        # have logged in)
        from trac.perm import PermissionSystem
        env = self._testenv.get_trac_environment()
        perm = PermissionSystem(env)
        users = perm.get_users_with_permission('TRAC_ADMIN')
        self.assertEqual(users, ['admin'])
        users = perm.get_users_with_permission('TICKET_MODIFY')
        self.assertEqual(users, ['admin', 'user'])


class RegressionTestTicket5022(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/5022
        """
        summary = 'RegressionTestTicket5022'
        ticket_id = self._tester.create_ticket(summary=summary)
        tc.go(self._tester.url + '/newticket?id=%s' % ticket_id)
        tc.notfind(summary)


class RegressionTestTicket5394a(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/5394 a
        Order user list alphabetically in (re)assign action
        """
        # set restrict_owner config
        env = self._testenv.get_trac_environment()
        env.config.set('ticket', 'restrict_owner', 'yes')
        env.config.save()
        self._testenv.restart()

        self._tester.go_to_front()
        self._tester.logout()

        test_users = ['alice', 'bob', 'jane', 'john', 'charlie', 'alan',
                      'zorro']
        # Apprently it takes a sec for the new user to be recognized by the
        # environment.  So we add all the users, then log in as the users
        # in a second loop.  This should be faster than adding a sleep(1)
        # between the .adduser and .login steps.
        for user in test_users:
            self._testenv.adduser(user)
        for user in test_users:
            self._tester.login(user)
            self._tester.logout()

        self._tester.login('admin')

        ticketid = self._tester.create_ticket("regression test 5394a")
        self._tester.go_to_ticket(ticketid)

        options = 'id="action_reassign_reassign_owner">' + \
            ''.join(['<option[^>]*>%s</option>' % user for user in
                     sorted(test_users + ['admin', 'user'])])
        tc.find(options, 's')
        # We don't have a good way to fully delete a user from the Trac db.
        # Once we do, we may want to cleanup our list of users here.


class RegressionTestTicket5394b(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/5394 b
        Order user list alphabetically on new ticket page
        """
        # Must run after RegressionTestTicket5394a
        self._tester.go_to_front()
        tc.follow('New Ticket')
        tc.find('Create New Ticket')

        test_users = ['alice', 'bob', 'jane', 'john', 'charlie', 'alan',
                      'zorro']
        options = 'id="field-owner"[^>]*>[[:space:]]*<option/>.*' + \
            '.*'.join(['<option[^>]*>%s</option>' % user for user in
                     sorted(test_users + ['admin', 'user'])])
        options = '.*'.join(sorted(test_users + ['admin', 'user']))
        tc.find(options, 's')


# TODO: this should probably be changed to be a testsuite derived from
# TestSetup
class RegressionTestTicket5497prep(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/5497 prep
        When the component is changed, the owner should update to the
        default owner of the component.
        If component is changed and the owner is changed (reassigned action
        for open tickets in the basic workflow), the owner should be the
        specified owner, not the owner of the component.
        """
        # The default owner for the component we're using for this testcase
        # is 'user', and we'll manually assign to 'admin'.
        self._tester.create_component('regression5497', 'user')

class RegressionTestTicket5497a(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/5497 a
        Open ticket, component changed, owner not changed"""
        ticketid = self._tester.create_ticket("regression test 5497a")
        self._tester.go_to_ticket(ticketid)
        tc.formvalue('propertyform', 'field-component', 'regression5497')
        tc.submit('submit')
        tc.find(regex_owned_by('user'))

class RegressionTestTicket5497b(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/5497 b
        Open ticket, component changed, owner changed"""
        ticketid = self._tester.create_ticket("regression test 5497b")
        self._tester.go_to_ticket(ticketid)
        tc.formvalue('propertyform', 'field-component', 'regression5497')
        tc.formvalue('propertyform', 'action', 'reassign')
        tc.formvalue('propertyform', 'action_reassign_reassign_owner', 'admin')
        tc.submit('submit')
        tc.notfind(regex_owned_by('user'))
        tc.find(regex_owned_by('admin'))

class RegressionTestTicket5497c(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/5497 c
        New ticket, component changed, owner not changed"""
        ticketid = self._tester.create_ticket("regression test 5497c",
            {'component':'regression5497'})
        self._tester.go_to_ticket(ticketid)
        tc.find(regex_owned_by('user'))

class RegressionTestTicket5497d(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/5497 d
        New ticket, component changed, owner changed"""
        ticketid = self._tester.create_ticket("regression test 5497d",
            {'component':'regression5497', 'owner':'admin'})
        self._tester.go_to_ticket(ticketid)
        tc.find(regex_owned_by('admin'))


class RegressionTestTicket5602(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/5602"""
        # Create a set of tickets, and assign them all to a milestone
        milestone = self._tester.create_milestone()
        ids = [self._tester.create_ticket() for x in range(5)]
        [self._tester.ticket_set_milestone(x, milestone) for x in ids]
        # Need a ticket in each state: new, assigned, accepted, closed,
        # reopened
        # leave ids[0] as new
        # make ids[1] be assigned
        self._tester.go_to_ticket(ids[1])
        tc.formvalue('propertyform', 'action', 'reassign')
        tc.formvalue('propertyform', 'action_reassign_reassign_owner', 'admin')
        tc.submit('submit')
        # make ids[2] be accepted
        self._tester.go_to_ticket(ids[2])
        tc.formvalue('propertyform', 'action', 'accept')
        tc.submit('submit')
        # make ids[3] be closed
        self._tester.go_to_ticket(ids[3])
        tc.formvalue('propertyform', 'action', 'resolve')
        tc.formvalue('propertyform', 'action_resolve_resolve_resolution', 'fixed')
        tc.submit('submit')
        # make ids[4] be reopened
        self._tester.go_to_ticket(ids[4])
        tc.formvalue('propertyform', 'action', 'resolve')
        tc.formvalue('propertyform', 'action_resolve_resolve_resolution', 'fixed')
        tc.submit('submit')
        # FIXME: we have to wait a second to avoid "IntegrityError: columns
        # ticket, time, field are not unique"
        time.sleep(1)
        tc.formvalue('propertyform', 'action', 'reopen')
        tc.submit('submit')
        tc.show()
        tc.notfind("Python Traceback")

        # Go to the milestone and follow the links to the closed and active
        # tickets.
        tc.go(self._tester.url + "/roadmap")
        tc.follow(milestone)

        tc.follow("closed:")
        tc.find("Resolution:[ \t\n]+fixed")

        tc.back()
        tc.follow("active:")
        tc.find("Status:[ \t\n]+new")
        tc.find("Status:[ \t\n]+assigned")
        tc.find("Status:[ \t\n]+accepted")
        tc.notfind("Status:[ \t\n]+closed")
        tc.find("Status:[ \t\n]+reopened")


class RegressionTestTicket5687(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/5687"""
        self._tester.logout()
        self._tester.login('user')
        ticketid = self._tester.create_ticket()
        self._tester.logout()
        self._tester.login('admin')


class RegressionTestTicket5930(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/5930
        TypeError: from_string() takes exactly 3 non-keyword arguments (4
        given)
        Caused by a saved query
        """
        self._tester.create_report('Saved Query', 'query:version=1.0', '')
        tc.notfind(internal_error)
        # TODO: Add a testcase for the following:
        # Can you also throw in addition of a 1.0 ticket and a 2.0 ticket
        # as part of the demo env, then see that only the correct one shows
        # up in the report?


class RegressionTestTicket6048(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/6048"""
        # Setup the DeleteTicket plugin
        plugin = open(os.path.join(self._testenv.command_cwd, 'sample-plugins',
                                   'workflow', 'DeleteTicket.py')).read()
        open(os.path.join(self._testenv.tracdir, 'plugins', 'DeleteTicket.py'),
             'w').write(plugin)
        env = self._testenv.get_trac_environment()
        prevconfig = env.config.get('ticket', 'workflow')
        env.config.set('ticket', 'workflow',
                       prevconfig + ',DeleteTicketActionController')
        env.config.save()
        env = self._testenv.get_trac_environment() # reload environment

        # Create a ticket and delete it
        ticket_id = self._tester.create_ticket(
            summary='RegressionTestTicket6048')
        # (Create a second ticket so that the ticket id does not get reused
        # and confuse the tester object.)
        self._tester.create_ticket(summary='RegressionTestTicket6048b')
        self._tester.go_to_ticket(ticket_id)
        tc.find('delete ticket')
        tc.formvalue('propertyform', 'action', 'delete')
        tc.submit('submit')

        self._tester.go_to_ticket(ticket_id)
        tc.find('Error: Invalid ticket number')
        tc.find('Ticket %s does not exist.' % ticket_id)

        # Remove the DeleteTicket plugin
        env.config.set('ticket', 'workflow', prevconfig)
        env.config.save()
        env = self._testenv.get_trac_environment() # reload environment
        for ext in ('py', 'pyc', 'pyo'):
            filename = os.path.join(self._testenv.tracdir, 'plugins',
                                    'DeleteTicket.%s' % ext)
            if os.path.exists(filename):
                os.unlink(filename)


class RegressionTestTicket6747(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/6747"""
        env = self._testenv.get_trac_environment()
        env.config.set('ticket-workflow', 'resolve.operations',
                       'set_resolution,set_owner')
        env.config.set('ticket-workflow', 'resolve.set_owner',
                       'a_specified_owner')
        env.config.save()

        try:
            self._testenv.restart()

            ticket_id = self._tester.create_ticket("RegressionTestTicket6747")
            self._tester.go_to_ticket(ticket_id)
            tc.find("a_specified_owner")
            tc.notfind("a_specified_owneras")

        finally:
            # Undo the config change to avoid causing problems for later
            # tests.
            env.config.set('ticket-workflow', 'resolve.operations',
                           'set_resolution')
            env.config.remove('ticket-workflow', 'resolve.set_owner')
            env.config.save()
            self._testenv.restart()


class RegressionTestTicket6879a(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/6879 a

        Make sure that previewing a close does not make the available actions
        be those for the close status.
        """
        # create a ticket, then preview resolving the ticket twice
        ticket_id = self._tester.create_ticket("RegressionTestTicket6879 a")
        self._tester.go_to_ticket(ticket_id)
        tc.formvalue('propertyform', 'action', 'resolve')
        tc.formvalue('propertyform', 'action_resolve_resolve_resolution', 'fixed')
        tc.submit('preview')
        tc.formvalue('propertyform', 'action', 'resolve')
        tc.submit('preview')


class RegressionTestTicket6879b(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/6879 a

        Make sure that previewing a close does not make the available actions
        be those for the close status.
        """
        # create a ticket, then preview resolving the ticket twice
        ticket_id = self._tester.create_ticket("RegressionTestTicket6879 b")
        self._tester.go_to_ticket(ticket_id)
        tc.formvalue('propertyform', 'action', 'resolve')
        tc.formvalue('propertyform', 'action_resolve_resolve_resolution', 'fixed')
        tc.submit('preview')
        tc.formvalue('propertyform', 'action', 'resolve')
        tc.submit('submit')


class RegressionTestTicket6912a(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/6912 a"""
        try:
            self._tester.create_component(name='RegressionTestTicket6912a',
                                          user='')
        except twill.utils.ClientForm.ItemNotFoundError, e:
            raise twill.errors.TwillAssertionError(e)


class RegressionTestTicket6912b(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/6912 b"""
        self._tester.create_component(name='RegressionTestTicket6912b',
                                      user='admin')
        tc.follow('RegressionTestTicket6912b')
        try:
            tc.formvalue('modcomp', 'owner', '')
        except twill.utils.ClientForm.ItemNotFoundError, e:
            raise twill.errors.TwillAssertionError(e)
        tc.formvalue('modcomp', 'save', 'Save')
        tc.submit()
        tc.find('RegressionTestTicket6912b</a>[ \n\t]*</td>[ \n\t]*'
                '<td class="owner"></td>', 's')


class RegressionTestTicket7821group(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/7821 group"""
        env = self._testenv.get_trac_environment()
        saved_default_query = env.config.get('query', 'default_query')
        default_query = 'status!=closed&order=status&group=status&max=42' \
                        '&desc=1&groupdesc=1&col=summary|status|cc' \
                        '&cc~=$USER'
        env.config.set('query', 'default_query', default_query)
        env.config.save()
        try:
            self._testenv.restart()
            self._tester.create_ticket('RegressionTestTicket7821 group')
            self._tester.go_to_query()
            # $USER
            tc.find('<input type="text" name="0_cc" value="admin"'
                    ' size="[0-9]+" />')
            # col
            tc.find('<input type="checkbox" name="col" value="summary"'
                    ' checked="checked" />')
            tc.find('<input type="checkbox" name="col" value="owner" />')
            tc.find('<input type="checkbox" name="col" value="status"'
                    ' checked="checked" />')
            tc.find('<input type="checkbox" name="col" value="cc"'
                    ' checked="checked" />')
            # group
            tc.find('<option selected="selected" value="status">Status'
                    '</option>')
            # groupdesc
            tc.find('<input type="checkbox" name="groupdesc" id="groupdesc"'
                    ' checked="checked" />')
            # max
            tc.find('<input type="text" name="max" id="max" size="[0-9]*?"'
                    ' value="42" />')
            # col in results
            tc.find('<a title="Sort by Ticket [(]ascending[)]" ')
            tc.find('<a title="Sort by Summary [(]ascending[)]" ')
            tc.find('<a title="Sort by Status [(]ascending[)]" ')
            tc.find('<a title="Sort by Cc [(]ascending[)]" ')
            tc.notfind('<a title="Sort by Owner "')
        finally:
            env.config.set('query', 'default_query', saved_default_query)
            env.config.save()
            self._testenv.restart()


class RegressionTestTicket7821var(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/7821 var"""
        env = self._testenv.get_trac_environment()
        saved_default_query = env.config.get('query', 'default_query')
        saved_restrict_owner = env.config.get('ticket', 'restrict_owner')
        default_query = '?status=!closed&cc=~$USER&owner=$USER'
        env.config.set('query', 'default_query', default_query)
        env.config.set('ticket', 'restrict_owner', 'no')
        env.config.save()
        try:
            self._testenv.restart()
            self._tester.create_ticket('RegressionTestTicket7821 var')
            self._tester.go_to_query()
            # $USER in default_query
            tc.find('<input type="text" name="0_owner" value="admin"'
                    ' size="[0-9]+" />')
            tc.find('<input type="text" name="0_cc" value="admin"'
                    ' size="[0-9]+" />')
            # query:owner=$USER&or&cc~=$USER
            tc.go(self._tester.url + \
                  '/intertrac/query:owner=$USER&or&cc~=$USER')
            tc.find('<input type="text" name="0_owner" value="admin"'
                    ' size="[0-9]+" />')
            tc.find('<input type="text" name="1_cc" value="admin"'
                    ' size="[0-9]+" />')
        finally:
            env.config.set('query', 'default_query', saved_default_query)
            env.config.set('ticket', 'restrict_owner', saved_restrict_owner)
            env.config.save()
            self._testenv.restart()


class RegressionTestTicket8247(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/8247
        Author field of ticket comment corresponding to the milestone removal
        was always 'anonymous'."""
        name = "MilestoneRemove"
        self._tester.create_milestone(name)
        id = self._tester.create_ticket(info={'milestone': name})
        ticket_url = self._tester.url + "/ticket/%d" % id
        tc.go(ticket_url)
        tc.find(name)
        tc.go(self._tester.url + "/admin/ticket/milestones")
        tc.formvalue('milestone_table', 'sel', name)
        tc.submit('remove')
        tc.go(ticket_url)
        tc.find('<strong>Milestone</strong>[ \n\t]*<em>%s</em> deleted' % name)
        tc.find('Changed <a.*</a> ago by admin')
        tc.notfind('anonymous')


class RegressionTestTicket8861(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/8816
        When creating a milestone with an already existing name, you get
        a warning. After changing the name you will find that the original
        milestone with that name is renamed instead of a new one being
        created."""
        name = "8861Milestone"
        self._tester.create_milestone(name)
        tc.go(self._tester.url + "/milestone?action=new")
        tc.formvalue('edit', 'name', name)
        tc.submit('Add milestone')
        tc.find('Milestone "%s" already exists' % name)
        tc.formvalue('edit', 'name', name + '__')
        tc.submit('Add milestone')
        tc.go(self._tester.url + "/roadmap")
        tc.find('Milestone: <em>%s</em>' % name)
        tc.find('Milestone: <em>%s</em>' % (name + '__'))


class RegressionTestTicket9084(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/9084"""
        ticketid = self._tester.create_ticket()
        self._tester.add_comment(ticketid)
        self._tester.go_to_ticket(ticketid)
        tc.formvalue('reply-to-comment-1', 'replyto', '1')
        tc.submit('Reply')
        tc.formvalue('propertyform', 'comment', random_sentence(3))
        tc.submit('Submit changes')
        tc.notfind('AssertionError')


def functionalSuite(suite=None):
    if not suite:
        import trac.tests.functional.testcases
        suite = trac.tests.functional.testcases.functionalSuite()
    suite.addTest(TestTickets())
    suite.addTest(TestTicketPreview())
    suite.addTest(TestTicketNoSummary())
    suite.addTest(TestTicketAltFormats())
    suite.addTest(TestTicketCSVFormat())
    suite.addTest(TestTicketTabFormat())
    suite.addTest(TestTicketRSSFormat())
    suite.addTest(TestTicketSearch())
    suite.addTest(TestNonTicketSearch())
    suite.addTest(TestTicketHistory())
    suite.addTest(TestTicketHistoryDiff())
    suite.addTest(TestTicketQueryLinks())
    suite.addTest(TestTicketQueryOrClause())
    suite.addTest(TestTimelineTicketDetails())
    suite.addTest(TestAdminComponent())
    suite.addTest(TestAdminComponentDuplicates())
    suite.addTest(TestAdminComponentRemoval())
    suite.addTest(TestAdminComponentNonRemoval())
    suite.addTest(TestAdminComponentDefault())
    suite.addTest(TestAdminComponentDetail())
    suite.addTest(TestAdminMilestone())
    suite.addTest(TestAdminMilestoneSpace())
    suite.addTest(TestAdminMilestoneDuplicates())
    suite.addTest(TestAdminMilestoneDetail())
    suite.addTest(TestAdminMilestoneDue())
    suite.addTest(TestAdminMilestoneDetailDue())
    suite.addTest(TestAdminMilestoneCompleted())
    suite.addTest(TestAdminMilestoneCompletedFuture())
    suite.addTest(TestAdminMilestoneRemove())
    suite.addTest(TestAdminMilestoneRemoveMulti())
    suite.addTest(TestAdminMilestoneNonRemoval())
    suite.addTest(TestAdminMilestoneDefault())
    suite.addTest(TestAdminPriority())
    suite.addTest(TestAdminPriorityModify())
    suite.addTest(TestAdminPriorityRemove())
    suite.addTest(TestAdminPriorityRemoveMulti())
    suite.addTest(TestAdminPriorityNonRemoval())
    suite.addTest(TestAdminPriorityDefault())
    suite.addTest(TestAdminPriorityDetail())
    suite.addTest(TestAdminPriorityRenumber())
    suite.addTest(TestAdminPriorityRenumberDup())
    suite.addTest(TestAdminResolution())
    suite.addTest(TestAdminResolutionDuplicates())
    suite.addTest(TestAdminSeverity())
    suite.addTest(TestAdminSeverityDuplicates())
    suite.addTest(TestAdminType())
    suite.addTest(TestAdminTypeDuplicates())
    suite.addTest(TestAdminVersion())
    suite.addTest(TestAdminVersionDuplicates())
    suite.addTest(TestAdminVersionDetail())
    suite.addTest(TestAdminVersionDetailTime())
    suite.addTest(TestAdminVersionDetailCancel())
    suite.addTest(TestAdminVersionRemove())
    suite.addTest(TestAdminVersionRemoveMulti())
    suite.addTest(TestAdminVersionNonRemoval())
    suite.addTest(TestAdminVersionDefault())
    suite.addTest(TestNewReport())
    suite.addTest(TestReportRealmDecoration())
    suite.addTest(RegressionTestRev5665())
    suite.addTest(RegressionTestRev5994())

    suite.addTest(RegressionTestTicket4447())
    suite.addTest(RegressionTestTicket4630a())
    suite.addTest(RegressionTestTicket4630b())
    suite.addTest(RegressionTestTicket5022())
    suite.addTest(RegressionTestTicket5394a())
    suite.addTest(RegressionTestTicket5394b())
    suite.addTest(RegressionTestTicket5497prep())
    suite.addTest(RegressionTestTicket5497a())
    suite.addTest(RegressionTestTicket5497b())
    suite.addTest(RegressionTestTicket5497c())
    suite.addTest(RegressionTestTicket5497d())
    suite.addTest(RegressionTestTicket5602())
    suite.addTest(RegressionTestTicket5687())
    suite.addTest(RegressionTestTicket5930())
    suite.addTest(RegressionTestTicket6048())
    suite.addTest(RegressionTestTicket6747())
    suite.addTest(RegressionTestTicket6879a())
    suite.addTest(RegressionTestTicket6879b())
    suite.addTest(RegressionTestTicket6912a())
    suite.addTest(RegressionTestTicket6912b())
    suite.addTest(RegressionTestTicket7821group())
    suite.addTest(RegressionTestTicket7821var())
    suite.addTest(RegressionTestTicket8247())
    suite.addTest(RegressionTestTicket8861())
    suite.addTest(RegressionTestTicket9084())

    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='functionalSuite')
