import doctest
import unittest

import trac.ticket
from trac.ticket.tests import api, model, query, wikisyntax, notification, \
                              conversion, report, roadmap
from trac.ticket.tests.functional import functionalSuite

def suite():
    suite = unittest.TestSuite()
    suite.addTest(api.suite())
    suite.addTest(model.suite())
    suite.addTest(query.suite())
    suite.addTest(wikisyntax.suite())
    suite.addTest(notification.suite())
    suite.addTest(conversion.suite())
    suite.addTest(report.suite())
    suite.addTest(roadmap.suite())
    suite.addTest(doctest.DocTestSuite(trac.ticket.api))
    suite.addTest(doctest.DocTestSuite(trac.ticket.report))
    suite.addTest(doctest.DocTestSuite(trac.ticket.roadmap))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
