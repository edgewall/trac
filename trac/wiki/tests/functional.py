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

def functionalSuite(suite=None):
    if not suite:
        import trac.tests.functional.testcases
        suite = trac.tests.functional.testcases.functionalSuite()
    suite.addTest(TestWiki())
    suite.addTest(RegressionTestTicket4812())
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
