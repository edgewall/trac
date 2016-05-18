# -*- coding: utf-8 -*-
#
# Copyright (C) 2004-2013 Edgewall Software
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

from trac.tests import attachment, config, core, env, perm, notification, \
                       resource, wikisyntax, functional

def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(basicSuite())
    suite.addTest(functionalSuite())
    return suite

def basicSuite():
    suite = unittest.TestSuite()
    suite.addTest(attachment.test_suite())
    suite.addTest(config.test_suite())
    suite.addTest(core.test_suite())
    suite.addTest(env.test_suite())
    suite.addTest(notification.test_suite())
    suite.addTest(perm.test_suite())
    suite.addTest(resource.test_suite())
    suite.addTest(wikisyntax.test_suite())
    return suite

def functionalSuite():
    return functional.test_suite()

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
