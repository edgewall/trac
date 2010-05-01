#!/usr/bin/python
from trac.tests.functional import *


class RegressionTestRev5883(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of the timeline fix in r5883
        From Tim:
        the issue was that event.markup was never being output anywhere, so
        you actually have to render the template with a wiki modification
        and see if '(diff)' shows up as the text in a link
        also note that (diff) should _not_ show up for a wiki creation
        """
        pagename = random_unique_camel()
        self._tester.create_wiki_page(pagename)
        self._tester.go_to_timeline()
        tc.find(pagename)
        tc.notfind(pagename + '.*diff</a>\\)')
        self._tester.go_to_wiki(pagename)
        tc.formvalue('modifypage', 'action', 'edit')
        tc.submit()
        tc.find('Editing ' + pagename)
        tc.formvalue('edit', 'text', random_page())
        tc.formvalue('edit', 'comment', random_sentence())
        tc.submit('save')
        self._tester.go_to_timeline()
        tc.find(pagename + '.*diff</a>\\)')


def functionalSuite(suite=None):
    if not suite:
        import trac.tests.functional.testcases
        suite = trac.tests.functional.testcases.functionalSuite()
    suite.addTest(RegressionTestRev5883())
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='functionalSuite')
