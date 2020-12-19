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

import http.client
import os
import unittest
import urllib.parse

from trac.mimeview.rst import has_docutils
from trac.tests.contentgen import random_sentence, random_unique_camel
from trac.tests.functional import FunctionalTestCaseSetup, \
                                  internal_error, tc
from trac.util import create_file, get_pkginfo
from trac.util.html import tag


class TestWiki(FunctionalTestCaseSetup):
    def runTest(self):
        """Create a wiki page."""
        self._tester.create_wiki_page()


class TestWikiEdit(FunctionalTestCaseSetup):
    def runTest(self):
        """Edit a wiki page."""
        pagename = self._tester.create_wiki_page()
        self._tester.edit_wiki_page(pagename)
        tc.find("Your changes have been saved in version 2")
        tc.find(r'\(<a href="/wiki/%s\?action=diff&amp;version=2">diff</a>\)'
                % pagename)


class TestWikiDelete(FunctionalTestCaseSetup):
    def runTest(self):
        """Delete a wiki page."""
        # Delete page with single version.
        name = self._tester.create_wiki_page()
        self._tester.go_to_wiki(name)
        tc.submit('delete_page')
        tc.find("Are you sure you want to completely delete this page?")
        tc.notfind("The following attachments will also be deleted:")
        tc.submit('delete', 'delete-confirm')
        tc.find("The page %s has been deleted." % name)
        tc.url(self._tester.url + '/wiki', regexp=False)

        # Delete page with attachment.
        name = self._tester.create_wiki_page()
        filename = self._tester.attach_file_to_wiki(name)
        self._tester.go_to_wiki(name)
        tc.submit('delete_page')
        tc.find("Are you sure you want to completely delete this page?")
        tc.find("The following attachments will also be deleted:")
        tc.find(filename)
        tc.submit('delete', 'delete-confirm')
        tc.find("The page %s has been deleted." % name)
        tc.url(self._tester.url + '/wiki', regexp=False)

        # Delete page with multiple versions.
        name = self._tester.create_wiki_page(content="Initial content.")
        self._tester.edit_wiki_page(name, content="Revised content.")
        self._tester.go_to_wiki(name)
        tc.submit('delete_page')
        tc.find("Are you sure you want to completely delete this page?")
        tc.find(r'Removing all\s+<a href="/wiki/%s\?action=history&amp;'
                r'version=2">2 versions</a>\s+of the page' % name)
        tc.notfind("The following attachments will also be deleted:")
        tc.submit('delete', 'delete-confirm')
        tc.find("The page %s has been deleted." % name)
        tc.url(self._tester.url + '/wiki', regexp=False)


class TestWikiAddAttachment(FunctionalTestCaseSetup):
    def runTest(self):
        """Add attachment to a wiki page. Test that the attachment
        button reads 'Attach file' when no files have been attached, and
        'Attach another file' when there are existing attachments.
        Feature added in https://trac.edgewall.org/ticket/10281"""
        name = self._tester.create_wiki_page()
        self._tester.go_to_wiki(name)
        tc.find("Attach file")
        filename = self._tester.attach_file_to_wiki(name)

        self._tester.go_to_wiki(name)
        tc.find("Attach another file")
        tc.find('Attachments[ \n]+<span class="trac-count">\(1\)</span>')
        tc.find(filename)
        tc.find('Download all attachments as:\s+<a rel="nofollow" '
                'href="/zip-attachment/wiki/%s/">.zip</a>' % name)


_plugin_py = """\
from trac.core import Component, implements
from trac.util.html import tag
from trac.util.translation import tag_
from trac.wiki.api import IWikiPageManipulator


class WikiPageManipulator(Component):
    implements(IWikiPageManipulator)

    def prepare_wiki_page(self, req, page, fields):
        pass

    def validate_wiki_page(self, req, page):
        field = 'comment'
        yield None, tag_("The page contains invalid markup at"
                         " line %(number)s.", number=tag.strong('10'))
        yield field, tag_("The field %(field)s cannot be empty.",
                          field=tag.strong(field))
"""


class TestWikiPageManipulator(FunctionalTestCaseSetup):
    def runTest(self):
        plugin_name = self.__class__.__name__
        env = self._testenv.get_trac_environment()
        env.config.set('components', plugin_name + '.*', 'enabled')
        env.config.save()
        create_file(os.path.join(env.plugins_dir, plugin_name + '.py'),
                    _plugin_py)
        self._testenv.restart()

        try:
            self._tester.go_to_front()
            tc.follow("Wiki")
            tc.submit(formname='modifypage')
            tc.submit('save', 'edit')
            tc.url(self._tester.url + '/wiki/WikiStart', regexp=False)
            tc.find("Invalid Wiki page: The page contains invalid markup at"
                    " line <strong>10</strong>.")
            tc.find("The Wiki page field <strong>comment</strong> is invalid:"
                    " The field <strong>comment</strong> cannot be empty.")
        finally:
            env.config.set('components', plugin_name + '.*', 'disabled')
            env.config.save()


class TestWikiHistory(FunctionalTestCaseSetup):
    """Create wiki page and navigate to page history."""
    def runTest(self):
        pagename = self._tester.create_wiki_page()
        self._tester.edit_wiki_page(pagename)
        url = self._tester.url
        tc.follow(r"\bHistory\b")
        tc.url('%s/wiki/%s?action=history' % (url, pagename), regexp=False)
        version_link = ('<td class="version">[ \n]*'
                        '<a href="/wiki/%(pagename)s\?version=%%(version)s"'
                        '[ \n]*title="View this version">%%(version)s[ \n]*</a>'
                        % {'pagename': pagename})
        tc.find(version_link % {'version': 1})
        tc.find(version_link % {'version': 2})
        tc.find(r'<th class="comment">Comment</th>')
        tc.formvalue('history', 'old_version', '1')
        tc.formvalue('history', 'version', '2')
        tc.submit(formname='history')
        tc.url(r'%s/wiki/%s\?action=diff&version=2&old_version=1'
               % (url, pagename))
        tc.find(r'<a href="/wiki/%s\?version=1">Version 1</a>' % pagename)
        tc.find(r'<a href="/wiki/%s\?version=2">Version 2</a>' % pagename)
        tc.find(r'<a href="/wiki/%(name)s">%(name)s</a>' % {'name': pagename})


class TestWikiEditComment(FunctionalTestCaseSetup):
    """Edit wiki page comment from diff and history."""
    def runTest(self):
        initial_comment = "Initial comment"
        pagename = self._tester.create_wiki_page(comment=initial_comment)
        url = self._tester.url
        tc.follow(r"\bHistory\b")
        history_url = url + r'/wiki/%s?action=history' % pagename
        tc.url(history_url, regexp=False)

        # Comment edit from history page
        tc.move_to('#fieldhist tbody tr:first-child')
        tc.follow(r"\bEdit\b")
        tc.url('%s/wiki/%s?action=edit_comment&version=1' % (url, pagename),
               regexp=False)
        tc.find("Old comment:[ \t\n]+%s" % initial_comment)
        first_comment_edit = "First comment edit"
        tc.formvalue('edit-comment-form', 'new_comment', first_comment_edit)
        tc.submit()
        tc.url(history_url, regexp=False)
        tc.find(r'<td class="comment">[ \t\n]+%s' % first_comment_edit)

        # Comment edit from diff page
        tc.formvalue('history', 'version', '1')
        tc.submit(formname='history')
        tc.url('%s/wiki/%s?action=diff&version=1#' % (url, pagename),
               regexp=False)
        tc.find(r'<p>[ \t\n]+%s[ \t\n]+</p>' % first_comment_edit)
        tc.follow(r"\bEdit\b")
        tc.url('%s/wiki/%s?action=edit_comment&redirect_to=diff&version=1' %
               (url, pagename), regexp=False)
        second_comment_edit = "Second comment edit"
        tc.formvalue('edit-comment-form', 'new_comment', second_comment_edit)
        tc.submit()
        tc.url('%s/wiki/%s?action=diff&old_version=0&version=1' %
               (url, pagename), regexp=False)
        tc.find(r'<p>[ \t\n]+%s[ \t\n]+</p>' % second_comment_edit)


class TestWikiReadonlyAttribute(FunctionalTestCaseSetup):
    """Test the wiki readonly attribute, which is enforce when
    DefaultWikiPolicy is in the list of active permission policies."""
    def runTest(self):
        self._tester.logout()
        self._tester.login('user')
        page_name = self._tester.create_wiki_page()
        permission_policies = \
            self._testenv.get_config('trac', 'permission_policies')
        readonly_checkbox = ('<input type="checkbox" name="readonly" '
                             'id="readonly"/>')
        attach_button = ('<input type="submit" id="attachfilebutton" '
                         'value="Attach.+file"/>')
        try:
            # User without WIKI_ADMIN can't set a page read-only
            tc.submit(formname='modifypage')
            tc.notfind(readonly_checkbox)

            # User with WIKI_ADMIN can set a page read-only
            # and still edit that page
            self._testenv.grant_perm('user', 'WIKI_ADMIN')
            self._tester.go_to_wiki(page_name)
            tc.submit(formname='modifypage')
            tc.find(readonly_checkbox)
            tc.formvalue('edit', 'readonly', True)
            tc.submit('save')
            tc.go(self._tester.url + '/attachment/wiki/' + page_name)
            tc.find(attach_button)
            self._tester.edit_wiki_page(page_name)

            # User without WIKI_ADMIN can't edit a read-only page
            self._testenv.revoke_perm('user', 'WIKI_ADMIN')
            self._tester.go_to_wiki(page_name)
            tc.notfind('<input type="submit" value="Edit this page" />')
            tc.go(self._tester.url + '/attachment/wiki/' + page_name)
            tc.notfind(attach_button)

            # Read-only checkbox is not present when DefaultWikiPolicy
            # is not in the list of active permission policies
            pp_list = [p.strip() for p in permission_policies.split(',')]
            pp_list.remove('DefaultWikiPolicy')
            self._testenv.set_config('trac', 'permission_policies',
                                     ', '.join(pp_list))
            self._testenv.grant_perm('user', 'WIKI_ADMIN')
            self._tester.go_to_wiki(page_name)
            tc.submit(formname='modifypage')
            tc.notfind(readonly_checkbox)
        finally:
            self._testenv.set_config('trac', 'permission_policies',
                                     permission_policies)
            self._testenv.revoke_perm('user', 'WIKI_ADMIN')
            self._tester.logout()
            self._tester.login('admin')


class TestWikiRename(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for simple wiki rename"""
        pagename = self._tester.create_wiki_page()
        attachment = self._tester.attach_file_to_wiki(pagename)
        base_url = self._tester.url
        page_url = base_url + "/wiki/" + pagename

        def click_rename():
            tc.submit(formname='rename')
            tc.url(page_url + r'?action=rename', regexp=False)
            tc.find("New name:")

        tc.go(page_url)
        tc.find("Rename page")
        click_rename()
        # attempt to give an empty new name
        tc.formvalue('rename-form', 'new_name', '')
        tc.submit('submit')
        tc.url(page_url, regexp=False)
        tc.find("A new name is mandatory for a rename")
        # attempt to rename the page to an invalid page name
        tc.formvalue('rename-form', 'new_name', '../WikiStart')
        tc.submit('submit')
        tc.url(page_url, regexp=False)
        tc.find("The new name is invalid")
        # attempt to rename the page to the current page name
        tc.formvalue('rename-form', 'new_name', pagename)
        tc.submit('submit')
        tc.url(page_url, regexp=False)
        tc.find("The new name must be different from the old name")
        # attempt to rename the page to an existing page name
        tc.formvalue('rename-form', 'new_name', 'WikiStart')
        tc.submit('submit')
        tc.url(page_url, regexp=False)
        tc.find("The page WikiStart already exists")
        # correct rename to new page name (old page replaced by a redirection)
        tc.go(page_url)
        click_rename()
        newpagename = pagename + 'Renamed'
        tc.formvalue('rename-form', 'new_name', newpagename)
        tc.formvalue('rename-form', 'redirect', True)
        tc.submit('submit')
        # check redirection page
        tc.url(page_url, regexp=False)
        tc.find("See.*/wiki/" + newpagename)
        tc.find("The page %s has been renamed to %s."
                % (pagename, newpagename))
        tc.find("The page %s has been recreated with a redirect to %s."
                % (pagename, newpagename))
        # check whether attachment exists on the new page but not on old page
        tc.go(base_url + '/attachment/wiki/' + newpagename + '/' + attachment)
        tc.notfind("Error: Invalid Attachment")
        tc.go(base_url + '/attachment/wiki/' + pagename + '/' + attachment)
        tc.find("Error: Invalid Attachment")
        # rename again to another new page name (this time, no redirection)
        tc.go(page_url)
        click_rename()
        newpagename = pagename + 'RenamedAgain'
        tc.formvalue('rename-form', 'new_name', newpagename)
        tc.formvalue('rename-form', 'redirect', False)
        tc.submit('submit')
        tc.url(base_url + "/wiki/" + newpagename, regexp=False)
        tc.find("The page %s has been renamed to %s."
                % (pagename, newpagename))
        # this time, the original page is gone
        self._tester.go_to_url(page_url)
        tc.find("The page[ \n]+%s[ \n]+does not exist" % tag.strong(pagename))


class RegressionTestTicket4812(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/4812"""
        pagename = random_unique_camel() + '/' + random_unique_camel()
        self._tester.create_wiki_page(pagename)
        self._tester.attach_file_to_wiki(pagename)
        tc.notfind('does not exist')


class ReStructuredTextWikiTest(FunctionalTestCaseSetup):
    def runTest(self):
        """Render reStructured text using a wikiprocessor"""
        pagename = self._tester.create_wiki_page(content="""
{{{
#!rst
Hello
=====

.. trac:: wiki:WikiStart Some Link
}}}
                                     """)
        self._tester.go_to_wiki(pagename)
        tc.find("Some Link")
        tc.find(r'<h1[^>]*>Hello')
        tc.notfind("wiki:WikiStart")
        tc.follow("Some Link")
        tc.url(self._tester.url + "/wiki/WikiStart", regexp=False)


class ReStructuredTextCodeBlockTest(FunctionalTestCaseSetup):
    def runTest(self):
        """Render reStructured code block"""
        pagename = self._tester.create_wiki_page(content="""
{{{
#!rst
.. code-block:: python

    print("123")
}}}
""")
        self._tester.go_to_wiki(pagename)
        tc.notfind("code-block")
        tc.find('print')
        tc.find('&quot;123&quot;')


class RegressionTestTicket8976(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/8976
        Test fine grained permissions policy on wiki for specific page
        versions."""
        name = self._tester.create_wiki_page()
        self._tester.edit_wiki_page(name)
        self._tester.edit_wiki_page(name)
        self._tester.logout()
        self._tester.login('user')
        try:
            self._tester.go_to_wiki(name, 1)
            tc.notfind(r"\bError: Forbidden\b")
            self._tester.go_to_wiki(name, 2)
            tc.notfind(r"\bError: Forbidden\b")
            self._tester.go_to_wiki(name, 3)
            tc.notfind(r"\bError: Forbidden\b")
            self._tester.go_to_wiki(name, 4)
            tc.find(r"\bTrac Error\b")
            self._tester.go_to_wiki(name)
            tc.notfind(r"\bError: Forbidden\b")
            self._testenv.enable_authz_permpolicy("""
                [wiki:%(name)s@1]
                * = !WIKI_VIEW
                [wiki:%(name)s@2]
                * = WIKI_VIEW
                [wiki:%(name)s@3]
                * = !WIKI_VIEW
                [wiki:%(name)s]
                * = WIKI_VIEW
            """ % {'name': name})
            self._tester.go_to_wiki(name, 1)
            tc.find(r"\bError: Forbidden\b")
            self._tester.go_to_wiki(name, 2)
            tc.notfind(r"\bError: Forbidden\b")
            self._tester.go_to_wiki(name, 3)
            tc.find(r"\bError: Forbidden\b")
            self._tester.go_to_wiki(name, 4)
            tc.find(r"\bTrac Error\b")
            self._tester.go_to_wiki(name)
            tc.notfind(r"\bError: Forbidden\b")
            self._tester.edit_wiki_page(name)
        finally:
            self._tester.logout()
            self._tester.login('admin')
            self._testenv.disable_authz_permpolicy()


class RegressionTestTicket10274(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/10274"""

        def fetch(url):
            # use directly HTTPConnection() to prevent normalization of URI
            parsed = urllib.parse.urlparse(url)
            cookie = '; '.join('%s=%s' % (c['name'], c['value'])
                               for c in tc.get_cookies())
            conn = http.client.HTTPConnection(parsed.netloc)
            try:
                conn.putrequest('GET', parsed.path)
                conn.putheader('Cookie', cookie)
                conn.endheaders(b'')
                resp = conn.getresponse()
                return resp.status, resp.read()
            finally:
                conn.close()

        url = self._tester.url
        status, content = fetch(url + '/wiki/WikiStart/..')
        self.assertIn(b'Invalid Wiki page name &#39;WikiStart/..&#39;',
                      content)
        status, content = fetch(url + '/wiki/../WikiStart')
        self.assertIn(b'Invalid Wiki page name &#39;../WikiStart&#39;',
                      content)
        status, content = fetch(url + '/wiki/WikiStart/./SubPage')
        self.assertIn(b'Invalid Wiki page name &#39;WikiStart/./SubPage&#39;',
                      content)


class RegressionTestTicket10850(FunctionalTestCaseSetup):
    @unittest.skipIf(os.name == 'nt', 'Unable to create file named with colon '
                                      'and backslash characters on Windows')
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/10850"""
        pagename = self._tester.create_wiki_page()
        # colon characters
        self._tester.attach_file_to_wiki(
            pagename, filename='2012-09-11_15:36:40-test.tbz2')
        base_url = self._tester.url
        tc.go(base_url + '/attachment/wiki/' + pagename +
              '/2012-09-11_15:36:40-test.tbz2')
        tc.notfind('Error: Invalid Attachment')
        # backslash characters
        self._tester.attach_file_to_wiki(
            pagename, filename=r'/tmp/back\slash.txt')
        base_url = self._tester.url
        tc.go(base_url + '/attachment/wiki/' + pagename + r'/back\slash.txt')
        tc.notfind('Error: Invalid Attachment')
        # Windows full path
        self._tester.attach_file_to_wiki(
            pagename, filename=r'z:\tmp\windows:path.txt')
        base_url = self._tester.url
        tc.go(base_url + '/attachment/wiki/' + pagename + r'/windows:path.txt')
        tc.notfind('Error: Invalid Attachment')
        # Windows share folder path
        self._tester.attach_file_to_wiki(
            pagename, filename=r'\\server\share\file:name.txt')
        base_url = self._tester.url
        tc.go(base_url + '/attachment/wiki/' + pagename + r'/file:name.txt')
        tc.notfind('Error: Invalid Attachment')


class RegressionTestTicket10957(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/10957"""

        self._tester.go_to_front()
        try:
            self._tester.logout()

            # Check that page can't be created without WIKI_CREATE
            page_name = random_unique_camel()
            self._tester.go_to_wiki(page_name)
            tc.find("Trac Error")
            tc.find("Page %s not found" % page_name)
            tc.notfind("Create this page")
            tc.go(self._tester.url + '/wiki/%s?action=edit' % page_name)
            tc.find("Error: Forbidden")
            tc.find(r"WIKI_CREATE privileges are required to perform this "
                    r"operation on %s\. You don&#39;t have the required "
                    r"permissions\." % page_name)

            # Check that page can be created when user has WIKI_CREATE
            self._testenv.grant_perm('anonymous', 'WIKI_CREATE')
            content_v1 = random_sentence()
            self._tester.create_wiki_page(page_name, content_v1)
            tc.find(content_v1)

            # Check that page can't be edited without WIKI_MODIFY
            tc.notfind("Edit this page")
            tc.notfind("Attach file")
            tc.go(self._tester.url + '/wiki/%s?action=edit' % page_name)
            tc.find("Error: Forbidden")
            tc.find(r"WIKI_MODIFY privileges are required to perform this "
                    r"operation on %s\. You don&#39;t have the required "
                    r"permissions\." % page_name)

            # Check that page can be edited when user has WIKI_MODIFY
            self._testenv.grant_perm('anonymous', 'WIKI_MODIFY')
            self._tester.go_to_wiki(page_name)
            tc.find("Edit this page")
            tc.find("Attach file")
            content_v2 = random_sentence()
            self._tester.edit_wiki_page(page_name, content_v2)
            tc.find(content_v2)

            # Check that page can be reverted to a previous revision
            tc.go(self._tester.url + '/wiki/%s?version=1' % page_name)
            tc.find("Revert to this version")
            tc.submit(formname='modifypage')
            tc.find(content_v1)

            # Check that page can't be reverted without WIKI_MODIFY
            self._tester.edit_wiki_page(page_name)
            self._testenv.revoke_perm('anonymous', 'WIKI_MODIFY')
            tc.go(self._tester.url + '/wiki/%s?version=1' % page_name)
            tc.notfind("Revert to this version")
            tc.go(self._tester.url + '/wiki/%s?action=edit&version=1' % page_name)
            tc.find(r"WIKI_MODIFY privileges are required to perform this "
                    r"operation on %s\. You don&#39;t have the required "
                    r"permissions\." % page_name)

        finally:
            # Restore pre-test state.
            self._tester.login('admin')
            self._testenv.revoke_perm('anonymous', 'WIKI_CREATE')


class RegressionTestTicket11302(FunctionalTestCaseSetup):
    def runTest(self):
        """Test for regression of https://trac.edgewall.org/ticket/11302"""
        pagename = self._tester.create_wiki_page()
        self._tester.attach_file_to_wiki(
            pagename, description="illustrates [./@1#point1]")
        self._tester.go_to_wiki(pagename + '?action=edit')
        tc.find(r'illustrates <a class="wiki"'
                r' href="/wiki/%s\?version=1#point1">@1</a>' % pagename)


def functionalSuite(suite=None):
    if not suite:
        import trac.tests.functional
        suite = trac.tests.functional.functionalSuite()
    suite.addTest(TestWiki())
    suite.addTest(TestWikiEdit())
    suite.addTest(TestWikiDelete())
    suite.addTest(TestWikiAddAttachment())
    suite.addTest(TestWikiPageManipulator())
    suite.addTest(TestWikiHistory())
    suite.addTest(TestWikiEditComment())
    suite.addTest(TestWikiReadonlyAttribute())
    suite.addTest(TestWikiRename())
    suite.addTest(RegressionTestTicket4812())
    suite.addTest(RegressionTestTicket8976())
    suite.addTest(RegressionTestTicket10274())
    suite.addTest(RegressionTestTicket10850())
    suite.addTest(RegressionTestTicket10957())
    suite.addTest(RegressionTestTicket11302())
    if has_docutils:
        import docutils
        if get_pkginfo(docutils):
            suite.addTest(ReStructuredTextWikiTest())
            suite.addTest(ReStructuredTextCodeBlockTest())
        else:
            print("SKIP: reST wiki tests (docutils has no setuptools"
                  " metadata)")
    else:
        print("SKIP: reST wiki tests (no docutils)")
    return suite


test_suite = functionalSuite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
