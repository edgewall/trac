# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2013 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import doctest
import unittest

import trac.ticket
from trac.ticket.tests import api, model, query, wikisyntax, notification, \
                              conversion, report, roadmap, batch, web_ui, \
                              default_workflow
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
    suite.addTest(batch.suite())
    suite.addTest(web_ui.suite())
    suite.addTest(default_workflow.suite())
    suite.addTest(doctest.DocTestSuite(trac.ticket.api))
    suite.addTest(doctest.DocTestSuite(trac.ticket.report))
    suite.addTest(doctest.DocTestSuite(trac.ticket.roadmap))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='suite')
