#!/usr/bin/env python
import unittest

from trac.tests import wiki, ticket, perm_test, environment, diff, tracadmin, query
from trac.tests import href
from trac.web.tests import cgi_frontend

def suite():
    suite = unittest.TestSuite()
    suite.addTest(wiki.suite())
    suite.addTest(ticket.suite())
    suite.addTest(perm_test.suite())
    suite.addTest(environment.suite())
    suite.addTest(diff.suite())
    suite.addTest(tracadmin.suite())
    suite.addTest(query.suite())
    suite.addTest(cgi_frontend.suite())
    suite.addTest(href.suite())
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
