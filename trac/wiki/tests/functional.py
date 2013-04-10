#!/usr/bin/python
from trac.tests.functional import *
from trac.mimeview.rst import has_docutils
from trac.util import get_pkginfo

class TestWiki(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Create a wiki page and attach a file"""
        # TODO: this should be split into multiple tests
        pagename = random_unique_camel()
        self._tester.create_wiki_page(pagename)
        self._tester.attach_file_to_wiki(pagename)


class TestWikiRename(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for simple wiki rename"""
        pagename = random_unique_camel()
        self._tester.create_wiki_page(pagename)
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
        pagename = random_unique_camel()
        self._tester.create_wiki_page(pagename, content="""
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
        pagename = random_unique_camel()
        self._tester.create_wiki_page(pagename, content="""
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
        pagename = random_unique_camel()
        self._tester.create_wiki_page(pagename)
        # colon characters
        attachment = self._tester.attach_file_to_wiki(
            pagename, tempfilename='2012-09-11_15:36:40-test.tbz2')
        base_url = self._tester.url
        tc.go(base_url + '/attachment/wiki/' + pagename +
              '/2012-09-11_15:36:40-test.tbz2')
        tc.notfind('Error: Invalid Attachment')
        # backslash characters
        attachment = self._tester.attach_file_to_wiki(
            pagename, tempfilename=r'/tmp/back\slash.txt')
        base_url = self._tester.url
        tc.go(base_url + '/attachment/wiki/' + pagename + r'/back\slash.txt')
        tc.notfind('Error: Invalid Attachment')
        # Windows full path
        attachment = self._tester.attach_file_to_wiki(
            pagename, tempfilename=r'z:\tmp\windows:path.txt')
        base_url = self._tester.url
        tc.go(base_url + '/attachment/wiki/' + pagename + r'/windows:path.txt')
        tc.notfind('Error: Invalid Attachment')
        # Windows share folder path
        attachment = self._tester.attach_file_to_wiki(
            pagename, tempfilename=r'\\server\share\file:name.txt')
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


def functionalSuite(suite=None):
    if not suite:
        import trac.tests.functional.testcases
        suite = trac.tests.functional.testcases.functionalSuite()
    suite.addTest(TestWiki())
    suite.addTest(TestWikiRename())
    suite.addTest(RegressionTestTicket4812())
    suite.addTest(RegressionTestTicket10274())
    suite.addTest(RegressionTestTicket10850())
    suite.addTest(RegressionTestTicket10957())
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
