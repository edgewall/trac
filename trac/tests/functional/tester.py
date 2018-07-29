# -*- coding: utf-8 -*-
#
# Copyright (C) 2008-2018 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

"""The :class:`FunctionalTester` object provides a higher-level interface to
working with a Trac environment to make test cases more succinct.
"""

import re

from genshi.builder import tag
from trac.tests.functional import internal_error
from trac.tests.functional.better_twill import tc, b
from trac.tests.contentgen import random_page, random_sentence, random_word, \
                                  random_unique_camel
from trac.util.text import to_utf8, unicode_quote

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO


class FunctionalTester(object):
    """Provides a library of higher-level operations for interacting with a
    test environment.

    It makes assumptions such as knowing what ticket number is next, so
    avoid doing things manually in a :class:`FunctionalTestCase` when you can.
    """

    def __init__(self, url):
        """Create a :class:`FunctionalTester` for the given Trac URL and
        Subversion URL"""
        self.url = url
        self.ticketcount = 0

        # Connect, and login so we can run tests.
        self.go_to_front()
        self.login('admin')

    def login(self, username):
        """Login as the given user"""
        username = to_utf8(username)
        tc.add_auth("", self.url, username, username)
        self.go_to_front()
        tc.find("Login")
        tc.follow(r"\bLogin\b")
        # We've provided authentication info earlier, so this should
        # redirect back to the base url.
        tc.find('logged in as[ \t\n]+<span class="trac-author-user">%s</span>'
                % username)
        tc.find("Logout")
        tc.url(self.url)
        tc.notfind(internal_error)

    def logout(self):
        """Logout"""
        tc.submit('logout', 'logout')
        tc.notfind(internal_error)
        tc.notfind('logged in as')

    def create_ticket(self, summary=None, info=None):
        """Create a new (random) ticket in the test environment.  Returns
        the new ticket number.

        :param summary:
            may optionally be set to the desired summary
        :param info:
            may optionally be set to a dictionary of field value pairs for
            populating the ticket.  ``info['summary']`` overrides summary.

        `summary` and `description` default to randomly-generated values.
        """
        info = info or {}
        self.go_to_front()
        tc.follow(r"\bNew Ticket\b")
        tc.notfind(internal_error)
        if summary is None:
            summary = random_sentence(5)
        tc.formvalue('propertyform', 'field_summary', summary)
        tc.formvalue('propertyform', 'field_description', random_page())
        if 'owner' in info:
            tc.formvalue('propertyform', 'action', 'assign')
            tc.formvalue('propertyform',
                         'action_create_and_assign_reassign_owner',
                         info.pop('owner'))
        for field, value in info.items():
            tc.formvalue('propertyform', 'field_%s' % field, value)
        tc.submit('submit')
        tc.notfind(internal_error)
        # we should be looking at the newly created ticket
        tc.url(self.url + '/ticket/%s' % (self.ticketcount + 1))
        # Increment self.ticketcount /after/ we've verified that the ticket
        # was created so a failure does not trigger spurious later
        # failures.
        self.ticketcount += 1

        return self.ticketcount

    def quickjump(self, search):
        """Do a quick search to jump to a page."""
        tc.formvalue('search', 'q', search)
        tc.submit()
        tc.notfind(internal_error)

    def go_to_url(self, url):
        tc.go(url)
        tc.url(re.escape(url))
        tc.notfind(internal_error)

    def go_to_front(self):
        """Go to the Trac front page"""
        self.go_to_url(self.url)

    def go_to_ticket(self, ticketid=None):
        """Surf to the page for the given ticket ID, or to the NewTicket page
        if `ticketid` is not specified or is `None`. If `ticketid` is
        specified, it assumes the ticket exists."""
        if ticketid is not None:
            ticket_url = self.url + '/ticket/%s' % ticketid
        else:
            ticket_url = self.url + '/newticket'
        self.go_to_url(ticket_url)
        tc.url(ticket_url + '$')

    def go_to_wiki(self, name, version=None):
        """Surf to the wiki page. By default this will be the latest version
        of the page.

        :param name: name of the wiki page.
        :param version: version of the wiki page.
        """
        # Used to go based on a quickjump, but if the wiki pagename isn't
        # camel case, that won't work.
        wiki_url = self.url + '/wiki/%s' % name
        if version:
            wiki_url += '?version=%s' % version
        self.go_to_url(wiki_url)

    def go_to_timeline(self):
        """Surf to the timeline page."""
        self.go_to_front()
        tc.follow(r"\bTimeline\b")
        tc.url(self.url + '/timeline')

    def go_to_view_tickets(self, href='report'):
        """Surf to the View Tickets page. By default this will be the Reports
        page, but 'query' can be specified for the `href` argument to support
        non-default configurations."""
        self.go_to_front()
        tc.follow(r"\bView Tickets\b")
        tc.url(self.url + '/' + href.lstrip('/'))

    def go_to_query(self):
        """Surf to the custom query page."""
        self.go_to_front()
        tc.follow(r"\bView Tickets\b")
        tc.follow(r"\bNew Custom Query\b")
        tc.url(self.url + '/query')

    def go_to_admin(self, panel_label=None):
        """Surf to the webadmin page. Continue surfing to a specific
        admin page if `panel_label` is specified."""
        self.go_to_front()
        tc.follow(r"\bAdmin\b")
        tc.url(self.url + '/admin')
        if panel_label is not None:
            tc.follow(r"\b%s\b" % panel_label)

    def go_to_roadmap(self):
        """Surf to the roadmap page."""
        self.go_to_front()
        tc.follow(r"\bRoadmap\b")
        tc.url(self.url + '/roadmap')

    def go_to_milestone(self, name):
        """Surf to the specified milestone page. Assumes milestone exists."""
        self.go_to_roadmap()
        tc.follow(r"\bMilestone: %s\b" % name)
        tc.url(self.url + '/milestone/%s' % name)

    def go_to_report(self, id, args=None):
        """Surf to the specified report.

        Assumes the report exists. Report variables will be appended if
        specified.

        :param id: id of the report
        :param args: may optionally specify a dictionary of arguments to
                     be encoded as a query string
        """
        report_url = self.url + "/report/%s" % id
        if args:
            arglist = []
            for param, value in args.items():
                arglist.append('%s=%s' % (param.upper(), unicode_quote(value)))
            report_url += '?' + '&'.join(arglist)
        tc.go(report_url)
        tc.url(report_url.encode('string-escape').replace('?', '\?'))

    def go_to_preferences(self, panel_label=None):
        """Surf to the preferences page. Continue surfing to a specific
        preferences panel if `panel_label` is specified."""
        self.go_to_front()
        tc.follow(r"\bPreferences\b")
        tc.url(self.url + '/prefs')
        if panel_label is not None:
            tc.follow(r"\b%s\b" % panel_label)

    def add_comment(self, ticketid, comment=None):
        """Adds a comment to the given ticket ID, assumes ticket exists."""
        self.go_to_ticket(ticketid)
        if comment is None:
            comment = random_sentence()
        tc.formvalue('propertyform', 'comment', comment)
        tc.submit("submit")
        # Verify we're where we're supposed to be.
        # The fragment is stripped since Python 2.7.1, see:
        # http://trac.edgewall.org/ticket/9990#comment:18
        tc.url(self.url + '/ticket/%s(?:#comment:.*)?$' % ticketid)
        return comment

    def attach_file_to_ticket(self, ticketid, data=None, filename=None,
                              description=None, replace=False,
                              content_type=None):
        """Attaches a file to the given ticket id, with random data if none is
        provided.  Assumes the ticket exists.
        """
        self.go_to_ticket(ticketid)
        return self._attach_file_to_resource('ticket', ticketid, data,
                                             filename, description,
                                             replace, content_type)

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

    def create_wiki_page(self, name=None, content=None, comment=None):
        """Creates a wiki page, with a random unique CamelCase name if none
        is provided, random content if none is provided and a random comment
        if none is provided.  Returns the name of the wiki page.
        """
        if name is None:
            name = random_unique_camel()
        if content is None:
            content = random_page()
        self.go_to_wiki(name)
        tc.find("The page %s does not exist." % tag.strong(name))

        self.edit_wiki_page(name, content, comment)

        # verify the event shows up in the timeline
        self.go_to_timeline()
        tc.formvalue('prefs', 'wiki', True)
        tc.submit()
        tc.find(name + ".*created")

        self.go_to_wiki(name)

        return name

    def edit_wiki_page(self, name, content=None, comment=None):
        """Edits a wiki page, with random content is none is provided.
        and a random comment if none is provided. Returns the content.
        """
        if content is None:
            content = random_page()
        if comment is None:
            comment = random_sentence()
        self.go_to_wiki(name)
        tc.formvalue('modifypage', 'action', 'edit')
        tc.submit()
        tc.formvalue('edit', 'text', content)
        tc.formvalue('edit', 'comment', comment)
        tc.submit('save')
        page_url = self.url + '/wiki/%s' % name
        tc.url(page_url+'$')

        return content

    def attach_file_to_wiki(self, name, data=None, filename=None,
                            description=None, replace=False,
                            content_type=None):
        """Attaches a file to the given wiki page, with random content if none
        is provided.  Assumes the wiki page exists.
        """

        self.go_to_wiki(name)
        return self._attach_file_to_resource('wiki', name, data,
                                             filename, description,
                                             replace, content_type)

    def create_milestone(self, name=None, due=None):
        """Creates the specified milestone, with a random name if none is
        provided.  Returns the name of the milestone.
        """
        if name is None:
            name = random_unique_camel()
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
        tc.follow(r"\bRoadmap\b")
        tc.url(self.url + "/roadmap")
        tc.find('Milestone:.*%s' % name)
        tc.follow(r"\b%s\b" % name)
        tc.url('%s/milestone/%s' % (self.url, unicode_quote(name)))
        if not due:
            tc.find('No date set')

        return name

    def attach_file_to_milestone(self, name, data=None, filename=None,
                                 description=None, replace=False,
                                 content_type=None):
        """Attaches a file to the given milestone, with random content if none
        is provided.  Assumes the milestone exists.
        """

        self.go_to_milestone(name)
        return self._attach_file_to_resource('milestone', name, data,
                                             filename, description,
                                             replace, content_type)

    def create_component(self, name=None, owner=None, description=None):
        """Creates the specified component, with a random camel-cased name if
        none is provided.  Returns the name."""
        if name is None:
            name = random_unique_camel()
        component_url = self.url + "/admin/ticket/components"
        tc.go(component_url)
        tc.url(component_url)
        tc.formvalue('addcomponent', 'name', name)
        if owner is not None:
            tc.formvalue('addcomponent', 'owner', owner)
        tc.submit()
        # Verify the component appears in the component list
        tc.url(component_url)
        tc.find(name)
        tc.notfind(internal_error)
        if description is not None:
            tc.follow(r"\b%s\b" % name)
            tc.formvalue('edit', 'description', description)
            tc.submit('save')
            tc.url(component_url)
            tc.find("Your changes have been saved.")
            tc.notfind(internal_error)
        # TODO: verify the component shows up in the newticket page
        return name

    def create_enum(self, kind, name=None):
        """Helper to create the specified enum (used for ``priority``,
        ``severity``, etc). If no name is given, a unique random word is used.
        The name is returned.
        """
        if name is None:
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
        """Create a new version.  The name defaults to a random camel-cased
        word if not provided."""
        version_admin = self.url + "/admin/ticket/versions"
        if name is None:
            name = random_unique_camel()
        tc.go(version_admin)
        tc.url(version_admin)
        tc.formvalue('addversion', 'name', name)
        if releasetime is not None:
            tc.formvalue('addversion', 'time', releasetime)
        tc.submit()
        tc.url(version_admin)
        tc.find(name)
        tc.notfind(internal_error)
        # TODO: verify releasetime

    def create_report(self, title, query, description):
        """Create a new report with the given title, query, and description"""
        self.go_to_front()
        tc.follow(r"\bView Tickets\b")
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
        """Set the milestone on a given ticket."""
        self.go_to_ticket(ticketid)
        tc.formvalue('propertyform', 'milestone', milestone)
        tc.submit('submit')
        # TODO: verify the change occurred.

    def _attach_file_to_resource(self, realm, name, data=None,
                                 filename=None, description=None,
                                 replace=False, content_type=None):
        """Attaches a file to a resource. Assumes the resource exists and
           has already been navigated to."""

        if data is None:
            data = random_page()
        if description is None:
            description = random_sentence()
        if filename is None:
            filename = random_word()

        tc.submit('attachfilebutton', 'attachfile')
        tc.url(self.url + r'/attachment/%s/%s/\?action=new$' % (realm, name))
        fp = StringIO(data)
        tc.formfile('attachment', 'attachment', filename,
                    content_type=content_type, fp=fp)
        tc.formvalue('attachment', 'description', description)
        if replace:
            tc.formvalue('attachment', 'replace', True)
        tc.submit()
        tc.url(self.url + r'/attachment/%s/%s/$' % (realm, name))

        return filename
