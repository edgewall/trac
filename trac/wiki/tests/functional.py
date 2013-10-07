#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2008-2013 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

from trac.tests.functional import *
from trac.mimeview.rst import has_docutils
from trac.util import get_pkginfo

class TestWiki(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Create a wiki page and attach a file"""
        # TODO: this should be split into multiple tests
        pagename = self._tester.create_wiki_page()
        self._tester.attach_file_to_wiki(pagename)


class TestWikiHistory(FunctionalTwillTestCaseSetup):
    """Create wiki page and navigate to page history."""
    def runTest(self):
        pagename = self._tester.create_wiki_page()
        self._tester.edit_wiki_page(pagename)
        tc.follow(r"\bHistory\b")
        tc.url(self._tester.url + r'/wiki/%s\?action=history' % pagename)
        version_link = '<td class="version">[ \t\n]*' \
                       '<a href="/wiki/%(pagename)s\?version=%%(version)s" ' \
                       'title="View this version">%%(version)s[ \t\n]*</a>' \
                        % {'pagename': pagename}
        tc.find(version_link % {'version': 1})
        tc.find(version_link % {'version': 2})


class TestWikiRename(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for simple wiki rename"""
        pagename = self._tester.create_wiki_page()
        attachment = self._tester.attach_file_to_wiki(pagename)
        base_url = self._tester.url
        page_url = base_url + "/wiki/" + pagename

        def click_rename():
            tc.formvalue('rename', 'action', 'rename')
            tc.submit()
            tc.url(page_url + r'\?action=rename')
            tc.find("New name:")

        tc.go(page_url)
        tc.find("Rename page")
        click_rename()
        # attempt to give an empty new name
        tc.formvalue('rename-form', 'new_name', '')
        tc.submit('submit')
        tc.url(page_url)
        tc.find("A new name is mandatory for a rename")
        # attempt to rename the page to an invalid page name
        tc.formvalue('rename-form', 'new_name', '../WikiStart')
        tc.submit('submit')
        tc.url(page_url)
        tc.find("The new name is invalid")
        # attempt to rename the page to the current page name
        tc.formvalue('rename-form', 'new_name', pagename)
        tc.submit('submit')
        tc.url(page_url)
        tc.find("The new name must be different from the old name")
        # attempt to rename the page to an existing page name
        tc.formvalue('rename-form', 'new_name', 'WikiStart')
        tc.submit('submit')
        tc.url(page_url)
        tc.find("The page WikiStart already exists")
        # correct rename to new page name (old page replaced by a redirection)
        tc.go(page_url)
        click_rename()
        newpagename = pagename + 'Renamed'
        tc.formvalue('rename-form', 'new_name', newpagename)
        tc.formvalue('rename-form', 'redirect', True)
        tc.submit('submit')
        # check redirection page
        tc.url(page_url)
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
        tc.url(base_url + "/wiki/" + newpagename)
        tc.find("The page %s has been renamed to %s."
                % (pagename, newpagename))
        # this time, the original page is gone
        tc.go(page_url)
        tc.url(page_url)
        tc.find("The page %s does not exist" % pagename)


class RegressionTestTicket4812(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/4812"""
        pagename = random_unique_camel() + '/' + random_unique_camel()
        self._tester.create_wiki_page(pagename)
        self._tester.attach_file_to_wiki(pagename)
        tc.notfind('does not exist')


class ReStructuredTextWikiTest(FunctionalTwillTestCaseSetup):
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
        tc.url(self._tester.url + "/wiki/WikiStart")


class ReStructuredTextCodeBlockTest(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Render reStructured code block"""
        pagename = self._tester.create_wiki_page(content="""
{{{
#!rst
.. code-block:: python

    print "123"
}}}
""")
        self._tester.go_to_wiki(pagename)
        tc.notfind("code-block")
        tc.find('print')
        tc.find('"123"')


class RegressionTestTicket8976(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/8976
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


class RegressionTestTicket10274(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/10274"""
        self._tester.go_to_wiki('WikiStart/..')
        tc.find("Invalid Wiki page name 'WikiStart/..'")
        self._tester.go_to_wiki('../WikiStart')
        tc.find("Invalid Wiki page name '../WikiStart'")
        self._tester.go_to_wiki('WikiStart/./SubPage')
        tc.find("Invalid Wiki page name 'WikiStart/./SubPage'")


class RegressionTestTicket10850(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/10850"""
        pagename = self._tester.create_wiki_page()
        # colon characters
        attachment = self._tester.attach_file_to_wiki(
            pagename, filename='2012-09-11_15:36:40-test.tbz2')
        base_url = self._tester.url
        tc.go(base_url + '/attachment/wiki/' + pagename +
              '/2012-09-11_15:36:40-test.tbz2')
        tc.notfind('Error: Invalid Attachment')
        # backslash characters
        attachment = self._tester.attach_file_to_wiki(
            pagename, filename=r'/tmp/back\slash.txt')
        base_url = self._tester.url
        tc.go(base_url + '/attachment/wiki/' + pagename + r'/back\slash.txt')
        tc.notfind('Error: Invalid Attachment')
        # Windows full path
        attachment = self._tester.attach_file_to_wiki(
            pagename, filename=r'z:\tmp\windows:path.txt')
        base_url = self._tester.url
        tc.go(base_url + '/attachment/wiki/' + pagename + r'/windows:path.txt')
        tc.notfind('Error: Invalid Attachment')
        # Windows share folder path
        attachment = self._tester.attach_file_to_wiki(
            pagename, filename=r'\\server\share\file:name.txt')
        base_url = self._tester.url
        tc.go(base_url + '/attachment/wiki/' + pagename + r'/file:name.txt')
        tc.notfind('Error: Invalid Attachment')


class RegressionTestTicket10957(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/10957"""

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
            tc.find("WIKI_CREATE privileges are required to perform this "
                    "operation on %s. You don't have the required permissions."
                    % page_name)

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
            tc.find("WIKI_MODIFY privileges are required to perform this "
                    "operation on %s. You don't have the required permissions."
                    % page_name)

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
            tc.formvalue('modifypage', 'action', 'edit')
            tc.submit()
            tc.find(content_v1)

            # Check that page can't be reverted without WIKI_MODIFY
            self._tester.edit_wiki_page(page_name)
            self._testenv.revoke_perm('anonymous', 'WIKI_MODIFY')
            tc.go(self._tester.url + '/wiki/%s?version=1' % page_name)
            tc.notfind("Revert to this version")
            tc.go(self._tester.url + '/wiki/%s?action=edit&version=1' % page_name)
            tc.find("WIKI_MODIFY privileges are required to perform this "
                    "operation on %s. You don't have the required permissions."
                    % page_name)

        finally:
            # Restore pre-test state.
            self._tester.login('admin')
            self._testenv.revoke_perm('anonymous', 'WIKI_CREATE')


class RegressionTestTicket11302(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/11302"""
        pagename = random_unique_camel()
        self._tester.create_wiki_page(pagename)
        attachment = self._tester.attach_file_to_wiki(
            pagename, description="illustrates [./@1#point1]")
        # self._tester.go_to_wiki(pagename + '?action=edit')
        # tc.url has trouble with that...
        tc.go(self._tester.url + '/wiki/' + pagename + '?action=edit')
        tc.find(r'illustrates <a class="wiki"'
                r' href="/wiki/%s\?version=1#point1">@1</a>' % pagename)


def functionalSuite(suite=None):
    if not suite:
        import trac.tests.functional.testcases
        suite = trac.tests.functional.testcases.functionalSuite()
    suite.addTest(TestWiki())
    suite.addTest(TestWikiHistory())
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
            print "SKIP: reST wiki tests (docutils has no setuptools metadata)"
    else:
        print "SKIP: reST wiki tests (no docutils)"
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='functionalSuite')
