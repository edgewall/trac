#!/usr/bin/python
import sys
from subprocess import call
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
        tc.notfind(pagename + '.*\\(diff\\)')
        self._tester.go_to_wiki(pagename)
        tc.formvalue('modifypage', 'action', 'edit')
        tc.submit()
        tc.find('Editing ' + pagename)
        tc.formvalue('edit', 'text', random_page())
        tc.formvalue('edit', 'comment', random_sentence())
        tc.submit('save')
        self._tester.go_to_timeline()
        tc.find(pagename + '.*\\(diff\\)')


class RegressionTestTicket5819(FunctionalTwillTestCaseSetup):
    def runTest(self):
        """Test for regression of http://trac.edgewall.org/ticket/5819
        Events with identical dates are reversed in timeline
        """
        # Multiple events very close together
        files = ['a', 'b', 'c', 'd']
        for filename in files:
            # We do a mkdir because it's easy.
            if call(['svn', '--username=admin', 'mkdir', '-m',
                     'Create component1/%s' % filename,
                     self._tester.repo_url + '/component1/trunk/' +
                     filename],
                    stdout=logfile, stderr=logfile, close_fds=close_fds):
                raise Exception('Failed to create component1 %s under %s' %
                                (filename, self._tester.repo_url))
        self._tester.go_to_timeline()
        # They are supposed to show up in d, c, b, a order.
        components = '.*'.join(['Create component1/%s' % f for f in
                                      reversed(files)])
        tc.find(components, 's')


def functionalSuite(suite=None):
    if not suite:
        import trac.tests.functional.testcases
        suite = trac.tests.functional.testcases.functionalSuite()
    suite.addTest(RegressionTestRev5883())
    if sys.version_info[:2] < (2, 4):
        print "SKIP: RegressionTestTicket5819 (python 2.3 issue)"
    else:
        suite.addTest(RegressionTestTicket5819())
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='functionalSuite')
