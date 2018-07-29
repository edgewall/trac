# -*- coding: utf-8 -*-
#
# Copyright (C) 2014-2018 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.

import unittest

from trac.ticket.tests.functional import admin, default_workflow, main


def functionalSuite(suite=None):
    if not suite:
        import trac.tests.functional
        suite = trac.tests.functional.functionalSuite()

    admin.functionalSuite(suite)
    default_workflow.functionalSuite(suite)
    main.functionalSuite(suite)

    return suite


test_suite = functionalSuite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
