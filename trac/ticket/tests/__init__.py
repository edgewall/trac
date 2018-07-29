# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2018 Edgewall Software
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
from trac.ticket.tests import admin, api, model, query, wikisyntax, \
                              notification, conversion, report, roadmap, \
                              batch, web_ui, default_workflow
from trac.ticket.tests.functional import functionalSuite


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(admin.test_suite())
    suite.addTest(api.test_suite())
    suite.addTest(model.test_suite())
    suite.addTest(query.test_suite())
    suite.addTest(wikisyntax.test_suite())
    suite.addTest(notification.test_suite())
    suite.addTest(conversion.test_suite())
    suite.addTest(report.test_suite())
    suite.addTest(roadmap.test_suite())
    suite.addTest(batch.test_suite())
    suite.addTest(web_ui.test_suite())
    suite.addTest(default_workflow.test_suite())
    suite.addTest(doctest.DocTestSuite(trac.ticket.api))
    suite.addTest(doctest.DocTestSuite(trac.ticket.report))
    suite.addTest(doctest.DocTestSuite(trac.ticket.roadmap))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
