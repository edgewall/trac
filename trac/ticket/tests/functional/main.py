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

import os
import textwrap
import time
import unittest

from datetime import timedelta

from trac.test import locale_en
from trac.tests.contentgen import random_sentence, random_unique_camel, \
                                  random_word
from trac.tests.functional import FunctionalTestCaseSetup, b, \
                                  internal_error, regex_owned_by, tc
from trac.util import create_file
from trac.util.datefmt import datetime_now, format_datetime, localtz, utc


def find_field_deleted(name, find=True):
    markup = ('<td>[ \n]+'
              '<span class="trac-field-deleted">%s</span>'
              '[ \n]+</td>' % name)
    if find:
        tc.find(markup)
    else:
        tc.notfind(markup)


def find_field_change(old_name, new_name, find=True):
    markup = ('<span class="trac-field-old">%s</span>'
              '[ \n]+→[ \n]+'
              '<span class="trac-field-new">%s</span>'
              % (old_name, new_name))
    if find:
        tc.find(markup)
    else:
        tc.notfind(markup)


class TestTickets(FunctionalTestCaseSetup):
    def runTest(self):
        """Create a ticket and comment on it."""
        # TODO: this should be split into multiple tests
        id = self._tester.create_ticket()
        self._tester.add_comment(id)


class TestTicketMaxSummarySize(FunctionalTestCaseSetup):
    def runTest(self):
        """Test `[ticket] max_summary_size` option.
        https://trac.edgewall.org/ticket/11472"""
        prev_max_summary_size = \
            self._testenv.get_config('ticket', 'max_summary_size')
        short_summary = "abcdefghijklmnopqrstuvwxyz"
        long_summary = short_summary + "."
        max_summary_size = len(short_summary)
        warning_message = "The ticket field <strong>summary</strong> is " \
                          "invalid: Must be less than or equal to %d " \
                          "characters" % max_summary_size
        self._testenv.set_config('ticket', 'max_summary_size',
                                 str(max_summary_size))
        try:
            self._tester.create_ticket(short_summary)
            tc.find(short_summary)
            tc.notfind(warning_message)
            self._tester.go_to_front()
            tc.follow(r"\bNew Ticket\b")
            tc.notfind(internal_error)
            tc.url(self._tester.url + '/newticket', regexp=False)
            tc.formvalue('propertyform', 'field_summary', long_summary)
            tc.submit('submit')
            tc.url(self._tester.url + '/newticket#ticket', regexp=False)
            tc.find(warning_message)
        finally:
            self._testenv.set_config('ticket', 'max_summary_size',
                                     prev_max_summary_size)


class TestTicketAddAttachment(FunctionalTestCaseSetup):
    def runTest(self):
        """Add attachment to a ticket. Test that the attachment button
        reads 'Attach file' when no files have been attached, and 'Attach
        another file' when there are existing attachments.
        Feature added in https://trac.edgewall.org/ticket/10281"""
        id = self._tester.create_ticket()
        tc.find("Attach file")
        filename = self._tester.attach_file_to_ticket(id)

        self._tester.go_to_ticket(id)
        tc.find("Attach another file")
        tc.find('Attachments[ \n]+<span class="trac-count">\(1\)</span>')
        tc.find(filename)
        tc.find('Download all attachments as:\s+<a rel="nofollow" '
                'href="/zip-attachment/ticket/%s/">.zip</a>' % id)


class TestTicketPreview(FunctionalTestCaseSetup):
    def runTest(self):
        """Preview ticket creation"""
        self._tester.go_to_front()
        tc.follow('New Ticket')
        summary = random_sentence(5)
        desc = random_sentence(5)
        tc.formvalue('propertyform', 'field-summary', summary)
        tc.formvalue('propertyform', 'field-description', desc)
        tc.submit('preview')
        tc.url(self._tester.url + '/newticket#ticket', regexp=False)
        tc.find('ticket not yet created')
        tc.find(summary)
        tc.find(desc)


class TestTicketNoSummary(FunctionalTestCaseSetup):
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


class TestTicketManipulator(FunctionalTestCaseSetup):
    def runTest(self):
        plugin_name = self.__class__.__name__
        env = self._testenv.get_trac_environment()
        env.config.set('components', plugin_name + '.*', 'enabled')
        env.config.save()
        create_file(os.path.join(env.plugins_dir, plugin_name + '.py'),
"""\
from trac.core import Component, implements
from trac.ticket.api import ITicketManipulator
from trac.util.html import tag
from trac.util.translation import tag_


class TicketManipulator(Component):
    implements(ITicketManipulator)

    def prepare_ticket(self, req, ticket, fields, actions):
        pass

    def validate_ticket(self, req, ticket):
        field = 'reporter'
        yield None, tag_("A ticket with the summary %(summary)s"
                         " already exists.",
                          summary=tag.em("Testing ticket manipulator"))
        yield field, tag_("The ticket %(field)s is %(status)s.",
                          field=tag.strong(field),
                          status=tag.em("invalid"))
""")
        self._testenv.restart()

        try:
            self._tester.go_to_front()
            tc.follow("New Ticket")
            tc.formvalue('propertyform', 'field-description',
                         "Testing ticket manipulator")
            tc.submit('submit')
            tc.url(self._tester.url + '/newticket#ticket', regexp=False)
            tc.find("The ticket field <strong>summary</strong> is invalid: "
                    "Tickets must contain a summary.")
            tc.find("The ticket field <strong>reporter</strong> is invalid: "
                    "The ticket <strong>reporter</strong> is "
                    "<em>invalid</em>.")
        finally:
            env.config.set('components', plugin_name + '.*', 'disabled')
            env.config.save()


class TestTicketAltFormats(FunctionalTestCaseSetup):
    def runTest(self):
        """Download ticket in alternative formats"""
        summary = random_sentence(5)
        summary_bytes = summary.encode('utf-8')
        self._tester.create_ticket(summary)
        for fmt in ('Comma-delimited Text', 'Tab-delimited Text', 'RSS Feed'):
            code, content = tc.download_link(fmt)
            self.assertEqual(200, code)
            if content.find(summary_bytes) < 0:
                url = tc.write_source(content)
                raise AssertionError('Summary missing from %s format in %s' %
                                     (fmt, url))


class TestTicketCSVFormat(FunctionalTestCaseSetup):
    def runTest(self):
        """Download ticket in CSV format"""
        self._tester.create_ticket()
        code, csv = tc.download_link('Comma-delimited Text')
        if not csv.startswith(b'\xef\xbb\xbfid,summary,'): # BOM
            raise AssertionError('Bad CSV format: %r' % csv)


class TestTicketTabFormat(FunctionalTestCaseSetup):
    def runTest(self):
        """Download ticket in Tab-delimited format"""
        self._tester.create_ticket()
        code, tab = tc.download_link('Tab-delimited Text')
        if not tab.startswith(b'\xef\xbb\xbfid\tsummary\t'): # BOM
            raise AssertionError('Bad tab delimited format: %r' % tab)


class TestTicketRSSFormat(FunctionalTestCaseSetup):
    def runTest(self):
        """Download ticket in RSS format"""
        summary = random_sentence(5)
        self._tester.create_ticket(summary)
        # Make a number of changes to exercise all of the RSS feed code
        tc.formvalue('propertyform', 'comment', random_sentence(3))
        tc.click('#propertyform .collapsed .foldable a')
        tc.formvalue('propertyform', 'field-type', 'task')
        tc.formvalue('propertyform', 'field-description',
                     summary + '\n\n' + random_sentence(8))
        tc.formvalue('propertyform', 'field-keywords', 'key')
        tc.submit('submit')
        tc.click('#propertyform .collapsed .foldable a')
        tc.formvalue('propertyform', 'field-keywords', '')
        tc.submit('submit')

        tc.find('RSS Feed')
        code, rss = tc.download_link('RSS Feed')
        if not rss.startswith(b'<?xml version="1.0"?>'):
            raise AssertionError('RSS Feed not valid feed')


class TestTicketSearch(FunctionalTestCaseSetup):
    def runTest(self):
        """Test ticket search"""
        summary = random_sentence(4)
        self._tester.create_ticket(summary)
        self._tester.go_to_front()
        tc.follow('Search')
        tc.formvalue('fullsearch', 'ticket', True)
        tc.formvalue('fullsearch', 'q', summary)
        tc.submit()
        tc.find('class="searchable">.*' + summary)
        tc.notfind('No matches found')


class TestNonTicketSearch(FunctionalTestCaseSetup):
    def runTest(self):
        """Test non-ticket search"""
        # Create a summary containing only unique words
        summary = ' '.join(random_word() + '_TestNonTicketSearch'
                           for i in range(5))
        self._tester.create_ticket(summary)
        self._tester.go_to_front()
        tc.follow('Search')
        tc.formvalue('fullsearch', 'ticket', False)
        tc.formvalue('fullsearch', 'q', summary)
        tc.submit()
        tc.notfind('class="searchable">' + summary)
        tc.find('No matches found')


class TestTicketHistory(FunctionalTestCaseSetup):
    def runTest(self):
        """Test ticket history"""
        summary = random_sentence(5)
        ticketid = self._tester.create_ticket(summary)
        comment = self._tester.add_comment(ticketid, "The original comment")
        self._tester.go_to_ticket(ticketid)
        tc.find(r'<a [^>]+>\bModify\b</a>')
        tc.find(r"\bAttach file\b")
        tc.find(r"\bAdd Comment\b")
        tc.find(r"\bModify Ticket\b")
        tc.find(r"\bPreview\b")
        tc.find(r"\bSubmit changes\b")
        url = b.get_url()

        tc.go(url + '?version=0')
        tc.find('at +<[^>]*>*Initial Version')
        tc.find(summary)
        tc.notfind(comment)
        tc.notfind(r'<a [^>]+>\bModify\b</a>')
        tc.notfind(r"\bAttach file\b")
        tc.notfind(r"\bAdd Comment\b")
        tc.notfind(r"\bModify Ticket\b")
        tc.notfind(r"\bPreview\b")
        tc.notfind(r"\bSubmit changes\b")

        tc.go(url + '?version=1')
        tc.find('at[ \n]+<[^>]*>*Version 1')
        tc.find(summary)
        tc.find(comment)
        tc.notfind(r'<a [^>]+>\bModify\b</a>')
        tc.notfind(r"\bAttach file\b")
        tc.notfind(r"\bAdd Comment\b")
        tc.notfind(r"\bModify Ticket\b")
        tc.notfind(r"\bPreview\b")
        tc.notfind(r"\bSubmit changes\b")

        tc.go(url + '?cnum_edit=1')
        revised_comment = "The edited comment."
        tc.formvalue('trac-comment-editor', 'edited_comment', revised_comment)
        tc.submit("Submit changes")

        # View comment versions.
        self._tester.go_to_ticket(ticketid)
        tc.follow(r"\bprevious\b")
        tc.url(url + '?cnum_hist=1&cversion=0#comment:1', regexp=False)
        tc.find(r"[^\"]%s[^\"]" % comment)
        tc.notfind(r"[^\"]%s[^\"]" % revised_comment)
        tc.follow(r"\bnext\b")
        tc.notfind(r"[^\"]%s[^\"]" % comment)
        tc.find(r"[^\"]%s[^\"]" % revised_comment)
        tc.url(url + '?cnum_hist=1&cversion=1#comment:1', regexp=False)

        # View comment diff.
        tc.follow(r'^/ticket/%s\?action=comment-diff&cnum=1&version=1$' %
                  ticketid)
        tc.notfind(r"\bComment:\b")
        tc.find(r"\bChanges between\b")
        tc.url(url + '?action=comment-diff&cnum=1&version=1', regexp=False)

        # View ticket comment history.
        tc.follow(r"\bTicket Comment History\b")
        tc.notfind(r'<th class="comment">Comment</th>')
        tc.find(r'\bChange History for '
                r'<a href="/ticket/\d+#comment:1">Ticket #\d+, comment 1</a>')


class TestTicketHistoryDiff(FunctionalTestCaseSetup):
    def runTest(self):
        """Test ticket history (diff)"""
        self._tester.create_ticket()
        tc.click('#propertyform .collapsed .foldable a')
        tc.formvalue('propertyform', 'field_description', random_sentence(6))
        tc.submit('submit')
        tc.find('Description:</th>[ \n]+<td>[ \n]+'
                'modified \\(<[^>]*>diff', 's')
        tc.follow('diff')
        tc.find('Changes\\s*between\\s*<[^>]*>Initial Version<[^>]*>\\s*and'
                '\\s*<[^>]*>Version 1<[^>]*>\\s*of\\s*<[^>]*>Ticket #' , 's')


class TestTicketHistoryInvalidCommentVersion(FunctionalTestCaseSetup):
    def runTest(self):
        """Viewing an invalid comment version does not raise a KeyError
        or AttributeError. Regression test for
        https://trac.edgewall.org/ticket/12060 and
        https://trac.edgewall.org/ticket/12277.
        """
        tkt = self._tester.create_ticket()
        self._tester.add_comment(tkt, "the comment")
        tc.click('[href="#comment:1"]')
        tc.move_to('[id="comment:1"]')
        tc.submit(formname='edit-comment-1')
        tc.formvalue('trac-comment-editor', 'edited_comment',
                     "the revised comment")
        tc.submit('edit_comment')

        for cversion in ('1', '2', 'A'):
            tc.go(self._tester.url + '/ticket/%s?cversion=%s&cnum_hist=1'
                  % (tkt, cversion))
            tc.notfind(internal_error)
            tc.find("the revised comment")
            tc.find("Last edited")
        for cversion in ('0', '-1'):
            tc.go(self._tester.url + '/ticket/%s?cversion=%s&cnum_hist=1'
                  % (tkt, cversion))
            tc.notfind(internal_error)
            tc.find("the comment")
            tc.find("Version 0")


class TestTicketQueryLinks(FunctionalTestCaseSetup):
    @tc.javascript_disabled
    def runTest(self):
        """Test ticket query links"""
        count = 3
        ticket_ids = [self._tester.create_ticket('TestTicketQueryLinks%s' % i)
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
        tc.find(r'\(%d matches\)' % count)
        for i in range(count):
            tc.find('TestTicketQueryLinks%s' % i)

        tc.follow('TestTicketQueryLinks0')
        tc.find('class="missing">&larr; Previous Ticket')
        tc.find('title="Ticket #%s">Next Ticket' % ticket_ids[1])
        tc.follow('Back to Query')
        tc.url(query_url, regexp=False)

        tc.follow('TestTicketQueryLinks1')
        tc.find('title="Ticket #%s">Previous Ticket' % ticket_ids[0])
        tc.find('title="Ticket #%s">Next Ticket' % ticket_ids[2])
        tc.follow('Next Ticket')

        tc.find('title="Ticket #%s">Previous Ticket' % ticket_ids[1])
        tc.find('class="missing">Next Ticket &rarr;')


class TestTicketQueryLinksQueryModuleDisabled(FunctionalTestCaseSetup):
    def runTest(self):
        """Ticket query links should not be present when the QueryModule
        is disabled."""
        def enable_query_module(enable):
            self._tester.go_to_admin('Plugins')
            tc.click('#trac-plugin-Trac.collapsed .foldable a')
            tc.formvalue('edit-plugin-trac', 'enable',
                         '%strac.ticket.query.QueryModule'
                         % ('+' if enable else '-'))
            tc.submit(formname='edit-plugin-trac')
            tc.find("The following component has been %s:"
                    ".*QueryModule.*\(trac\.ticket\.query\.\*\)"
                    % ("enabled" if enable else "disabled"))
        props = {'cc': 'user1, user2',
                 'component': 'component1',
                 'keywords': 'kw1, kw2',
                 'milestone': 'milestone1',
                 'owner': 'user',
                 'priority': 'major',
                 'reporter': 'admin',
                 'version': '2.0'}
        tid = self._tester.create_ticket(info=props)
        milestone_cell = \
            r'<td headers="h_milestone">\s*' \
            r'<a class="milestone" href="/milestone/%(milestone)s" ' \
            r'title=".*">\s*%(milestone)s\s*</a>\s*</td>'\
            % {'milestone': props['milestone']}
        try:
            for field, value in props.items():
                if field != 'milestone':
                    links = r', '.join(r'<a[^>]+href="/query.*>%s</a>'
                                       % v.strip() for v in value.split(','))
                    tc.find(r'<td( class="searchable")? headers="h_%s">'
                            r'\s*%s\s*</td>' % (field, links))
                else:
                    tc.find(milestone_cell)
            enable_query_module(False)
            self._tester.go_to_ticket(tid)
            for field, value in props.items():
                if field != 'milestone':
                    tc.find(r'<td( class="searchable")? headers="h_%s">'
                            r'\s*%s\s*</td>' % (field, value))
                else:
                    tc.find(milestone_cell)
        finally:
            enable_query_module(True)


class TestTicketQueryOrClause(FunctionalTestCaseSetup):
    @tc.javascript_disabled
    def runTest(self):
        """Test ticket query with an or clauses"""
        count = 3
        [self._tester.create_ticket(summary='TestTicketQueryOrClause%s' % i,
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
        for i in (1, 2):
            tc.find('TestTicketQueryOrClause%s' % i)


class TestTicketCustomFieldTextNoFormat(FunctionalTestCaseSetup):
    def runTest(self):
        """Test custom text field with no format explicitly specified.
        Its contents should be rendered as plain text.
        """
        env = self._testenv.get_trac_environment()
        env.config.set('ticket-custom', 'newfield', 'text')
        env.config.set('ticket-custom', 'newfield.label',
                       'Another Custom Field')
        env.config.set('ticket-custom', 'newfield.format', '')
        env.config.save()

        val = "%s %s" % (random_unique_camel(), random_word())
        self._tester.create_ticket(info={'newfield': val})
        tc.find('<td headers="h_newfield">\s*%s\s*</td>' % val)


class TestTicketCustomFieldTextAreaNoFormat(FunctionalTestCaseSetup):
    def runTest(self):
        """Test custom textarea field with no format explicitly specified,
        its contents should be rendered as plain text.
        """
        env = self._testenv.get_trac_environment()
        env.config.set('ticket-custom', 'newfield', 'textarea')
        env.config.set('ticket-custom', 'newfield.label',
                       'Another Custom Field')
        env.config.set('ticket-custom', 'newfield.format', '')
        env.config.save()

        val = "%s %s" % (random_unique_camel(), random_word())
        self._tester.create_ticket(info={'newfield': val})
        tc.find('<td colspan="3" headers="h_newfield">\s*%s\s*</td>' % val)


class TestTicketCustomFieldTextWikiFormat(FunctionalTestCaseSetup):
    def runTest(self):
        """Test custom text field with `wiki` format.
        Its contents should through the wiki engine, wiki-links and all.
        Feature added in https://trac.edgewall.org/ticket/1791
        """
        env = self._testenv.get_trac_environment()
        env.config.set('ticket-custom', 'newfield', 'text')
        env.config.set('ticket-custom', 'newfield.label',
                       'Another Custom Field')
        env.config.set('ticket-custom', 'newfield.format', 'wiki')
        env.config.save()

        word1 = random_unique_camel()
        word2 = random_word()
        val = "%s %s" % (word1, word2)
        self._tester.create_ticket(info={'newfield': val})
        wiki = '<a [^>]*>%s\??</a> %s' % (word1, word2)
        tc.find('<td headers="h_newfield">\s*%s\s*</td>' % wiki)


class TestTicketCustomFieldTextAreaWikiFormat(FunctionalTestCaseSetup):
    def runTest(self):
        """Test custom textarea field with no format explicitly specified,
        its contents should be rendered as plain text.
        """
        env = self._testenv.get_trac_environment()
        env.config.set('ticket-custom', 'newfield', 'textarea')
        env.config.set('ticket-custom', 'newfield.label',
                       'Another Custom Field')
        env.config.set('ticket-custom', 'newfield.format', 'wiki')
        env.config.save()

        word1 = random_unique_camel()
        word2 = random_word()
        val = "%s %s" % (word1, word2)
        self._tester.create_ticket(info={'newfield': val})
        wiki = '<p>\s*<a [^>]*>%s\??</a> %s<br />\s*</p>' % (word1, word2)
        tc.find('<td colspan="3" headers="h_newfield">\s*%s\s*</td>' % wiki)


class TestTicketCustomFieldTextReferenceFormat(FunctionalTestCaseSetup):
    def runTest(self):
        """Test custom text field with `reference` format.
        Its contents are treated as a single value
        and are rendered as an auto-query link.
        Feature added in https://trac.edgewall.org/ticket/10643
        """
        env = self._testenv.get_trac_environment()
        env.config.set('ticket-custom', 'newfield', 'text')
        env.config.set('ticket-custom', 'newfield.label',
                       'Another Custom Field')
        env.config.set('ticket-custom', 'newfield.format', 'reference')
        env.config.save()

        word1 = random_unique_camel()
        word2 = random_word()
        val = "%s %s" % (word1, word2)
        self._tester.create_ticket(info={'newfield': val})
        query = 'newfield=%s\+%s&amp;status=!closed' % (word1, word2)
        querylink = '<a href="/query\?%s">%s</a>' % (query, val)
        tc.find('<td headers="h_newfield">\s*%s\s*</td>' % querylink)


class TestTicketCustomFieldTextListFormat(FunctionalTestCaseSetup):
    def runTest(self):
        """Test custom text field with `list` format.
        Its contents are treated as a space-separated list of values
        and are rendered as separate auto-query links per word.
        Feature added in https://trac.edgewall.org/ticket/10643
        """
        env = self._testenv.get_trac_environment()
        env.config.set('ticket-custom', 'newfield', 'text')
        env.config.set('ticket-custom', 'newfield.label',
                       'Another Custom Field')
        env.config.set('ticket-custom', 'newfield.format', 'list')
        env.config.save()

        word1 = random_unique_camel()
        word2 = random_word()
        val = "%s %s" % (word1, word2)
        self._tester.create_ticket(info={'newfield': val})
        query1 = 'newfield=~%s&amp;status=!closed' % word1
        query2 = 'newfield=~%s&amp;status=!closed' % word2
        querylink1 = '<a href="/query\?%s">%s</a>' % (query1, word1)
        querylink2 = '<a href="/query\?%s">%s</a>' % (query2, word2)
        querylinks = '%s %s' % (querylink1, querylink2)
        tc.find('<td headers="h_newfield">\s*%s\s*</td>' % querylinks)


class RegressionTestTicket10828(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/10828
        Rendered property changes should be described as lists of added and
        removed items, even in the presence of comma and semicolon separators.
        """
        env = self._testenv.get_trac_environment()
        env.config.set('ticket-custom', 'newfield', 'text')
        env.config.set('ticket-custom', 'newfield.label',
                       'A Custom Field')
        env.config.set('ticket-custom', 'newfield.format', 'list')
        env.config.save()

        self._tester.create_ticket()

        word1 = random_unique_camel()
        word2 = random_word()
        val = "%s %s" % (word1, word2)
        tc.click('#propertyform .collapsed .foldable a')
        tc.formvalue('propertyform', 'field-newfield', val)
        tc.submit('submit')
        tc.find('%s %s added' % (word1, word2))

        word3 = random_unique_camel()
        word4 = random_unique_camel()
        val = "%s,  %s; %s" % (word2, word3, word4)
        tc.click('#propertyform .collapsed .foldable a')
        tc.formvalue('propertyform', 'field-newfield', val)
        tc.submit('submit')
        tc.find('%s %s added; %s removed' % (word3, word4, word1))

        tc.click('#propertyform .collapsed .foldable a')
        tc.formvalue('propertyform', 'field-newfield', '')
        tc.submit('submit')
        tc.find('%s %s %s removed' % (word2, word3, word4))

        val = "%s %s,%s" % (word1, word2, word3)
        tc.click('#propertyform .collapsed .foldable a')
        tc.formvalue('propertyform', 'field-newfield', val)
        tc.submit('submit')
        tc.find('%s %s %s added' % (word1, word2, word3))
        query1 = 'newfield=~%s&amp;status=!closed' % word1
        query2 = 'newfield=~%s&amp;status=!closed' % word2
        query3 = 'newfield=~%s&amp;status=!closed' % word3
        querylink1 = '<a href="/query\?%s">%s</a>' % (query1, word1)
        querylink2 = '<a href="/query\?%s">%s</a>' % (query2, word2)
        querylink3 = '<a href="/query\?%s">%s</a>' % (query3, word3)
        querylinks = '%s %s, %s' % (querylink1, querylink2, querylink3)
        tc.find('<td headers="h_newfield">\s*%s\s*</td>' % querylinks)


class TestTicketTimeline(FunctionalTestCaseSetup):
    def runTest(self):
        """Test ticket details on timeline"""
        env = self._testenv.get_trac_environment()
        env.config.set('timeline', 'ticket_show_details', 'yes')
        env.config.save()
        summary = random_sentence(5)
        ticketid = self._tester.create_ticket(summary)
        self._tester.add_comment(ticketid)

        self._tester.go_to_timeline()
        tc.formvalue('prefs', 'ticket', True)
        tc.submit(formname='prefs')
        tc.find('Ticket.*#%s.*created' % ticketid)
        tc.formvalue('prefs', 'ticket_details', True)
        tc.submit(formname='prefs')
        htmltags = '(<[^>]*>)*'
        tc.find('Ticket ' + htmltags + '#' + str(ticketid) + htmltags +
                ' \\(' + summary.split()[0] +
                ' [^\\)]+\\) updated\\s+by\\s+' + htmltags + 'admin', 's')


class TestNewReport(FunctionalTestCaseSetup):
    def runTest(self):
        """Create a new report"""
        self._tester.create_report(
            'Closed tickets, modified in the past 7 days by owner.', """
              SELECT DISTINCT p.value AS __color__,
               id AS ticket,
               summary, component, milestone, t.type AS type,
               reporter, time AS created,
               changetime AS modified, description AS _description,
               priority,
               round(julianday('now') -
                     julianday(changetime, 'unixepoch')) as days,
               resolution,
               owner as __group__
              FROM ticket t
              LEFT JOIN enum p ON p.name = t.priority AND
                                  p.type = 'priority'
              WHERE ((julianday('now') -
                      julianday(changetime, 'unixepoch')) < 7)
               AND status = 'closed'
              ORDER BY __group__, changetime, p.value
            """,
            'List of all tickets that are closed, and have been modified in'
            ' the past 7 days, grouped by owner.\n\n(So they have probably'
            ' been closed this week.)')


class TestReportRealmDecoration(FunctionalTestCaseSetup):
    def runTest(self):
        """Realm/id decoration in report"""
        self._tester.create_report(
            'Realm/id decoration', textwrap.dedent("""\
            SELECT NULL AS _realm,
             NULL AS id,
             NULL AS _parent_realm,
             NULL AS _parent_id
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
            """), '')
        tc.find('<a title="View ticket"[ \n]+'
                'href="[^"]*?/ticket/42">#42</a>')
        tc.find('<a title="View report"[ \n]+'
                'href="[^"]*?/report/42">report:42</a>')
        tc.find('<a title="View milestone"[ \n]+'
                'href="[^"]*?/milestone/42">42</a>')
        tc.find('<a title="View wiki"[ \n]+'
                'href="[^"]*?/wiki/WikiStart">'
                'WikiStart</a>')
        tc.find('<a title="View changeset"[ \n]+'
                'href="[^"]*?/changeset/42/trunk">'
                'Changeset 42/trunk</a>')
        tc.find('<a title="View changeset"[ \n]+'
                'href="[^"]*?/changeset/42/trunk/repo">'
                'Changeset 42/trunk in repo</a>')
        tc.find('<a title="View changeset"[ \n]+'
                'href="[^"]*?/changeset/43/tags">'
                'Changeset 43/tags</a>')
        tc.find('<a title="View attachment"[ \n]+'
                'href="[^"]*?/attachment/ticket/42/file[.]ext">'
                'file[.]ext [(]Ticket #42[)]</a>')
        tc.find('<a title="View attachment"[ \n]+'
                'href="[^"]*?/attachment/milestone/42/file[.]ext">'
                'file[.]ext [(]Milestone 42[)]</a>')
        tc.find('<a title="View attachment"[ \n]+'
                'href="[^"]*?/attachment/wiki/WikiStart/file[.]ext">'
                'file[.]ext [(]WikiStart[)]</a>')


class TestReportDynamicVariables(FunctionalTestCaseSetup):
    def runTest(self):
        """Generate a report with dynamic variables in title, summary
        and SQL"""
        summary = random_sentence(3)
        fields = {'component': 'component1'}
        ticket_id = self._tester.create_ticket(summary, fields)
        fields2 = {'component': 'component2'}
        ticket_id2 = self._tester.create_ticket(summary, fields2)
        reportnum = self._tester.create_report(
           "$USER's tickets for component $COMPONENT",
           """-- COMPONENT = component2
              SELECT DISTINCT
               t.id AS ticket, summary, component, version, milestone,
               t.type AS type, priority, t.time AS created,
               t.changetime AS _changetime, summary AS _description,
               reporter AS _reporter
              FROM ticket t
              LEFT JOIN enum p ON p.name = t.priority AND p.type = 'priority'
              LEFT JOIN ticket_change tc ON tc.ticket = t.id AND tc.author = $USER
               AND tc.field = 'comment'
              WHERE t.status <> 'closed'
               AND component = $COMPONENT
               AND (owner = $USER OR reporter = $USER OR author = $USER)
            """,
           "Tickets assigned to $USER for component $COMPONENT"
        )
        self._tester.go_to_report(reportnum, fields)
        tc.find("admin&#39;s tickets for component component1")
        tc.find("Tickets assigned to admin for component component1")
        tc.find('<a title="View ticket"[ \n]+href="/ticket/%s">%s</a>' %
                (ticket_id, summary))
        # Testing default parameter
        self._tester.go_to_report(reportnum)
        tc.find("admin&#39;s tickets for component component2")
        tc.find("Tickets assigned to admin for component component2")
        tc.find('<a title="View ticket"[ \n]+href="/ticket/%s">%s</a>' %
                (ticket_id2, summary))


class TestReportSorting(FunctionalTestCaseSetup):
    def runTest(self):
        """Test sorting of report.
        """
        tid = (self._tester.create_ticket(),
               self._tester.create_ticket())
        sort_href_desc = 'href="/report/1\?sort=ticket"'
        sort_href_asc = 'href="/report/1\?asc=1&amp;sort=ticket"'
        sort_text = r'(?<!New )\bTicket\b'

        def find_table_entries(tid):
            tc.find('<a [^>]+ href="/ticket/%d">'
                    '(?:(?!</tbody>).)+'
                    '<a [^>]+ href="/ticket/%d">' % tid, 's')

        self._tester.go_to_report(1)
        tc.find(sort_href_asc)
        find_table_entries(tid)
        tc.follow(sort_text)  # Sort ascending
        tc.find(sort_href_desc)
        find_table_entries(tid)
        tc.follow(sort_text)  # Sort descending
        tc.find(sort_href_asc)
        find_table_entries(tuple(reversed(tid)))
        # Sort order preserved when submitting preferences form.
        sort_href_desc = 'href="/report/1\?sort=summary"'
        sort_href_asc = 'href="/report/1\?asc=1&amp;sort=summary"'
        tc.find(sort_href_asc)
        tc.follow(r'\bSummary\b')
        tc.find(sort_href_desc)
        tc.submit(formname='trac-report-prefs')
        tc.find(sort_href_desc)
        tc.follow(r'\bSummary\b')
        tc.find(sort_href_asc)
        tc.submit(formname='trac-report-prefs')
        tc.find(sort_href_asc)


class TestMilestone(FunctionalTestCaseSetup):
    def runTest(self):
        """Create a milestone."""
        self._tester.go_to_roadmap()
        tc.submit(formname='add')
        tc.url(self._tester.url + '/milestone?action=new', regexp=False)
        name = random_unique_camel()
        due = format_datetime(datetime_now(tz=utc) + timedelta(hours=1),
                              tzinfo=localtz, locale=locale_en)
        tc.formvalue('edit', 'name', name)
        tc.formvalue('edit', 'due', True)
        tc.formvalue('edit', 'duedate', due)
        tc.notfind("Retarget associated open tickets to milestone:")
        tc.submit('add')
        tc.url(self._tester.url + '/milestone/' + name, regexp=False)
        tc.find(r'<h1>Milestone %s</h1>' % name)
        tc.find(due)
        self._tester.create_ticket(info={'milestone': name})
        tc.find('<a class="milestone" href="/milestone/%(name)s" '
                'title="Due in .+ (.+)">%(name)s</a>'
                % {'name': name})


class TestMilestoneAddAttachment(FunctionalTestCaseSetup):
    def runTest(self):
        """Add attachment to a milestone. Test that the attachment
        button reads 'Attach file' when no files have been attached, and
        'Attach another file' when there are existing attachments.
        Feature added in https://trac.edgewall.org/ticket/10281."""
        name = self._tester.create_milestone()
        self._tester.go_to_milestone(name)
        tc.find("Attach file")
        filename = self._tester.attach_file_to_milestone(name)

        self._tester.go_to_milestone(name)
        tc.find("Attach another file")
        tc.find('Attachments[ \n]+<span class="trac-count">\(1\)</span>')
        tc.find(filename)
        tc.find('Download all attachments as:\s+<a rel="nofollow" '
                'href="/zip-attachment/milestone/%s/">.zip</a>' % name)


class TestMilestoneClose(FunctionalTestCaseSetup):
    """Close a milestone and verify that tickets are retargeted
    to the selected milestone"""
    def runTest(self):
        name = self._tester.create_milestone()
        tid1 = self._tester.create_ticket(info={'milestone': name})
        tc.click('#propertyform .collapsed .foldable a')
        tc.formvalue('propertyform', 'action', 'resolve')
        tc.formvalue('propertyform',
                     'action_resolve_resolve_resolution', 'fixed')
        tc.submit('submit')

        # Check that hint is shown when there are no open tickets to retarget
        self._tester.go_to_milestone(name)
        tc.submit(formname='editmilestone')
        tc.find("There are no open tickets associated with this milestone.")

        retarget_to = self._tester.create_milestone()

        # Check that open tickets retargeted, closed not retargeted
        tid2 = self._tester.create_ticket(info={'milestone': name})
        self._tester.go_to_milestone(name)
        completed = format_datetime(datetime_now(tz=utc) - timedelta(hours=1),
                                    tzinfo=localtz, locale=locale_en)
        tc.submit(formname='editmilestone')
        tc.formvalue('edit', 'completed', True)
        tc.formvalue('edit', 'completeddate', completed)
        tc.formvalue('edit', 'target', retarget_to)
        tc.submit('save')

        tc.url(self._tester.url + '/milestone/%s' % name, regexp=False)
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
        find_field_change(name, retarget_to)
        tc.find("Ticket retargeted after milestone closed")


class TestMilestoneDelete(FunctionalTestCaseSetup):
    def runTest(self):
        """Delete a milestone and verify that tickets are retargeted
        to the selected milestone."""
        def submit_delete(name, retarget_to=None, tid=None):
            tc.submit('delete', 'delete-confirm')
            tc.url(self._tester.url + '/roadmap', regexp=False)
            tc.find('The milestone "%s" has been deleted.' % name)
            tc.notfind('Milestone:.*%s' % name)
            retarget_notice = 'The tickets associated with milestone "%s" ' \
                              'have been retargeted to milestone "%s".' \
                              % (name, str(retarget_to))
            if retarget_to is not None:
                tc.find('Milestone:.*%s' % retarget_to)
            if tid is not None:
                tc.find(retarget_notice)
                self._tester.go_to_ticket(tid)
                tc.find('by <span class="trac-author-user">admin</span>,'
                        '[ \n]+<a .*>\d+ seconds? ago</a>')
                if retarget_to is not None:
                    tc.find('<a class="milestone" href="/milestone/%(name)s" '
                            'title="No date set">%(name)s</a>'
                            % {'name': retarget_to})
                    find_field_change(name, retarget_to)
                else:
                    tc.find('<th class="missing" id="h_milestone">'
                            '[ \n]*Milestone:[ \n]*</th>')
                    find_field_deleted(name)
                tc.find("Ticket retargeted after milestone deleted")
            else:
                tc.notfind(retarget_notice)

        # No tickets associated with milestone to be retargeted
        name = self._tester.create_milestone()
        self._tester.go_to_milestone(name)
        tc.submit(formname='deletemilestone')
        tc.find("There are no tickets associated with this milestone.")
        submit_delete(name)

        # Don't select a milestone to retarget to
        name = self._tester.create_milestone()
        tid = self._tester.create_ticket(info={'milestone': name})
        self._tester.go_to_milestone(name)
        tc.submit(formname='deletemilestone')
        submit_delete(name, tid=tid)

        # Select a milestone to retarget to
        name = self._tester.create_milestone()
        retarget_to = self._tester.create_milestone()
        tid = self._tester.create_ticket(info={'milestone': name})
        self._tester.go_to_milestone(name)
        tc.submit(formname='deletemilestone')
        tc.formvalue('delete-confirm', 'target', retarget_to)
        submit_delete(name, retarget_to, tid)

        # Just navigate to the page and select cancel
        name = self._tester.create_milestone()
        tid = self._tester.create_ticket(info={'milestone': name})
        self._tester.go_to_milestone(name)
        tc.submit(formname='deletemilestone')
        tc.submit('cancel', 'delete-confirm')

        tc.url(self._tester.url + '/milestone/%s' % name, regexp=False)
        tc.notfind('The milestone "%s" has been deleted.' % name)
        tc.notfind('The tickets associated with milestone "%s" '
                   'have been retargeted to milestone' % name)
        self._tester.go_to_ticket(tid)
        tc.find('<a class="milestone" href="/milestone/%(name)s" '
                'title="No date set">%(name)s</a>' % {'name': name})
        find_field_deleted(name, False)
        tc.notfind("Ticket retargeted after milestone deleted<br>")

        # No attachments associated with milestone
        name = self._tester.create_milestone()
        self._tester.go_to_milestone(name)
        tc.submit(formname='deletemilestone')
        tc.notfind("The following attachments will also be deleted:")
        tc.submit('delete', 'delete-confirm')
        tc.find('The milestone "%s" has been deleted.' % name)
        tc.url(self._tester.url + '/roadmap', regexp=False)

        # Attachments associated with milestone
        name = self._tester.create_milestone()
        filename = self._tester.attach_file_to_milestone(name)
        self._tester.go_to_milestone(name)
        tc.submit(formname='deletemilestone')
        tc.find("The following attachments will also be deleted:")
        tc.find(filename)
        tc.submit('delete', 'delete-confirm')
        tc.find('The milestone "%s" has been deleted.' % name)
        tc.url(self._tester.url + '/roadmap', regexp=False)


class TestMilestoneRename(FunctionalTestCaseSetup):
    def runTest(self):
        """Rename a milestone and verify that the rename is shown in the
        change history for the associated tickets."""
        name = self._tester.create_milestone()
        new_name = random_unique_camel()
        tid = self._tester.create_ticket(info={'milestone': name})

        self._tester.go_to_milestone(name)
        tc.submit(formname='editmilestone')
        tc.formvalue('edit', 'name', new_name)
        tc.submit('save')

        tc.url(self._tester.url + '/milestone/' + new_name, regexp=False)
        tc.find("Your changes have been saved.")
        tc.find(r"<h1>Milestone %s</h1>" % new_name)
        self._tester.go_to_ticket(tid)
        tc.find('by <span class="trac-author-user">admin</span>,'
                '[ \n]+<a .*>\d+ seconds? ago</a>')
        tc.find('<a class="milestone" href="/milestone/%(name)s" '
                'title="No date set">%(name)s</a>' % {'name': new_name})
        find_field_change(name, new_name)
        tc.find("Milestone renamed")


class TestMilestoneGroupedProgress(FunctionalTestCaseSetup):
    def runTest(self):
        """Verify that grouped progress bar is displayed with proper
        owner/reporter and link obfuscation.
        """
        name = self._tester.create_milestone()
        self._tester.create_ticket(info={'milestone': name,
                                         'owner': 'user1@example.com'})
        self._tester.go_to_milestone(name)

        # Owner should not be obfuscated.
        tc.click('#stats select[name="by"] option[value="owner"]')
        tc.find('<th scope="row">[ \t\n]+'
                '<a href="[^"]+">'
                '<span class="trac-author">user1@example.com</span>')
        tc.find('<form id="stats" class="trac-groupprogress" [^>]+>.*'
                '<td class="open" style="width: 100%">[ \t\n]+'
                '<a href="[^"]+" title="1/1 active">', 's')

        # Owner should be obfuscated.
        self._tester.logout()
        self._tester.go_to_milestone(name)
        tc.click('#stats select[name="by"] option[value="owner"]')
        tc.find('<th scope="row">[ \t\n]+'
                '<span class="trac-author">user1@…</span>')
        tc.find('<form id="stats" class="trac-groupprogress" [^>]+>.*'
                '<td class="open" style="width: 100%">[ \t\n]+'
                '<a title="1/1 active">', 's')
        self._tester.login('admin')


class RegressionTestRev5994(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of the column label fix in r5994"""
        env = self._testenv.get_trac_environment()
        env.config.set('ticket-custom', 'custfield', 'text')
        env.config.set('ticket-custom', 'custfield.label', 'Custom Field')
        env.config.save()
        try:
            self._tester.go_to_query()
            tc.find('<label>( |\\n)*<input[^<]*value="custfield"'
                    '[^<]*>( |\\n)*Custom Field( |\\n)*</label>', 's')
        finally:
            pass
            #env.config.set('ticket', 'restrict_owner', 'no')
            #env.config.save()


class RegressionTestTicket4447(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/4447"""
        ticketid = self._tester.create_ticket("Hello World")
        env = self._testenv.get_trac_environment()
        env.config.set('ticket-custom', 'newfield', 'text')
        env.config.set('ticket-custom', 'newfield.label',
                       'Another Custom Field')
        env.config.save()

        self._tester.add_comment(ticketid)
        tc.notfind('<strong class="trac-field-newfield">Another Custom Field'
                   '</strong>[ \n]+<em></em>[ \n]+deleted')
        tc.notfind('<strong class="trac-field-newfield">Another Custom Field'
                   '</strong>[ \n]*set to <em>')


class RegressionTestTicket4630a(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/4630 a"""
        env = self._testenv.get_trac_environment()
        env.config.set('ticket', 'restrict_owner', 'yes')
        env.config.save()
        try:
            # Make sure 'user' has logged in.
            self._tester.go_to_front()
            self._tester.logout()
            self._tester.login('user')
            self._tester.go_to_front()
            self._tester.logout()
            self._tester.login('joe')
            self._tester.go_to_front()
            self._tester.logout()
            self._tester.login('admin')
            self._tester.create_ticket()
            tc.click('#propertyform .collapsed .foldable a')
            tc.formvalue('propertyform', 'action', 'reassign')
            tc.find('reassign_reassign_owner')
            tc.formvalue('propertyform', 'action_reassign_reassign_owner',
                         'user')
            tc.submit('submit')
        finally:
            # Undo the config change for now since this (failing)
            # regression test causes problems for later tests.
            env.config.set('ticket', 'restrict_owner', 'no')
            env.config.save()


class RegressionTestTicket4630b(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/4630 b"""
        # NOTE: this must be run after RegressionTestTicket4630 (user must
        # have logged in)
        from trac.perm import PermissionSystem
        env = self._testenv.get_trac_environment()
        perm = PermissionSystem(env)
        users = perm.get_users_with_permission('TRAC_ADMIN')
        self.assertEqual(users, ['admin'])
        users = perm.get_users_with_permission('TICKET_MODIFY')
        self.assertEqual(sorted(users), ['admin', 'joe', 'user'])


class RegressionTestTicket5022(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/5022
        """
        summary = 'RegressionTestTicket5022'
        ticket_id = self._tester.create_ticket(summary)
        tc.go(self._tester.url + '/newticket?id=%s' % ticket_id)
        tc.notfind(summary)


class RegressionTestTicket5394a(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/5394 a
        Order user list alphabetically in (re)assign action
        """
        # set restrict_owner config
        env = self._testenv.get_trac_environment()
        env.config.set('ticket', 'restrict_owner', 'yes')
        env.config.save()

        self._tester.go_to_front()
        self._tester.logout()

        test_users = ['alice', 'bob', 'jane', 'john', 'charlie', 'alan',
                      'zorro']
        # Apparently it takes a sec for the new user to be recognized by the
        # environment.  So we add all the users, then log in as the users
        # in a second loop.  This should be faster than adding a sleep(1)
        # between the .adduser and .login steps.
        for user in test_users:
            self._testenv.adduser(user)
        for user in test_users:
            self._tester.login(user)
            self._tester.go_to_front()
            self._tester.logout()

        self._tester.login('admin')

        self._tester.create_ticket("regression test 5394a")

        options = 'name="action_reassign_reassign_owner">' + \
            ''.join('<option[^>]*>%s</option>' % user for user in
                    sorted(test_users + ['admin', 'joe', 'user']))
        tc.find(options, 's')
        # We don't have a good way to fully delete a user from the Trac db.
        # Once we do, we may want to cleanup our list of users here.


class RegressionTestTicket5394b(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/5394 b
        Order user list alphabetically on new ticket page
        """
        # Must run after RegressionTestTicket5394a
        self._tester.go_to_front()
        tc.follow('New Ticket')
        tc.find('Create New Ticket')

        test_users = ['alice', 'bob', 'jane', 'john', 'charlie', 'alan',
                      'zorro']
        options = '.*'.join(sorted(test_users + ['admin', 'user']))
        tc.find(options, 's')


# TODO: this should probably be changed to be a testsuite derived from
# TestSetup
class RegressionTestTicket5497prep(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/5497 prep
        When the component is changed, the owner should update to the
        default owner of the component.
        If component is changed and the owner is changed (reassigned action
        for open tickets in the basic workflow), the owner should be the
        specified owner, not the owner of the component.
        """
        # The default owner for the component we're using for this testcase
        # is 'user', and we'll manually assign to 'admin'.
        self._tester.create_component('regression5497', 'user')


class RegressionTestTicket5497a(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/5497 a
        Open ticket, component changed, owner not changed"""
        self._tester.create_ticket("regression test 5497a")
        tc.click('#propertyform .collapsed .foldable a')
        tc.formvalue('propertyform', 'field-component', 'regression5497')
        tc.submit('submit')
        tc.find(regex_owned_by('user'))


class RegressionTestTicket5497b(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/5497 b
        Open ticket, component changed, owner changed"""
        self._tester.create_ticket("regression test 5497b")
        tc.click('#propertyform .collapsed .foldable a')
        tc.formvalue('propertyform', 'field-component', 'regression5497')
        tc.formvalue('propertyform', 'action', 'reassign')
        tc.formvalue('propertyform', 'action_reassign_reassign_owner',
                     'admin')
        tc.submit('submit')
        tc.notfind(regex_owned_by('user'))
        tc.find(regex_owned_by('admin'))


class RegressionTestTicket5497c(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/5497 c
        New ticket, component changed, owner not changed"""
        self._tester.create_ticket("regression test 5497c",
                                   {'component':'regression5497'})
        tc.find(regex_owned_by('user'))


class RegressionTestTicket5497d(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/5497 d
        New ticket, component changed, owner changed"""
        self._tester.create_ticket("regression test 5497d",
                                   {'component': 'regression5497',
                                    'owner': 'admin'})
        tc.find(regex_owned_by('admin'))


class RegressionTestTicket5602(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/5602"""
        # Create a set of tickets, and assign them all to a milestone
        milestone = self._tester.create_milestone()
        ids = [self._tester.create_ticket(info={'milestone': milestone})
               for x in range(5)]
        # Need a ticket in each state: new, assigned, accepted, closed,
        # reopened
        # leave ids[0] as new
        # make ids[1] be assigned
        self._tester.go_to_ticket(ids[1])
        tc.click('#propertyform .collapsed .foldable a')
        tc.formvalue('propertyform', 'action', 'reassign')
        tc.formvalue('propertyform', 'action_reassign_reassign_owner',
                     'admin')
        tc.submit('submit')
        # make ids[2] be accepted
        self._tester.go_to_ticket(ids[2])
        tc.click('#propertyform .collapsed .foldable a')
        tc.formvalue('propertyform', 'action', 'accept')
        tc.submit('submit')
        # make ids[3] be closed
        self._tester.go_to_ticket(ids[3])
        tc.click('#propertyform .collapsed .foldable a')
        tc.formvalue('propertyform', 'action', 'resolve')
        tc.formvalue('propertyform', 'action_resolve_resolve_resolution',
                     'fixed')
        tc.submit('submit')
        # make ids[4] be reopened
        self._tester.go_to_ticket(ids[4])
        tc.click('#propertyform .collapsed .foldable a')
        tc.formvalue('propertyform', 'action', 'resolve')
        tc.formvalue('propertyform', 'action_resolve_resolve_resolution',
                     'fixed')
        tc.submit('submit')
        # FIXME: we have to wait a second to avoid "IntegrityError: columns
        # ticket, time, field are not unique"
        time.sleep(1)
        tc.click('#propertyform .collapsed .foldable a')
        tc.formvalue('propertyform', 'action', 'reopen')
        tc.submit('submit')
        tc.notfind("Python Traceback")

        # Go to the milestone and follow the links to the closed and active
        # tickets.
        tc.go(self._tester.url + "/roadmap")
        tc.follow(milestone)

        tc.follow("closed:")
        tc.find("Resolution:[ \n]+fixed")

        tc.back()
        tc.follow("active:")
        tc.find("Status:[ \n]+new")
        tc.find("Status:[ \n]+assigned")
        tc.find("Status:[ \n]+accepted")
        tc.notfind("Status:[ \n]+closed")
        tc.find("Status:[ \n]+reopened")


class RegressionTestTicket5687(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/5687"""
        self._tester.go_to_front()
        self._tester.logout()
        self._tester.login('user')
        self._tester.create_ticket()
        self._tester.logout()
        self._tester.login('admin')


class RegressionTestTicket5930(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/5930
        TypeError: from_string() takes exactly 3 non-keyword arguments (4
        given)
        Caused by a saved query
        """
        self._tester.create_report('Saved Query', 'query:version=1.0', '')
        tc.notfind(internal_error)
        tc.submit(formname='trac-report-edit')
        tc.find("Modify Query:")
        tc.find("Save query")
        # TODO: Add a testcase for the following:
        # Can you also throw in addition of a 1.0 ticket and a 2.0 ticket
        # as part of the demo env, then see that only the correct one shows
        # up in the report?


class RegressionTestTicket6747(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/6747"""
        env = self._testenv.get_trac_environment()
        env.config.set('ticket-workflow', 'resolve.operations',
                       'set_resolution,set_owner')
        env.config.set('ticket-workflow', 'resolve.set_owner',
                       'a_specified_owner')
        env.config.save()

        try:
            self._tester.create_ticket("RegressionTestTicket6747")
            tc.find("a_specified_owner")
            tc.notfind("a_specified_owneras")

        finally:
            # Undo the config change to avoid causing problems for later
            # tests.
            env.config.set('ticket-workflow', 'resolve.operations',
                           'set_resolution')
            env.config.remove('ticket-workflow', 'resolve.set_owner')
            env.config.save()


class RegressionTestTicket6879a(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/6879 a

        Make sure that previewing a close does not make the available actions
        be those for the close status.
        """
        # create a ticket, then preview resolving the ticket twice
        self._tester.create_ticket("RegressionTestTicket6879 a")
        tc.click('#propertyform .collapsed .foldable a')
        tc.formvalue('propertyform', 'action', 'resolve')
        tc.formvalue('propertyform', 'action_resolve_resolve_resolution',
                     'fixed')
        tc.submit('preview')
        tc.click('#propertyform .collapsed .foldable a')
        tc.formvalue('propertyform', 'action', 'resolve')
        tc.submit('preview')


class RegressionTestTicket6879b(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/6879 a

        Make sure that previewing a close does not make the available actions
        be those for the close status.
        """
        # create a ticket, then preview resolving the ticket twice
        self._tester.create_ticket("RegressionTestTicket6879 b")
        tc.click('#propertyform .collapsed .foldable a')
        tc.formvalue('propertyform', 'action', 'resolve')
        tc.formvalue('propertyform', 'action_resolve_resolve_resolution',
                     'fixed')
        tc.submit('preview')
        tc.click('#propertyform .collapsed .foldable a')
        tc.formvalue('propertyform', 'action', 'resolve')
        tc.submit('submit')


class RegressionTestTicket6912a(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/6912 a"""
        self._tester.create_component(name='RegressionTestTicket6912a',
                                      owner='')


class RegressionTestTicket6912b(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/6912 b"""
        self._tester.create_component(name='RegressionTestTicket6912b',
                                      owner='admin')
        tc.follow('RegressionTestTicket6912b')
        tc.formvalue('edit', 'owner', '')
        tc.submit('save', formname='edit')
        tc.find('RegressionTestTicket6912b</a>[ \n]*</td>[ \n]*'
                '<td class="owner"></td>', 's')


class RegressionTestTicket7821group(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/7821 group.
        """
        env = self._testenv.get_trac_environment()
        saved_default_query = env.config.get('query', 'default_query')
        default_query = 'status!=closed&order=status&group=status&max=42' \
                        '&desc=1&groupdesc=1&col=summary|status|cc' \
                        '&cc~=$USER'
        env.config.set('query', 'default_query', default_query)
        env.config.save()
        try:
            self._tester.create_ticket('RegressionTestTicket7821 group')
            self._tester.go_to_query()
            # $USER
            tc.find('<input type="text" name="0_cc"[ \n]+value="admin"'
                    ' size="[0-9]+"/>')
            # col
            tc.find('<input type="checkbox" name="col" checked="checked"'
                    ' value="summary"/>')
            tc.find('<input type="checkbox" name="col" value="owner"/>')
            tc.find('<input type="checkbox" name="col" checked="checked"'
                    ' value="status"/>')
            tc.find('<input type="checkbox" name="col" checked="checked"'
                    ' value="cc"/>')
            # group
            tc.find('<option selected="selected" value="status">Status'
                    '</option>')
            # groupdesc
            tc.find('<input type="checkbox" name="groupdesc" id="groupdesc"'
                    ' checked="checked"/>')
            # max
            tc.find('<input type="text" name="max" id="max" size="[0-9]*?"'
                    '[ \n]+value="42"/>')
            # col in results
            tc.find('<a title="Sort by Ticket [(]ascending[)]"[ \n]+href')
            tc.find('<a title="Sort by Summary [(]ascending[)]"[ \n]+href')
            tc.find('<a title="Sort by Status [(]ascending[)]"[ \n]+href')
            tc.find('<a title="Sort by Cc [(]ascending[)]"[ \n]+href')
            tc.notfind('<a title="Sort by Owner "')
        finally:
            env.config.set('query', 'default_query', saved_default_query)
            env.config.save()


class RegressionTestTicket7821var(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/7821 var"""
        env = self._testenv.get_trac_environment()
        saved_default_query = env.config.get('query', 'default_query')
        saved_restrict_owner = env.config.get('ticket', 'restrict_owner')
        default_query = '?status=!closed&cc=~$USER&owner=$USER'
        env.config.set('query', 'default_query', default_query)
        env.config.set('ticket', 'restrict_owner', 'no')
        env.config.save()
        try:
            self._tester.create_ticket('RegressionTestTicket7821 var')
            self._tester.go_to_query()
            # $USER in default_query
            tc.find('<input type="text" name="0_owner"[ \n]+value="admin"'
                    ' size="[0-9]+"/>')
            tc.find('<input type="text" name="0_cc"[ \n]+value="admin"'
                    ' size="[0-9]+"/>')
            # query:owner=$USER&or&cc~=$USER
            tc.go(self._tester.url +
                  '/intertrac/query:owner=$USER&or&cc~=$USER')
            tc.find('<input type="text" name="0_owner"[ \n]+value="admin"'
                    ' size="[0-9]+"/>')
            tc.find('<input type="text" name="1_cc"[ \n]+value="admin"'
                    ' size="[0-9]+"/>')
        finally:
            env.config.set('query', 'default_query', saved_default_query)
            env.config.set('ticket', 'restrict_owner', saved_restrict_owner)
            env.config.save()


class RegressionTestTicket8247(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/8247
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
        find_field_deleted(name)
        tc.find('by <span class="trac-author-user">admin</span>,'
                '[ \n]+<a .*>\d+ seconds? ago</a>')
        tc.notfind('</a> ago by anonymous')


class RegressionTestTicket8861(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/8816
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
        tc.find('Milestone: +<em>%s</em>' % name)
        tc.find('Milestone: +<em>%s</em>' % (name + '__'))


class RegressionTestTicket9084(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/9084"""
        ticketid = self._tester.create_ticket()
        self._tester.add_comment(ticketid)
        self._tester.go_to_ticket(ticketid)
        tc.click('[href="#comment:1"]')
        tc.move_to('[id="comment:1"]')
        tc.submit(formname='reply-to-comment-1')
        tc.formvalue('propertyform', 'comment', random_sentence(3))
        tc.submit('Submit changes')
        tc.notfind('AssertionError')


class RegressionTestTicket9981(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/9981"""
        tid1 = self._tester.create_ticket()
        self._tester.add_comment(tid1)
        tc.click('#propertyform .collapsed .foldable a')
        tc.formvalue('propertyform', 'action', 'resolve')
        tc.submit('submit')
        tid2 = self._tester.create_ticket()
        comment = '[comment:1:ticket:%s]' % tid1
        self._tester.add_comment(tid2, comment)
        self._tester.go_to_ticket(tid2)
        tc.find('<a class="closed ticket"[ \t\n]+'
                'href="/ticket/%(num)s#comment:1"' % {'num': tid1})


class RegressionTestTicket10010(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/10010
        Allow configuring the default retargeting option when closing or
        deleting a milestone."""
        m1 = self._tester.create_milestone()
        m2 = self._tester.create_milestone()
        self._tester.create_ticket(info={'milestone': m1})
        def go_to_and_find_markup(markup, find=True):
            self._tester.go_to_milestone(m1)
            tc.submit(formname='editmilestone')
            if find:
                tc.find(markup)
            else:
                tc.notfind(markup)
            self._tester.go_to_milestone(m1)
            tc.submit(formname='deletemilestone')
            if find:
                tc.find(markup)
            else:
                tc.notfind(markup)
        try:
            go_to_and_find_markup('<option selected="selected" ', False)
            self._testenv.set_config('milestone', 'default_retarget_to', m2)
            go_to_and_find_markup('<option selected="selected" '
                                  'value="%(name)s">%(name)s</option>' % {'name': m2})
            self._testenv.set_config('milestone', 'default_retarget_to', m1)
            go_to_and_find_markup('<option selected="selected" ', False)
            self._testenv.set_config('milestone', 'default_retarget_to', '')
            go_to_and_find_markup('<option selected="selected" ', False)
        finally:
            self._testenv.remove_config('milestone', 'default_retarget_to')


class RegressionTestTicket10984(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/10984
        The milestone field should be hidden from the newticket, ticket
        and query forms when the user doesn't have MILESTONE_VIEW.
        """
        # Check that user with MILESTONE_VIEW can set and view the field
        self._tester.go_to_ticket()
        tc.find('<label for="field-milestone">Milestone:</label>')
        ticketid = self._tester.create_ticket(info={'milestone': 'milestone1'})
        self._tester.go_to_ticket(ticketid)
        tc.find(r'<label for="field-milestone">Milestone:</label>')
        tc.find(r'<option selected="selected" value="milestone1">')

        # Check that anonymous user w/o MILESTONE_VIEW doesn't see the field
        self._testenv.revoke_perm('anonymous', 'MILESTONE_VIEW')
        self._testenv.grant_perm('anonymous', 'TICKET_CREATE')
        self._testenv.grant_perm('anonymous', 'TICKET_MODIFY')
        self._tester.logout()
        try:
            self._tester.go_to_ticket()
            tc.notfind(r'<label for="field-milestone">Milestone:</label>')
            tc.notfind(r'<select id="field-milestone"')
            self._tester.go_to_ticket(ticketid)
            tc.notfind(r'<label for="field-milestone">Milestone:</label>')
            tc.notfind(r'<select id="field-milestone"')
        finally:
            self._tester.login('admin')
            self._testenv.revoke_perm('anonymous', 'TICKET_CREATE')
            self._testenv.revoke_perm('anonymous', 'TICKET_MODIFY')
            self._testenv.grant_perm('anonymous', 'MILESTONE_VIEW')


class RegressionTestTicket11028(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/11028"""
        self._tester.go_to_roadmap()

        logged_out = False
        try:
            # Check that a milestone is found on the roadmap,
            # even for anonymous
            tc.find('<a href="/milestone/milestone1">[ \n]*'
                    'Milestone: +<em>milestone1</em>[ \n]*</a>')
            self._tester.logout()
            logged_out = True
            tc.find('<a href="/milestone/milestone1">[ \n]*'
                    'Milestone: +<em>milestone1</em>[ \n]*</a>')

            # Check that no milestones are found on the roadmap when
            # MILESTONE_VIEW is revoked
            self._testenv.revoke_perm('anonymous', 'MILESTONE_VIEW')
            tc.reload()
            tc.notfind('Milestone: +<em>milestone\d+</em>')

            # Check that roadmap can't be viewed without ROADMAP_VIEW

            self._testenv.revoke_perm('anonymous', 'ROADMAP_VIEW')
            self._tester.go_to_url(self._tester.url + '/roadmap')
            tc.find('<h1>Error: Forbidden</h1>')
        finally:
            # Restore state prior to test execution
            if logged_out:
                self._tester.login('admin')
            self._testenv.grant_perm('anonymous',
                                     ('ROADMAP_VIEW', 'MILESTONE_VIEW'))


class RegressionTestTicket11176(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/11176
        Fine-grained permission checks should be enforced on the Report list
        page, the report pages and query pages."""
        self._testenv.enable_authz_permpolicy("""
            [ticket:*]
            anonymous = TICKET_VIEW
            [report:-1]
            anonymous = REPORT_VIEW
            [report:1]
            anonymous = REPORT_VIEW
            [report:2]
            anonymous = REPORT_VIEW
            [report:*]
            anonymous =
        """)
        self._tester.go_to_front()
        self._tester.logout()
        self._tester.go_to_view_tickets()
        try:
            # Check that permissions are enforced on the report list page
            tc.find(r'<a title="View report" '
                    r'href="/report/1">[ \n]*<em>\{1\}</em>')
            tc.find(r'<a title="View report" '
                    r'href="/report/2">[ \n]*<em>\{2\}</em>')
            for report_num in range(3, 9):
                tc.notfind(r'<a title="View report" '
                           r'href="/report/%(num)s">[ \n]*'
                           r'<em>\{%(num)s\}</em>' % {'num': report_num})
            # Check that permissions are enforced on the report pages
            tc.go(self._tester.url + '/report/1')
            tc.find(r'<h1>\{1\} Active Tickets[ \n]*'
                    r'(<span class="numrows">\(\d+ matches\)</span>)?'
                    r'[ \n]*</h1>')
            tc.go(self._tester.url + '/report/2')
            tc.find(r'<h1>\{2\} Active Tickets by Version[ \n]*'
                    r'(<span class="numrows">\(\d+ matches\)</span>)?'
                    r'[ \n]*</h1>')
            for report_num in range(3, 9):
                tc.go(self._tester.url + '/report/%d' % report_num)
                tc.find(r'<h1>Error: Forbidden</h1>')
            # Check that permissions are enforced on the query pages
            tc.go(self._tester.url + '/query?report=1')
            tc.find(r'<h1>Active Tickets '
                    r'<span class="numrows">\(\d+ matches\)</span></h1>')
            tc.go(self._tester.url + '/query?report=2')
            tc.find(r'<h1>Active Tickets by Version '
                    r'<span class="numrows">\(\d+ matches\)</span></h1>')
            for report_num in range(3, 9):
                tc.go(self._tester.url + '/query?report=%d' % report_num)
                tc.find(r'<h1>Error: Forbidden</h1>')
        finally:
            self._tester.login('admin')
            self._testenv.disable_authz_permpolicy()


class RegressionTestTicket11590(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/11590"""
        report_id = self._tester.create_report('#11590', 'SELECT 1',
                                               '[. this report]')
        self._tester.go_to_view_tickets()
        tc.notfind(internal_error)
        tc.find('<a class="report" href="[^>"]*?/report/%s">this report</a>' %
                report_id)


class RegressionTestTicket11996(FunctionalTestCaseSetup):
    def runTest(self):
        """Field default value is only selected for new tickets.
        Test for regression https://trac.edgewall.org/ticket/11996
        """
        milestone = self._testenv.get_config('ticket', 'default_milestone')
        self._testenv.set_config('ticket', 'default_milestone', 'milestone3')
        try:
            self._tester.go_to_ticket()
            tc.find('<option selected="selected" value="milestone3">')
            self._tester.create_ticket(info={'milestone': ''})
            tc.find('<td headers="h_milestone">[ \n]*</td>')
            tc.notfind('<option value="milestone3" selected="selected">')
        finally:
            self._testenv.set_config('ticket', 'default_milestone', milestone)


class RegressionTestTicket12801(FunctionalTestCaseSetup):
    def runTest(self):
        """Textarea fields with plain format preserve newlines.
        Test for regression https://trac.edgewall.org/ticket/12801
        """
        env = self._testenv.get_trac_environment()
        try:
            env.config.set('ticket-custom', 't12801_plain', 'textarea')
            env.config.set('ticket-custom', 't12801_plain.format', '')
            env.config.set('ticket-custom', 't12801_wiki', 'textarea')
            env.config.set('ticket-custom', 't12801_wiki.format', 'wiki')
            env.config.save()

            tkt = self._tester.create_ticket(
                info={'description': "//**description field**//\n",
                      't12801_plain': "- //plain 1//\n- ~~plain 2~~\n",
                      't12801_wiki': "- ~~wiki 1~~\n- //wiki 2//\n"})
            tc.find(r'<em><strong>description field</strong></em>')
            tc.find(r'<td colspan="3" headers="h_t12801_plain">\n'
                    r'\s*- //plain 1//\n'
                    r'\s*<br />\n'
                    r'\s*- ~~plain 2~~\n'
                    r'\s*</td>')
            tc.find(r'<li><del>wiki 1</del>\s*</li>'
                    r'<li><em>wiki 2</em>\s*</li>')

            tc.go('%s/query?id=%s&&row=description&row=t12801_plain&'
                  'row=t12801_wiki' % (self._tester.url, tkt))
            tc.find(r'<em><strong>description field</strong></em>')
            tc.find(r'<td class="trac-colspan" colspan="[0-9]+">\n'
                    r'\s*- //plain 1//\n'
                    r'\s*<br />\n'
                    r'\s*- ~~plain 2~~\n'
                    r'\s*</td>')
            tc.find(r'<li><del>wiki 1</del>\s*</li>'
                    r'<li><em>wiki 2</em>\s*</li>')

        finally:
            for name in ('t12801_plain', 't12801_plain.format',
                         't12801_wiki', 't12801_wiki.format'):
                env.config.remove('ticket-custom', name)
            env.config.save()


class RegressionTestTicket12919(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression https://trac.edgewall.org/ticket/12919"""
        self._tester.create_report('#12919.', "SELECT 'blah' as keywords", '')
        tc.find(r'<td class="fullrow keywords" colspan="100">blah\s*<hr />')


def functionalSuite(suite=None):
    if not suite:
        import trac.tests.functional
        suite = trac.tests.functional.functionalSuite()
    suite.addTest(TestTickets())
    suite.addTest(TestTicketMaxSummarySize())
    suite.addTest(TestTicketAddAttachment())
    suite.addTest(TestTicketPreview())
    suite.addTest(TestTicketNoSummary())
    suite.addTest(TestTicketManipulator())
    suite.addTest(TestTicketAltFormats())
    suite.addTest(TestTicketCSVFormat())
    suite.addTest(TestTicketTabFormat())
    suite.addTest(TestTicketRSSFormat())
    suite.addTest(TestTicketSearch())
    suite.addTest(TestNonTicketSearch())
    suite.addTest(TestTicketHistory())
    suite.addTest(TestTicketHistoryDiff())
    suite.addTest(TestTicketHistoryInvalidCommentVersion())
    suite.addTest(TestTicketQueryLinks())
    suite.addTest(TestTicketQueryLinksQueryModuleDisabled())
    suite.addTest(TestTicketQueryOrClause())
    suite.addTest(TestTicketCustomFieldTextNoFormat())
    suite.addTest(TestTicketCustomFieldTextWikiFormat())
    suite.addTest(TestTicketCustomFieldTextAreaNoFormat())
    suite.addTest(TestTicketCustomFieldTextAreaWikiFormat())
    suite.addTest(TestTicketCustomFieldTextReferenceFormat())
    suite.addTest(TestTicketCustomFieldTextListFormat())
    suite.addTest(RegressionTestTicket10828())
    suite.addTest(TestTicketTimeline())
    suite.addTest(TestNewReport())
    suite.addTest(TestReportRealmDecoration())
    suite.addTest(TestReportDynamicVariables())
    suite.addTest(TestReportSorting())
    suite.addTest(TestMilestone())
    suite.addTest(TestMilestoneAddAttachment())
    suite.addTest(TestMilestoneClose())
    suite.addTest(TestMilestoneDelete())
    suite.addTest(TestMilestoneRename())
    suite.addTest(TestMilestoneGroupedProgress())
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
    suite.addTest(RegressionTestTicket9981())
    suite.addTest(RegressionTestTicket10010())
    suite.addTest(RegressionTestTicket10984())
    suite.addTest(RegressionTestTicket11028())
    suite.addTest(RegressionTestTicket11176())
    suite.addTest(RegressionTestTicket11590())
    suite.addTest(RegressionTestTicket11996())
    suite.addTest(RegressionTestTicket12801())
    suite.addTest(RegressionTestTicket12919())

    return suite


test_suite = functionalSuite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
