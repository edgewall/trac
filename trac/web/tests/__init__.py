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

import unittest

from trac.web.tests import api, auth, cgi_frontend, chrome, href, session, \
                           wikisyntax, main

def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(api.test_suite())
    suite.addTest(auth.test_suite())
    suite.addTest(cgi_frontend.test_suite())
    suite.addTest(chrome.test_suite())
    suite.addTest(href.test_suite())
    suite.addTest(session.test_suite())
    suite.addTest(wikisyntax.test_suite())
    suite.addTest(main.test_suite())
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
