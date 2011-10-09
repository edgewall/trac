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


def functionalSuite(suite=None):
    if not suite:
        import trac.tests.functional.testcases
        suite = trac.tests.functional.testcases.functionalSuite()
    suite.addTest(TestWiki())
    suite.addTest(TestWikiRename())
    suite.addTest(RegressionTestTicket4812())
    suite.addTest(RegressionTestTicket10274())
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
