import unittest

import trac.tests.wikisyntax
import trac.ticket.tests.wikisyntax
import trac.versioncontrol.web_ui.tests.wikisyntax
import trac.web.tests.wikisyntax
import trac.wiki.tests.wikisyntax
import trac.wiki.tests.formatter

def suite():
    suite = unittest.TestSuite()
    suite.addTest(trac.tests.wikisyntax.suite())
    suite.addTest(trac.ticket.tests.wikisyntax.suite())
    suite.addTest(trac.versioncontrol.web_ui.tests.wikisyntax.suite())
    suite.addTest(trac.web.tests.wikisyntax.suite())
    suite.addTest(trac.wiki.tests.macros.suite())
    suite.addTest(trac.wiki.tests.wikisyntax.suite())
    suite.addTest(trac.wiki.tests.formatter.suite())
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
