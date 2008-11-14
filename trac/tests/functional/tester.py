#!/usr/bin/python
"""The FunctionalTester object provides a higher-level interface to working
with a Trac environment to make test cases more succinct.
"""

import os
import re
from datetime import datetime, timedelta
from subprocess import call, Popen, PIPE
from tempfile import mkdtemp

from trac.tests.functional import internal_error, logfile, close_fds, rmtree
from trac.tests.functional.better_twill import tc, b
from trac.tests.contentgen import random_page, random_sentence, random_word, \
    random_unique_camel
from trac.util.datefmt import format_date, utc
from trac.util.text import unicode_quote

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

class FunctionalTester(object):
    """Provides a library of higher-level operations for interacting with a
    test environment.

    It makes assumptions such as knowing what ticket number is next, so
    avoid doing things manually in testcases when you can.
    """

    def __init__(self, url, repo_url):
        """Create a FunctionalTester for the given Trac URL and Subversion
        URL"""
        self.url = url
        self.repo_url = repo_url
        self.ticketcount = 0

        # Connect, and login so we can run tests.
        self.go_to_front()
        self.login('admin')

    def login(self, username):
        """Login as the given user"""
        tc.add_auth("", self.url, username, username)
        self.go_to_front()
        tc.find("Login")
        tc.follow("Login")
        # We've provided authentication info earlier, so this should
        # redirect back to the base url.
        tc.find("logged in as %s" % username)
        tc.find("Logout")
        tc.url(self.url)
        tc.notfind(internal_error)

    def logout(self):
        """Logout"""
        tc.follow("Logout")
        tc.notfind(internal_error)

    def create_ticket(self, summary=None, info=None):
        """Create a new (random) ticket in the test environment.  Returns
        the new ticket number.
        summary may optionally be set to the desired summary
        info may optionally be set to a dictionary of field value pairs for
        populating the ticket.
        info['summary'] overrides summary.
        summary and description default to randomly generated values.
        """
        self.go_to_front()
        tc.follow('New Ticket')
        tc.notfind(internal_error)
        if summary == None:
            summary = random_sentence(4)
        tc.formvalue('propertyform', 'field_summary', summary)
        tc.formvalue('propertyform', 'field_description', random_page())
        if info:
            for field, value in info.items():
                tc.formvalue('propertyform', 'field_%s' % field, value)
        tc.submit('submit')
        # we should be looking at the newly created ticket
        tc.url(self.url + '/ticket/%s' % (self.ticketcount + 1))
        # Increment self.ticketcount /after/ we've verified that the ticket
        # was created so a failure does not trigger spurious later
        # failures.
        self.ticketcount += 1

        # verify the ticket creation event shows up in the timeline
        self.go_to_timeline()
        tc.formvalue('prefs', 'ticket', True)
        tc.submit()
        tc.find('Ticket.*#%s.*created' % self.ticketcount)

        return self.ticketcount

    def quickjump(self, search):
        """Do a quick search to jump to a page."""
        tc.formvalue('search', 'q', search)
        tc.submit()
        tc.notfind(internal_error)

    def go_to_front(self):
        """Go to the Trac front page"""
        tc.go(self.url)
        tc.url(self.url)
        tc.notfind(internal_error)

    def go_to_ticket(self, ticketid):
        """Surf to the page for the given ticket ID.  Assumes ticket
        exists."""
        ticket_url = self.url + "/ticket/%s" % ticketid
        tc.go(ticket_url)
        tc.url(ticket_url)

    def go_to_wiki(self, name):
        """Surf to the page for the given wiki page."""
        # Used to go based on a quickjump, but if the wiki pagename isn't
        # camel case, that won't work.
        wiki_url = self.url + '/wiki/%s' % name
        tc.go(wiki_url)
        tc.url(wiki_url)

    def go_to_timeline(self):
        """Surf to the timeine page."""
        self.go_to_front()
        tc.follow('Timeline')
        tc.url(self.url + '/timeline')

    def go_to_query(self):
        """Surf to the custom query page."""
        self.go_to_front()
        tc.follow('View Tickets')
        tc.follow('Custom Query')
        tc.url(self.url + '/query')

    def go_to_admin(self):
        """Surf to the webadmin page."""
        self.go_to_front()
        tc.follow('Admin')

    def go_to_roadmap(self):
        """Surf to the roadmap page."""
        self.go_to_front()
        tc.follow('\\bRoadmap\\b')
        tc.url(self.url + '/roadmap')

    def add_comment(self, ticketid, comment=None):
        """Adds a comment to the given ticket ID, assumes ticket exists."""
        self.go_to_ticket(ticketid)
        if comment is None:
            comment = random_sentence()
        tc.formvalue('propertyform', 'comment', comment)
        tc.submit("submit")
        # Verify we're where we're supposed to be.
        tc.url(self.url + '/ticket/%s#comment:.*' % ticketid)
        return comment

    def attach_file_to_ticket(self, ticketid, data=None):
        """Attaches a file to the given ticket id.  Assumes the ticket
        exists.
        """
        if data == None:
            data = random_page()
        self.go_to_ticket(ticketid)
        # set the value to what it already is, so that twill will know we
        # want this form.
        tc.formvalue('attachfile', 'action', 'new')
        tc.submit()
        tc.url(self.url + "/attachment/ticket/" \
               "%s/\\?action=new&attachfilebutton=Attach\\+file" % ticketid)
        tempfilename = random_word()
        fp = StringIO(data)
        tc.formfile('attachment', 'attachment', tempfilename, fp=fp)
        tc.formvalue('attachment', 'description', random_sentence())
        tc.submit()
        tc.url(self.url + '/attachment/ticket/%s/$' % ticketid)

    def clone_ticket(self, ticketid):
        """Create a clone of the given ticket id using the clone button."""
        ticket_url = self.url + '/ticket/%s' % ticketid
        tc.go(ticket_url)
        tc.url(ticket_url)
        tc.formvalue('clone', 'clone', 'Clone')
        tc.submit()
        # we should be looking at the newly created ticket
        self.ticketcount += 1
        tc.url(self.url + "/ticket/%s" % self.ticketcount)
        return self.ticketcount

    def create_wiki_page(self, page, content=None):
        """Creates the specified wiki page, with random content if none is
        provided.
        """
        if content == None:
            content = random_page()
        page_url = self.url + "/wiki/" + page
        tc.go(page_url)
        tc.url(page_url)
        tc.find("Describe %s here." % page)
        tc.formvalue('modifypage', 'action', 'edit')
        tc.submit()
        tc.url(page_url + '\\?action=edit')

        tc.formvalue('edit', 'text', content)
        tc.submit('save')
        tc.url(page_url+'$')

        # verify the event shows up in the timeline
        self.go_to_timeline()
        tc.formvalue('prefs', 'wiki', True)
        tc.submit()
        tc.find(page + ".*created")

    def attach_file_to_wiki(self, name, data=None):
        """Attaches a file to the given wiki page.  Assumes the wiki page
        exists.
        """
        if data == None:
            data = random_page()
        self.go_to_wiki(name)
        # set the value to what it already is, so that twill will know we
        # want this form.
        tc.formvalue('attachfile', 'action', 'new')
        tc.submit()
        tc.url(self.url + "/attachment/wiki/" \
               "%s/\\?action=new&attachfilebutton=Attach\\+file" % name)
        tempfilename = random_word()
        fp = StringIO(data)
        tc.formfile('attachment', 'attachment', tempfilename, fp=fp)
        tc.formvalue('attachment', 'description', random_sentence())
        tc.submit()
        tc.url(self.url + '/attachment/wiki/%s/$' % name)

    def create_milestone(self, name=None, due=None):
        """Creates the specified milestone.  Returns the name of the
        milestone.
        """
        find = False
        if name == None:
            name = random_unique_camel()
            find = True
        milestone_url = self.url + "/admin/ticket/milestones"
        tc.go(milestone_url)
        tc.url(milestone_url)
        tc.formvalue('addmilestone', 'name', name)
        if due:
            # TODO: How should we deal with differences in date formats?
            tc.formvalue('addmilestone', 'duedate', due)
        tc.submit()
        tc.notfind(internal_error)
        tc.notfind('Milestone .* already exists')
        tc.url(milestone_url)
        tc.find(name)

        # Make sure it's on the roadmap.
        tc.follow('Roadmap')
        tc.url(self.url + "/roadmap")
        tc.find('Milestone:.*%s' % name)
        tc.follow(name)
        tc.url('%s/milestone/%s' % (self.url, unicode_quote(name)))
        if not due:
            tc.find('No date set')

        return name

    def create_component(self, name=None, user=None):
        """Creates the specified component"""
        if name == None:
            name = random_unique_camel()
        component_url = self.url + "/admin/ticket/components"
        tc.go(component_url)
        tc.url(component_url)
        tc.formvalue('addcomponent', 'name', name)
        if user != None:
            tc.formvalue('addcomponent', 'owner', user)
        tc.submit()
        # Verify the component appears in the component list
        tc.url(component_url)
        tc.find(name)
        tc.notfind(internal_error)
        # TODO: verify the component shows up in the newticket page

    def create_enum(self, kind, name=None):
        """Creates the specified enum.
        kind is 'priority', 'severity', etc.
        If no name is given, a unique random word is used.
        The name is returned.
        """
        if name == None:
            name = random_unique_camel()
        priority_url = self.url + "/admin/ticket/" + kind
        tc.go(priority_url)
        tc.url(priority_url)
        tc.formvalue('addenum', 'name', name)
        tc.submit()
        tc.url(priority_url)
        tc.find(name)
        tc.notfind(internal_error)
        return name

    def create_priority(self, name=None):
        """Create a new priority enum"""
        return self.create_enum('priority', name)

    def create_resolution(self, name=None):
        """Create a new resolution enum"""
        return self.create_enum('resolution', name)

    def create_severity(self, name=None):
        """Create a new severity enum"""
        return self.create_enum('severity', name)

    def create_type(self, name=None):
        """Create a new ticket type enum"""
        return self.create_enum('type', name)

    def create_version(self, name=None, releasetime=None):
        """Create a new version"""
        version_admin = self.url + "/admin/ticket/versions"
        if name == None:
            name = random_unique_camel()
        tc.go(version_admin)
        tc.url(version_admin)
        tc.formvalue('addversion', 'name', name)
        if releasetime != None:
            tc.formvalue('addversion', 'time', releasetime)
        tc.submit()
        tc.url(version_admin)
        tc.find(name)
        tc.notfind(internal_error)
        # TODO: verify releasetime

    def create_report(self, title, query, description):
        """Create a new report with the given title, query, and description"""
        self.go_to_front()
        tc.follow('View Tickets')
        tc.formvalue('create_report', 'action', 'new') # select the right form
        tc.submit()
        tc.find('New Report')
        tc.notfind(internal_error)
        tc.formvalue('edit_report', 'title', title)
        tc.formvalue('edit_report', 'description', description)
        tc.formvalue('edit_report', 'query', query)
        tc.submit()
        reportnum = b.get_url().split('/')[-1]
        # TODO: verify the url is correct
        # TODO: verify the report number is correct
        # TODO: verify the report does not cause an internal error
        # TODO: verify the title appears on the report list
        return reportnum

    def ticket_set_milestone(self, ticketid, milestone):
        """Set the milestone on a given ticket"""
        self.go_to_ticket(ticketid)
        tc.formvalue('propertyform', 'milestone', milestone)
        tc.submit('submit')
        # TODO: verify the change occurred.

    def svn_mkdir(self, paths, msg):
        # This happens with a url so no need for a working copy
        if call(['svn', '--username=admin', 'mkdir', '-m', msg]
                + [self.repo_url + '/' + d for d in paths],
                stdout=logfile, stderr=logfile, close_fds=close_fds):
            raise Exception('Failed to create directories')
 
    def svn_add(self, path, filename, data):
        tempdir = mkdtemp()
        working_copy = os.path.join(tempdir, 'wc')

        if call(['svn', 'co', self.repo_url + path,
                 working_copy], stdout=logfile, stderr=logfile,
                 close_fds=close_fds):
            raise Exception('Checkout from %s failed.' % self.repo_url)
        temppathname = os.path.join(working_copy, filename)
        f = open(temppathname, 'w')
        f.write(data)
        f.close()
        if call(['svn', 'add', filename], cwd=working_copy,
                stdout=logfile, stderr=logfile, close_fds=close_fds):
            raise Exception('Add of %s failed.' % filename)
        commit = Popen(['svn', '--username=admin', 'commit', '-m',
                        'Add %s' % filename, filename],
                       cwd=working_copy, stdout=PIPE, stderr=logfile,
                       close_fds=close_fds)
        output = commit.stdout.read()
        if commit.wait():
            raise Exception('Commit failed.')
        try:
            revision = re.search(r'Committed revision ([0-9]+)\.',
                                 output).group(1)
        except Exception, e:
            args = e.args + (output, )
            raise Exception(*args)
        rmtree(tempdir) # Cleanup
        return int(revision)

