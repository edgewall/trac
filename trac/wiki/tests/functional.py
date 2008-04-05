#!/usr/bin/python
from trac.tests.functional import *


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


def functionalSuite(suite=None):
    if not suite:
        import trac.tests.functional.testcases
        suite = trac.tests.functional.testcases.functionalSuite()
    suite.addTest(TestWiki())
    suite.addTest(RegressionTestTicket4812())
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='functionalSuite')
