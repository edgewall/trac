# -*- coding: utf-8 -*-
#
# Copyright (C) 2006-2013 Edgewall Software
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
