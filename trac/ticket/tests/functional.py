#!/usr/bin/python
import os

from datetime import datetime, timedelta

from trac.tests.functional import *
from trac.util.datefmt import utc, format_date

class TestTickets(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Create a ticket, comment on it, and attach a file"""
        # TODO: this should be split into multiple tests
        summary = random_sentence(5)
        ticketid = self._tester.create_ticket(summary)
        self._tester.create_ticket()
        self._tester.add_comment(ticketid)
        self._tester.attach_file_to_ticket(ticketid)


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
        tc.find('<option selected="selected">%s</option>' % name)
        

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
        cdate_string = format_date(cdate, tzinfo=utc)
        tc.formvalue('modifymilestone', 'completeddate', cdate_string)
        tc.submit('save')
        tc.find('Completion date may not be in the future')
        # And make sure it wasn't marked as completed.
        self._tester.go_to_roadmap()
        tc.find(name)


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
        tc.find('Resolution %s already exists' % name)


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
        tc.find('Severity %s already exists' % name)


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
        tc.find('Type %s already exists' % name)


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
            tc.formvalue('propform', 'action', 'reassign')
            tc.find('reassign_reassign_owner')
            tc.formvalue('propform', 'action_reassign_reassign_owner', 'user')
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
        summary='RegressionTestTicket5022'
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
        tc.formvalue('propform', 'field-component', 'regression5497')
        tc.submit('submit')
        tc.find(regex_owned_by('user'))

class RegressionTestTicket5497b(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/5497 b
        Open ticket, component changed, owner changed"""
        ticketid = self._tester.create_ticket("regression test 5497b")
        self._tester.go_to_ticket(ticketid)
        tc.formvalue('propform', 'field-component', 'regression5497')
        tc.formvalue('propform', 'action', 'reassign')
        tc.formvalue('propform', 'action_reassign_reassign_owner', 'admin')
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
        tc.formvalue('propform', 'action', 'reassign')
        tc.formvalue('propform', 'action_reassign_reassign_owner', 'admin')
        tc.submit('submit')
        # make ids[2] be accepted
        self._tester.go_to_ticket(ids[2])
        tc.formvalue('propform', 'action', 'accept')
        tc.submit('submit')
        # make ids[3] be closed
        self._tester.go_to_ticket(ids[3])
        tc.formvalue('propform', 'action', 'resolve')
        tc.formvalue('propform', 'action_resolve_resolve_resolution', 'fixed')
        tc.submit('submit')
        # make ids[4] be reopened
        self._tester.go_to_ticket(ids[4])
        tc.formvalue('propform', 'action', 'resolve')
        tc.formvalue('propform', 'action_resolve_resolve_resolution', 'fixed')
        tc.submit('submit')
        # FIXME: we have to wait a second to avoid "IntegrityError: columns
        # ticket, time, field are not unique"
        time.sleep(1)
        tc.formvalue('propform', 'action', 'reopen')
        tc.submit('submit')
        tc.show()
        tc.notfind("Python Traceback")

        # Go to the milestone and follow the links to the closed and active
        # tickets.
        tc.go(self._tester.url + "/roadmap")
        tc.follow(milestone)

        tc.follow("Closed tickets:")
        tc.find("Resolution:[ \t\n]+fixed")

        tc.back()
        tc.follow("Active tickets:")
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
        tc.formvalue('propform', 'action', 'delete')
        tc.submit('submit')

        self._tester.go_to_ticket(ticket_id)
        tc.find('Error: Invalid Ticket Number')
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
        tc.formvalue('propform', 'action', 'resolve')
        tc.formvalue('propform', 'action_resolve_resolve_resolution', 'fixed')
        tc.submit('preview')
        tc.formvalue('propform', 'action', 'resolve')
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
        tc.formvalue('propform', 'action', 'resolve')
        tc.formvalue('propform', 'action_resolve_resolve_resolution', 'fixed')
        tc.submit('preview')
        tc.formvalue('propform', 'action', 'resolve')
        tc.submit('submit')


class RegressionTestTicket6912a(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/6912 a"""
        try:
            self._tester.create_component(name='RegressionTestTicket6912a',
                                          user='')
        except twill.utils.mechanize.ClientForm.ItemNotFoundError, e:
            raise twill.errors.TwillAssertionError(e)


class RegressionTestTicket6912b(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/6912 b"""
        self._tester.create_component(name='RegressionTestTicket6912b',
                                      user='admin')
        tc.follow('RegressionTestTicket6912b')
        try:
            tc.formvalue('modcomp', 'owner', '')
        except twill.utils.mechanize.ClientForm.ItemNotFoundError, e:
            raise twill.errors.TwillAssertionError(e)
        tc.formvalue('modcomp', 'save', 'Save')
        tc.submit()
        tc.find('RegressionTestTicket6912b</a>[ \n\t]*</td>[ \n\t]*'
                '<td class="owner"></td>', 's')


def functionalSuite(suite=None):
    if not suite:
        import trac.tests.functional.testcases
        suite = trac.tests.functional.testcases.functionalSuite()
    suite.addTest(TestTickets())
    suite.addTest(TestAdminComponent())
    suite.addTest(TestAdminComponentDuplicates())
    suite.addTest(TestAdminComponentRemoval())
    suite.addTest(TestAdminComponentNonRemoval())
    suite.addTest(TestAdminComponentDefault())
    suite.addTest(TestAdminMilestone())
    suite.addTest(TestAdminMilestoneSpace())
    suite.addTest(TestAdminMilestoneDuplicates())
    suite.addTest(TestAdminMilestoneDetail())
    suite.addTest(TestAdminMilestoneDue())
    suite.addTest(TestAdminMilestoneCompleted())
    suite.addTest(TestAdminMilestoneCompletedFuture())
    suite.addTest(TestAdminPriority())
    suite.addTest(TestAdminPriorityDuplicates())
    suite.addTest(TestAdminResolution())
    suite.addTest(TestAdminResolutionDuplicates())
    suite.addTest(TestAdminSeverity())
    suite.addTest(TestAdminSeverityDuplicates())
    suite.addTest(TestAdminType())
    suite.addTest(TestAdminTypeDuplicates())
    suite.addTest(TestAdminVersion())
    suite.addTest(TestAdminVersionDuplicates())
    suite.addTest(TestAdminVersionDetail())
    suite.addTest(TestNewReport())
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

    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='functionalSuite')
